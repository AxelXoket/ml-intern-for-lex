# ml-intern

Companion dashboard and research sidecar for [lex_study_foundation](https://github.com/AxelXoket/lex-study-foundation).

## What is this?

`ml-intern` is a **separate, lightweight web dashboard** that observes and runs selected
`lex_study_foundation` CLI commands through a browser UI. It is NOT the core project —
it is a companion tool designed to stay decoupled.

**Role:** visual companion, research sidecar, command observation layer.

## Quick Start

### Prerequisites

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- `lex_study_foundation` installed and configured in its own venv

### Install & Run

```bash
git clone <repo-url>
cd ml-intern

# Install dependencies
uv sync

# Configure (fill in your paths)
cp .env.example .env
# Edit .env: set LEX_PYTHON_EXE and LEX_PROJECT_ROOT

# Start dashboard (development)
uv run ml-intern serve

# Or install CLI globally
uv tool install -e .
ml-intern serve
```

Dashboard opens at `http://127.0.0.1:8642`.

### CLI Usage

```
ml-intern              → shows help
ml-intern serve        → starts dashboard
ml-intern serve --port 9000  → custom port
```

## Configuration

### Required Variables

| Variable | Description |
|----------|-------------|
| `LEX_PYTHON_EXE` | Absolute path to Python in `lex_study_foundation`'s venv |
| `LEX_PROJECT_ROOT` | Absolute path to `lex_study_foundation` repo root |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LEX_CONFIG_DIR` | `{ROOT}/configs` | Override config file directory |
| `ML_INTERN_HOST` | `127.0.0.1` | Server bind host |
| `ML_INTERN_PORT` | `8642` | Server port |
| `RESEARCH_ENABLED` | `false` | Enable research features |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (ml-intern only) |
| `HF_TOKEN` | — | HuggingFace token (ml-intern only) |
| `GITHUB_TOKEN` | — | GitHub token (ml-intern only) |

### .env Resolution

The `.env` file is resolved **deterministically from the package location** — never
from the current working directory. This ensures consistent behavior regardless of
where you run `ml-intern serve`.

Override with `ML_INTERN_ENV_FILE=<absolute-path>` for non-standard layouts.

> **Note:** Default resolution assumes editable install (`uv sync` or `uv tool install -e .`).
> For non-editable installs, use `ML_INTERN_ENV_FILE`.

## Features Without Provider Tokens

The following features work without any provider tokens:

- ✅ Dashboard UI
- ✅ CLI command execution (doctor, info, paths, validate-config)
- ✅ Real-time output streaming (SSE)
- ✅ Config file viewing
- ✅ Job history
- ✅ Health status checks
- ✅ Session summary

Provider tokens are only needed for research-mode features (disabled by default in V1).

## Security & Boundary Design

### Why Two Repos?

`ml-intern` and `lex_study_foundation` are **separate repos with separate concerns**:

- Separate git repositories
- Separate virtual environments
- Separate `.env` files
- Separate dependency sets
- No shared secrets
- No import-level coupling

`ml-intern` communicates with `lex_study_foundation` exclusively through subprocess
invocation — never through direct Python imports.

### Secret Boundary

> **Critical design constraint:** Provider secrets never cross repo boundaries.

**Ownership rules:**
- `ml-intern` secrets (`ANTHROPIC_API_KEY`, `HF_TOKEN`, `GITHUB_TOKEN`) → belong to `ml-intern` only
- `lex_study_foundation` secrets (`GEMINI_API_KEY`) → belong to `lex_study_foundation` only
- Each repo loads its own secrets from its own `.env` file

**What `ml-intern` does NOT do:**
- Does NOT inject `GEMINI_API_KEY` into lex subprocesses
- Does NOT read `lex_study_foundation/.env`
- Does NOT forward `os.environ` to child processes
- Does NOT silently compensate for missing lex-side configuration

**What `ml-intern` DOES do:**
- Builds a **minimal, allowlisted subprocess environment** (only OS runtime vars)
- Enforces a **deny list** of secrets that must never appear in subprocess env
- Raises a hard `RuntimeError` if a denied secret is detected
- Applies **secret redaction** to all output, error messages, and session summaries

**If a lex command needs provider credentials:**
That is a `lex_study_foundation` configuration issue. The lex CLI loads its own `.env`
from its own project root (set as CWD in the subprocess). `ml-intern` will not inject,
guess, or share secrets on lex's behalf.

### Subprocess Environment

When `ml-intern` launches `lex_study_foundation` commands, it constructs a **fresh,
minimal environment** from scratch:

**Forwarded (allowlist):**
- Windows runtime essentials (`SystemRoot`, `COMSPEC`, `PATH`, etc.)
- Temp directories (`TEMP`, `TMP`)
- User profile vars

**Never forwarded (deny list):**
- `ANTHROPIC_API_KEY`, `HF_TOKEN`, `GITHUB_TOKEN`
- `GEMINI_API_KEY`, `OPENAI_API_KEY`
- `AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`

### Command Allowlist

Only explicitly registered commands can be executed:
- `doctor` — environment health check
- `info` — project metadata
- `paths` — resolved directory paths
- `validate-config` — YAML config validation

No arbitrary shell commands. No `shell=True`. No raw user input reaches subprocess.

### Read / Observe Boundary

`ml-intern` operates in **read/observe mode only** toward `lex_study_foundation`:

- ✅ Run allowlisted commands
- ✅ Read config files
- ✅ View command output
- ❌ No file modification in lex repo
- ❌ No config rewriting
- ❌ No automatic code changes

### Network Exposure

Dashboard binds to `127.0.0.1` (localhost) by default.
Binding to `0.0.0.0` requires explicit opt-in via `ML_INTERN_HOST`.

### Token Hygiene

- **GitHub:** Prefer fine-grained PAT with minimum permissions and expiration
- **HuggingFace:** Prefer read-only token unless write access is actually needed
- **Anthropic:** Only configure if research mode is actually being used

## Architecture

```
ml-intern (FastAPI)  ─── subprocess ──▶  lex_study_foundation (Typer CLI)
     │                                        cwd = LEX_PROJECT_ROOT
     │ SSE                                    env = allowlisted minimal
     ▼
  Browser UI (vanilla HTML/JS/CSS)
```

## License

MIT
