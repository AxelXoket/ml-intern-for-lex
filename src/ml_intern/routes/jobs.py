"""Job routes — create, query, stream, and cancel jobs."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ml_intern.commands import all_commands, get_command, is_allowed
from ml_intern.jobs import job_manager
from ml_intern.schemas import JobCreateRequest, JobResponse


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ── Create Job ──────────────────────────────────────────────────

@router.post("", response_model=JobResponse)
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


# ── Query Jobs ──────────────────────────────────────────────────

@router.get("/recent")
async def recent_jobs(limit: int = 20):
    """Return recent jobs, newest first."""
    return job_manager.recent_jobs(limit=min(limit, 50))


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get current state of a job."""
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_response()


# ── Stream Job ──────────────────────────────────────────────────

@router.get("/{job_id}/stream")
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


# ── Cancel Job ──────────────────────────────────────────────────

@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str):
    """Cancel a running job."""
    job = await job_manager.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_response()
