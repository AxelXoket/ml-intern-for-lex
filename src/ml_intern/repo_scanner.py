"""Repository scanning layer — read-only repo observation collector.

Scans both local repositories and produces Observation objects.
This layer is strictly read-only: it inspects paths, reads metadata,
and examines selected file contents. It never writes, modifies, or
deletes anything.

Ignore policy:
    Uses a hardcoded prune set derived from the project's .gitignore.
    This is NOT equivalent to full .gitignore semantics — it is a practical
    subset. The prune set is passed as a parameter to enable future
    replacement with Git-aware ignore checking without redesigning the
    scanner function signature.

Binary detection:
    Uses an extension-based text allowlist. Files not matching the allowlist
    are counted but not opened or read.

Symlink / junction policy:
    Symlinks and junctions are NOT followed during traversal to prevent
    infinite recursion. If encountered, they are recorded as observations.
"""

from __future__ import annotations

import configparser
import os
import re
from pathlib import Path

from ml_intern.report_schemas import Observation, ObservationGranularity, SourceKind
from ml_intern.security import redact_secrets


# ── Ignore Policy ────────────────────────────────────────────────
# Hardcoded prune set — derived from project .gitignore patterns.
# NOT equivalent to full .gitignore semantics. Structured as a
# parameter-ready constant so future Git-aware ignore checking can
# replace it without changing scanner function signatures.

DEFAULT_PRUNE_DIRS: frozenset[str] = frozenset({
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".eggs",
    "htmlcov",
    ".vscode",
    ".idea",
})


# ── Binary Detection ────────────────────────────────────────────
# Extension-based text allowlist. Files not in this set are counted
# but never opened or read.

TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".md", ".txt", ".toml", ".yaml", ".yml",
    ".json", ".cfg", ".ini", ".rst", ".html", ".css",
    ".js", ".bat", ".sh",
})

# Files that are text-readable but have no extension
TEXT_EXACT_NAMES: frozenset[str] = frozenset({
    ".gitignore", ".gitkeep", ".gitleaksignore",
    ".env.example", ".pre-commit-config.yaml",
    "Makefile", "Dockerfile", "LICENSE", "README",
})


# ── Sensitive File Detection ────────────────────────────────────
# Files whose contents should NEVER be read or summarized.
# Presence/absence and size are observable; content is not.

SENSITIVE_PATTERNS: frozenset[str] = frozenset({
    ".env",
})


def _is_sensitive_file(name: str) -> bool:
    """Check if a filename matches a sensitive pattern."""
    if name in SENSITIVE_PATTERNS:
        return True
    # Match .env but not .env.example
    if name.startswith(".env") and name != ".env.example":
        return True
    return False


def _is_text_file(path: Path) -> bool:
    """Check if a file should be treated as text based on extension/name."""
    if path.name in TEXT_EXACT_NAMES:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


# ── Git Remote URL Reader ───────────────────────────────────────


def read_git_remote_url(repo_root: Path) -> str | None:
    """Attempt to read the 'origin' remote URL from .git/config.

    Returns the URL string if found, or None if:
    - .git/config does not exist
    - .git/config cannot be parsed
    - No 'origin' remote is configured

    This fallback to None is intentional: the remote URL is informational
    metadata, not a requirement. A missing or unreadable .git/config should
    never prevent report generation.
    """
    git_config_path = repo_root / ".git" / "config"
    if not git_config_path.is_file():
        # .git/config not found — repo may not be a git repo,
        # or .git may be a gitfile (submodule). Return None.
        return None

    try:
        parser = configparser.ConfigParser()
        parser.read(str(git_config_path), encoding="utf-8")
        # Standard git config section for origin remote
        return parser.get('remote "origin"', "url", fallback=None)
    except (configparser.Error, OSError):
        # Parse error or read error — return None, do not crash.
        # This is expected if .git/config has non-standard formatting.
        return None


# ── Directory Tree Scanner ──────────────────────────────────────


