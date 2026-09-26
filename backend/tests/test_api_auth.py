"""Production API access and CORS safety tests."""
import os

import pytest
from starlette.testclient import TestClient


def test_mutating_job_request_rejects_missing_or_wrong_api_key(monkeypatch):
    """Every mutation must require the configured API key."""
    monkeypatch.setenv("API_KEY", "test-key")
    from backend.app.api.server import app

    client = TestClient(app)
    payload = {"prompt": "a calm lake"}
    assert client.post("/api/v1/jobs", json=payload).status_code == 401
    assert client.post(
        "/api/v1/jobs", json=payload, headers={"X-API-Key": "wrong"}
    ).status_code == 401
    assert client.post(
        "/api/v1/jobs", json=payload, headers={"X-API-Key": "test-key"}
    ).status_code == 202


def test_production_settings_require_key_and_explicit_origins(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    from backend.app.config import SettingsError, load_settings

    with pytest.raises(SettingsError, match="API_KEY"):
        load_settings()

    monkeypatch.setenv("API_KEY", "production-key")
    with pytest.raises(SettingsError, match="CORS_ORIGINS"):
        load_settings()


def test_cors_uses_configured_origin_and_never_pairs_wildcard_with_credentials(monkeypatch):
    from backend.app.config import SettingsError, cors_options, load_settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", "production-key")
    monkeypatch.setenv("CORS_ORIGINS", "https://dashboard.example, https://ops.example")
    options = cors_options(load_settings())
    assert options["allow_origins"] == ["https://dashboard.example", "https://ops.example"]
    assert options["allow_credentials"] is True

    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(SettingsError, match="wildcard"):
        load_settings()

    monkeypatch.setenv("APP_ENV", "development")
    options = cors_options(load_settings())
    assert options["allow_origins"] == ["*"]
    assert options["allow_credentials"] is False

    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    with pytest.raises(SettingsError, match="wildcard"):
        load_settings()


def test_unset_api_key_is_fail_closed_outside_development(monkeypatch):
    """An unset API_KEY must never be a silent allow outside development.

    Previously `require_api_key` returned True whenever API_KEY was empty, so a
    staging/production deploy started with no secret and served every protected
    route to anyone. The test asserts the secure behaviour: a clear refusal.
    """
    from backend.app.api.server import app

    for env in ("staging", "production"):
        monkeypatch.setenv("APP_ENV", env)
        monkeypatch.delenv("API_KEY", raising=False)
        client = TestClient(app)
        r = client.post("/api/v1/jobs", json={"prompt": "a calm lake"})
        assert r.status_code == 503, f"{env}: expected 503, got {r.status_code}"
        assert "fail-closed" in r.json()["detail"]


def test_unset_api_key_still_allows_offline_development(monkeypatch):
    """Documented exception: development with no key stays open for the demo."""
    from backend.app.api.server import app

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("API_KEY", raising=False)
    client = TestClient(app)
    assert client.post(
        "/api/v1/jobs", json={"prompt": "a calm lake"}
    ).status_code == 202


def test_api_key_comparison_is_constant_time(monkeypatch):
    """The key check must use secrets.compare_digest, not `!=`."""
    import inspect

    from backend.app.api import server

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("API_KEY", "k")
    src = inspect.getsource(server.require_api_key)
    assert "secrets.compare_digest" in src, (
        "require_api_key must compare with secrets.compare_digest so a wrong "
        "key cannot be recovered from response timing"
    )
    assert "x_api_key != expected" not in src