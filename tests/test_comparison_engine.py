"""Tests for Part 3 — comparison engine and rules.

All tests use synthetic RealityReport fixtures.
No real repositories, no network, no API keys.
"""

from __future__ import annotations

import pytest

from ml_intern.comparison_engine import (
    _next_fnd_id,
    _next_qst_id,
    apply_comparison_rules,
)
from ml_intern.comparison_rules import (
    EXPECTED_COMMAND_COUNT,
    _parse_cli_observation,
    rule_cli_surface_charter_alignment,
    rule_expected_repo_layout,
    rule_required_documents_baseline,
)
from ml_intern.report_schemas import (
    CompletenessStatus,
    DocumentReadResult,
    DocumentRole,
    EvidenceItem,
    EvidenceOrigin,
    ExecutiveSummary,
    Finding,
    FindingCategory,
    Observation,
    ObservationGranularity,
    ProjectPhase,
    QuestionRaised,
    RealityReport,
    ScanMode,
    SourceKind,
)


# ══════════════════════════════════════════════════════════════════
# Fixture Helpers
# ══════════════════════════════════════════════════════════════════


def _make_summary() -> ExecutiveSummary:
    return ExecutiveSummary(
        repos_covered=["lex_study_foundation", "ml-intern-for-lex"],
        documents_read=3,
        documents_found=3,
        observations_count=0,
        findings_by_category={},
        questions_raised_count=0,
        summary_text="Test summary.",
    )


def _make_docs(all_found: bool = True) -> list[DocumentReadResult]:
    return [
        DocumentReadResult(
            id="doc-001",
            target_path="docs/PROJECT_CHARTER.md",
            repo="ml-intern-for-lex",
            role=DocumentRole.SOURCE_OF_INTENT,
            found=True,
            summary="Charter with 11 sections.",
        ),
        DocumentReadResult(
            id="doc-002",
            target_path="docs/progress.md",
            repo="ml-intern-for-lex",
            role=DocumentRole.OPERATIONAL_HISTORY,
            found=True,
            summary="Progress log.",
        ),
        DocumentReadResult(
            id="doc-003",
            target_path="docs/progress.md",
            repo="lex_study_foundation",
            role=DocumentRole.OPERATIONAL_HISTORY,
            found=all_found,
            summary="Progress log." if all_found else None,
        ),
    ]


def _make_cli_obs(
    implemented: str = "doctor, info, paths, validate-config",
    stubs: str = "generate, validate, dedup, train, merge, eval, quantize, chat",
    impl_count: int = 4,
    stub_count: int = 8,
    total: int = 12,
) -> Observation:
    return Observation(
        id="obs-007",
        repo="lex_study_foundation",
        paths=["src/lex_study_foundation/cli.py"],
        source_kind=SourceKind.COMMAND_SURFACE,
        granularity=ObservationGranularity.INTERFACE_LEVEL,
        description=(
            f"CLI exposes {total} commands. "
            f"Implemented ({impl_count}): {implemented}. "
            f"Stubs ({stub_count}): {stubs}."
        ),
    )


def _make_file_obs() -> list[Observation]:
    return [
        Observation(
            id="obs-001",
            repo="lex_study_foundation",
            paths=[],
            source_kind=SourceKind.DIRECTORY_STRUCTURE,
            granularity=ObservationGranularity.DIRECTORY_LEVEL,
            description=(
                "Top-level directories: configs, data, docs, models, runs, "
                "src, tests, tools. Top-level files: .env.example, .gitignore, "
                "pyproject.toml, README.md."
            ),
        ),
        Observation(
            id="obs-003",
            repo="lex_study_foundation",
            paths=["pyproject.toml", "README.md", ".gitignore", ".env.example"],
            source_kind=SourceKind.FILE_PRESENCE,
            granularity=ObservationGranularity.FILE_LEVEL,
            description=(
                "Key files present: pyproject.toml, README.md, .gitignore, "
                ".env.example. Missing: (none)."
            ),
        ),
        Observation(
            id="obs-013",
            repo="ml-intern-for-lex",
            paths=["pyproject.toml", "README.md", ".gitignore", ".env.example"],
            source_kind=SourceKind.FILE_PRESENCE,
            granularity=ObservationGranularity.FILE_LEVEL,
            description=(
                "Key files present: pyproject.toml, README.md, .gitignore, "
                ".env.example. Missing: .pre-commit-config.yaml."
            ),
        ),
    ]


