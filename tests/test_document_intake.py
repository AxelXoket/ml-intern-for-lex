"""Tests for document intake layer.

Tests document reading with real and missing paths using tmp_path fixture.
Does NOT depend on the real lex repo being present.
"""

from __future__ import annotations

from pathlib import Path

from ml_intern.document_intake import read_documents
from ml_intern.report_schemas import DocumentRole


class TestReadDocuments:
    """Document intake should handle found and missing documents cleanly."""

    def test_all_documents_found(self, tmp_path: Path):
        """When all documents exist, all should be found=True with summaries."""
        # Create ml-intern repo structure
        ml_root = tmp_path / "ml-intern"
        ml_docs = ml_root / "docs"
        ml_docs.mkdir(parents=True)

        charter = ml_docs / "PROJECT_CHARTER.md"
        charter.write_text(
            "# Charter\n\n## 1. Overview\n\nContent here.\n\n## 2. Model\n\nMore content.\n",
            encoding="utf-8",
        )

        ml_progress = ml_docs / "progress.md"
        ml_progress.write_text(
            "# Progress\n\n## 2026-04-22 (Tuesday) — 02:30 — Initial\n\nDone.\n",
            encoding="utf-8",
        )

        # Create lex repo structure
        lex_root = tmp_path / "lex"
        lex_docs = lex_root / "docs"
        lex_docs.mkdir(parents=True)

        lex_progress = lex_docs / "progress.md"
        lex_progress.write_text(
            "# Progress\n\n## 2026-04-15 (Monday) — 18:00 — Phase 1\n\nStarted.\n"
            "## 2026-04-22 (Tuesday) — 20:00 — Phase 2.5\n\nMigrated.\n",
            encoding="utf-8",
        )

        repo_roots = {
            "ml-intern-for-lex": ml_root,
            "lex_study_foundation": lex_root,
        }

        results = read_documents(repo_roots)

        assert len(results) == 3
        assert all(r.found for r in results)
        assert results[0].role == DocumentRole.SOURCE_OF_INTENT
        assert results[1].role == DocumentRole.OPERATIONAL_HISTORY
        assert results[2].role == DocumentRole.OPERATIONAL_HISTORY
        # Charter summary should mention sections
        assert "2 sections" in results[0].summary
        # Progress summary should mention entries
        assert "1 entries" in results[1].summary or "1 entry" in results[1].summary
        assert "2 entries" in results[2].summary

    def test_missing_documents(self, tmp_path: Path):
        """When documents are missing, they should be found=False with no crash."""
        ml_root = tmp_path / "ml-intern"
        ml_root.mkdir()
        lex_root = tmp_path / "lex"
        lex_root.mkdir()

        repo_roots = {
            "ml-intern-for-lex": ml_root,
            "lex_study_foundation": lex_root,
        }

        results = read_documents(repo_roots)

        assert len(results) == 3
        assert not any(r.found for r in results)
        assert all(r.summary is None for r in results)

    def test_missing_repo_root(self):
        """When a repo root is not provided, documents should be marked missing."""
        repo_roots = {
            "ml-intern-for-lex": Path("/nonexistent/path"),
        }

        results = read_documents(repo_roots)

        assert len(results) == 3
        # ml-intern docs get found=False (path doesn't exist)
        assert not results[0].found
        assert not results[1].found
        # lex doc gets a note about missing repo root
        assert not results[2].found
        assert "not provided" in (results[2].notes or "")

    def test_document_ids_are_sequential(self, tmp_path: Path):
        """Document IDs should follow doc-001, doc-002, doc-003 pattern."""
        ml_root = tmp_path / "ml"
        ml_root.mkdir()
        lex_root = tmp_path / "lex"
        lex_root.mkdir()

        results = read_documents({
            "ml-intern-for-lex": ml_root,
            "lex_study_foundation": lex_root,
        })

        assert results[0].id == "doc-001"
        assert results[1].id == "doc-002"
        assert results[2].id == "doc-003"

    def test_bom_handling(self, tmp_path: Path):
        """Files with BOM should be read correctly."""
        ml_root = tmp_path / "ml"
        docs = ml_root / "docs"
        docs.mkdir(parents=True)

        charter = docs / "PROJECT_CHARTER.md"
        # Write with BOM
        charter.write_bytes(b"\xef\xbb\xbf# Charter\n\n## 1. Test\n\nContent.\n")

        results = read_documents({"ml-intern-for-lex": ml_root})

        charter_result = results[0]
        assert charter_result.found is True
        # Summary should not start with BOM character
        assert not charter_result.summary.startswith("\ufeff")
