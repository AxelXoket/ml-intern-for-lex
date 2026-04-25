"""Integration tests for /api/repos/* endpoints.

Tests path traversal blocking, sensitive file blocking, binary file
rejection, and successful file reading through the API layer.
"""

from __future__ import annotations

import pytest


class TestListRepos:
    def test_list_repos_returns_list(self, client):
        response = client.get("/api/repos")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Each repo has required fields
        for repo in data:
            assert "key" in repo
            assert "name" in repo
            assert "accessible" in repo

    def test_list_repos_contains_intern(self, client):
        response = client.get("/api/repos")
        keys = [r["key"] for r in response.json()]
        assert "intern" in keys


class TestRepoTree:
    def test_tree_returns_entries(self, client):
        response = client.get("/api/repos/intern/tree")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_tree_has_expected_fields(self, client):
        response = client.get("/api/repos/intern/tree")
        data = response.json()
        # Find a file entry
        files = [e for e in data if e["type"] == "file"]
        assert len(files) > 0
        f = files[0]
        assert "path" in f
        assert "type" in f
        assert f["type"] == "file"

    def test_tree_unknown_repo_404(self, client):
        response = client.get("/api/repos/unknown_repo_xyz/tree")
        assert response.status_code == 404


class TestFileMeta:
    def test_meta_for_readme(self, client):
        response = client.get("/api/repos/intern/file/meta", params={"path": "README.md"})
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "README.md"
        assert data["is_text"] is True
        assert data["sensitive"] is False
        assert data["size_bytes"] > 0

    def test_meta_path_traversal_blocked(self, client):
        response = client.get(
            "/api/repos/intern/file/meta",
            params={"path": "../../etc/passwd"},
        )
        assert response.status_code == 403

    def test_meta_unknown_repo_404(self, client):
        response = client.get(
            "/api/repos/nonexistent/file/meta",
            params={"path": "README.md"},
        )
        assert response.status_code == 404

    def test_meta_nonexistent_file_404(self, client):
        response = client.get(
            "/api/repos/intern/file/meta",
            params={"path": "this_file_does_not_exist.xyz"},
        )
        assert response.status_code == 404


class TestFileContent:
    def test_read_readme_lines(self, client):
        response = client.get(
            "/api/repos/intern/file",
            params={"path": "README.md", "start": 1, "end": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "lines" in data
        assert len(data["lines"]) > 0
        assert data["start"] == 1

    def test_path_traversal_blocked(self, client):
        response = client.get(
            "/api/repos/intern/file",
            params={"path": "../../../etc/passwd"},
        )
        assert response.status_code == 403

    def test_binary_file_rejected(self, client):
        """Binary files should return 403 (if sensitive) or 415 (if not)."""
        # First check if there's a binary file in the tree
        tree = client.get("/api/repos/intern/tree").json()
        binary_files = [
            e for e in tree
            if e["type"] == "file" and e.get("is_text") is False
        ]
        if not binary_files:
            pytest.skip("No binary files in intern repo")

        response = client.get(
            "/api/repos/intern/file",
            params={"path": binary_files[0]["path"]},
        )
        # Sensitive check runs before binary check, so could be 403 or 415
        assert response.status_code in (403, 415)

    def test_range_exceeds_cap_400(self, client):
        response = client.get(
            "/api/repos/intern/file",
            params={"path": "README.md", "start": 1, "end": 1500},
        )
        assert response.status_code == 400
        assert "exceeds" in response.json()["detail"].lower()
