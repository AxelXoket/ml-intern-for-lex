"""Tests for report builder — the assembly layer.

Smoke test that the builder produces a valid RealityReport from
temporary repo structures. Does NOT depend on real repos.
"""

from __future__ import annotations

from pathlib import Path

from ml_intern.report_builder import generate_report
from ml_intern.report_schemas import (
    CompletenessStatus,
    ProjectPhase,
    ScanMode,
)


class TestGenerateReport:
    """Report builder should produce valid, complete reports."""

    def test_smoke_valid_repos(self, tmp_path: Path):
        """Builder should produce a valid RealityReport from temp repos."""
        # Create ml-intern structure
        ml_root = tmp_path / "ml-intern"
        ml_docs = ml_root / "docs"
        ml_docs.mkdir(parents=True)
        (ml_docs / "PROJECT_CHARTER.md").write_text(
            "# Charter\n\n## 1. Overview\n\nContent.\n"
        )
        (ml_docs / "progress.md").write_text(
            "# Progress\n\n## 2026-04-22 (Tue) — 02:30 — Init\n\nDone.\n"
        )
        (ml_root / "pyproject.toml").write_text(
            '[project]\nname = "ml-intern"\nversion = "0.1.0"\n'
        )

        # Create lex structure
        lex_root = tmp_path / "lex"
        lex_docs = lex_root / "docs"
        lex_docs.mkdir(parents=True)
        (lex_docs / "progress.md").write_text(
            "# Progress\n\n## 2026-04-15 (Mon) — 18:00 — Phase 1\n\nStarted.\n"
        )
        (lex_root / "pyproject.toml").write_text(
            '[project]\nname = "lex"\nversion = "0.1.0"\n'
        )

        report = generate_report(ml_root, lex_root)

        # Report envelope
        assert report.report_id.startswith("rpt-")
        assert report.schema_version == "1.0.0"
        assert report.current_phase == ProjectPhase.BETWEEN_2_5_AND_3
        assert report.scan_mode == ScanMode.FULL
        assert report.snapshot_id is None
        assert report.compared_to_snapshot_id is None

        # Documents
        assert len(report.documents) == 3
        assert all(d.found for d in report.documents)
        assert report.documents[0].id == "doc-001"
        assert report.documents[1].id == "doc-002"
        assert report.documents[2].id == "doc-003"

        # Observations
        assert len(report.observations) > 0
        assert all(o.id.startswith("obs-") for o in report.observations)

        # Executive summary
        assert report.executive_summary.documents_read == 3
        assert report.executive_summary.documents_found == 3
        assert len(report.executive_summary.summary_text) > 0

        # Completeness
        assert report.completeness == CompletenessStatus.COMPLETE

        # Target repos
        assert len(report.target_repos) == 2

    def test_missing_documents_partial(self, tmp_path: Path):
        """Report should be partial when documents are missing."""
        ml_root = tmp_path / "ml"
        ml_root.mkdir()
        lex_root = tmp_path / "lex"
        lex_root.mkdir()

        report = generate_report(ml_root, lex_root)

        assert report.completeness == CompletenessStatus.PARTIAL
        assert report.executive_summary.documents_found == 0

    def test_report_is_json_serializable(self, tmp_path: Path):
        """Report should serialize to JSON without errors."""
        import json

        ml_root = tmp_path / "ml"
        ml_root.mkdir()
        lex_root = tmp_path / "lex"
        lex_root.mkdir()

        report = generate_report(ml_root, lex_root)

        json_str = report.model_dump_json()
        parsed = json.loads(json_str)
        assert "report_id" in parsed
        assert "executive_summary" in parsed

    def test_observation_ids_are_sequential(self, tmp_path: Path):
        """All observation IDs should be sequential obs-001, obs-002, ..."""
        ml_root = tmp_path / "ml"
        ml_root.mkdir()
        lex_root = tmp_path / "lex"
        lex_root.mkdir()

        report = generate_report(ml_root, lex_root)

        for i, obs in enumerate(report.observations, start=1):
            assert obs.id == f"obs-{i:03d}"

    def test_custom_phase(self, tmp_path: Path):
        """Report should accept custom phase parameter."""
        ml_root = tmp_path / "ml"
        ml_root.mkdir()
        lex_root = tmp_path / "lex"
        lex_root.mkdir()

        report = generate_report(ml_root, lex_root, current_phase=ProjectPhase.PHASE_3)

        assert report.current_phase == ProjectPhase.PHASE_3
