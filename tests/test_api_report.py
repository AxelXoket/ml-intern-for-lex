"""Integration tests for /api/report/* and /api/dashboard/summary endpoints.

Tests the POST/GET cache pattern, sub-section endpoints, and
dashboard summary aggregation.
"""

from __future__ import annotations


class TestReportCache:
    def test_get_before_post_returns_404(self, client):
        """GET /api/report should return 404 if no report has been generated."""
        # Reset cache by importing the module and clearing it
        from ml_intern.routes import report as report_module
        report_module._cached_report = None

        response = client.get("/api/report")
        assert response.status_code == 404

    def test_post_generates_report(self, client):
        """POST /api/report should generate and return a full report."""
        response = client.post("/api/report")
        assert response.status_code == 200
        data = response.json()
        assert "report_id" in data
        assert "findings" in data
        assert "observations" in data
        assert "executive_summary" in data

    def test_get_after_post_returns_cached(self, client):
        """GET /api/report should return the cached report after POST."""
        # Generate first
        client.post("/api/report")
        # Then read cached
        response = client.get("/api/report")
        assert response.status_code == 200
        data = response.json()
        assert "report_id" in data

    def test_report_status_ready(self, client):
        """GET /api/report/status should return 'ready' after POST."""
        client.post("/api/report")
        response = client.get("/api/report/status")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_report_status_never_run(self, client):
        """GET /api/report/status should return 'never_run' before POST."""
        from ml_intern.routes import report as report_module
        report_module._cached_report = None

        response = client.get("/api/report/status")
        assert response.status_code == 200
        assert response.json()["status"] == "never_run"


class TestReportSubEndpoints:
    def test_findings_returns_list(self, client):
        client.post("/api/report")
        response = client.get("/api/report/findings")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_observations_returns_list(self, client):
        client.post("/api/report")
        response = client.get("/api/report/observations")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_questions_returns_list(self, client):
        client.post("/api/report")
        response = client.get("/api/report/questions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_summary_returns_dict(self, client):
        client.post("/api/report")
        response = client.get("/api/report/summary")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "observations_count" in data
        assert "findings_by_category" in data


class TestDashboardSummary:
    def test_dashboard_summary_structure(self, client):
        response = client.get("/api/dashboard/summary")
        assert response.status_code == 200
        data = response.json()
        assert "repos" in data
        assert "report_status" in data
        assert "health" in data
        assert isinstance(data["repos"], list)
