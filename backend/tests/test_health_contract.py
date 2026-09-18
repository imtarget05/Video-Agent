import pytest
from starlette.testclient import TestClient
from backend.app.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_live_ok_without_dependencies(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_reports_checks(client):
    r = client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    assert body["status"] in ("ready", "not-ready")
    assert "checks" in body
    assert "config" in body["checks"]
    assert "storage" in body["checks"]
    # Default local env must be ready: proves the checks really pass,
    # not just that the keys exist.
    assert body["status"] == "ready", body


def test_legacy_health_still_served(client):
    assert client.get("/health").status_code == 200