def _make_report(
    docs: list[DocumentReadResult] | None = None,
    observations: list[Observation] | None = None,
    findings: list[Finding] | None = None,
    questions: list[QuestionRaised] | None = None,
    phase: ProjectPhase = ProjectPhase.BETWEEN_2_5_AND_3,
) -> RealityReport:
    return RealityReport(
        report_id="rpt-20260424-120000",
        timestamp="2026-04-24T12:00:00Z",
        schema_version="1.0.0",
        target_repos=[],
        current_phase=phase,
        completeness=CompletenessStatus.COMPLETE,
        documents=docs or [],
        observations=observations or [],
        findings=findings or [],
        questions=questions or [],
        executive_summary=_make_summary(),
    )


def _make_existing_finding(fnd_id: str = "fnd-001") -> Finding:
    return Finding(
        id=fnd_id,
        category=FindingCategory.STRUCTURAL_INCONSISTENCY,
        description="Existing Part 2 finding.",
        evidence=[
            EvidenceItem(
                repo="ml-intern-for-lex",
                path="test.md",
                source_kind=SourceKind.FILE_PRESENCE,
            ),
        ],
        evidence_origin=EvidenceOrigin.REPO_BASED,
        referenced_observations=[],
        referenced_documents=["doc-003"],
    )


def _make_existing_question(qst_id: str = "qst-001") -> QuestionRaised:
    return QuestionRaised(
        id=qst_id,
        text="Existing Part 2 question.",
        triggered_by=["fnd-001"],
    )


# ══════════════════════════════════════════════════════════════════
# Test 1: Existing findings are preserved
# ══════════════════════════════════════════════════════════════════


class TestPreservation:
    def test_existing_findings_preserved(self):
        existing = _make_existing_finding("fnd-001")
        report = _make_report(
            docs=_make_docs(),
            observations=[_make_cli_obs()] + _make_file_obs(),
            findings=[existing],
        )
        enriched = apply_comparison_rules(report)
        assert enriched.findings[0].id == "fnd-001"
        assert enriched.findings[0].description == "Existing Part 2 finding."

    def test_existing_questions_preserved(self):
        existing_q = _make_existing_question("qst-001")
        report = _make_report(
            docs=_make_docs(),
            observations=[_make_cli_obs()] + _make_file_obs(),
            questions=[existing_q],
        )
        enriched = apply_comparison_rules(report)
        assert enriched.questions[0].id == "qst-001"
        assert enriched.questions[0].text == "Existing Part 2 question."


# ══════════════════════════════════════════════════════════════════
# Test 2: ID continuation
# ══════════════════════════════════════════════════════════════════


class TestIDContinuation:
    def test_finding_ids_continue(self):
        existing = _make_existing_finding("fnd-002")
        report = _make_report(
            docs=_make_docs(),
            observations=[_make_cli_obs()] + _make_file_obs(),
            findings=[existing],
        )
        enriched = apply_comparison_rules(report)
        new_ids = [f.id for f in enriched.findings if f.id != "fnd-002"]
        assert all(int(fid.split("-")[1]) >= 3 for fid in new_ids)

    def test_question_ids_continue(self):
        existing_q = _make_existing_question("qst-003")
        report = _make_report(
            docs=_make_docs(),
            observations=[_make_cli_obs()] + _make_file_obs(),
            questions=[existing_q],
        )
        enriched = apply_comparison_rules(report)
        new_ids = [q.id for q in enriched.questions if q.id != "qst-003"]
        for qid in new_ids:
            assert int(qid.split("-")[1]) >= 4

    def test_start_from_001_when_empty(self):
        report = _make_report(
            docs=_make_docs(),
            observations=[_make_cli_obs()] + _make_file_obs(),
        )
        enriched = apply_comparison_rules(report)
        assert enriched.findings[0].id == "fnd-001"

    def test_next_fnd_id_helper(self):
        assert _next_fnd_id([]) == 1
        f = _make_existing_finding("fnd-005")
        assert _next_fnd_id([f]) == 6

    def test_next_qst_id_helper(self):
        assert _next_qst_id([]) == 1
        q = _make_existing_question("qst-010")
        assert _next_qst_id([q]) == 11


# ══════════════════════════════════════════════════════════════════
# Test 3: Rule 1 — Required documents
# ══════════════════════════════════════════════════════════════════


class TestRule1Documents:
    def test_all_present_creates_aligned(self):
        report = _make_report(docs=_make_docs(all_found=True))
        result = rule_required_documents_baseline(report)
        assert len(result.findings) == 1
        assert result.findings[0].category == FindingCategory.ALIGNED

    def test_missing_creates_structural_inconsistency(self):
        report = _make_report(docs=_make_docs(all_found=False))
        result = rule_required_documents_baseline(report)
        assert len(result.findings) == 1
        assert result.findings[0].category == FindingCategory.STRUCTURAL_INCONSISTENCY

    def test_no_docs_emits_nothing(self):
        report = _make_report(docs=[])
        result = rule_required_documents_baseline(report)
        assert len(result.findings) == 0


