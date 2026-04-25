"""Typed request/response schemas for the ml-intern API.

All API communication uses these models. No loose strings or dicts
cross the boundary between frontend and backend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Health ───────────────────────────────────────────────────────

HealthState = Literal["healthy", "degraded", "unavailable"]

ResearchState = Literal["disabled", "unconfigured", "available"]


# ── Job Lifecycle ────────────────────────────────────────────────

JobStatus = Literal["queued", "running", "success", "error", "cancelled", "timeout"]


class JobCreateRequest(BaseModel):
    """Request to create and start a new job."""

    command: str = Field(description="Command name (must be in allowlist)")
    config_file: str | None = Field(
        default=None,
        description="Config file name for commands that need one",
    )
    flags: dict[str, str | bool] = Field(
        default_factory=dict,
        description="Typed flag overrides (e.g. {'type': 'generation'})",
    )


class JobResponse(BaseModel):
    """Job state returned to the frontend."""

    job_id: str
    command: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    exit_code: int | None = None
    error_message: str | None = None
    args_used: list[str] = Field(default_factory=list)


class JobSummary(BaseModel):
    """Compact job entry for recent jobs list."""

    job_id: str
    command: str
    status: JobStatus
    exit_code: int | None = None
    duration_ms: int | None = None
    created_at: str


# ── Output Line ──────────────────────────────────────────────────

class OutputLine(BaseModel):
    """Single line of job output."""

    stream: Literal["stdout", "stderr"]
    text: str
    text_clean: str  # ANSI stripped
    timestamp: str


# ── Status ───────────────────────────────────────────────────────

class StatusResponse(BaseModel):
    """Health check response with real verification."""

    health: HealthState
    server_ok: bool = True
    python_exe_exists: bool
    python_exe_path: str
    project_root_exists: bool
    project_root_path: str
    config_dir_exists: bool
    config_dir_path: str
    cli_callable: bool
    cli_version: str | None = None
    research_status: ResearchState = "disabled"
    error: str | None = None


# ── Commands ─────────────────────────────────────────────────────

class CommandInfo(BaseModel):
    """Metadata for an allowed command."""

    name: str
    description: str
    phase: int
    timeout: int
    has_args: bool = False
    needs_config: bool = False


# ── Config Files ─────────────────────────────────────────────────

class ConfigFileInfo(BaseModel):
    """Metadata for a config YAML file."""

    name: str
    path: str
    size_bytes: int
    category: str  # "generation" or "training"


class ConfigFileContent(BaseModel):
    """Config file with its raw content."""

    name: str
    category: str
    content: str


# ── Session Summary ──────────────────────────────────────────────

class SessionSummary(BaseModel):
    """Compact end-of-session recap."""

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    total_jobs: int = 0
    last_command: str | None = None
    last_status: JobStatus | None = None
    last_exit_code: int | None = None
    open_issue: str | None = None
    suggested_next: str | None = None
