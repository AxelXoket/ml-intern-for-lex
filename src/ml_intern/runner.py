"""Async subprocess runner with ANSI stripping and line streaming.

Executes lex_study_foundation CLI commands via subprocess with:
- Incremental stdout/stderr streaming
- ANSI escape code stripping for clean web display
- Secret redaction on all output
- Timeout enforcement
- Exit code capture
- No shell=True
- Minimal allowlisted subprocess environment
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from ml_intern.security import build_subprocess_env, redact_secrets

# ANSI escape sequence pattern (covers CSI, OSC, and simple escapes)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[^[\]()]")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from a string."""
    return _ANSI_RE.sub("", text)


@dataclass
class OutputRecord:
    """A single line of captured output."""

    stream: str  # "stdout" or "stderr"
    text: str  # raw text (may contain ANSI), redacted
    text_clean: str  # ANSI-stripped, redacted
    timestamp: str


@dataclass
class RunResult:
    """Final result of a completed subprocess run."""

    exit_code: int
    duration_ms: int
    lines: list[OutputRecord] = field(default_factory=list)
    error: str | None = None


async def stream_command(
    python_exe: Path,
    project_root: Path,
    args: list[str],
    timeout: int = 30,
) -> AsyncIterator[OutputRecord | RunResult]:
    """Run a CLI command and yield output lines as they arrive.

    Invocation: {python_exe} -m lex_study_foundation {args}
    Environment: minimal allowlisted env (no secrets forwarded)
    CWD: {project_root} (so lex CLI can find its own .env)

    Yields OutputRecord for each line, then a final RunResult.
    """
    cmd = [str(python_exe), "-m", "lex_study_foundation"] + args

    start_time = time.monotonic()

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_root),
            env=build_subprocess_env(project_root),
        )
    except FileNotFoundError as exc:
        yield RunResult(
            exit_code=-1,
            duration_ms=0,
            error=redact_secrets(f"Failed to start process: {exc}"),
        )
        return
    except OSError as exc:
        yield RunResult(
            exit_code=-1,
            duration_ms=0,
            error=redact_secrets(f"OS error starting process: {exc}"),
        )
        return

    all_lines: list[OutputRecord] = []

    async def _read_stream(
        stream: asyncio.StreamReader | None,
        stream_name: str,
    ) -> None:
        if stream is None:
            return
        while True:
            line_bytes = await stream.readline()
            if not line_bytes:
                break
            text = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
            # Redact secrets before storing
            text_redacted = redact_secrets(text)
            text_clean = redact_secrets(strip_ansi(text))
            record = OutputRecord(
                stream=stream_name,
                text=text_redacted,
                text_clean=text_clean,
                timestamp=datetime.now().isoformat(),
            )
            all_lines.append(record)

    try:
        # Read both streams concurrently with timeout
        await asyncio.wait_for(
            asyncio.gather(
                _read_stream(process.stdout, "stdout"),
                _read_stream(process.stderr, "stderr"),
            ),
            timeout=timeout,
        )
        exit_code = await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        elapsed = int((time.monotonic() - start_time) * 1000)
        # Yield all collected lines before the timeout
        for line in all_lines:
            yield line
        yield RunResult(
            exit_code=-1,
            duration_ms=elapsed,
            lines=all_lines,
            error=f"Command timed out after {timeout}s",
        )
        return

    elapsed = int((time.monotonic() - start_time) * 1000)

    # Yield all lines
    for line in all_lines:
        yield line

    # Final result
    yield RunResult(
        exit_code=exit_code,
        duration_ms=elapsed,
        lines=all_lines,
    )


async def check_cli_available(python_exe: Path, project_root: Path) -> tuple[bool, str | None]:
    """Smoke-check: run `python -m lex_study_foundation --help` and see if it works.

    Returns (is_callable, version_or_none).
    """
    try:
        process = await asyncio.create_subprocess_exec(
            str(python_exe),
            "-m",
            "lex_study_foundation",
            "--help",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_root),
            env=build_subprocess_env(project_root),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        if process.returncode == 0:
            text = stdout.decode("utf-8", errors="replace")
            return True, _extract_version(text)
        return False, None
    except (FileNotFoundError, OSError, asyncio.TimeoutError):
        return False, None


def _extract_version(help_text: str) -> str | None:
    """Try to extract version from CLI help output."""
    for line in help_text.splitlines():
        lower = line.lower()
        if "version" in lower:
            match = re.search(r"(\d+\.\d+\.\d+)", line)
            if match:
                return match.group(1)
    return None