# ══════════════════════════════════════════════════════════════════
# Test 4: Rule 2 — CLI alignment
# ══════════════════════════════════════════════════════════════════


class TestRule2CLIAlignment:
    def test_full_alignment_creates_one_finding(self):
        """12 commands, 4 impl, 8 stubs at between_2_5_and_3 → ONE aligned."""
        obs = _make_cli_obs()
        report = _make_report(
            docs=_make_docs(),
            observations=[obs],
        )
        result = rule_cli_surface_charter_alignment(report)
        assert len(result.findings) == 1
        assert result.findings[0].category == FindingCategory.ALIGNED
        # No duplicate finding — single aligned
        assert len(result.questions) == 0

    def test_all_implemented_creates_misalignment(self):
        """All commands implemented at between_2_5_and_3 → misalignment."""
        obs = _make_cli_obs(
            implemented=(
                "doctor, info, paths, validate-config, generate, validate, "
                "dedup, train, merge, eval, quantize, chat"
            ),
            stubs="(none)",
            impl_count=12,
            stub_count=0,
        )
        report = _make_report(
            docs=_make_docs(),
            observations=[obs],
        )
        result = rule_cli_surface_charter_alignment(report)
        assert len(result.findings) == 1
        assert result.findings[0].category == FindingCategory.MISALIGNMENT
        assert len(result.questions) == 1

    def test_count_mismatch_creates_structural_inconsistency(self):
        obs = _make_cli_obs(
            implemented="doctor, info",
            stubs="generate",
            impl_count=2,
            stub_count=1,
            total=3,
        )
        report = _make_report(observations=[obs])
        result = rule_cli_surface_charter_alignment(report)
        assert len(result.findings) == 1
        assert result.findings[0].category == FindingCategory.STRUCTURAL_INCONSISTENCY

    def test_no_cli_obs_emits_nothing(self):
        report = _make_report(observations=[])
        result = rule_cli_surface_charter_alignment(report)
        assert len(result.findings) == 0

    def test_unparseable_emits_nothing(self):
        obs = Observation(
            id="obs-007",
            repo="lex_study_foundation",
            paths=[],
            source_kind=SourceKind.COMMAND_SURFACE,
            granularity=ObservationGranularity.INTERFACE_LEVEL,
            description="Some unparseable text.",
        )
        report = _make_report(observations=[obs])
        result = rule_cli_surface_charter_alignment(report)
        assert len(result.findings) == 0


# ══════════════════════════════════════════════════════════════════
# Test 5: Future stubs are NOT incomplete_implementation
# ══════════════════════════════════════════════════════════════════


class TestStubsNotIncomplete:
    def test_phase3_stubs_not_incomplete(self):
        """Phase 3 stubs at between_2_5_and_3 → aligned, not incomplete."""
        obs = _make_cli_obs()
        report = _make_report(
            docs=_make_docs(),
            observations=[obs],
        )
        result = rule_cli_surface_charter_alignment(report)
        for f in result.findings:
            assert f.category != FindingCategory.INCOMPLETE_IMPLEMENTATION

    def test_future_stubs_aligned(self):
        enriched = apply_comparison_rules(
            _make_report(
                docs=_make_docs(),
                observations=[_make_cli_obs()] + _make_file_obs(),
            )
        )
        for f in enriched.findings:
            assert f.category != FindingCategory.INCOMPLETE_IMPLEMENTATION


# ══════════════════════════════════════════════════════════════════
# Test 6: Executive summary counts
# ══════════════════════════════════════════════════════════════════


class TestExecutiveSummary:
    def test_summary_counts_match(self):
        """After enrichment, summary must reflect actual counts."""
        report = _make_report(
            docs=_make_docs(),
            observations=[_make_cli_obs()] + _make_file_obs(),
        )
        # Use the full pipeline (which rebuilds summary in report_builder)
        from ml_intern.report_builder import _build_executive_summary

        enriched = apply_comparison_rules(report)
        summary = _build_executive_summary(
            ["lex_study_foundation", "ml-intern-for-lex"],
            enriched.documents,
            enriched.observations,
            enriched.findings,
            enriched.questions,
            CompletenessStatus.COMPLETE,
        )
        assert summary.findings_by_category.get("aligned", 0) == len(
            [f for f in enriched.findings if f.category == FindingCategory.ALIGNED]
        )
        assert summary.questions_raised_count == len(enriched.questions)
        assert summary.observations_count == len(enriched.observations)


