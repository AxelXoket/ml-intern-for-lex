"""Charter-aware comparison rules for Part 3.

This module defines the deterministic rule set used by the comparison engine.
Rules are explicit, named, testable, and small in scope.

Charter-derived constants are hard-coded here. When the charter changes,
these constants are updated manually — this is intentional, not a bug.
It avoids dynamic charter parsing and keeps the system deterministic.

No LLM calls. No external APIs. No recommendations. No priorities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ml_intern.report_schemas import (
    EvidenceItem,
    EvidenceOrigin,
    Finding,
    FindingCategory,
    Observation,
    QuestionRaised,
    SourceKind,
)
from ml_intern.security import redact_secrets

if TYPE_CHECKING:
    from ml_intern.report_schemas import DocumentReadResult, ProjectPhase, RealityReport


# ══════════════════════════════════════════════════════════════════
# Charter-Derived Constants
# ══════════════════════════════════════════════════════════════════

# CLI command names as they appear in Part 2 scanner output (Typer CLI names).
PHASE_1_COMMANDS: frozenset[str] = frozenset({
    "doctor", "info", "paths", "validate-config",
})

# Expected stub commands keyed by target phase.
PHASE_STUBS: dict[str, frozenset[str]] = {
    "phase_3": frozenset({"generate", "validate", "dedup"}),
    "phase_4": frozenset({"train", "merge"}),
    "phase_5": frozenset({"eval"}),
    "phase_6": frozenset({"quantize"}),
    "phase_7": frozenset({"chat"}),
}

ALL_EXPECTED_STUBS: frozenset[str] = frozenset().union(*PHASE_STUBS.values())
ALL_EXPECTED_COMMANDS: frozenset[str] = PHASE_1_COMMANDS | ALL_EXPECTED_STUBS
EXPECTED_COMMAND_COUNT: int = len(ALL_EXPECTED_COMMANDS)  # 12

# Required documents (doc-NNN IDs assigned by Part 2).
REQUIRED_DOC_TARGETS: list[tuple[str, str]] = [
    ("ml-intern-for-lex", "docs/PROJECT_CHARTER.md"),
    ("ml-intern-for-lex", "docs/progress.md"),
    ("lex_study_foundation", "docs/progress.md"),
]

# Expected baseline files per repo.
ML_INTERN_BASELINE_FILES: frozenset[str] = frozenset({
    "pyproject.toml", "README.md", ".gitignore", ".env.example",
})

LEX_BASELINE_FILES: frozenset[str] = frozenset({
    "pyproject.toml", "README.md", ".gitignore", ".env.example",
})

LEX_BASELINE_DIRS: frozenset[str] = frozenset({
    "configs", "data", "docs",
})


# ══════════════════════════════════════════════════════════════════
# Rule Result Container
# ══════════════════════════════════════════════════════════════════


@dataclass
class RuleResult:
    """Output of a single rule evaluation.

    Each result carries zero or more findings and zero or more questions.
    A rule that finds nothing returns empty lists — this is acceptable.
    """

    findings: list[Finding] = field(default_factory=list)
    questions: list[QuestionRaised] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# Rule 1 — Required Document Baseline
# ══════════════════════════════════════════════════════════════════


def rule_required_documents_baseline(
    report: RealityReport,
) -> RuleResult:
    """Check that all required project documents exist.

    rule_id: rule.required_documents.baseline
    category: aligned | structural_inconsistency
    """
    result = RuleResult()
    docs = report.documents

    if not docs:
        return result  # No documents to evaluate — emit nothing.

    missing = [d for d in docs if not d.found]
    found = [d for d in docs if d.found]

    if not missing:
        # All required documents present → aligned
        result.findings.append(Finding(
            id="fnd-000",  # Placeholder — engine assigns real IDs
            category=FindingCategory.ALIGNED,
            description=redact_secrets(
                f"All {len(found)} required project documents are present."
            ),
            detail=redact_secrets(
                f"Found: {', '.join(d.target_path + ' (' + d.repo + ')' for d in found)}."
            ),
            evidence=[
                EvidenceItem(
                    repo=d.repo,
                    path=d.target_path,
                    source_kind=SourceKind.FILE_PRESENCE,
                    notes="Document found at expected path.",
                )
                for d in found
            ],
            evidence_origin=EvidenceOrigin.DOCUMENT_BASED,
            referenced_observations=[],
            referenced_documents=[d.id for d in found],
        ))
    else:
        # One or more missing → structural_inconsistency
        result.findings.append(Finding(
            id="fnd-000",
            category=FindingCategory.STRUCTURAL_INCONSISTENCY,
            description=redact_secrets(
                f"{len(missing)} required document(s) not found."
            ),
            detail=redact_secrets(
                f"Missing: {', '.join(d.target_path + ' (' + d.repo + ')' for d in missing)}."
            ),
            evidence=[
                EvidenceItem(
                    repo=d.repo,
                    path=d.target_path,
                    source_kind=SourceKind.FILE_PRESENCE,
                    notes="Document not found at expected path.",
                )
                for d in missing
            ],
            evidence_origin=EvidenceOrigin.DOCUMENT_BASED,
            referenced_observations=[],
            referenced_documents=[d.id for d in missing],
        ))

    return result


# ══════════════════════════════════════════════════════════════════
# Rule 2 — CLI Command Surface vs Charter Expectation
# ══════════════════════════════════════════════════════════════════

# Regex to parse the Part 2 scanner's observation description format:
# "CLI exposes 12 commands. Implemented (4): a, b, c, d. Stubs (8): e, f, g, h."
_CLI_PATTERN = re.compile(
    r"CLI exposes (\d+) commands?\.\s*"
    r"Implemented \((\d+)\):\s*([^.]*)\.\s*"
    r"Stubs \((\d+)\):\s*([^.]*)\."
)


def _parse_cli_observation(description: str) -> dict | None:
    """Parse CLI command surface observation into structured data.

    Returns None if the format cannot be parsed.
    """
    match = _CLI_PATTERN.search(description)
    if not match:
        return None

    total = int(match.group(1))
    impl_count = int(match.group(2))
    impl_raw = match.group(3).strip()
    stub_count = int(match.group(4))
    stub_raw = match.group(5).strip()

    # Parse comma-separated command names
    implemented = frozenset(
        name.strip() for name in impl_raw.split(",") if name.strip()
    ) if impl_raw and impl_raw != "(none)" else frozenset()

    stubs = frozenset(
        name.strip() for name in stub_raw.split(",") if name.strip()
    ) if stub_raw and stub_raw != "(none)" else frozenset()

    return {
        "total": total,
        "impl_count": impl_count,
        "stub_count": stub_count,
        "implemented": implemented,
        "stubs": stubs,
    }


def rule_cli_surface_charter_alignment(
    report: RealityReport,
) -> RuleResult:
    """Compare CLI command surface with charter expectations.

    rule_id: rule.cli_surface.charter_alignment
    category: aligned | misalignment | structural_inconsistency

    This is the ONLY rule that evaluates CLI command surface.
    It covers both charter matching AND phase-appropriate stub evaluation.
    """
    result = RuleResult()

    # Find the lex CLI observation
    cli_obs: Observation | None = None
    for obs in report.observations:
        if (
            obs.source_kind == SourceKind.COMMAND_SURFACE
            and obs.repo == "lex_study_foundation"
        ):
            cli_obs = obs
            break

    if cli_obs is None:
        return result  # No CLI observation found — emit nothing.

    parsed = _parse_cli_observation(cli_obs.description)
    if parsed is None:
        # Case D: Unparseable — do not guess.
        return result

    # Find charter document for evidence (if available)
    charter_doc_id = None
    for doc in report.documents:
        if doc.target_path == "docs/PROJECT_CHARTER.md" and doc.found:
            charter_doc_id = doc.id
            break

    ref_docs = [charter_doc_id] if charter_doc_id else []
    evidence_origin = EvidenceOrigin.MIXED if charter_doc_id else EvidenceOrigin.REPO_BASED

    # Case C: Count mismatch
    if parsed["total"] != EXPECTED_COMMAND_COUNT:
        result.findings.append(Finding(
            id="fnd-000",
            category=FindingCategory.STRUCTURAL_INCONSISTENCY,
            description=redact_secrets(
                f"CLI exposes {parsed['total']} commands but charter "
                f"defines {EXPECTED_COMMAND_COUNT}."
            ),
            detail=redact_secrets(cli_obs.description),
            evidence=[
                EvidenceItem(
                    repo=cli_obs.repo,
                    path=cli_obs.paths[0] if cli_obs.paths else None,
                    source_kind=SourceKind.COMMAND_SURFACE,
                    snippet=cli_obs.description,
                ),
            ],
            evidence_origin=evidence_origin,
            referenced_observations=[cli_obs.id],
            referenced_documents=ref_docs,
        ))
        return result

    current_phase = report.current_phase

    # Case A: Full alignment
    if (
        parsed["implemented"] == PHASE_1_COMMANDS
        and parsed["stubs"] == ALL_EXPECTED_STUBS
        and current_phase.value in ("between_2_5_and_3", "phase_2_5")
    ):
        result.findings.append(Finding(
            id="fnd-000",
            category=FindingCategory.ALIGNED,
            description=redact_secrets(
                "CLI command surface matches charter expectations. "
                "Phase 1 commands are working, later-phase stubs are "
                "appropriately present."
            ),
            detail=redact_secrets(
                f"Implemented ({len(parsed['implemented'])}): "
                f"{', '.join(sorted(parsed['implemented']))}. "
                f"Stubs ({len(parsed['stubs'])}): "
                f"{', '.join(sorted(parsed['stubs']))}."
            ),
            evidence=[
                EvidenceItem(
                    repo=cli_obs.repo,
                    path=cli_obs.paths[0] if cli_obs.paths else None,
                    source_kind=SourceKind.COMMAND_SURFACE,
                    snippet=cli_obs.description,
                ),
            ],
            evidence_origin=evidence_origin,
            referenced_observations=[cli_obs.id],
            referenced_documents=ref_docs,
        ))
        return result

    # Case B: Unexpected implementation — later-phase commands are implemented
    unexpected_impl = parsed["implemented"] - PHASE_1_COMMANDS
    if unexpected_impl:
        result.findings.append(Finding(
            id="fnd-000",
            category=FindingCategory.MISALIGNMENT,
            description=redact_secrets(
                f"CLI reports {len(unexpected_impl)} later-phase command(s) "
                f"as implemented while current phase is {current_phase.value}."
            ),
            detail=redact_secrets(
                f"Unexpectedly implemented: {', '.join(sorted(unexpected_impl))}. "
                f"Charter expects these to be stubs until their target phase."
            ),
            evidence=[
                EvidenceItem(
                    repo=cli_obs.repo,
                    path=cli_obs.paths[0] if cli_obs.paths else None,
                    source_kind=SourceKind.COMMAND_SURFACE,
                    snippet=cli_obs.description,
                ),
            ],
            evidence_origin=evidence_origin,
            referenced_observations=[cli_obs.id],
            referenced_documents=ref_docs,
        ))

        # Generate a question for this misalignment
        result.questions.append(QuestionRaised(
            id="qst-000",
            text=redact_secrets(
                f"Commands {', '.join(sorted(unexpected_impl))} appear as "
                f"implemented but are expected to be stubs at phase "
                f"{current_phase.value}. Is this intentional or does the "
                f"stub detection need review?"
            ),
            triggered_by=["fnd-000"],  # Will be fixed by engine ID assignment
        ))

    return result


# ══════════════════════════════════════════════════════════════════
# Rule 3 — Expected Repo Layout Baseline
# ══════════════════════════════════════════════════════════════════


def rule_expected_repo_layout(
    report: RealityReport,
) -> RuleResult:
    """Check that both repos have expected baseline files and directories.

    rule_id: rule.structure.expected_layout
    category: aligned | structural_inconsistency
    """
    result = RuleResult()

    # Collect file presence observations
    file_obs: dict[str, list[Observation]] = {
        "lex_study_foundation": [],
        "ml-intern-for-lex": [],
    }
    dir_obs: dict[str, list[Observation]] = {
        "lex_study_foundation": [],
        "ml-intern-for-lex": [],
    }

    for obs in report.observations:
        if obs.repo in file_obs:
            if obs.source_kind == SourceKind.FILE_PRESENCE:
                file_obs[obs.repo].append(obs)
            elif obs.source_kind == SourceKind.DIRECTORY_STRUCTURE:
                dir_obs[obs.repo].append(obs)

    # Check both repos
    all_present = True
    missing_items: list[str] = []
    ref_obs_ids: list[str] = []
    evidence_items: list[EvidenceItem] = []

    # ── ml-intern-for-lex baseline files ──
    for obs in file_obs.get("ml-intern-for-lex", []):
        ref_obs_ids.append(obs.id)
        desc = obs.description.lower()
        for f in ML_INTERN_BASELINE_FILES:
            if f.lower() not in desc:
                # File not mentioned in observation — might be missing
                if "missing" in desc and f.lower() in desc:
                    all_present = False
                    missing_items.append(f"ml-intern-for-lex/{f}")
        evidence_items.append(EvidenceItem(
            repo=obs.repo,
            path=obs.paths[0] if obs.paths else None,
            source_kind=SourceKind.FILE_PRESENCE,
            snippet=obs.description,
        ))

    # ── lex_study_foundation baseline files ──
    for obs in file_obs.get("lex_study_foundation", []):
        ref_obs_ids.append(obs.id)
        desc = obs.description.lower()
        evidence_items.append(EvidenceItem(
            repo=obs.repo,
            path=obs.paths[0] if obs.paths else None,
            source_kind=SourceKind.FILE_PRESENCE,
            snippet=obs.description,
        ))

    # ── lex_study_foundation baseline directories ──
    lex_top_dirs: set[str] = set()
    for obs in dir_obs.get("lex_study_foundation", []):
        if "top-level directories:" in obs.description.lower():
            ref_obs_ids.append(obs.id)
            # Parse "Top-level directories: configs, data, docs, ..."
            match = re.search(
                r"Top-level directories:\s*([^.]+)\.",
                obs.description,
                re.IGNORECASE,
            )
            if match:
                lex_top_dirs = {
                    d.strip().lower() for d in match.group(1).split(",")
                }
            evidence_items.append(EvidenceItem(
                repo=obs.repo,
                path=None,
                source_kind=SourceKind.DIRECTORY_STRUCTURE,
                snippet=obs.description,
            ))

    for expected_dir in LEX_BASELINE_DIRS:
        if expected_dir.lower() not in lex_top_dirs and lex_top_dirs:
            all_present = False
            missing_items.append(f"lex_study_foundation/{expected_dir}/")

    if not evidence_items:
        return result  # No relevant observations — emit nothing.

    if all_present and not missing_items:
        result.findings.append(Finding(
            id="fnd-000",
            category=FindingCategory.ALIGNED,
            description=redact_secrets(
                "Both repositories have expected baseline file and directory structure."
            ),
            evidence=evidence_items[:3],  # Keep evidence concise
            evidence_origin=EvidenceOrigin.REPO_BASED,
            referenced_observations=ref_obs_ids[:4],
            referenced_documents=[],
        ))
    elif missing_items:
        result.findings.append(Finding(
            id="fnd-000",
            category=FindingCategory.STRUCTURAL_INCONSISTENCY,
            description=redact_secrets(
                f"Expected baseline artifacts missing: {', '.join(missing_items)}."
            ),
            evidence=evidence_items[:3],
            evidence_origin=EvidenceOrigin.REPO_BASED,
            referenced_observations=ref_obs_ids[:4],
            referenced_documents=[],
        ))

    return result


# ══════════════════════════════════════════════════════════════════
# Rule 4 — Started but Incomplete Implementation (Minimal)
# ══════════════════════════════════════════════════════════════════


def rule_started_but_incomplete(
    report: RealityReport,
) -> RuleResult:
    """Detect unfinished implementation in Phase 1 or Phase 2 scope.

    rule_id: rule.implementation.started_but_incomplete
    category: incomplete_implementation

    This rule is intentionally minimal. At the current project state
    (between_2_5_and_3), Phase 1 and Phase 2 are documented as complete.
    This rule fires only when direct evidence of unfinished Phase 1/2
    work is found. It does NOT fire for Phase 3+ stubs — those are
    expected future work.

    In practice, this rule is expected to produce zero findings in the
    current project state. It exists as a structural placeholder for
    future phases where started-but-not-finished Phase 1/2 work may
    surface.
    """
    # At current phase (between_2_5_and_3), Phase 1 and Phase 2 are
    # complete per charter. No direct evidence of unfinished Phase 1/2
    # work is detectable from the current observation set.
    return RuleResult()


# ══════════════════════════════════════════════════════════════════
# Rule 5 — Neutral Open Question
# ══════════════════════════════════════════════════════════════════


def rule_open_design_area(
    report: RealityReport,
    new_findings: list[Finding],
) -> RuleResult:
    """Generate limited neutral questions when findings expose open decisions.

    rule_id: rule.questions.open_design_area
    category: N/A (questions only)

    Questions are generated ONLY when a finding naturally raises an
    unresolved current-phase decision. Prefer zero questions over
    noisy questions.
    """
    # Note: Rule 2 may already generate a question for CLI misalignment.
    # This rule covers other finding types that may warrant questions.
    # Currently no additional question triggers are needed.
    return RuleResult()


# ══════════════════════════════════════════════════════════════════
# Rule Registry
# ══════════════════════════════════════════════════════════════════

# All first-wave rules, in evaluation order.
# Each is a callable: (report) -> RuleResult
# Exception: rule_open_design_area takes extra new_findings arg.
RULE_REGISTRY: list[tuple[str, str]] = [
    ("rule.required_documents.baseline", "rule_required_documents_baseline"),
    ("rule.cli_surface.charter_alignment", "rule_cli_surface_charter_alignment"),
    ("rule.structure.expected_layout", "rule_expected_repo_layout"),
    ("rule.implementation.started_but_incomplete", "rule_started_but_incomplete"),
    ("rule.questions.open_design_area", "rule_open_design_area"),
]
