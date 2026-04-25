# PROJECT CHARTER — Lex Study Foundation Ecosystem

> **Document Role:** This is the canonical project-defining document for the `lex_study_foundation` + `ml-intern-for-lex` ecosystem. It defines the mission, current phase, priorities, constraints, and operating model. The research console (`ml-intern-for-lex`) uses this document as its primary source of project intent. Repo reality should be compared against this document to surface misalignments, gaps, and missing decisions.

> **Location:** `ml-intern-for-lex/docs/PROJECT_CHARTER.md`
> **Companion:** `ml-intern-for-lex/docs/progress.md` (operational history log)

---

## 1. Ecosystem Overview

This project ecosystem consists of two repositories:

| Repository | Role | GitHub |
|------------|------|--------|
| `lex_study_foundation` | **Main project.** The real work lives here. | [AxelXoket/lex-study-foundation](https://github.com/AxelXoket/lex-study-foundation) |
| `ml-intern-for-lex` | **Companion.** A repo-aware research and observation console around the main project. | [AxelXoket/ml-intern-for-lex](https://github.com/AxelXoket/ml-intern-for-lex) |

**Hierarchy is strict:**
- `lex_study_foundation` is the center. All core work — data generation, training, evaluation, deployment — belongs there.
- `ml-intern-for-lex` is a supporting layer. It inspects, observes, compares, and researches. It does not own the core pipeline.

### Naming Disambiguation

`ml-intern-for-lex` is **not** the same as Hugging Face's `ml-intern` (an agentic LLM post-training tool built on `smolagents`). The name is inspired by the broader concept of an ML research assistant, but this project is a purpose-built, human-supervised research console specific to this ecosystem. It does not use `smolagents`, does not run autonomous training loops, and does not auto-apply changes.

---

## 2. Main Project: lex_study_foundation

### What It Is

A Turkish educational LLM fine-tuning system. The goal is to take a capable base model and specialize it for Turkish educational content, with planned focus on law-study assistance.

### Core Pipeline

```
Data Design → Data Generation → Training → Evaluation → Quantization → Local Deployment
```

### Technical Stack

| Component | Choice | Status |
|-----------|--------|--------|
| Base model | Google Gemma 4 E4B-it (~4B effective / 8B total, 128K context) | Locked |
| Data generation provider | Gemini 2.5 Flash (API-driven synthetic data) | Current direction (see Section 4 for provider separation) |
| Training method | LoRA / QLoRA fine-tuning | Locked |
| Runtime | Python 3.12.10 | Locked (migrated in Phase 2.5) |
| Package manager | uv | Locked |
| CLI framework | Typer + Rich | Locked |
| Config system | Pydantic v2 + pydantic-settings + YAML | Locked |
| Hardware target | RTX 5080 (16 GB VRAM), Ryzen 9800X3D, 64 GB DDR5, Windows 11 | Locked |

> **Note:** The research provider (Claude / Anthropic) belongs to `ml-intern-for-lex`, not to this repo. See Section 4 for details. Provider choices between the two repos are independent decisions and must not be conflated.

### Project Structure

```
lex_study_foundation/
├── src/lex_study_foundation/     # Python package
│   ├── cli.py                    # 4 working commands + 8 stubs
│   ├── config/                   # Settings + YAML schemas
│   ├── data/                     # Data schemas (Tier, Message, TrainingExample)
│   ├── evaluation/               # Phase 5 (stub)
│   ├── inference/                # Phase 7 (stub)
│   ├── training/                 # Phase 4 (stub)
│   └── utils/                    # text.py, io.py, console.py, paths.py, gpu.py
├── configs/                      # YAML config files (generation, training)
├── data/                         # Pipeline stages: seeds → raw → processed → training
├── runs/                         # Training run outputs
├── models/                       # Exported models
├── docs/                         # architecture.md, progress.md
├── tests/                        # 54 passing tests
└── tools/                        # BAT convenience wrappers
```

### CLI Commands

| Command | Status | Phase |
|---------|--------|-------|
| `doctor` | ✅ Working | 1 |
| `info` | ✅ Working | 1 |
| `paths` | ✅ Working | 1 |
| `validate-config` | ✅ Working | 1 |
| `generate` | 🔲 Stub | 3 |
| `validate` | 🔲 Stub | 3 |
| `dedup` | 🔲 Stub | 3 |
| `train` | 🔲 Stub | 4 |
| `merge` | 🔲 Stub | 4 |
| `eval` | 🔲 Stub | 5 |
| `quantize` | 🔲 Stub | 6 |
| `chat` | 🔲 Stub | 7 |

---

## 3. Target Model and Behavior

### Target Audience

University-level law students (1st–4th year) studying in Turkey.

### Desired Answer Behavior

The behavioral specification was locked in Phase 2a. The fine-tuned model should exhibit:

- **Teacher-like tone** — formal but natural, not robotic
- **Clear Turkish expression** — strong, precise, idiomatic Turkish
- **Default brevity** — short to medium answers unless depth is requested
- **No unnecessary verbosity** — useful, not theatrical
- **No fake confidence** — honest uncertainty when appropriate
- **Teaching flexibility** — adapts explanation depth to the question
- **Empathy boundaries** — supportive but not sycophantic
- **Precision profile** — legally accurate within educational scope, not professional legal advice

### What Is Locked vs Research-Dependent

| Aspect | Status |
|--------|--------|
| Target audience | ✅ Locked |
| Behavioral personality | ✅ Locked (Phase 2a spec) |
| Answer style principles | ✅ Locked |
| Base model (Gemma 4 E4B-it) | ✅ Locked |
| Data generation provider (Gemini 2.5 Flash) | 🔒 Current direction |
| Dataset format details | 🔬 Open — requires research |
| Metadata field set | 🔬 Open — requires research |
| Task family coverage | 🔬 Open — requires research |
| Dataset size strategy | 🔬 Open — requires research |
| Source corpus policy | 🔬 Open — requires research |
| Legal domain training precedents | 🔬 Open — requires research |

---

## 4. Companion: ml-intern-for-lex

### Why It Exists

`ml-intern-for-lex` exists because working on a multi-phase LLM project requires more than just writing code. It requires:

- **Visibility** — the ability to see the current state of the project clearly, without manually grepping through files and configs
- **Project-awareness** — a layer that understands what phase we are in, what decisions are locked, what is still open, and what the next meaningful step is
- **Research discipline** — a structured way to research external questions (dataset formats, legal corpora, model behavior) grounded in local project context, not generic advice
- **Context-grounded analysis** — comparison of what the repo actually contains against what we intend it to become, surfacing real gaps instead of imagined ones
- **Decision support** — presenting findings, options, and trade-offs to the human clearly, without substituting human judgment

It is not "just a dashboard" and not "just a research tool." It is a repo-aware supporting layer that helps the human understand the project more clearly and research more intelligently. The dashboard is one interface; the research console is the evolving capability; the charter and project documents are the context backbone.

### What It Is

A repo-aware, human-supervised research and observation console built around `lex_study_foundation`. It provides:

- A web dashboard (FastAPI + vanilla HTML/CSS/JS) for running and observing lex CLI commands
- A secure subprocess layer with env allowlisting and secret redaction
- A foundation for repo-aware research capabilities

### What It Is Not

- **Not the main project.** Core data generation, training, evaluation belong in `lex_study_foundation`.
- **Not an autonomous agent.** It does not make decisions, auto-apply changes, or run unsupervised loops.
- **Not the Hugging Face ml-intern.** Different tool, different purpose, different architecture.
- **Not a black box.** All findings, recommendations, and actions must be visible and reviewable.

### Research Provider

The current research-provider direction for `ml-intern-for-lex` is **Claude (Anthropic)**.

This is a separate decision from the main project's data-generation provider (Gemini 2.5 Flash). The two provider choices are independent:

| Scope | Provider | Purpose | Belongs To |
|-------|----------|---------|------------|
| Research & analysis | Claude (Anthropic) | Powers the research console's analysis and research capabilities | `ml-intern-for-lex` |
| Synthetic data generation | Gemini 2.5 Flash | Generates training data for the fine-tuning pipeline | `lex_study_foundation` |

These providers serve different roles and must not be conflated. A change in one does not imply a change in the other. Each repo manages its own provider credentials independently.

### Current Capabilities (V1)

- Dashboard UI with cyberpunk dark theme
- 4 CLI commands executable through the browser (doctor, info, paths, validate-config)
- Real-time SSE output streaming
- Job lifecycle management (create, cancel, history)
- Config file viewing with path traversal protection
- Subprocess env allowlist — only OS runtime vars forwarded
- Secret deny list — provider keys never forwarded, RuntimeError if detected
- Secret redaction on all output, errors, and session summaries
- Health state reporting (healthy / degraded / unavailable)
- Research mode infrastructure (feature flag, config, status badge — no provider features yet)

### Intended Evolution

The companion is intended to evolve into a **research console** that can:

- Inspect the local repository in depth (structure, files, state, gaps)
- Read and understand this charter and other project-defining documents
- Compare repo reality against project intent
- Identify misalignments, missing decisions, incomplete implementations, and research gaps
- Perform focused external research when explicitly directed
- Present findings in a visible, reviewable, discussion-friendly format
- Support human decisions — never replace them

### Technical Stack

| Component | Choice |
|-----------|--------|
| Backend | FastAPI + Uvicorn |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| CLI | Typer (`ml-intern serve`) |
| Streaming | Server-Sent Events (SSE) |
| Config | Pydantic v2 + pydantic-settings |
| Packaging | Hatchling, src/ layout, uv |
| Runtime | Python 3.12.10 |
| Research provider | Claude (Anthropic) — current direction |

### Security Boundary

This boundary is a hard design constraint:

- `ml-intern-for-lex` secrets (`ANTHROPIC_API_KEY`, `HF_TOKEN`, `GITHUB_TOKEN`) → belong to ml-intern only
- `lex_study_foundation` secrets (`GEMINI_API_KEY`) → belong to lex only
- Each repo loads its own secrets from its own `.env` file
- Subprocess environment is built from an explicit allowlist — `os.environ` is never copied
- A deny list of provider keys raises `RuntimeError` if any appear in subprocess env
- ml-intern operates in read/observe mode toward lex — no file modification, no config rewriting

---

## 5. Phase Status

### Completed

| Phase | Description | Date |
|-------|-------------|------|
| Phase 1 | Project skeleton — CLI, config, tooling, 12 tests | 2026-04-15 |
| Phase 2a | Behavioral specification — locked | 2026-04-19 |
| Phase 2b | Utility foundation — text normalization, JSONL I/O, 54 tests | 2026-04-19 |
| Phase 2.5 | ml-intern companion dashboard, runtime stabilization, Python 3.12.10 migration | 2026-04-22 |

### Phase 2.5 Details

Phase 2.5 covered:

- Building the initial `ml-intern-for-lex` companion dashboard from scratch
- Establishing the security boundary (subprocess allowlist, secret redaction, deny list)
- Migrating both repositories from Python 3.14 to Python 3.12.10 for stability
- Setting up `uv` as the package manager for both repos
- Verifying CLI interoperability (ml-intern subprocess → lex CLI)
- Git initialization, GitHub remote setup, initial commits for both repos
- `setup_env.bat` update to use `py -3.12` explicitly

### Current Position

**We are between Phase 2.5 and Phase 3.**

Phase 3 is the data generation core. Before implementation can begin, several research questions must be answered and design decisions must be made. This is the current priority.

### Future Phases (Not Current Focus)

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 3 | Data generation pipeline | 🔲 Next — requires research first |
| Phase 4 | LoRA/QLoRA fine-tuning | 🔲 Planned |
| Phase 5 | Evaluation benchmarks | 🔲 Planned |
| Phase 6 | GGUF quantization export | 🔲 Planned |
| Phase 7 | Local chat interface | 🔲 Planned |

---

## 6. Phase 3: Data Generation Core

Phase 3 is the next major work phase. It is specifically about building the synthetic data generation pipeline.

### What Must Be Decided Before Implementation

The following questions require focused research and explicit human decisions before Phase 3 code is written:

**Dataset Format:**
- What is the best dataset format for Gemma 4 E4B-it fine-tuning?
- How should instruction-following behavior be structured in training examples?
- What metadata fields are useful vs unnecessary?
- What is the right balance between structure and simplicity?

**Source Corpus:**
- What source materials should be used as the basis for synthetic data generation?
- What Turkish legal sources are available, safe, and useful?
- What existing legal datasets (if any) are relevant?
- What should count as source material vs training data?
- How should PDFs and academic texts be handled (if at all)?

**Task Design:**
- What task families should exist in the dataset? (e.g., concept explanation, comparison, case analysis, exam preparation, definition, scenario-based reasoning)
- What answer behaviors do we want the final model to learn?
- How do task types map to the tier system (short / medium / long / list)?

**Scale and Strategy:**
- What is a reasonable size for the first inspectable dataset?
- What is the iteration strategy — small seed → evaluate → expand?
- What quality gates should be applied before training?

**Legal Domain Precedents:**
- What prior work exists for legal-domain LLM fine-tuning?
- What Turkish-language fine-tuning approaches have been tried?
- What lessons can be drawn from existing legal LLM projects?

### How These Questions Will Be Answered

These questions will be answered through the research console's inspect-discuss-research-decide loop (see Section 7). Research findings will be presented for human review. No dataset design decision will be auto-applied.

---

## 7. Human-in-the-Loop Operating Model

This is the most important section of this charter.

### Core Principle

This ecosystem is **not** building a fully autonomous agent. The human is the decision-maker. The system is a decision-support tool.

### Operating Loop

```
inspect → discuss → refine → research → compare → decide → act
```

| Stage | System Role | Human Role |
|-------|------------|------------|
| Inspect | Read repo, parse structure, understand state | Direct what to inspect |
| Discuss | Present findings, surface gaps | Evaluate, question, redirect |
| Refine | Narrow focus based on feedback | Set priorities |
| Research | Perform focused external research | Approve research scope |
| Compare | Compare findings against repo/plan | Judge relevance |
| Decide | Recommend options with reasoning | Make the decision |
| Act | Implement approved changes only | Approve before execution |

### Rules

**The system MAY:**
- Inspect, read, and analyze any part of the repository
- Read and interpret this charter and other project documents
- Identify gaps, contradictions, and misalignments
- Summarize and compare findings
- Perform external research when directed
- Recommend actions with reasoning
- Ask clarifying questions

**The system MUST NOT:**
- Silently mutate files or repo state
- Treat recommendations as approved actions
- Auto-fix issues without explicit approval
- Make important decisions autonomously
- Assume a suggestion equals permission to implement
- Bypass the human review step under any circumstance
- Run autonomous loops without human checkpoints

**The principle:** suggest is not approve. Recommend is not execute.

---

## 8. Repo-to-Intent Comparison Model

### How the Research Console Adds Value

The research console's primary value is comparing two things:

1. **Repo reality** — what the files, structure, configs, tests, and artifacts actually contain
2. **Project intent** — what this charter says the project is trying to achieve

### What Comparison Should Surface

When reality diverges from intent, the console should classify findings as:

| Category | Meaning |
|----------|---------|
| **Misalignment** | Repo state contradicts a locked decision |
| **Missing decision** | A decision is needed but hasn't been made yet |
| **Incomplete implementation** | Work has started but isn't finished |
| **Phase drift** | Work is happening in the wrong phase order |
| **Research gap** | A question needs research before proceeding |
| **Structural inconsistency** | File organization or naming doesn't match conventions |

### Why Context-First Matters

External research is only useful when grounded in local context. Without understanding the repo first, research produces generic advice that may contradict existing decisions, duplicate completed work, or misunderstand actual constraints.

**Correct order:**
1. Understand the repo — structure, files, current state, what exists
2. Understand this charter — what we intend to build, current phase, priorities
3. Identify the actual gap — what is specifically unclear or missing
4. Research — with a focused question shaped by local context

Research without context is noise. Context-first research is signal.

---

## 9. Decision Classification

### Locked Decisions

These are established and should not be reopened without a real blocker:

- `lex_study_foundation` is the main repository
- `ml-intern-for-lex` is a companion/research console, not the main project
- Human-in-the-loop is mandatory — no silent mutation, no autonomous decisions
- Phase 1 (skeleton) is complete
- Phase 2 (behavioral spec + utilities) is complete
- Phase 2.5 (companion dashboard + runtime stabilization) is complete
- Phase 3 = data generation core
- Target model = Gemma 4 E4B-it
- Training method = LoRA / QLoRA
- Target audience = Turkish law students (1st–4th year)
- Behavioral personality = locked (Phase 2a spec)
- Runtime = Python 3.12.10 for both repos
- Package management = uv for both repos
- Two separate repos, two separate venvs, two separate `.env` files
- Security boundary between repos is mandatory
- Tier system: short (180 tokens), medium (400), long (650), list (450)
- JSONL rules: UTF-8, no BOM, `ensure_ascii=False`, trailing newline, strict-by-default
- Text normalization: NFC Unicode, Turkish-safe (no case-folding)

### Current Provider Directions

Provider choices are established as current direction but are independent decisions that may evolve:

- **Data generation** (lex_study_foundation): Gemini 2.5 Flash — current direction for the Phase 3 synthetic data pipeline
- **Research & analysis** (ml-intern-for-lex): Claude / Anthropic — current direction for the research console's analysis capabilities

These are separate decisions. A change in one does not require or imply a change in the other.

### Current Working Assumptions

These are the current direction but may be refined:

- The companion dashboard (FastAPI + SSE) will be extended with research console capabilities, not replaced
- `PROJECT_CHARTER.md` is the primary source-of-intent document
- The first dataset should be small and inspectable before scaling
- Data generation will use Gemini API calls with structured prompting

### Open Research Questions

These require focused research before they can be locked:

- What dataset format works best for Gemma 4 E4B-it instruction tuning?
- What metadata fields are genuinely useful for training data quality?
- What Turkish legal sources and corpora are available and safe to use?
- What existing legal-domain fine-tuning work is relevant?
- What task families should be represented in the training data?
- What is a reasonable scale for the first inspectable dataset?
- How should source material (PDFs, textbooks, legal codes) be handled?
- What quality gates should be applied to synthetic data before training?
- What evaluation benchmarks exist for Turkish legal/educational models?

---

## 10. Research Discipline

### How Research Should Be Performed

Research in this ecosystem follows strict rules:

1. **Context first.** Understand the repo and this charter before researching externally.
2. **Focused questions.** Research should answer specific, locally-grounded questions — not produce generic surveys.
3. **Transparent findings.** All research results must be presented in a visible, reviewable form.
4. **No silent application.** Research findings are inputs to human decisions, not automatic actions.
5. **Incremental depth.** Start narrow, go deeper only when directed. Do not dump exhaustive surveys without being asked.

### What Good Research Looks Like

- "The Gemma 4 E4B-it model expects chat-template formatted data in this specific structure: [details]. Here's how that maps to our current tier system: [comparison]."
- "Three Turkish legal corpora exist publicly: [list]. Here's a relevance assessment against our target audience: [analysis]."

### What Bad Research Looks Like

- Generic "best practices for LLM fine-tuning" dumps with no local context
- Long surveys that don't connect to any open question in this charter
- Recommendations that ignore existing locked decisions

---

## 11. Boundaries and Constraints

These apply at all times, regardless of phase.

### Operational Boundaries

These govern how work is performed and how decisions flow:

- **All repo-affecting actions require explicit human approval.** This includes code changes, file edits, commits, pushes, and any modification to repo state. No exceptions.
- **No autonomous decision-making.** The system recommends; the human decides.
- **No silent mutation.** Files, configs, and repo state must not be changed without visibility and consent.
- **No unsupervised loops.** All research, analysis, and action cycles must include human checkpoints.
- **Phase discipline.** No Phase 4+ work until Phase 3 is meaningfully complete. Do not drift into later-phase topics unless explicitly directed.
- **Progress documentation.** Both repos maintain `docs/progress.md` as an operational history log. Entries are written in English.
- **Commit message format.** `Type : Description` — capital letter start, space before and after colon. Example: `Chore : Update setup_env.bat to use Python 3.12 explicitly`

### Engineering Constraints

These govern the technical implementation and must be respected in all code and configuration:

**Repo & Environment Separation:**
- Two repos remain separate — no monorepo merge unless explicitly decided
- Each repo has its own venv, `.env`, dependency set, and git history
- Provider secrets never cross repo boundaries
- Each repo loads its own secrets from its own `.env` file — no cross-loading

**Subprocess Security:**
- Subprocess environment is always built from an explicit allowlist, never `os.environ.copy()`
- A deny list of provider keys raises `RuntimeError` if detected in subprocess env
- No `shell=True` in subprocess calls
- No arbitrary user input reaches subprocess without sanitization

**Data & Text Integrity:**
- All existing tests must continue to pass
- Turkish text handling must remain safe — NFC Unicode normalization, no case-folding
- JSONL rules are non-negotiable: UTF-8, no BOM, `ensure_ascii=False`, `allow_nan=False`, trailing newline, strict-by-default
- Config validation schemas must be kept in sync with actual config files

**Provider Isolation:**
- `ANTHROPIC_API_KEY`, `HF_TOKEN`, `GITHUB_TOKEN` → belong to `ml-intern-for-lex` only
- `GEMINI_API_KEY` → belongs to `lex_study_foundation` only
- Provider credentials are never forwarded across repo boundaries via subprocess or any other mechanism

---

*This document was last reviewed: 2026-04-24*
*Phase status at time of writing: Between Phase 2.5 and Phase 3*
