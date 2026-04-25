"""Report routes — generate, cache, and serve Reality Report sub-sections.

Cache pattern: module-level variable (_cached_report).
- POST /api/report → run pipeline, store result in cache
- GET /api/report → return cached result or 404
- Sub-endpoints (/findings, /observations, etc.) slice the cached report
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from ml_intern.config import INTERN_REPO_ROOT, get_integration_settings
from ml_intern.repo_access import get_allowed_repos
from ml_intern.report_builder import generate_report
from ml_intern.report_schemas import RealityReport
from ml_intern.schemas import HealthState, RepoInfo


router = APIRouter(tags=["report"])

# ── Module-level cache ──────────────────────────────────────────
_cached_report: RealityReport | None = None


# ── Generate Report ─────────────────────────────────────────────

@router.post("/api/report")
async def trigger_report():
    """Generate a Reality Report and cache the result.

    Runs the full pipeline (document intake + repo scan + comparison engine)
    via run_in_executor to avoid blocking the async event loop.
    """
    global _cached_report

    config = get_integration_settings()

    loop = asyncio.get_event_loop()
    try:
        report = await loop.run_in_executor(
            None,
            generate_report,
            INTERN_REPO_ROOT,
            config.project_root,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {exc}",
        )

    _cached_report = report
    return report.model_dump(mode="json")


# ── Read Cached Report ──────────────────────────────────────────

@router.get("/api/report")
def get_report():
    """Return the cached Reality Report, or 404 if never generated."""
    if _cached_report is None:
        raise HTTPException(status_code=404, detail="No report cached. POST /api/report first.")
    return _cached_report.model_dump(mode="json")


@router.get("/api/report/status")
def get_report_status():
    """Check whether a cached report exists."""
    return {"status": "ready" if _cached_report is not None else "never_run"}


@router.get("/api/report/findings")
def get_report_findings():
    """Return just the findings from the cached report."""
    if _cached_report is None:
        raise HTTPException(status_code=404, detail="No report cached.")
    return [f.model_dump(mode="json") for f in _cached_report.findings]


@router.get("/api/report/observations")
def get_report_observations():
    """Return just the observations from the cached report."""
    if _cached_report is None:
        raise HTTPException(status_code=404, detail="No report cached.")
    return [o.model_dump(mode="json") for o in _cached_report.observations]


@router.get("/api/report/questions")
def get_report_questions():
    """Return just the questions from the cached report."""
    if _cached_report is None:
        raise HTTPException(status_code=404, detail="No report cached.")
    return [q.model_dump(mode="json") for q in _cached_report.questions]


@router.get("/api/report/summary")
def get_report_summary():
    """Return just the executive summary from the cached report."""
    if _cached_report is None:
        raise HTTPException(status_code=404, detail="No report cached.")
    return _cached_report.executive_summary.model_dump(mode="json")


# ── Dashboard Summary ──────────────────────────────────────────

@router.get("/api/dashboard/summary")
def get_dashboard_summary():
    """Lightweight aggregation for the dashboard overview."""
    repos = get_allowed_repos()
    repo_list = [
        RepoInfo(
            key=key,
            name=root.name,
            path=str(root),
            accessible=root.is_dir(),
        )
        for key, root in repos.items()
    ]

    report_status = "ready" if _cached_report is not None else "never_run"

    # Determine overall health
    all_accessible = all(r.accessible for r in repo_list)
    health: HealthState = "healthy" if all_accessible else "degraded"

    return {
        "repos": [r.model_dump() for r in repo_list],
        "report_status": report_status,
        "report_summary": (
            _cached_report.executive_summary.model_dump(mode="json")
            if _cached_report is not None
            else None
        ),
        "health": health,
    }
