"""Comparison engine — applies deterministic rules to enrich a RealityReport.

This module is the single entry point for Part 3. It consumes a Part 2
RealityReport, applies the rule set from comparison_rules.py, and returns
an enriched report with appended findings and questions.

Import direction (circular import prevention):
    comparison_rules → comparison_engine → report_builder
    This module does NOT import from report_builder.py.

Executive summary rebuild is NOT done here — that is report_builder.py's
responsibility after calling apply_comparison_rules().

No LLM calls. No external APIs. No repository mutation.
No recommendations. No priorities. No severity labels.
"""

from __future__ import annotations

import re

from ml_intern.comparison_rules import (
    rule_cli_surface_charter_alignment,
    rule_expected_repo_layout,
    rule_open_design_area,
    rule_required_documents_baseline,
    rule_started_but_incomplete,
)
from ml_intern.report_schemas import (
    Finding,
    QuestionRaised,
    RealityReport,
)


def _next_fnd_id(existing: list[Finding]) -> int:
    """Return the next available finding ID number.

    If existing has fnd-001, fnd-002, returns 3.
    If no existing findings, returns 1.
    """
    if not existing:
        return 1
    max_num = 0
    for f in existing:
        match = re.search(r"fnd-(\d{3})", f.id)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num + 1


def _next_qst_id(existing: list[QuestionRaised]) -> int:
    """Return the next available question ID number.

    If existing has qst-001, returns 2.
    If no existing questions, returns 1.
    """
    if not existing:
        return 1
    max_num = 0
    for q in existing:
        match = re.search(r"qst-(\d{3})", q.id)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num + 1


def _already_covered(
    existing: list[Finding],
    obs_id: str,
    category: str,
) -> bool:
    """Check if an existing finding already covers the same observation+category.

    Prevents duplicate findings between Part 2 and Part 3.
    """
    for f in existing:
        if (
            f.category.value == category
            and obs_id in f.referenced_observations
        ):
            return True
    return False


def apply_comparison_rules(report: RealityReport) -> RealityReport:
    """Apply all Part 3 comparison rules and return an enriched report.

    This function:
    - preserves all existing Part 2 findings and questions
    - applies deterministic rules
    - appends new findings and questions with continued IDs
    - does NOT rebuild executive_summary (report_builder.py does that)

    Args:
        report: A valid RealityReport from Part 2.

    Returns:
        Enriched RealityReport with Part 3 findings and questions appended.
    """
    existing_findings = list(report.findings)
    existing_questions = list(report.questions)

    new_findings: list[Finding] = []
    new_questions: list[QuestionRaised] = []

    # ── Apply Rule 1: Required document baseline ──
    r1 = rule_required_documents_baseline(report)
    new_findings.extend(r1.findings)
    new_questions.extend(r1.questions)

    # ── Apply Rule 2: CLI command surface vs charter ──
    r2 = rule_cli_surface_charter_alignment(report)
    # Deduplication check
    for f in r2.findings:
        covered = False
        for obs_id in f.referenced_observations:
            if _already_covered(existing_findings, obs_id, f.category.value):
                covered = True
                break
        if not covered:
            new_findings.append(f)
    new_questions.extend(r2.questions)

    # ── Apply Rule 3: Expected repo layout ──
    r3 = rule_expected_repo_layout(report)
    new_findings.extend(r3.findings)
    new_questions.extend(r3.questions)

    # ── Apply Rule 4: Started but incomplete (minimal) ──
    r4 = rule_started_but_incomplete(report)
    new_findings.extend(r4.findings)
    new_questions.extend(r4.questions)

    # ── Apply Rule 5: Open design area questions ──
    r5 = rule_open_design_area(report, new_findings)
    new_findings.extend(r5.findings)
    new_questions.extend(r5.questions)

    # ── Assign sequential IDs to new findings ──
    fnd_counter = _next_fnd_id(existing_findings)
    for finding in new_findings:
        old_id = finding.id
        new_id = f"fnd-{fnd_counter:03d}"

        # Update any question triggered_by references
        for q in new_questions:
            q.triggered_by = [
                new_id if t == old_id else t
                for t in q.triggered_by
            ]

        finding.id = new_id
        fnd_counter += 1

    # ── Assign sequential IDs to new questions ──
    qst_counter = _next_qst_id(existing_questions)
    for question in new_questions:
        question.id = f"qst-{qst_counter:03d}"
        qst_counter += 1

    # ── Combine existing + new ──
    all_findings = existing_findings + new_findings
    all_questions = existing_questions + new_questions

    # Return enriched report (without rebuilding executive_summary)
    return report.model_copy(update={
        "findings": all_findings,
        "questions": all_questions,
    })
