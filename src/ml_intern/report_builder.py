"""Report assembly layer — orchestrates intake + scan, builds RealityReport.

This module is the single entry point for generating a reality report.
It coordinates the document intake layer and repo scanning layer, assigns
stable IDs, computes completeness, and assembles the final RealityReport.

This layer is strictly read-only and non-recommendatory. It produces
observations, limited findings, and neutral questions — never priorities,
actions, or fix suggestions.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ml_intern.comparison_engine import apply_comparison_rules
from ml_intern.document_intake import read_documents
from ml_intern.report_schemas import (
    CompletenessStatus,
    DocumentReadResult,
    EvidenceItem,
    EvidenceOrigin,
    ExecutiveSummary,
    Finding,
    FindingCategory,
    Observation,
    ProjectPhase,
    QuestionRaised,
    RealityReport,
    RepoIdentity,
    ScanMode,
    SourceKind,
)
from ml_intern.repo_scanner import read_git_remote_url, scan_repository
from ml_intern.security import redact_secrets


# ── ID Generators ────────────────────────────────────────────────


def _assign_doc_ids(docs: list[DocumentReadResult]) -> list[DocumentReadResult]:
    """Re-assign sequential doc-NNN IDs to document results."""
    result = []
    for i, doc in enumerate(docs, start=1):
        result.append(doc.model_copy(update={"id": f"doc-{i:03d}"}))
    return result


def _assign_obs_ids(observations: list[Observation]) -> list[Observation]:
    """Assign sequential obs-NNN IDs to observations."""
    result = []
    for i, obs in enumerate(observations, start=1):
        result.append(obs.model_copy(update={"id": f"obs-{i:03d}"}))
    return result


def _assign_fnd_ids(findings: list[Finding]) -> list[Finding]:
    """Assign sequential fnd-NNN IDs to findings."""
    result = []
    for i, fnd in enumerate(findings, start=1):
        result.append(fnd.model_copy(update={"id": f"fnd-{i:03d}"}))
    return result


def _assign_qst_ids(questions: list[QuestionRaised]) -> list[QuestionRaised]:
    """Assign sequential qst-NNN IDs to questions."""
    result = []
    for i, qst in enumerate(questions, start=1):
        result.append(qst.model_copy(update={"id": f"qst-{i:03d}"}))
    return result


# ── Findings Generator ──────────────────────────────────────────


def _generate_findings(
    documents: list[DocumentReadResult],
    observations: list[Observation],
) -> list[Finding]:
    """Generate limited, evidence-backed findings from documents and observations.

    Part 2 findings are restricted to:
    - clearly aligned states
    - clearly incomplete implementations
    - clearly missing structures

    No strategic recommendations, design judgments, or speculative interpretation.
    """
    findings: list[Finding] = []

    # ── Note: CLI command surface findings are NOT generated here. ──
    # CLI-vs-charter comparison logic belongs in Part 3's comparison
    # engine (comparison_rules.py + comparison_engine.py) where it can
    # be evaluated against charter expectations and phase context.
    # Part 2 only records the raw CLI observation in observations.

    # ── Finding: Missing mandatory documents ──
    missing_docs = [d for d in documents if not d.found]
    if missing_docs:
        for doc in missing_docs:
            findings.append(
                Finding(
                    id="fnd-000",  # Placeholder
                    category=FindingCategory.STRUCTURAL_INCONSISTENCY,
                    description=redact_secrets(
                        f"Expected document '{doc.target_path}' not found in {doc.repo}."
                    ),
                    evidence=[
                        EvidenceItem(
                            repo=doc.repo,
                            path=doc.target_path,
                            source_kind=SourceKind.FILE_PRESENCE,
                            notes="File does not exist at expected path.",
                        ),
                    ],
                    evidence_origin=EvidenceOrigin.REPO_BASED,
                    referenced_observations=[],
                    referenced_documents=[doc.id],
                )
            )

    return findings


# ── Questions Generator ─────────────────────────────────────────


def _generate_questions(
    documents: list[DocumentReadResult],
    observations: list[Observation],
    findings: list[Finding],
) -> list[QuestionRaised]:
    """Generate neutral, evidence-grounded questions for human review.

    Questions must be non-prescriptive and non-prioritized.
    They ask 'what?' — never 'you should'.
    Limited to 2-5 questions maximum.
    """
    questions: list[QuestionRaised] = []

    # ── Question: Missing documents ──
    missing_docs = [d for d in documents if not d.found]
    if missing_docs:
        missing_paths = ", ".join(f"{d.repo}:{d.target_path}" for d in missing_docs)
        questions.append(
            QuestionRaised(
                id="qst-000",  # Placeholder
                text=redact_secrets(
                    f"Documents not found: {missing_paths}. "
                    f"Are these documents expected to exist at this point, "
                    f"or is their absence intentional?"
                ),
                triggered_by=[d.id for d in missing_docs],
            )
        )

    # ── Note: CLI stub/phase questions are NOT generated here. ──
    # CLI-vs-charter question generation belongs in Part 3's comparison
    # engine where phase context is available.

    # Limit to 5 questions
    return questions[:5]


# ── Completeness Calculator ─────────────────────────────────────


def _compute_completeness(
    documents: list[DocumentReadResult],
    scan_errors: bool,
) -> CompletenessStatus:
    """Determine report completeness status.

    - complete: all 3 required documents found, no scan errors
    - partial: some documents missing OR scan errors present
    - failed: not used in normal operation (reserved for catastrophic failure)
    """
    all_found = all(d.found for d in documents)
    if all_found and not scan_errors:
        return CompletenessStatus.COMPLETE
    return CompletenessStatus.PARTIAL


# ── Executive Summary Builder ───────────────────────────────────


def _build_executive_summary(
    repo_names: list[str],
    documents: list[DocumentReadResult],
    observations: list[Observation],
    findings: list[Finding],
    questions: list[QuestionRaised],
    completeness: CompletenessStatus,
) -> ExecutiveSummary:
    """Build a compact, factual executive summary.

    Free of recommendations, priorities, and next-step language.
    """
    docs_found = sum(1 for d in documents if d.found)

    # Count findings by category
    category_counts: dict[str, int] = dict(Counter(f.category.value for f in findings))

    # Build summary text
    parts = [
        f"Report covers {len(repo_names)} repositories: {', '.join(repo_names)}.",
        f"{docs_found} of {len(documents)} required documents found.",
        f"{len(observations)} observations recorded across both repositories.",
    ]
    if findings:
        parts.append(f"{len(findings)} findings identified.")
    if questions:
        parts.append(f"{len(questions)} questions raised for review.")
    parts.append(f"Report completeness: {completeness.value}.")

    return ExecutiveSummary(
        repos_covered=repo_names,
        documents_read=len(documents),
        documents_found=docs_found,
        observations_count=len(observations),
        findings_by_category=category_counts,
        questions_raised_count=len(questions),
        summary_text=redact_secrets(" ".join(parts)),
    )


# ── Main Entry Point ────────────────────────────────────────────


def generate_report(
    ml_intern_root: Path,
    lex_root: Path,
    current_phase: ProjectPhase = ProjectPhase.BETWEEN_2_5_AND_3,
) -> RealityReport:
    """Generate a complete reality report by scanning both repositories.

    This is the primary entry point for Part 2. It orchestrates document
    intake, repository scanning, finding generation, and report assembly.

    This function is synchronous — filesystem I/O does not benefit from async.
    For use in async contexts (FastAPI), call via run_in_executor.

    Args:
        ml_intern_root: Absolute path to ml-intern-for-lex repo root.
        lex_root: Absolute path to lex_study_foundation repo root.
        current_phase: Current project phase (default: between_2_5_and_3).

    Returns:
        A complete, validated RealityReport object.
    """
    now = datetime.now(tz=timezone.utc)
    report_id = f"rpt-{now.strftime('%Y%m%d-%H%M%S')}"
    timestamp = now.isoformat()

    # ── Build repo identities ──
    # remote_url is read from .git/config if available.
    # If .git/config is missing, unreadable, or has no 'origin' remote,
    # remote_url is set to None. This is intentional — the URL is
    # informational metadata, not a requirement for report generation.
    ml_intern_remote = read_git_remote_url(ml_intern_root)
    lex_remote = read_git_remote_url(lex_root)

    target_repos = [
        RepoIdentity(
            name="lex_study_foundation",
            local_path=str(lex_root),
            # None if .git/config missing, parse error, or no origin remote
            remote_url=lex_remote,
        ),
        RepoIdentity(
            name="ml-intern-for-lex",
            local_path=str(ml_intern_root),
            # None if .git/config missing, parse error, or no origin remote
            remote_url=ml_intern_remote,
        ),
    ]

    repo_roots = {
        "ml-intern-for-lex": ml_intern_root,
        "lex_study_foundation": lex_root,
    }

    # ── Layer A: Document intake ──
    documents = read_documents(repo_roots)
    documents = _assign_doc_ids(documents)

    # ── Layer B: Repo scanning ──
    lex_observations = scan_repository("lex_study_foundation", lex_root)
    ml_observations = scan_repository("ml-intern-for-lex", ml_intern_root)
    all_observations = lex_observations + ml_observations
    all_observations = _assign_obs_ids(all_observations)

    # Check if any scan errors occurred
    scan_errors = any(
        obs.source_kind == SourceKind.ENVIRONMENT
        for obs in all_observations
    )

    # ── Layer C: Report assembly ──
    findings = _generate_findings(documents, all_observations)
    findings = _assign_fnd_ids(findings)

    questions = _generate_questions(documents, all_observations, findings)
    questions = _assign_qst_ids(questions)

    completeness = _compute_completeness(documents, scan_errors)

    repo_names = ["lex_study_foundation", "ml-intern-for-lex"]
    executive_summary = _build_executive_summary(
        repo_names, documents, all_observations, findings, questions, completeness,
    )

    base_report = RealityReport(
        report_id=report_id,
        timestamp=timestamp,
        schema_version="1.0.0",
        target_repos=target_repos,
        current_phase=current_phase,
        completeness=completeness,
        snapshot_id=None,
        scan_mode=ScanMode.FULL,
        compared_to_snapshot_id=None,
        documents=documents,
        observations=all_observations,
        findings=findings,
        questions=questions,
        executive_summary=executive_summary,
    )

    # ── Layer D: Part 3 — Deterministic comparison enrichment ──
    enriched_report = apply_comparison_rules(base_report)

    # ── Layer E: Rebuild executive summary with enriched data ──
    enriched_summary = _build_executive_summary(
        repo_names,
        enriched_report.documents,
        enriched_report.observations,
        enriched_report.findings,
        enriched_report.questions,
        completeness,
    )

    return enriched_report.model_copy(update={
        "executive_summary": enriched_summary,
    })
