"""Document intake layer — read project-defining documents.

Reads the mandatory project documents and produces DocumentReadResult
objects for the reality report. This layer is strictly read-only: it
opens files for reading, extracts summaries, and records metadata.

Redaction: All text-bearing outputs are passed through redact_secrets()
before entering any DocumentReadResult field.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from ml_intern.report_schemas import DocumentReadResult, DocumentRole
from ml_intern.security import redact_secrets


# ── Document Manifest ────────────────────────────────────────────
# Each tuple: (relative_path, repo_name, role)
# These are the mandatory documents Part 2 must attempt to read.

DOCUMENT_MANIFEST: list[tuple[str, str, DocumentRole]] = [
    ("docs/PROJECT_CHARTER.md", "ml-intern-for-lex", DocumentRole.SOURCE_OF_INTENT),
    ("docs/progress.md", "ml-intern-for-lex", DocumentRole.OPERATIONAL_HISTORY),
    ("docs/progress.md", "lex_study_foundation", DocumentRole.OPERATIONAL_HISTORY),
]


# ── Summarizers ──────────────────────────────────────────────────


def _summarize_charter(content: str) -> str:
    """Summarize PROJECT_CHARTER.md by extracting section structure.

    Extracts section count and section names from ## N. Title format.
    Returns a concise 1-3 sentence summary — never the full text.
    """
    sections: list[str] = []
    for match in re.finditer(r"^##\s+\d+\.\s+(.+)$", content, re.MULTILINE):
        sections.append(match.group(1).strip())

    line_count = content.count("\n") + 1
    section_count = len(sections)

    if section_count == 0:
        return f"Project charter document ({line_count} lines). No numbered sections detected."

    section_list = ", ".join(sections)
    return (
        f"Project charter with {section_count} sections ({line_count} lines): "
        f"{section_list}."
    )


def _summarize_progress(content: str, repo: str) -> str:
    """Summarize a progress.md by extracting entry count and date range.

    Extracts entry dates from ## YYYY-MM-DD format headers.
    Returns a concise 1-3 sentence summary — never the full text.
    """
    dates: list[str] = []
    titles: list[str] = []
    for match in re.finditer(
        r"^##\s+(\d{4}-\d{2}-\d{2})\s+.*?—\s+(.+)$", content, re.MULTILINE
    ):
        dates.append(match.group(1))
        titles.append(match.group(2).strip())

    line_count = content.count("\n") + 1
    entry_count = len(dates)

    if entry_count == 0:
        return f"Progress log for {repo} ({line_count} lines). No dated entries detected."

    most_recent_date = dates[-1]
    most_recent_title = titles[-1]
    date_range = f"{dates[0]} to {dates[-1]}" if entry_count > 1 else dates[0]

    return (
        f"Progress log for {repo} with {entry_count} entries ({line_count} lines). "
        f"Date range: {date_range}. "
        f"Most recent: {most_recent_date} — {most_recent_title}."
    )


def _get_summarizer(role: DocumentRole, repo: str):
    """Return the appropriate summarizer function for a document role."""
    if role == DocumentRole.SOURCE_OF_INTENT:
        return _summarize_charter
    if role == DocumentRole.OPERATIONAL_HISTORY:
        return lambda content: _summarize_progress(content, repo)
    # Default: line count only
    return lambda content: f"Document ({content.count(chr(10)) + 1} lines)."


# ── File Reading ─────────────────────────────────────────────────


def _read_file_safe(path: Path) -> str | None:
    """Read a file as UTF-8 text, returning None on failure.

    Uses errors='replace' for non-UTF-8 bytes (same pattern as runner.py).
    Strips BOM if present.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        # Strip BOM if present
        if content.startswith("\ufeff"):
            content = content[1:]
        return content
    except OSError:
        return None


def _get_last_modified(path: Path) -> str | None:
    """Return ISO 8601 timestamp of file's last modification, or None."""
    try:
        mtime = path.stat().st_mtime
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        return dt.isoformat()
    except OSError:
        return None


# ── Public API ───────────────────────────────────────────────────


def read_documents(
    repo_roots: dict[str, Path],
) -> list[DocumentReadResult]:
    """Read all mandatory project documents and produce DocumentReadResult list.

    Args:
        repo_roots: Mapping of repo name → absolute local path.
                    Expected keys: 'ml-intern-for-lex', 'lex_study_foundation'.

    Returns:
        List of DocumentReadResult objects, one per manifest entry.
        Missing documents are recorded with found=False, not raised as errors.
    """
    results: list[DocumentReadResult] = []
    counter = 0

    for rel_path, repo_name, role in DOCUMENT_MANIFEST:
        counter += 1
        doc_id = f"doc-{counter:03d}"

        root = repo_roots.get(repo_name)
        if root is None:
            # Repo root not available — record as missing
            results.append(
                DocumentReadResult(
                    id=doc_id,
                    target_path=rel_path,
                    repo=repo_name,
                    role=role,
                    found=False,
                    summary=None,
                    notes=f"Repository root for '{repo_name}' was not provided.",
                    last_modified=None,
                )
            )
            continue

        full_path = root / rel_path

        if not full_path.is_file():
            results.append(
                DocumentReadResult(
                    id=doc_id,
                    target_path=rel_path,
                    repo=repo_name,
                    role=role,
                    found=False,
                    summary=None,
                    notes=None,
                    last_modified=None,
                )
            )
            continue

        # File exists — read and summarize
        content = _read_file_safe(full_path)
        if content is None:
            results.append(
                DocumentReadResult(
                    id=doc_id,
                    target_path=rel_path,
                    repo=repo_name,
                    role=role,
                    found=True,
                    summary=None,
                    notes="File exists but could not be read (encoding or permission error).",
                    last_modified=_get_last_modified(full_path),
                )
            )
            continue

        summarizer = _get_summarizer(role, repo_name)
        raw_summary = summarizer(content)
        # Redact before storing — contract requirement
        safe_summary = redact_secrets(raw_summary)

        results.append(
            DocumentReadResult(
                id=doc_id,
                target_path=rel_path,
                repo=repo_name,
                role=role,
                found=True,
                summary=safe_summary,
                notes=None,
                last_modified=_get_last_modified(full_path),
            )
        )

    return results
