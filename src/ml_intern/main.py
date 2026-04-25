"""FastAPI application — app creation, lifespan, static mounts, router inclusion.

All route handlers live in the routes/ package. This module handles:
- App creation and configuration
- Lifespan (startup/shutdown)
- Static file mounts (CSS, JS)
- Router inclusion
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ml_intern.config import get_integration_settings
from ml_intern.jobs import job_manager
from ml_intern.routes.configs import router as configs_router
from ml_intern.routes.dashboard import router as dashboard_router
from ml_intern.routes.jobs import router as jobs_router
from ml_intern.routes.report import router as report_router
from ml_intern.routes.repos import router as repos_router


# ── Lifespan ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    config = get_integration_settings()
    print(f"\n  ml-intern starting...")
    print(f"  LEX_PYTHON_EXE:  {config.lex_python_exe}")
    print(f"  LEX_PROJECT_ROOT: {config.lex_project_root}")
    print(f"  Config dir:       {config.config_dir}")
    print(f"  Dashboard:        http://{config.ml_intern_host}:{config.ml_intern_port}\n")
    yield
    # Shutdown: write session summary
    summary_path = Path("session_summary.json")
    job_manager.write_session_summary(summary_path)
    print(f"\n  Session summary written to {summary_path.resolve()}\n")


# ── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="ml-intern",
    description="Companion dashboard for lex_study_foundation",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Static files (package-relative) ─────────────────────────────

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Mount static assets (CSS, JS) — must be before the catch-all route
app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(STATIC_DIR / "js")), name="js")


# ── Include Routers ─────────────────────────────────────────────

app.include_router(dashboard_router)
app.include_router(jobs_router)
app.include_router(configs_router)
app.include_router(repos_router)
app.include_router(report_router)
