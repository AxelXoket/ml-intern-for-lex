"""Tests for Part 1 report schema models.

Validates that all enums and models instantiate correctly with example data.
"""

from __future__ import annotations

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
    RepoIdentity,
    ScanMode,
    SourceKind,
)


class TestEnums:
    """All StrEnum classes should have expected values."""

    def test_document_role_values(self):
        assert DocumentRole.SOURCE_OF_INTENT == "source_of_intent"
        assert DocumentRole.OPERATIONAL_HISTORY == "operational_history"
        assert len(DocumentRole) == 5

    def test_source_kind_has_command_surface(self):
        assert SourceKind.COMMAND_SURFACE == "command_surface"
        assert len(SourceKind) == 8

    def test_observation_granularity_has_interface_level(self):
        assert ObservationGranularity.INTERFACE_LEVEL == "interface_level"
        assert len(ObservationGranularity) == 6

    def test_finding_category_count(self):
        assert len(FindingCategory) == 7
        assert FindingCategory.ALIGNED == "aligned"

    def test_project_phase_values(self):
        assert ProjectPhase.BETWEEN_2_5_AND_3 == "between_2_5_and_3"
        assert len(ProjectPhase) == 10

    def test_scan_mode_values(self):
        assert ScanMode.FULL == "full"
        assert ScanMode.BASELINE == "baseline"
        assert len(ScanMode) == 4


class TestModels:
    """Core models should instantiate with valid data."""

    def test_repo_identity(self):
        repo = RepoIdentity(
            name="test-repo",
            local_path="/tmp/test",
            remote_url=None,
        )
        assert repo.name == "test-repo"
        assert repo.remote_url is None

    def test_evidence_item(self):
        item = EvidenceItem(
            repo="test-repo",
            path="src/main.py",
            source_kind=SourceKind.FILE_CONTENT,
            snippet="some code",
        )
        assert item.repo == "test-repo"

    def test_document_read_result_found(self):
        doc = DocumentReadResult(
            id="doc-001",
            target_path="docs/README.md",
            repo="test-repo",
            role=DocumentRole.OTHER,
            found=True,
            summary="A readme file.",
        )
        assert doc.found is True
        assert doc.id == "doc-001"

    def test_document_read_result_missing(self):
        doc = DocumentReadResult(
            id="doc-002",
            target_path="docs/MISSING.md",
            repo="test-repo",
            role=DocumentRole.OTHER,
            found=False,
        )
        assert doc.found is False
        assert doc.summary is None

    def test_observation(self):
        obs = Observation(
            id="obs-001",
            repo="test-repo",
            paths=["src/"],
            source_kind=SourceKind.DIRECTORY_STRUCTURE,
            granularity=ObservationGranularity.DIRECTORY_LEVEL,
            description="src/ directory exists with 5 files.",
        )
        assert obs.id == "obs-001"

    def test_finding_requires_evidence(self):
        fnd = Finding(
            id="fnd-001",
            category=FindingCategory.ALIGNED,
            description="Everything matches.",
            evidence=[
                EvidenceItem(
                    repo="test-repo",
                    source_kind=SourceKind.FILE_CONTENT,
                    snippet="match",
                ),
            ],
            evidence_origin=EvidenceOrigin.REPO_BASED,
        )
        assert len(fnd.evidence) == 1

    def test_finding_rejects_empty_evidence(self):
        import pytest

        with pytest.raises(Exception):
            Finding(
                id="fnd-002",
                category=FindingCategory.ALIGNED,
                description="No evidence.",
                evidence=[],
                evidence_origin=EvidenceOrigin.REPO_BASED,
            )

    def test_question_raised(self):
        qst = QuestionRaised(
            id="qst-001",
            text="Is this intended?",
            triggered_by=["fnd-001"],
        )
        assert qst.id == "qst-001"

    def test_executive_summary(self):
        summary = ExecutiveSummary(
            repos_covered=["repo-a"],
            documents_read=2,
            documents_found=1,
            observations_count=5,
            findings_by_category={"aligned": 1},
            questions_raised_count=0,
            summary_text="Report complete.",
        )
        assert summary.documents_found == 1

    def test_reality_report_minimal(self):
        report = RealityReport(
            report_id="rpt-20260424-120000",
            timestamp="2026-04-24T12:00:00+00:00",
            target_repos=[
                RepoIdentity(name="test", local_path="/tmp/test"),
            ],
            current_phase=ProjectPhase.BETWEEN_2_5_AND_3,
            completeness=CompletenessStatus.COMPLETE,
            executive_summary=ExecutiveSummary(
                repos_covered=["test"],
                documents_read=0,
                documents_found=0,
                observations_count=0,
                findings_by_category={},
                questions_raised_count=0,
                summary_text="Empty report.",
            ),
        )
        assert report.report_id == "rpt-20260424-120000"
        assert report.scan_mode == ScanMode.FULL
        assert report.snapshot_id is None

    def test_report_id_pattern(self):
        import pytest

        with pytest.raises(Exception):
            RealityReport(
                report_id="invalid-id",
                timestamp="2026-04-24T12:00:00+00:00",
                target_repos=[],
                current_phase=ProjectPhase.PHASE_1,
                completeness=CompletenessStatus.COMPLETE,
                executive_summary=ExecutiveSummary(
                    repos_covered=[],
                    documents_read=0,
                    documents_found=0,
                    observations_count=0,
                    findings_by_category={},
                    questions_raised_count=0,
                    summary_text="Bad ID.",
                ),
            )