def _scan_directory_tree(
    root: Path,
    prune_dirs: frozenset[str] = DEFAULT_PRUNE_DIRS,
) -> dict:
    """Walk a repository tree and collect structural metadata.

    Returns a dict with:
    - top_level_dirs: list of directory names at root level
    - top_level_files: list of file names at root level
    - file_count: total text files found
    - non_text_count: total non-text files found
    - dir_count: total directories found
    - symlinks: list of symlink/junction paths found
    - errors: list of paths that could not be accessed

    This function does NOT follow symlinks or junctions.
    """
    result = {
        "top_level_dirs": [],
        "top_level_files": [],
        "file_count": 0,
        "non_text_count": 0,
        "dir_count": 0,
        "symlinks": [],
        "errors": [],
    }

    if not root.is_dir():
        result["errors"].append(str(root))
        return result

    # Top-level enumeration
    try:
        for entry in sorted(root.iterdir()):
            name = entry.name
            if entry.is_symlink():
                # Record symlinks but do not follow them
                result["symlinks"].append(name)
            elif entry.is_dir():
                if name not in prune_dirs:
                    result["top_level_dirs"].append(name)
            elif entry.is_file():
                result["top_level_files"].append(name)
    except OSError as exc:
        result["errors"].append(f"Root enumeration failed: {exc}")
        return result

    # Recursive walk — prune ignored dirs, don't follow symlinks
    try:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Prune ignored directories in-place (prevents os.walk from descending)
            dirnames[:] = [
                d for d in dirnames
                if d not in prune_dirs
                and not Path(dirpath, d).is_symlink()
            ]

            rel_dir = Path(dirpath).relative_to(root)

            result["dir_count"] += len(dirnames)

            for fname in filenames:
                fpath = Path(dirpath) / fname

                # Check for symlinks
                if fpath.is_symlink():
                    rel = str(rel_dir / fname)
                    result["symlinks"].append(rel)
                    continue

                if _is_text_file(fpath):
                    result["file_count"] += 1
                else:
                    result["non_text_count"] += 1

    except OSError as exc:
        result["errors"].append(f"Walk failed: {exc}")

    return result


# ── Targeted Content Readers ────────────────────────────────────


