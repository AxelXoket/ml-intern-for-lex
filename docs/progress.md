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

**Stack:** Python 3.12 (originally built on 3.14, migrated to 3.12.10 in Phase 2.5), FastAPI, Uvicorn, Typer, Pydantic v2, pydantic-settings, Hatchling, uv

---

## 2026-04-24 (Thursday) — 06:00 — Project Charter + Part 1 Schema Design

### Canonical Project Charter ✅

Created `docs/PROJECT_CHARTER.md` — the single source of intent for the entire ecosystem.

**What was done:**
- 11-section charter covering: ecosystem overview, main project, target model/behavior, companion role, phase status, Phase 3 research questions, human-in-the-loop model, repo-to-intent comparison, decision classification, research discipline, and boundaries
- Strict separation between Locked decisions, Current Provider Directions, Current Working Assumptions, and Open Research Questions
- Provider isolation documented: Claude (Anthropic) for ml-intern research, Gemini 2.5 Flash for lex data generation — independent decisions
- Operational Boundaries and Engineering Constraints split into clear subsections (repo separation, subprocess security, data integrity, provider isolation)
- Base model (Gemma 4 E4B-it) confirmed as Locked
- "All repo-affecting actions require explicit human approval" consolidated as a single boundary rule
- Commit message format codified: `Type : Description`

### Part 1: Reality Report Output Schema ✅

Designed the structured output contract for the Context Intake + Repo Reality Report — the first capability of the research console evolution.

**What was done:**
- 8 Pydantic v2 enums: `DocumentRole`, `SourceKind`, `ObservationGranularity`, `FindingCategory`, `EvidenceOrigin`, `CompletenessStatus`, `ProjectPhase`, `ScanMode`
- 8 Pydantic v2 models: `RepoIdentity`, `EvidenceItem`, `DocumentReadResult`, `Observation`, `Finding`, `QuestionRaised`, `ExecutiveSummary`, `RealityReport`
- Strict 4-category separation: document reads → observations → findings → questions
- Evidence provenance system with cross-repo support (single finding can draw from both repos)
- Human-readable report-scoped IDs: `doc-001`, `obs-001`, `fnd-001`, `qst-001`
- Report envelope with identity (`rpt-YYYYMMDD-HHMMSS`), timestamp, schema version, target repos, phase, completeness
- Snapshot-aware fields: `snapshot_id` (`snp-YYYYMMDD-HHMMSS`), `scan_mode` (full/baseline/incremental/compare), `compared_to_snapshot_id` — future-ready without implementing diff logic
- `COMMAND_SURFACE` source kind + `INTERFACE_LEVEL` granularity for CLI observations
- Finding categories aligned with charter Section 8: aligned, misalignment, missing_decision, incomplete_implementation, phase_drift, research_gap, structural_inconsistency
- Redaction contract documented in module docstring and all text-bearing field descriptions
- No recommendation, severity, priority, or action fields — Part 1 is strictly descriptive

**Key design decisions:**
- Part 1 is ONLY the output contract — no scanning logic, no research logic, no UI
- Schema is designed so Part 2 (document reading + repo scanning) can populate it without schema changes
- `ProjectPhase` enum replaces free string to prevent typo risk
- Snapshot awareness is forward-compatible: fields exist but carry no comparison logic in Part 1

**Status:** Part 1 final. Part 2 (read-only document reading + repo scanning logic) not started.

---
