"""Job lifecycle manager with in-memory registry.

Manages job creation, execution, output buffering, and session summary.
Single-job execution model — only one job can run at a time.
Jobs are retained in memory with bounded history.

Security:
- Process reference stored for reliable cancellation (kill + wait)
- Output buffer capped at MAX_OUTPUT_LINES per job
- Secret redaction applied to error messages and session summaries
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ml_intern.commands import CommandSpec, build_args
from ml_intern.config import get_integration_settings
from ml_intern.runner import OutputRecord, RunResult, stream_command
from ml_intern.schemas import (
    JobCreateRequest,
    JobResponse,
    JobStatus,
    JobSummary,
    OutputLine,
    SessionSummary,
)
from ml_intern.security import redact_secrets

# ── Constants ────────────────────────────────────────────────────

MAX_OUTPUT_LINES = 5000  # per job
MAX_JOB_HISTORY = 50


# ── Job ──────────────────────────────────────────────────────────

class Job:
    """Internal job representation with output buffer and process reference."""

    def __init__(self, job_id: str, command: str, spec: CommandSpec, request: JobCreateRequest) -> None:
        self.job_id = job_id
        self.command = command
        self.spec = spec
        self.request = request
        self.status: JobStatus = "queued"
        self.created_at = datetime.now()
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.duration_ms: int | None = None
        self.exit_code: int | None = None
        self.error_message: str | None = None
        self.args_used: list[str] = []

        # Output buffer — bounded, stores all lines for reconnection
        self.output_lines: list[OutputLine] = []
        self._subscribers: list[asyncio.Queue[OutputLine | None]] = []

        # Process reference for reliable cancellation
        self._process: asyncio.subprocess.Process | None = None

    def to_response(self) -> JobResponse:
        return JobResponse(
            job_id=self.job_id,
            command=self.command,
            status=self.status,
            created_at=self.created_at.isoformat(),
            started_at=self.started_at.isoformat() if self.started_at else None,
            finished_at=self.finished_at.isoformat() if self.finished_at else None,
            duration_ms=self.duration_ms,
            exit_code=self.exit_code,
            error_message=self.error_message,
            args_used=self.args_used,
        )

    def to_summary(self) -> JobSummary:
        return JobSummary(
            job_id=self.job_id,
            command=self.command,
            status=self.status,
            exit_code=self.exit_code,
            duration_ms=self.duration_ms,
            created_at=self.created_at.isoformat(),
        )

    def subscribe(self) -> asyncio.Queue[OutputLine | None]:
        """Subscribe to live output. Returns a queue that receives lines."""
        q: asyncio.Queue[OutputLine | None] = asyncio.Queue()
        # Send buffered lines first (for reconnection)
        for line in self.output_lines:
            q.put_nowait(line)
        if self.status in ("success", "error", "cancelled", "timeout"):
            q.put_nowait(None)  # signal completion
        else:
            self._subscribers.append(q)
        return q

    def _push_line(self, line: OutputLine) -> None:
        """Push a new output line to buffer and all subscribers.

        Buffer is capped at MAX_OUTPUT_LINES — oldest lines are dropped.
        """
        if len(self.output_lines) >= MAX_OUTPUT_LINES:
            # Drop the oldest line to maintain cap
            self.output_lines.pop(0)
        self.output_lines.append(line)
        for q in self._subscribers:
            q.put_nowait(line)

    def _finish(self) -> None:
        """Signal completion to all subscribers."""
        for q in self._subscribers:
            q.put_nowait(None)
        self._subscribers.clear()


# ── Job Manager ──────────────────────────────────────────────────

class JobManager:
    """In-memory job registry with single-job execution."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._running_job: str | None = None

    @property
    def is_busy(self) -> bool:
        return self._running_job is not None

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def recent_jobs(self, limit: int = 20) -> list[JobSummary]:
        """Return most recent jobs, newest first."""
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [j.to_summary() for j in jobs[:limit]]

    async def create_and_run(self, request: JobCreateRequest, spec: CommandSpec) -> Job:
        """Create a job and start execution. Raises if already busy."""
        if self.is_busy:
            raise RuntimeError("A job is already running. Wait for it to complete.")

        job_id = uuid.uuid4().hex[:12]
        job = Job(job_id=job_id, command=request.command, spec=spec, request=request)
        self._jobs[job_id] = job

        # Trim old jobs if exceeding max history
        if len(self._jobs) > MAX_JOB_HISTORY:
            oldest_keys = sorted(self._jobs, key=lambda k: self._jobs[k].created_at)
            for key in oldest_keys[: len(self._jobs) - MAX_JOB_HISTORY]:
                if key != job_id and key != self._running_job:
                    del self._jobs[key]

        # Start execution in background
        self._running_job = job_id
        asyncio.create_task(self._execute(job))
        return job

    async def cancel_job(self, job_id: str) -> Job | None:
        """Cancel a running job — kills the subprocess."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.status == "running":
            # Kill the subprocess if it exists
            if job._process is not None:
                try:
                    job._process.kill()
                    await job._process.wait()  # prevent orphan
                except ProcessLookupError:
                    pass  # already dead
            job.status = "cancelled"
            job.finished_at = datetime.now()
            if job.started_at:
                job.duration_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
            job._finish()
            self._running_job = None
        return job

    async def _execute(self, job: Job) -> None:
        """Execute a job via subprocess streaming."""
        config = get_integration_settings()

        # Build args from the typed request
        try:
            config_file = job.request.config_file
            if job.spec.needs_config and config_file:
                config_path = config.config_dir / _resolve_config_subpath(config_file, config.config_dir)
                if config_path.is_file():
                    config_file = str(config_path)

            raw_args = build_args(job.spec, config_file, job.request.flags)
            job.args_used = raw_args
        except ValueError as exc:
            job.status = "error"
            job.error_message = redact_secrets(str(exc))
            job.finished_at = datetime.now()
            job._finish()
            self._running_job = None
            return

        job.status = "running"
        job.started_at = datetime.now()

        try:
            async for item in stream_command(
                python_exe=config.python_exe,
                project_root=config.project_root,
                args=raw_args,
                timeout=job.spec.timeout,
            ):
                if job.status == "cancelled":
                    break

                if isinstance(item, OutputRecord):
                    line = OutputLine(
                        stream=item.stream,
                        text=item.text,
                        text_clean=item.text_clean,
                        timestamp=item.timestamp,
                    )
                    job._push_line(line)

                elif isinstance(item, RunResult):
                    job.exit_code = item.exit_code
                    job.duration_ms = item.duration_ms
                    if item.error:
                        if "timed out" in (item.error or ""):
                            job.status = "timeout"
                        else:
                            job.status = "error"
                        job.error_message = redact_secrets(item.error)
                    else:
                        job.status = "success" if item.exit_code == 0 else "error"
                    job.finished_at = datetime.now()

        except Exception as exc:
            job.status = "error"
            job.error_message = redact_secrets(f"Unexpected error: {exc}")
            job.finished_at = datetime.now()

        job._finish()
        self._running_job = None

    def generate_session_summary(self) -> SessionSummary:
        """Generate a compact session-end summary (redacted)."""
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        total = len(jobs)

        last_job = jobs[0] if jobs else None

        open_issue: str | None = None
        suggested_next: str | None = None

        if last_job:
            if last_job.status in ("error", "timeout"):
                open_issue = f"Last command '{last_job.command}' failed"
                if last_job.error_message:
                    open_issue += f": {redact_secrets(last_job.error_message)}"
                suggested_next = f"Investigate and re-run '{last_job.command}'"
            elif last_job.status == "success":
                suggested_next = _suggest_next_command(last_job.command)

        return SessionSummary(
            total_jobs=total,
            last_command=last_job.command if last_job else None,
            last_status=last_job.status if last_job else None,
            last_exit_code=last_job.exit_code if last_job else None,
            open_issue=open_issue,
            suggested_next=suggested_next,
        )

    def write_session_summary(self, path: Path) -> None:
        """Write a compact session recap file (redacted, no raw dumps)."""
        summary = self.generate_session_summary()
        data = summary.model_dump()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")


def _suggest_next_command(last_command: str) -> str | None:
    """Suggest a natural next step based on the last successful command."""
    suggestions = {
        "doctor": "Run 'info' to check project metadata",
        "info": "Run 'paths' to inspect directory layout",
        "paths": "Run 'validate-config' to check your config files",
        "validate-config": "Config validated — ready for data generation (Phase 3)",
    }
    return suggestions.get(last_command)


def _resolve_config_subpath(name: str, config_dir: Path) -> str:
    """Resolve a config file name to its subpath within config_dir."""
    if (config_dir / name).is_file():
        return name
    for subdir in ("generation", "training"):
        candidate = config_dir / subdir / name
        if candidate.is_file():
            return f"{subdir}/{name}"
    return name


# ── Singleton ────────────────────────────────────────────────────
job_manager = JobManager()
