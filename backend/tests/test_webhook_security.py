"""Webhook subscription + delivery security tests (plan Task 4).

Rejects localhost / RFC1918 / link-local / DNS-resolved private targets,
requires a secret in production (no dev-secret fallback), and proves
duplicate event delivery shares one idempotency record.
"""
import pytest


@pytest.fixture()
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'va-sec.db'}")
    import importlib

    from backend.app.api import store as store_mod

    importlib.reload(store_mod)
    store_mod.reset_store(str(tmp_path / "va-sec.db"))
    yield store_mod
    store_mod.reset_store(":memory:")


# --- URL validation --------------------------------------------------------
def test_reject_localhost_and_loopback_targets():
    from backend.app.api.webhooks import WebhookSecurityError, validate_webhook_url

    for url in ("http://localhost/hook", "http://127.0.0.1/hook",
                "http://api.localhost/hook", "http://0.0.0.0/hook"):
        with pytest.raises(WebhookSecurityError):
            validate_webhook_url(url)


def test_reject_rfc1918_and_link_literal_targets():
    from backend.app.api.webhooks import WebhookSecurityError, validate_webhook_url

    for url in ("http://10.0.0.5/hook", "http://192.168.1.10/hook",
                "http://172.16.0.9/hook", "http://169.254.169.254/latest/meta-data",
                "http://[::1]/hook", "http://224.0.0.1/hook"):
        with pytest.raises(WebhookSecurityError):
            validate_webhook_url(url)


def test_reject_dns_resolved_private_target(monkeypatch):
    """A public-looking hostname that resolves private must be rejected."""
    import socket

    from backend.app.api.webhooks import WebhookSecurityError, validate_webhook_url

    def fake_getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.0.44", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(WebhookSecurityError, match="private"):
        validate_webhook_url("http://internal-staging.example.com/hook")


def test_allowlisted_hostname_bypasses_dns_check(monkeypatch):
    import socket

    from backend.app.api.webhooks import validate_webhook_url

    def fail_getaddrinfo(host, port):  # allowlisted hosts skip resolution
        raise AssertionError("allowlisted host must not be resolved")

    monkeypatch.setattr(socket, "getaddrinfo", fail_getaddrinfo)
    info = validate_webhook_url("https://hooks.trusted.example/hook",
                                allowlist=["hooks.trusted.example"])
    assert info["allowlisted"] is True


def test_reject_non_http_schemes():
    from backend.app.api.webhooks import WebhookSecurityError, validate_webhook_url

    with pytest.raises(WebhookSecurityError):
        validate_webhook_url("file:///etc/passwd")
    with pytest.raises(WebhookSecurityError):
        validate_webhook_url("ftp://example.com/x")


# --- secret handling --------------------------------------------------------
def test_production_requires_webhook_secret(monkeypatch):
    from backend.app.api.webhooks import WebhookSecurityError, resolve_target_secret

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    with pytest.raises(WebhookSecurityError, match="required in production"):
        resolve_target_secret(None)
    monkeypatch.setenv("WEBHOOK_SECRET", "prod-secret")
    assert resolve_target_secret(None) == "prod-secret"


def test_dev_secret_only_outside_production(monkeypatch):
    from backend.app.api.webhooks import resolve_target_secret

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    assert resolve_target_secret(None) == "dev-secret"
    assert resolve_target_secret("per-target") == "per-target"


# --- idempotent delivery ----------------------------------------------------
def test_duplicate_event_delivery_shares_one_receipt(monkeypatch, isolated_store):
    """The same (url, event, payload) must not create a second delivery record."""
    from backend.app.delivery import dispatcher as d

    attempts = {"n": 0}

    def fake_post(url, content=None, headers=None, timeout=None):
        attempts["n"] += 1

        class R:
            status_code = 200

            def raise_for_status(self):
                return None

        return R()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")
    target = d.DeliveryTarget(url="https://hooks.example.com/hook", secret="s")
    payload = b'{"project_id":"p1"}'

    first = d.deliver_idempotent(target, payload, event="project.completed")
    second = d.deliver_idempotent(target, payload, event="project.completed")

    assert first.ok is True
    assert second.replayed is True
    assert second.idempotency_key == first.idempotency_key
    assert attempts["n"] == 1
    assert isolated_store.get_store().get_receipt(first.idempotency_key) is not None


def test_dispatcher_rejects_private_target_before_network(monkeypatch):
    """SSRF targets fail fast with WEBHOOK_TARGET_REJECTED and zero attempts."""
    import httpx

    from backend.app.delivery import dispatcher as d

    def fail_post(*a, **k):
        raise AssertionError("network call must not happen for rejected targets")

    monkeypatch.setattr(httpx, "post", fail_post)
    receipt = d.deliver(d.DeliveryTarget(url="http://169.254.169.254/meta", secret="s"),
                        b"{}")
    assert receipt.ok is False
    assert receipt.attempts == 0
    assert "WEBHOOK_TARGET_REJECTED" in (receipt.error or "")


# --- API layer --------------------------------------------------------------
def test_subscribe_rejects_private_url_via_api(monkeypatch, isolated_store):
    from starlette.testclient import TestClient

    import backend.app.api.server as srv

    client = TestClient(srv.app)
    res = client.post("/api/v1/webhooks/subscribe", json={"url": "http://127.0.0.1:9/hook"})
    assert res.status_code == 400
    assert "WEBHOOK_TARGET_REJECTED" in res.json()["detail"]


def test_subscribe_persists_and_lists(monkeypatch, isolated_store):
    monkeypatch.setenv("WEBHOOK_ALLOWED_HOSTS", "hooks.example.com")
    from starlette.testclient import TestClient

    import backend.app.api.server as srv

    client = TestClient(srv.app)
    ok = client.post("/api/v1/webhooks/subscribe", json={
        "url": "https://hooks.example.com/hook", "events": ["project.completed"]})
    assert ok.status_code == 201
    listed = client.get("/api/v1/webhooks/subscriptions")
    assert listed.status_code == 200
    assert any(s["url"] == "https://hooks.example.com/hook" for s in listed.json())


def test_signature_roundtrip_uses_hmac_sha256():
    from backend.app.api.webhooks import sign_payload, verify_signature

    sig = sign_payload(b"hello", "secret")
    assert len(sig) == 64
    assert verify_signature(b"hello", sig, "secret") is True
    assert verify_signature(b"hello", sig, "wrong") is False