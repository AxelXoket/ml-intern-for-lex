"""Dashboard routes — serves HTML, status, commands, session summary."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from ml_intern.commands import all_commands
from ml_intern.config import get_integration_settings, get_research_settings
from ml_intern.jobs import job_manager
from ml_intern.runner import check_cli_available
from ml_intern.schemas import (
    CommandInfo,
    HealthState,
    StatusResponse,
)


router = APIRouter(tags=["dashboard"])

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# ── Dashboard ────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=500, detail="Dashboard HTML not found")
    return index_path.read_text(encoding="utf-8")


# ── API: Status ──────────────────────────────────────────────────

@router.get("/api/status", response_model=StatusResponse)
async def get_status():
    """Real health check — verifies Python exe, project root, CLI, and research state."""
    config = get_integration_settings()
    research = get_research_settings()

    python_exists = config.python_exe.is_file()
    root_exists = config.project_root.is_dir()
    config_dir_exists = config.config_dir.is_dir()

    cli_ok = False
    cli_version = None
    error = None

    if python_exists and root_exists:
        try:
            cli_ok, cli_version = await check_cli_available(
                config.python_exe, config.project_root
            )
        except Exception as exc:
            error = str(exc)

    # Determine health state
    health: HealthState
    if python_exists and root_exists and cli_ok:
        health = "healthy"
    elif python_exists and root_exists:
        health = "degraded"
    else:
        health = "unavailable"

    return StatusResponse(
        health=health,
        python_exe_exists=python_exists,
        python_exe_path=str(config.python_exe),
        project_root_exists=root_exists,
        project_root_path=str(config.project_root),
        config_dir_exists=config_dir_exists,
        config_dir_path=str(config.config_dir),
        cli_callable=cli_ok,
        cli_version=cli_version,
        research_status=research.research_status,
        error=error,
    )


# ── API: Commands ────────────────────────────────────────────────

@router.get("/api/commands")
async def list_commands() -> dict[str, CommandInfo]:
    """Return the command allowlist."""
    registry = all_commands()
    return {
        name: CommandInfo(
            name=spec.name,
            description=spec.description,
            phase=spec.phase,
            timeout=spec.timeout,
            has_args=bool(spec.allowed_flags),
            needs_config=spec.needs_config,
        )
        for name, spec in registry.items()
    }


# ── API: Session Summary ────────────────────────────────────────

@router.get("/api/session/summary")
async def get_session_summary():
    """Get the current session summary (without writing to file)."""
    return job_manager.generate_session_summary()
