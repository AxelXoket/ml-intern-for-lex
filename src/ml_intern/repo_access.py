"""Safe file access utilities — path validation, sensitive file blocking, file reading.

This module enforces the read-only repo access boundary defined in the
project charter. All API route handlers that serve file content must use
these functions to guarantee:
- Path traversal prevention (resolve + is_relative_to)
- Sensitive file blocking (.env variants)
- Binary file detection (extension allowlist)
- Content redaction (redact_secrets on every line)
- Line range enforcement (MAX_LINES_PER_REQUEST cap)

Write operations are NOT provided here — this module is strictly read-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from ml_intern.repo_scanner import (
    SENSITIVE_PATTERNS,
    TEXT_EXACT_NAMES,
    TEXT_EXTENSIONS,
    _is_sensitive_file,
    _is_text_file,
)
from ml_intern.security import redact_secrets


# ── Constants ────────────────────────────────────────────────────

MAX_LINES_PER_REQUEST: int = 1000
"""Maximum number of lines that can be read in a single API request."""

# Maximum file size (in bytes) for counting lines in get_file_meta.
# Files larger than this skip line counting to avoid performance issues.
_MAX_SIZE_FOR_LINE_COUNT: int = 2 * 1024 * 1024  # 2 MB


# ── Repo Root Resolution ────────────────────────────────────────


def get_allowed_repos() -> dict[str, Path]:
    """Build the map of allowed repo keys to their root paths.

    Lazily imports config to avoid circular imports when this module
    is used in tests without a full config available.

    Returns:
        Dict mapping repo key ("lex", "intern") to resolved root paths.
    """
    from ml_intern.config import INTERN_REPO_ROOT, get_integration_settings

    repos: dict[str, Path] = {}
    repos["intern"] = INTERN_REPO_ROOT.resolve()

    try:
        config = get_integration_settings()
        repos["lex"] = config.project_root.resolve()
    except Exception:
        # lex config may not be available in test environments
        pass

    return repos


def get_repo_root(repo_key: str) -> Path:
    """Resolve a repo key to its root path.

    Args:
        repo_key: Short name ("lex" or "intern").

    Returns:
        Resolved absolute path to the repo root.

    Raises:
        ValueError: If repo_key is not in the allowed repos.
    """
    repos = get_allowed_repos()
    if repo_key not in repos:
        raise ValueError(f"Unknown repository: '{repo_key}'. Allowed: {list(repos.keys())}")
    return repos[repo_key]


# ── Path Validation ─────────────────────────────────────────────


def validate_path(user_path: str, repo_root: Path) -> Path:
    """Validate that a user-provided path stays within the repo root.

    Uses pathlib resolve() + is_relative_to() — the 2026 OWASP-recommended
    pattern for path traversal defense. This handles:
    - ../../../ escape attempts
    - Symlink resolution (resolve follows symlinks)
    - Mixed forward/backward slashes (pathlib normalizes on Windows)

    Args:
        user_path: Relative path from the user (e.g., "src/main.py").
        repo_root: Absolute path to the allowed repo root.

    Returns:
        Resolved absolute path guaranteed to be within repo_root.

    Raises:
        PermissionError: If the resolved path escapes repo_root.
    """
    root_resolved = repo_root.resolve()
    target_resolved = (root_resolved / user_path).resolve()

    if not target_resolved.is_relative_to(root_resolved):
        raise PermissionError(
            f"Path traversal denied: resolved path escapes repo root"
        )

    return target_resolved


# ── File Classification ─────────────────────────────────────────


def is_sensitive_file(path: Path) -> bool:
    """Check if a file is sensitive (e.g., .env).

    Delegates to repo_scanner._is_sensitive_file for consistency.
    """
    return _is_sensitive_file(path.name)


def is_text_file(path: Path) -> bool:
    """Check if a file is text-readable based on extension/name.

    Delegates to repo_scanner._is_text_file for consistency.
    """
    return _is_text_file(path)


# ── File Metadata ────────────────────────────────────────────────


def get_file_meta(path: Path, repo_root: Path) -> dict:
    """Get metadata for a single file.

    Args:
        path: Absolute path to the file (must be validated already).
        repo_root: Repo root for computing relative path.

    Returns:
        Dict with: path, size_bytes, line_count, is_text, sensitive, modified_at.

    Raises:
        FileNotFoundError: If path doesn't exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    stat = path.stat()
    text = is_text_file(path)
    sensitive = is_sensitive_file(path)

    # Relative path from repo root
    try:
        rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel_path = path.name

    # Line count for text files under size limit
    line_count = None
    if text and not sensitive and stat.st_size <= _MAX_SIZE_FOR_LINE_COUNT:
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                line_count = sum(1 for _ in f)
        except OSError:
            pass

    modified_at = datetime.fromtimestamp(
        stat.st_mtime, tz=timezone.utc
    ).isoformat(timespec="seconds")

    return {
        "path": rel_path,
        "size_bytes": stat.st_size,
        "line_count": line_count,
        "is_text": text,
        "sensitive": sensitive,
        "modified_at": modified_at,
    }


# ── File Content Reader ─────────────────────────────────────────


def read_file_lines(
    path: Path,
    start: int = 1,
    end: int | None = None,
) -> Generator[str, None, None]:
    """Read lines from a file in a specified range, yielding redacted content.

    Uses a generator pattern to keep memory usage constant regardless of
    file size. Each line is passed through redact_secrets() before yielding.

    Args:
        path: Absolute path to the file.
        start: First line to read (1-indexed, inclusive). Default: 1.
        end: Last line to read (1-indexed, inclusive). Default: start + MAX_LINES_PER_REQUEST - 1.

    Yields:
        Redacted lines (with newline stripped).

    Raises:
        FileNotFoundError: If path doesn't exist.
        ValueError: If start/end range exceeds MAX_LINES_PER_REQUEST.
        PermissionError: If file is sensitive.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if is_sensitive_file(path):
        raise PermissionError(f"Content of sensitive file cannot be read: {path.name}")

    if not is_text_file(path):
        raise ValueError(f"Binary file content cannot be read: {path.name}")

    if start < 1:
        start = 1

    if end is None:
        end = start + MAX_LINES_PER_REQUEST - 1

    if end - start + 1 > MAX_LINES_PER_REQUEST:
        raise ValueError(
            f"Requested range ({end - start + 1} lines) exceeds maximum "
            f"of {MAX_LINES_PER_REQUEST} lines per request"
        )

    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            if line_num < start:
                continue
            if line_num > end:
                break
            yield redact_secrets(line.rstrip("\n\r"))
