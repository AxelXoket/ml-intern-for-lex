"""FastAPI application — routes, SSE streaming, static file serving.

All routes go through typed schemas. No raw strings reach subprocess.
SSE streaming delivers real-time output from running jobs.
Static files are served from within the package (package-relative).
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ml_intern.commands import all_commands, get_command, is_allowed
from ml_intern.config import get_integration_settings, get_research_settings
from ml_intern.jobs import job_manager
from ml_intern.runner import check_cli_available
from ml_intern.schemas import (
    CommandInfo,
    ConfigFileContent,
    ConfigFileInfo,
    HealthState,
    JobCreateRequest,
    JobResponse,
    StatusResponse,
)


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


# ── Dashboard ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=500, detail="Dashboard HTML not found")
    return index_path.read_text(encoding="utf-8")


# ── API: Status ──────────────────────────────────────────────────

@app.get("/api/status", response_model=StatusResponse)
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

@app.get("/api/commands")
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


# ── API: Jobs ────────────────────────────────────────────────────

@app.post("/api/jobs", response_model=JobResponse)
async def create_job(request: JobCreateRequest):
    """Create and start a new job."""
    # Validate command is in allowlist
    if not is_allowed(request.command):
        raise HTTPException(
            status_code=400,
            detail=f"Command '{request.command}' is not allowed. Allowed: {list(all_commands().keys())}",
        )

    spec = get_command(request.command)
    if spec is None:
        raise HTTPException(status_code=400, detail="Command not found")

    # Validate config requirement
    if spec.needs_config and not request.config_file:
        raise HTTPException(
            status_code=400,
            detail=f"Command '{request.command}' requires a config_file",
        )

    # Check if busy — return 409 Conflict
    if job_manager.is_busy:
        raise HTTPException(
            status_code=409,
            detail="A job is already running. Wait for it to complete or cancel it.",
        )

    try:
        job = await job_manager.create_and_run(request, spec)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return job.to_response()


@app.get("/api/jobs/recent")
async def recent_jobs(limit: int = 20):
    """Return recent jobs, newest first."""
    return job_manager.recent_jobs(limit=min(limit, 50))


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get current state of a job."""
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_response()


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    """SSE stream for real-time job output.

    Sends buffered lines immediately (supports reconnection),
    then streams new lines as they arrive.
    """
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        queue = job.subscribe()
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
                    continue

                if line is None:
                    # Job completed — send final status event
                    final = job.to_response().model_dump()
                    yield f"event: status\ndata: {json.dumps(final)}\n\n"
                    break

                # Send output line event
                data = line.model_dump()
                yield f"event: output\ndata: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str):
    """Cancel a running job."""
    job = await job_manager.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_response()


# ── API: Config Files ────────────────────────────────────────────

@app.get("/api/configs", response_model=list[ConfigFileInfo])
async def list_configs():
    """List available YAML config files from lex_study_foundation."""
    config = get_integration_settings()
    config_dir = config.config_dir
    files: list[ConfigFileInfo] = []

    if not config_dir.is_dir():
        return files

    for category_dir in sorted(config_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        for yaml_file in sorted(category_dir.glob("*.yaml")):
            files.append(
                ConfigFileInfo(
                    name=yaml_file.name,
                    path=f"{category}/{yaml_file.name}",
                    size_bytes=yaml_file.stat().st_size,
                    category=category,
                )
            )
        for yml_file in sorted(category_dir.glob("*.yml")):
            files.append(
                ConfigFileInfo(
                    name=yml_file.name,
                    path=f"{category}/{yml_file.name}",
                    size_bytes=yml_file.stat().st_size,
                    category=category,
                )
            )

    return files


@app.get("/api/configs/{category}/{name}", response_model=ConfigFileContent)
async def get_config_file(category: str, name: str):
    """Read a specific config file's content."""
    config = get_integration_settings()

    # Sanitize inputs
    safe_category = category.replace("..", "").replace("/", "").replace("\\", "")
    safe_name = name.replace("..", "").replace("/", "").replace("\\", "")

    file_path = config.config_dir / safe_category / safe_name
    if not file_path.is_file() or file_path.suffix not in (".yaml", ".yml"):
        raise HTTPException(status_code=404, detail="Config file not found")

    # Ensure we don't escape the config directory
    try:
        file_path.resolve().relative_to(config.config_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal denied")

    content = file_path.read_text(encoding="utf-8")
    return ConfigFileContent(name=safe_name, category=safe_category, content=content)


# ── API: Session Summary ────────────────────────────────────────

@app.get("/api/session/summary")
async def get_session_summary():
    """Get the current session summary (without writing to file)."""
    return job_manager.generate_session_summary()


# ── API: Reality Report ─────────────────────────────────────────

@app.get("/api/report")
async def get_reality_report():
    """Generate a Context Intake + Repo Reality Report.

    Scans both repositories (lex_study_foundation and ml-intern-for-lex)
    in read-only mode and produces a structured RealityReport.

    This endpoint calls the synchronous report builder via run_in_executor
    to avoid blocking the async event loop during filesystem I/O.

    Returns a complete RealityReport JSON object conforming to the
    Part 1 output contract schema.
    """
    from ml_intern.config import _REPO_ROOT
    from ml_intern.report_builder import generate_report

    config = get_integration_settings()

    loop = asyncio.get_event_loop()
    try:
        report = await loop.run_in_executor(
            None,
            generate_report,
            _REPO_ROOT,
            config.project_root,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {exc}",
        )

    return report.model_dump(mode="json")