def _read_pyproject_metadata(repo_root: Path) -> dict | None:
    """Extract non-secret structural values from pyproject.toml.

    Returns: project name, version, requires-python, dependency count.
    Never extracts secret values. Returns None if file missing/unreadable.
    """
    toml_path = repo_root / "pyproject.toml"
    if not toml_path.is_file():
        return None

    try:
        content = toml_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    meta = {}

    # Extract selected values via regex — avoids adding tomli dependency
    name_match = re.search(r'^name\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if name_match:
        meta["name"] = name_match.group(1)

    version_match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if version_match:
        meta["version"] = version_match.group(1)

    python_match = re.search(r'^requires-python\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if python_match:
        meta["requires_python"] = python_match.group(1)

    # Count dependencies — match from 'dependencies = [' to the closing ']'
    # on its own line. We can't use lazy .*? because dependency specifiers
    # like 'uvicorn[standard]' contain square brackets that would match early.
    deps_match = re.search(
        r"^dependencies\s*=\s*\[(.*?)^\]",
        content,
        re.DOTALL | re.MULTILINE,
    )
    if deps_match:
        dep_lines = [
            line.strip() for line in deps_match.group(1).splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        meta["dependency_count"] = len(dep_lines)

    return meta if meta else None


def _scan_cli_commands(repo_root: Path) -> dict | None:
    """Inspect CLI command surface by reading cli.py.

    Returns: list of command names, counts of implemented vs stub commands.
    Returns None if cli.py is missing/unreadable.
    """
    cli_path = repo_root / "src" / "lex_study_foundation" / "cli.py"
    if not cli_path.is_file():
        return None

    try:
        content = cli_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Find @app.command() decorated functions
    commands = re.findall(r'@app\.command\(\)\s*\ndef\s+(\w+)', content)

    # Check for NotImplementedError stubs
    stubs = []
    implemented = []
    for cmd in commands:
        # Find the function body and check for NotImplementedError
        pattern = rf'def\s+{cmd}\b.*?(?=\ndef\s|\Z)'
        func_match = re.search(pattern, content, re.DOTALL)
        if func_match and "NotImplementedError" in func_match.group():
            stubs.append(cmd)
        else:
            implemented.append(cmd)

    return {
        "total": len(commands),
        "implemented": implemented,
        "stubs": stubs,
    }


def _scan_test_files(repo_root: Path) -> dict | None:
    """Count test files in the tests/ directory.

    Returns: file count, file names. Returns None if tests/ missing.
    """
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return None

    test_files = []
    try:
        for f in sorted(tests_dir.rglob("test_*.py")):
            test_files.append(str(f.relative_to(tests_dir)))
    except OSError:
        return None

    return {
        "count": len(test_files),
        "files": test_files,
    }


# ── Main Scanner ────────────────────────────────────────────────


def scan_repository(
    repo_name: str,
    repo_root: Path,
    prune_dirs: frozenset[str] = DEFAULT_PRUNE_DIRS,
) -> list[Observation]:
    """Scan a single repository and produce a list of Observation objects.

    This function is read-only. It inspects paths, reads metadata, and
    examines selected file contents. It never writes, modifies, or deletes.

    Observations are raw facts — no interpretation, no recommendations.
    All text outputs are redacted before entering observation descriptions.

    Args:
        repo_name: Short name for repo identity in observations.
        repo_root: Absolute path to repo root directory.
        prune_dirs: Directory names to skip during traversal.

    Returns:
        List of Observation objects (without IDs — IDs are assigned by report_builder).
    """
    observations: list[Observation] = []

    def _add(
        paths: list[str],
        source_kind: SourceKind,
        granularity: ObservationGranularity,
        description: str,
    ) -> None:
        """Helper to append an observation with redaction applied."""
        observations.append(
            Observation(
                id="obs-000",  # Placeholder — real IDs assigned by report_builder
                repo=repo_name,
                paths=paths,
                source_kind=source_kind,
                granularity=granularity,
                description=redact_secrets(description),
            )
        )

    # ── 1. Repo root existence ──
    if not repo_root.is_dir():
        _add(
            paths=[],
            source_kind=SourceKind.ENVIRONMENT,
            granularity=ObservationGranularity.DIRECTORY_LEVEL,
            description=f"Repository root does not exist or is not accessible: {repo_root}",
        )
        return observations

    # ── 2. Directory tree structure ──
    tree = _scan_directory_tree(repo_root, prune_dirs)

    _add(
        paths=[],
        source_kind=SourceKind.DIRECTORY_STRUCTURE,
        granularity=ObservationGranularity.DIRECTORY_LEVEL,
        description=(
            f"Top-level directories: {', '.join(tree['top_level_dirs']) or '(none)'}. "
            f"Top-level files: {', '.join(tree['top_level_files']) or '(none)'}."
        ),
    )

    _add(
        paths=[],
        source_kind=SourceKind.DIRECTORY_STRUCTURE,
        granularity=ObservationGranularity.DIRECTORY_LEVEL,
        description=(
            f"Total text files: {tree['file_count']}. "
            f"Non-text files: {tree['non_text_count']}. "
            f"Directories (excluding pruned): {tree['dir_count']}."
        ),
    )

    # ── 3. Symlinks / junctions ──
    if tree["symlinks"]:
        _add(
            paths=tree["symlinks"],
            source_kind=SourceKind.FILE_PRESENCE,
            granularity=ObservationGranularity.FILE_LEVEL,
            description=(
                f"Symlinks/junctions found (not followed during scan): "
                f"{', '.join(tree['symlinks'])}."
            ),
        )

    # ── 4. Scan errors ──
    if tree["errors"]:
        for err in tree["errors"]:
            _add(
                paths=[],
                source_kind=SourceKind.ENVIRONMENT,
                granularity=ObservationGranularity.DIRECTORY_LEVEL,
                description=f"Scan error: {err}",
            )

    # ── 5. Key file presence ──
    key_files = [
        "pyproject.toml", "README.md", ".gitignore",
        ".env.example", ".pre-commit-config.yaml",
    ]
    present = [f for f in key_files if (repo_root / f).is_file()]
    absent = [f for f in key_files if not (repo_root / f).is_file()]

    _add(
        paths=present,
        source_kind=SourceKind.FILE_PRESENCE,
        granularity=ObservationGranularity.FILE_LEVEL,
        description=(
            f"Key files present: {', '.join(present) or '(none)'}. "
            f"Missing: {', '.join(absent) or '(none)'}."
        ),
    )

    # ── 6. Sensitive file presence (content NOT read) ──
    env_file = repo_root / ".env"
    if env_file.is_file():
        try:
            size = env_file.stat().st_size
        except OSError:
            size = -1
        _add(
            paths=[".env"],
            source_kind=SourceKind.FILE_PRESENCE,
            granularity=ObservationGranularity.FILE_LEVEL,
            description=(
                f".env file present ({size} bytes). "
                f"Content NOT read — sensitive file."
            ),
        )

    # ── 7. pyproject.toml metadata ──
    pyproject = _read_pyproject_metadata(repo_root)
    if pyproject:
        parts = []
        if "name" in pyproject:
            parts.append(f"name={pyproject['name']}")
        if "version" in pyproject:
            parts.append(f"version={pyproject['version']}")
        if "requires_python" in pyproject:
            parts.append(f"requires-python={pyproject['requires_python']}")
        if "dependency_count" in pyproject:
            parts.append(f"dependencies={pyproject['dependency_count']}")

        _add(
            paths=["pyproject.toml"],
            source_kind=SourceKind.CONFIG_VALUE,
            granularity=ObservationGranularity.CONFIG_LEVEL,
            description=f"pyproject.toml metadata: {', '.join(parts)}.",
        )

    # ── 8. docs/ directory ──
    docs_dir = repo_root / "docs"
    if docs_dir.is_dir():
        try:
            doc_files = sorted(f.name for f in docs_dir.iterdir() if f.is_file())
        except OSError:
            doc_files = []
        _add(
            paths=[f"docs/{f}" for f in doc_files],
            source_kind=SourceKind.DIRECTORY_STRUCTURE,
            granularity=ObservationGranularity.DIRECTORY_LEVEL,
            description=f"docs/ contains {len(doc_files)} files: {', '.join(doc_files) or '(none)'}.",
        )

    # ── 9. tests/ directory ──
    tests_info = _scan_test_files(repo_root)
    if tests_info:
        _add(
            paths=[f"tests/{f}" for f in tests_info["files"]],
            source_kind=SourceKind.DIRECTORY_STRUCTURE,
            granularity=ObservationGranularity.DIRECTORY_LEVEL,
            description=f"tests/ contains {tests_info['count']} test files: {', '.join(tests_info['files'])}.",
        )
    elif (repo_root / "tests").is_dir():
        _add(
            paths=["tests/"],
            source_kind=SourceKind.DIRECTORY_STRUCTURE,
            granularity=ObservationGranularity.DIRECTORY_LEVEL,
            description="tests/ directory exists but no test_*.py files found.",
        )

    # ── 10. CLI command surface (lex only) ──
    cli_info = _scan_cli_commands(repo_root)
    if cli_info:
        impl_list = ", ".join(cli_info["implemented"]) or "(none)"
        stub_list = ", ".join(cli_info["stubs"]) or "(none)"
        _add(
            paths=["src/lex_study_foundation/cli.py"],
            source_kind=SourceKind.COMMAND_SURFACE,
            granularity=ObservationGranularity.INTERFACE_LEVEL,
            description=(
                f"CLI exposes {cli_info['total']} commands. "
                f"Implemented ({len(cli_info['implemented'])}): {impl_list}. "
                f"Stubs ({len(cli_info['stubs'])}): {stub_list}."
            ),
        )

    # ── 11. src/ package structure ──
    src_dir = repo_root / "src"
    if src_dir.is_dir():
        packages = []
        try:
            for pkg_dir in sorted(src_dir.iterdir()):
                if pkg_dir.is_dir() and (pkg_dir / "__init__.py").is_file():
                    # Count modules in this package
                    modules = sorted(
                        f.stem for f in pkg_dir.iterdir()
                        if f.is_file() and f.suffix == ".py" and f.name != "__init__.py"
                    )
                    subpackages = sorted(
                        d.name for d in pkg_dir.iterdir()
                        if d.is_dir() and (d / "__init__.py").is_file()
                    )
                    parts = []
                    if modules:
                        parts.append(f"modules=[{', '.join(modules)}]")
                    if subpackages:
                        parts.append(f"subpackages=[{', '.join(subpackages)}]")
                    packages.append(f"{pkg_dir.name} ({', '.join(parts)})")
        except OSError:
            pass

        if packages:
            _add(
                paths=["src/"],
                source_kind=SourceKind.DIRECTORY_STRUCTURE,
                granularity=ObservationGranularity.DIRECTORY_LEVEL,
                description=f"src/ packages: {'; '.join(packages)}.",
            )

    # ── 12. configs/ directory ──
    configs_dir = repo_root / "configs"
    if configs_dir.is_dir():
        config_files = []
        try:
            for cat_dir in sorted(configs_dir.iterdir()):
                if cat_dir.is_dir():
                    for cfg_file in sorted(cat_dir.iterdir()):
                        if cfg_file.is_file():
                            config_files.append(f"{cat_dir.name}/{cfg_file.name}")
        except OSError:
            pass

        _add(
            paths=[f"configs/{f}" for f in config_files],
            source_kind=SourceKind.DIRECTORY_STRUCTURE,
            granularity=ObservationGranularity.DIRECTORY_LEVEL,
            description=(
                f"configs/ contains {len(config_files)} files: "
                f"{', '.join(config_files) or '(none)'}."
            ),
        )

    # ── 13. data/ directory ──
    data_dir = repo_root / "data"
    if data_dir.is_dir():
        data_subdirs = []
        try:
            for sub in sorted(data_dir.iterdir()):
                if sub.is_dir():
                    file_count = sum(1 for f in sub.rglob("*") if f.is_file())
                    data_subdirs.append(f"{sub.name} ({file_count} files)")
        except OSError:
            pass

        _add(
            paths=["data/"],
            source_kind=SourceKind.DIRECTORY_STRUCTURE,
            granularity=ObservationGranularity.DIRECTORY_LEVEL,
            description=f"data/ subdirectories: {', '.join(data_subdirs) or '(none)'}.",
        )

    return observations