# ══════════════════════════════════════════════════════════════════
# Test 7: No recommendation language
# ══════════════════════════════════════════════════════════════════

FORBIDDEN_FRAGMENTS = [
    "should fix", "recommended", "priority", "urgent",
    "best next step", "must implement next", "action item",
]


class TestNoRecommendationLanguage:
    def test_findings_have_no_recommendations(self):
        report = _make_report(
            docs=_make_docs(),
            observations=[_make_cli_obs()] + _make_file_obs(),
        )
        enriched = apply_comparison_rules(report)
        for f in enriched.findings:
            text = (f.description + " " + (f.detail or "")).lower()
            for forbidden in FORBIDDEN_FRAGMENTS:
                assert forbidden not in text, (
                    f"Finding {f.id} contains forbidden fragment: '{forbidden}'"
                )

    def test_questions_have_no_recommendations(self):
        # Force misalignment to get questions
        obs = _make_cli_obs(
            implemented=(
                "doctor, info, paths, validate-config, generate, validate, "
                "dedup, train, merge, eval, quantize, chat"
            ),
            stubs="(none)",
            impl_count=12,
            stub_count=0,
        )
        report = _make_report(
            docs=_make_docs(),
            observations=[obs] + _make_file_obs(),
        )
        enriched = apply_comparison_rules(report)
        for q in enriched.questions:
            text = q.text.lower()
            for forbidden in FORBIDDEN_FRAGMENTS:
                assert forbidden not in text, (
                    f"Question {q.id} contains forbidden fragment: '{forbidden}'"
                )


# ══════════════════════════════════════════════════════════════════
# Test 8: No duplicate findings
# ══════════════════════════════════════════════════════════════════


class TestDeduplication:
    def test_no_duplicate_if_part2_covers_same_obs(self):
        """If Part 2 already has a finding for obs-007, Part 3 should not duplicate."""
        existing = Finding(
            id="fnd-001",
            category=FindingCategory.ALIGNED,
            description="Part 2 CLI finding.",
            evidence=[
                EvidenceItem(
                    repo="lex_study_foundation",
                    path="src/lex_study_foundation/cli.py",
                    source_kind=SourceKind.COMMAND_SURFACE,
                ),
            ],
            evidence_origin=EvidenceOrigin.REPO_BASED,
            referenced_observations=["obs-007"],
            referenced_documents=[],
        )
        report = _make_report(
            docs=_make_docs(),
            observations=[_make_cli_obs()] + _make_file_obs(),
            findings=[existing],
        )
        enriched = apply_comparison_rules(report)
        # Rule 2 should NOT emit since obs-007/aligned is already covered
        aligned_cli = [
            f for f in enriched.findings
            if f.category == FindingCategory.ALIGNED
            and "obs-007" in f.referenced_observations
        ]
        assert len(aligned_cli) == 1  # Only the existing one


# ══════════════════════════════════════════════════════════════════
# Test 9: CLI observation parser
# ══════════════════════════════════════════════════════════════════


class TestCLIParser:
    def test_parses_normal_output(self):
        desc = (
            "CLI exposes 12 commands. Implemented (4): doctor, info, paths, "
            "validate-config. Stubs (8): generate, validate, dedup, train, "
            "merge, eval, quantize, chat."
        )
        parsed = _parse_cli_observation(desc)
        assert parsed is not None
        assert parsed["total"] == 12
        assert parsed["impl_count"] == 4
        assert parsed["stub_count"] == 8
        assert "doctor" in parsed["implemented"]
        assert "validate-config" in parsed["implemented"]
        assert "generate" in parsed["stubs"]

    def test_returns_none_for_garbage(self):
        assert _parse_cli_observation("random text") is None

    def test_expected_command_count(self):
        assert EXPECTED_COMMAND_COUNT == 12


# ══════════════════════════════════════════════════════════════════
# Test 10: Ambiguous evidence does not overproduce
# ══════════════════════════════════════════════════════════════════


class TestConservatism:
    def test_empty_report_produces_no_findings(self):
        report = _make_report()
        enriched = apply_comparison_rules(report)
        assert len(enriched.findings) == 0
        assert len(enriched.questions) == 0

    def test_partial_observations_produce_limited_findings(self):
        """Report with only docs but no observations → only doc finding."""
        report = _make_report(docs=_make_docs())
        enriched = apply_comparison_rules(report)
        categories = [f.category for f in enriched.findings]
        # Should have aligned for docs but no CLI/layout findings
        assert FindingCategory.ALIGNED in categories
        assert len(enriched.findings) == 1  # Only doc baseline
