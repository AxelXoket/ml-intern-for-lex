"""Tests for repo_access.py — path traversal, sensitive file blocking, file reading.

These are security-critical tests. They verify the boundary enforcement
that prevents API endpoints from reading files outside allowed repos,
reading .env files, or reading binary files.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from ml_intern.repo_access import (
    MAX_LINES_PER_REQUEST,
    get_file_meta,
    is_sensitive_file,
    is_text_file,
    read_file_lines,
    validate_path,
)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Create a fake repo root with test files."""
    # Regular text file
    (tmp_path / "README.md").write_text("# Hello\nWorld\n", encoding="utf-8")

    # Python source
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')\n", encoding="utf-8")

    # Sensitive file
    (tmp_path / ".env").write_text("SECRET_KEY=mysecret\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("DB_URL=postgres://\n", encoding="utf-8")

    # Non-sensitive env example
    (tmp_path / ".env.example").write_text("SECRET_KEY=changeme\n", encoding="utf-8")

    # Binary file
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")

    # Nested directory
    sub = tmp_path / "sub" / "deep"
    sub.mkdir(parents=True)
    (sub / "nested.py").write_text("x = 1\n", encoding="utf-8")

    # Multi-line file for range testing
    lines = [f"line {i}" for i in range(1, 51)]
    (tmp_path / "multiline.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # File with a secret in content
    (tmp_path / "with_secret.py").write_text(
        "key = 'hf_ABCDEFGHIJKLMNOPQRSTuvwx'\n",
        encoding="utf-8",
    )

    # UTF-8 BOM file
    bom = b"\xef\xbb\xbf"
    (tmp_path / "bom_file.txt").write_bytes(bom + "BOM content\n".encode("utf-8"))

    return tmp_path


# ── Path Traversal Tests ────────────────────────────────────────


class TestPathTraversal:
    def test_relative_path_within_root_succeeds(self, repo_root: Path):
        result = validate_path("README.md", repo_root)
        assert result == (repo_root / "README.md").resolve()

    def test_nested_path_succeeds(self, repo_root: Path):
        result = validate_path("src/main.py", repo_root)
        assert result == (repo_root / "src" / "main.py").resolve()

    def test_dotdot_escape_blocked(self, repo_root: Path):
        with pytest.raises(PermissionError, match="Path traversal denied"):
            validate_path("../../../etc/passwd", repo_root)

    def test_backslash_escape_blocked(self, repo_root: Path):
        with pytest.raises(PermissionError, match="Path traversal denied"):
            validate_path("..\\\\..\\\\windows\\\\system32", repo_root)

    def test_nested_dotdot_escape_blocked(self, repo_root: Path):
        with pytest.raises(PermissionError, match="Path traversal denied"):
            validate_path("sub/../../../escape", repo_root)

    def test_deep_nested_succeeds(self, repo_root: Path):
        result = validate_path("sub/deep/nested.py", repo_root)
        assert result.is_relative_to(repo_root.resolve())


# ── Sensitive File Tests ────────────────────────────────────────


class TestSensitiveFile:
    def test_env_is_sensitive(self, repo_root: Path):
        assert is_sensitive_file(repo_root / ".env") is True

    def test_env_local_is_sensitive(self, repo_root: Path):
        assert is_sensitive_file(repo_root / ".env.local") is True

    def test_env_example_is_not_sensitive(self, repo_root: Path):
        assert is_sensitive_file(repo_root / ".env.example") is False

    def test_normal_config_not_sensitive(self, repo_root: Path):
        assert is_sensitive_file(repo_root / "config.yaml") is False

    def test_environment_is_sensitive(self, repo_root: Path):
        """Names starting with .env are sensitive (repo_scanner policy)."""
        assert is_sensitive_file(repo_root / ".environment") is True


# ── Binary Detection Tests ──────────────────────────────────────


class TestBinaryDetection:
    def test_py_is_text(self, repo_root: Path):
        assert is_text_file(repo_root / "src" / "main.py") is True

    def test_md_is_text(self, repo_root: Path):
        assert is_text_file(repo_root / "README.md") is True

    def test_png_is_binary(self, repo_root: Path):
        assert is_text_file(repo_root / "image.png") is False

    def test_unknown_extension_is_binary(self, repo_root: Path):
        assert is_text_file(repo_root / "data.whl") is False

    def test_gitignore_is_text(self, repo_root: Path):
        """Extensionless files in TEXT_EXACT_NAMES should be text."""
        assert is_text_file(repo_root / ".gitignore") is True


# ── File Metadata Tests ────────────────────────────────────────


class TestFileMeta:
    def test_meta_for_text_file(self, repo_root: Path):
        meta = get_file_meta(repo_root / "README.md", repo_root)
        assert meta["path"] == "README.md"
        assert meta["is_text"] is True
        assert meta["sensitive"] is False
        assert meta["size_bytes"] > 0
        assert meta["line_count"] is not None
        assert "modified_at" in meta

    def test_meta_for_sensitive_file(self, repo_root: Path):
        meta = get_file_meta(repo_root / ".env", repo_root)
        assert meta["sensitive"] is True
        # Line count should be None for sensitive files
        assert meta["line_count"] is None

    def test_meta_for_binary_file(self, repo_root: Path):
        meta = get_file_meta(repo_root / "image.png", repo_root)
        assert meta["is_text"] is False
        assert meta["line_count"] is None

    def test_meta_for_missing_file(self, repo_root: Path):
        with pytest.raises(FileNotFoundError):
            get_file_meta(repo_root / "nonexistent.py", repo_root)


# ── File Reader Tests ───────────────────────────────────────────


class TestFileReader:
    def test_reads_correct_line_range(self, repo_root: Path):
        lines = list(read_file_lines(repo_root / "multiline.txt", start=5, end=10))
        assert len(lines) == 6
        assert lines[0] == "line 5"
        assert lines[-1] == "line 10"

    def test_reads_from_start_by_default(self, repo_root: Path):
        lines = list(read_file_lines(repo_root / "multiline.txt", end=3))
        assert len(lines) == 3
        assert lines[0] == "line 1"

    def test_cap_enforced(self, repo_root: Path):
        with pytest.raises(ValueError, match="exceeds maximum"):
            list(read_file_lines(
                repo_root / "multiline.txt",
                start=1,
                end=MAX_LINES_PER_REQUEST + 10,
            ))

    def test_redaction_applied(self, repo_root: Path):
        lines = list(read_file_lines(repo_root / "with_secret.py"))
        assert any("[REDACTED]" in line for line in lines)

    def test_sensitive_file_blocked(self, repo_root: Path):
        with pytest.raises(PermissionError, match="sensitive"):
            list(read_file_lines(repo_root / ".env"))

    def test_binary_file_blocked(self, repo_root: Path):
        with pytest.raises(ValueError, match="Binary"):
            list(read_file_lines(repo_root / "image.png"))

    def test_missing_file_raises(self, repo_root: Path):
        with pytest.raises(FileNotFoundError):
            list(read_file_lines(repo_root / "nonexistent.py"))

    def test_bom_handled(self, repo_root: Path):
        lines = list(read_file_lines(repo_root / "bom_file.txt"))
        # BOM should be stripped — first line should not start with \ufeff
        assert not lines[0].startswith("\ufeff")
        assert "BOM content" in lines[0]
