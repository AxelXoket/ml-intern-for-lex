"""Shared test fixtures for endpoint integration tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ml_intern.main import app


@pytest.fixture
def client():
    """TestClient fixture — creates a sync test client for the FastAPI app."""
    with TestClient(app) as c:
        yield c
