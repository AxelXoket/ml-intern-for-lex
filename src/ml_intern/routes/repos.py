"""Repository access routes — list repos, browse tree, read file meta/content.

All endpoints enforce:
1. Allowed repo key validation (unknown repo → 404)
2. Path traversal prevention (resolve + is_relative_to → 403)
3. Sensitive file blocking (.env → 403, meta still OK)
4. Binary file blocking (non-text → 415)
5. Content redaction (redact_secrets on every line)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ml_intern.repo_access import (
    MAX_LINES_PER_REQUEST,
    get_allowed_repos,
    get_file_meta,
    get_repo_root,
    is_sensitive_file,
    is_text_file,
    read_file_lines,
    validate_path,
)
from ml_intern.repo_scanner import DEFAULT_PRUNE_DIRS
from ml_intern.schemas import (
    FileContentResponse,
    FileMetaResponse,
    RepoInfo,
    TreeEntry,
)


router = APIRouter(prefix="/api/repos", tags=["repos"])


# ── List Repos ──────────────────────────────────────────────────

@router.get("", response_model=list[RepoInfo])
def list_repos():
    """List available repositories."""
    repos = get_allowed_repos()
    result = []
    for key, root in repos.items():
        result.append(
            RepoInfo(
                key=key,
                name=root.name,
                path=str(root),
                accessible=root.is_dir(),
            )
        )
    return result


# ── Directory Tree ──────────────────────────────────────────────

@router.get("/{repo}/tree", response_model=list[TreeEntry])
def get_tree(repo: str):
    """Get flat directory tree for a repository.

    Returns a flat list (not nested) of all files and directories,
    pruning common non-essential directories (.git, .venv, __pycache__, etc).
    """
    try:
        root = get_repo_root(repo)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown repository: '{repo}'")

    if not root.is_dir():
        raise HTTPException(status_code=404, detail="Repository root not found")

    entries: list[TreeEntry] = []

    for dirpath, dirnames, filenames in root.walk():
        # Prune non-essential directories
        dirnames[:] = [
            d for d in dirnames
            if d not in DEFAULT_PRUNE_DIRS and not d.startswith(".")
        ]

        # Relative path from repo root
        rel_dir = dirpath.relative_to(root)

        # Add directories
        for d in sorted(dirnames):
            entries.append(
                TreeEntry(
                    path=str(rel_dir / d).replace("\\", "/"),
                    type="directory",
                )
            )

        # Add files
        for f in sorted(filenames):
            fpath = dirpath / f
            try:
                stat = fpath.stat()
                size = stat.st_size
            except OSError:
                size = None

            entries.append(
                TreeEntry(
                    path=str(rel_dir / f).replace("\\", "/"),
                    type="file",
                    size_bytes=size,
                    extension=fpath.suffix.lower() or None,
                    is_text=is_text_file(fpath),
                    sensitive=is_sensitive_file(fpath),
                )
            )

    return entries


# ── File Metadata ───────────────────────────────────────────────

@router.get("/{repo}/file/meta", response_model=FileMetaResponse)
def get_file_meta_endpoint(
    repo: str,
    path: str = Query(..., description="Relative file path within the repo"),
):
    """Get metadata for a specific file.

    Sensitive files (.env) return metadata (size, existence) but with
    sensitive=true flag. Content is never exposed.
    """
    try:
        root = get_repo_root(repo)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown repository: '{repo}'")

    try:
        resolved = validate_path(path, root)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Path traversal denied")

    try:
        meta = get_file_meta(resolved, root)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

    return FileMetaResponse(**meta)


# ── File Content ────────────────────────────────────────────────

@router.get("/{repo}/file", response_model=FileContentResponse)
def get_file_content(
    repo: str,
    path: str = Query(..., description="Relative file path within the repo"),
    start: int = Query(1, ge=1, description="Start line (1-indexed, inclusive)"),
    end: int = Query(None, ge=1, description="End line (1-indexed, inclusive)"),
):
    """Read file content with line range support.

    Returns redacted lines within the specified range.
    Max 1000 lines per request.
    """
    try:
        root = get_repo_root(repo)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown repository: '{repo}'")

    try:
        resolved = validate_path(path, root)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Path traversal denied")

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if is_sensitive_file(resolved):
        raise HTTPException(status_code=403, detail="Cannot read sensitive file content")

    if not is_text_file(resolved):
        raise HTTPException(status_code=415, detail="Cannot read binary file content")

    # Apply defaults and validate range
    if end is None:
        end = start + MAX_LINES_PER_REQUEST - 1

    if end - start + 1 > MAX_LINES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Requested range ({end - start + 1} lines) exceeds "
                   f"maximum of {MAX_LINES_PER_REQUEST} lines per request",
        )

    try:
        lines = list(read_file_lines(resolved, start=start, end=end))
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

    # Get total line count for the response
    meta = get_file_meta(resolved, root)

    return FileContentResponse(
        path=meta["path"],
        start=start,
        end=min(end, start + len(lines) - 1) if lines else start,
        total_lines=meta.get("line_count"),
        lines=lines,
    )
