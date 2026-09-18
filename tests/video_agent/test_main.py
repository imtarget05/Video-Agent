"""Tests for the Video-Agent main application."""

from fastapi.testclient import TestClient

from video_agent.main import app


def test_health_endpoint():
    """Verify the /health endpoint returns 200."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200