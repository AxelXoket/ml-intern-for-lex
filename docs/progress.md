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

**Status:** Part 1 final. Part 2 complete.

---

## 2026-04-24 (Thursday) — 18:00 — Part 2: Reality Report Engine

### Part 2: Read-Only Inspect Engine ✅

Built the document intake + repository scanning + report assembly engine that fills the Part 1 schema.

**New files:**
- `report_schemas.py` — Part 1 output contract transcribed as importable Pydantic v2 code (8 enums, 8 models)
- `document_intake.py` — reads PROJECT_CHARTER.md and progress.md files, produces DocumentReadResult list with structured summaries
- `repo_scanner.py` — recursive read-only repository scanner with prune set, binary detection, symlink safety, CLI surface inspection
- `report_builder.py` — orchestrates intake + scan, assigns stable IDs, generates limited findings, neutral questions, executive summary

**Modified files:**
- `main.py` — added `GET /api/report` endpoint via `run_in_executor` (sync core, async wrapper)

**New tests (41 total, all passing):**
- `test_report_schemas.py` — enum values, model instantiation, ID pattern validation, evidence enforcement
- `test_document_intake.py` — found/missing docs, BOM handling, sequential IDs, missing repo roots
- `test_repo_scanner.py` — directory tree, prune behavior, text detection, git remote URL, sensitive file protection
- `test_report_builder.py` — smoke test, partial completeness, JSON serialization, sequential IDs

**Key design decisions:**
- Sync core functions, async wrapper for FastAPI — filesystem I/O doesn't benefit from async
- Flat module layout preserved (no subpackages)
- Hardcoded prune set (parameter-based, swappable for future Git-aware ignore)
- Extension-based text file allowlist — non-text files counted but never opened
- Errors become observations (SourceKind.ENVIRONMENT), never silently swallowed
- UTF-8 with `errors='replace'`, BOM skipping — matches runner.py pattern
- `.env` files observed for presence/size only, content never read
- `remote_url` from `.git/config` with explicit None fallback (documented in code comments)
- False-positive stub finding fixed: only emits when actual stubs exist

**Verification:**
- 41 tests passing (0.16s)
- Live report against real repos: 3/3 docs found, 18 observations, 0 false findings
- JSON serialization verified
- `GET /api/report` endpoint ready

**Strict boundaries maintained:**
- Read-only: no file writes, no git mutations, no caches
- Non-recommendatory: no severity, priority, or action fields
- Human-in-the-loop: questions are neutral, findings are evidence-backed

---

## 2026-04-24 (Thursday) — 23:00 - Part 3: Deterministic Comparison Engine

### Part 3: Charter-Aware Comparison Layer ✅

Built the first deterministic comparison engine that enriches Part 2's RealityReport with charter-derived findings.

**New files:**
- `comparison_rules.py` - charter-derived constants (CLI command table, baseline file sets), 5 rule functions, CLI observation parser, RuleResult container
- `comparison_engine.py` - single entry point `apply_comparison_rules()`, ID continuation, deduplication, redaction

**Modified files:**
- `report_builder.py` - integrated Part 3 at the end of `generate_report()` flow (Layer D: enrich, Layer E: rebuild summary)
- `repo_scanner.py` - fixed CLI scanner regex: `@app.command()` → `@app.command([^)]*)` to catch all Typer decorator variants; added `_stub()` helper detection

**Part 2 cleanup (before Part 3):**
- Removed CLI stub finding logic from `_generate_findings()` - now owned by Part 3 Rule 2
- Removed CLI stub question logic from `_generate_questions()` - now owned by Part 3 Rule 5

**New tests (26 Part 3 + 41 Part 2 = 67 total, all passing):**
- `test_comparison_engine.py` - preservation, ID continuation, all 5 rules, deduplication, recommendation language prohibition, conservatism, CLI parser

**Rules implemented (first wave):**
1. `rule.required_documents.baseline` - checks 3 required docs → aligned or structural_inconsistency
2. `rule.cli_surface.charter_alignment` - compares 12-command surface vs charter → aligned, misalignment, or structural_inconsistency
3. `rule.structure.expected_layout` - checks baseline files/dirs for both repos → aligned or structural_inconsistency
4. `rule.implementation.started_but_incomplete` - minimal/no-op at current phase (Phase 1/2 complete)
5. `rule.questions.open_design_area` - neutral question generation (currently defers to Rule 2's own question logic)

**Key design decisions:**
- Unidirectional imports: comparison_rules → comparison_engine → report_builder (no circular imports)
- Executive summary rebuild owned by report_builder.py, not comparison_engine.py
- Rule 4 intentionally minimal - Phase 1/2 documented as complete
- Rule 2 merged original Rule 2 (CLI alignment) and Rule 3 (phase-appropriate stubs) into single rule - one finding, not two
- Phase 3+ stubs treated as EXPECTED, never as incomplete_implementation
- CLI scanner now correctly detects all 12 commands (was 10 due to missed decorator variants)

**Live report output (real repos):**
- 3 findings: all aligned (documents present, CLI matches charter, repo layout correct)
- 0 questions (everything aligned - no open decisions)
- Executive summary: `{"aligned": 3}`, 18 observations, 3 documents

**Strict boundaries maintained:**
- No LLM calls, no external APIs, no repository mutation
- No recommendations, priorities, severity, or urgency language
- Deterministic predicates only — same input always produces same output
- Under-claiming: ambiguous evidence → no finding

---
