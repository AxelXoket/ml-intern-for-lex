"""Tests for repository scanning layer.

Tests scanner against temporary directory trees using tmp_path fixture.
Does NOT depend on the real lex or ml-intern repos being present.
"""

from __future__ import annotations

from pathlib import Path

from ml_intern.repo_scanner import (
    DEFAULT_PRUNE_DIRS,
    _is_text_file,
    _scan_directory_tree,
    read_git_remote_url,
    scan_repository,
)
from ml_intern.report_schemas import SourceKind


class TestDirectoryTree:
    """Directory tree scanner should handle various filesystem shapes."""

    def test_empty_directory(self, tmp_path: Path):
        tree = _scan_directory_tree(tmp_path)
        assert tree["file_count"] == 0
        assert tree["dir_count"] == 0
        assert tree["top_level_dirs"] == []
        assert tree["top_level_files"] == []

    def test_basic_structure(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "docs").mkdir()
        (tmp_path / "README.md").write_text("hello")
        (tmp_path / "src" / "main.py").write_text("pass")

        tree = _scan_directory_tree(tmp_path)
        assert "src" in tree["top_level_dirs"]
        assert "docs" in tree["top_level_dirs"]
        assert "README.md" in tree["top_level_files"]
        assert tree["file_count"] >= 2

    def test_prune_dirs_skipped(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("[core]")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "module.pyc").write_bytes(b"\x00")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("pass")

        tree = _scan_directory_tree(tmp_path, DEFAULT_PRUNE_DIRS)
        # .git and __pycache__ should be pruned from top_level_dirs
        assert ".git" not in tree["top_level_dirs"]
        assert "__pycache__" not in tree["top_level_dirs"]
        assert "src" in tree["top_level_dirs"]

    def test_nonexistent_root(self, tmp_path: Path):
        tree = _scan_directory_tree(tmp_path / "nonexistent")
        assert len(tree["errors"]) > 0


class TestTextFileDetection:
    """Binary vs text detection should work by extension."""

    def test_python_is_text(self, tmp_path: Path):
        assert _is_text_file(tmp_path / "main.py")

    def test_markdown_is_text(self, tmp_path: Path):
        assert _is_text_file(tmp_path / "README.md")

    def test_binary_is_not_text(self, tmp_path: Path):
        assert not _is_text_file(tmp_path / "image.png")
        assert not _is_text_file(tmp_path / "data.bin")

    def test_gitignore_is_text(self, tmp_path: Path):
        assert _is_text_file(tmp_path / ".gitignore")


class TestGitRemoteUrl:
    """Git remote URL reader should handle various .git/config states."""

    def test_reads_origin_url(self, tmp_path: Path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text(
            '[remote "origin"]\n'
            "\turl = https://github.com/user/repo.git\n"
            "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
        )

        url = read_git_remote_url(tmp_path)
        assert url == "https://github.com/user/repo.git"

    def test_returns_none_when_no_git_dir(self, tmp_path: Path):
        url = read_git_remote_url(tmp_path)
        assert url is None

    def test_returns_none_when_no_origin(self, tmp_path: Path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text("[core]\n\tbare = false\n")

        url = read_git_remote_url(tmp_path)
        assert url is None


class TestScanRepository:
    """Full repository scan should produce observations."""

    def test_basic_repo_scan(self, tmp_path: Path):
        # Create a minimal repo structure
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test-proj"\nversion = "0.1.0"\n'
            'requires-python = ">=3.11"\ndependencies = [\n  "fastapi",\n]\n'
        )
        (tmp_path / "README.md").write_text("# Test")
        (tmp_path / ".gitignore").write_text("*.pyc\n")
        (tmp_path / "src").mkdir()
        src_pkg = tmp_path / "src" / "test_proj"
        src_pkg.mkdir()
        (src_pkg / "__init__.py").write_text("")
        (src_pkg / "main.py").write_text("pass")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "notes.md").write_text("# Notes")

        observations = scan_repository("test-repo", tmp_path)

        assert len(observations) > 0
        # All observations should have the repo name
        assert all(obs.repo == "test-repo" for obs in observations)
        # Should have directory structure observations
        dir_obs = [o for o in observations if o.source_kind == SourceKind.DIRECTORY_STRUCTURE]
        assert len(dir_obs) >= 2

    def test_nonexistent_repo(self, tmp_path: Path):
        observations = scan_repository("ghost", tmp_path / "nonexistent")
        assert len(observations) == 1
        assert observations[0].source_kind == SourceKind.ENVIRONMENT

    def test_sensitive_file_not_read(self, tmp_path: Path):
        (tmp_path / ".env").write_text("SECRET_KEY=super_secret_value")
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')

        observations = scan_repository("test", tmp_path)

        # .env should be observed as present but content should not appear
        env_obs = [
            o for o in observations
            if ".env" in (o.description or "") and "present" in (o.description or "")
        ]
        assert len(env_obs) >= 1
        # Secret value should never appear in any observation
        for obs in observations:
            assert "super_secret_value" not in obs.description
