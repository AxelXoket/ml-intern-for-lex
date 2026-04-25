# Progress Log

---

## 2026-04-22 (Tuesday) — 02:30 — Initial Architecture

### V1: Hardened Companion Dashboard ✅

Built from scratch as a secure, isolated companion dashboard for `lex_study_foundation`.

**What was done:**
- Full project skeleton: `src/ml_intern/` package layout, hatchling build, `uv`-based workflow
- CLI entry point: `ml-intern serve` (Typer, subcommand-based, `no_args_is_help`)
- FastAPI backend with SSE-based real-time output streaming
- Cyberpunk dark theme UI (vanilla HTML/CSS/JS — navy/black base, cyan + crimson accents)
- Split settings: `IntegrationSettings` (lex connection) + `ResearchProviderSettings` (ml-intern tokens)
- Deterministic `.env` loading from package location, never CWD-dependent
- Subprocess env allowlist — `os.environ.copy()` replaced with explicit allowlist + deny list
- Secret redaction on all output, errors, and session summaries
- Process kill on cancel (`process.kill()` + `await process.wait()`)
- Output buffer cap (5000 lines per job)
- Health state enum: `healthy` / `degraded` / `unavailable`
- Research mode V1: config + feature flags only, no real provider features yet
- Command allowlist: `doctor`, `info`, `paths`, `validate-config`
- Job lifecycle manager with in-memory registry, single-job execution
- Session summary mechanism (compact, redacted, overwritten each session)
- Config file viewer with path traversal protection
- Secret boundary fully documented in README

**Key security decisions:**
- ml-intern secrets never forwarded to lex subprocesses
- lex secrets never injected by ml-intern — lex CLI loads its own `.env`
- `RuntimeError` instead of `assert` for security-critical checks
- PYTHONPATH not injected by default — verified unnecessary
- Localhost-only binding by default

**Verification:**
- `uv sync` → 27 packages
- `uv run ml-intern serve` → dashboard loads, Connected, doctor command works
- `uv tool install -e .` → global CLI works
- Git hygiene clean — `.env`, `.venv`, caches excluded

**Stack:** Python 3.14, FastAPI, Uvicorn, Typer, Pydantic v2, pydantic-settings, Hatchling, uv

---
