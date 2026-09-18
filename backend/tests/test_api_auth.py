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
