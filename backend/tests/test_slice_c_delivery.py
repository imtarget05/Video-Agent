"""Slice C acceptance tests (delivery/docs/CI): dispatcher, server endpoints, ledger path."""
import os


def test_ledger_database_url_env():
    from backend.app.cost.ledger import CostLedger
    from backend.app.agent.state import CostRecord
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        custom = os.path.join(td, "custom_video_agent.db")
        os.environ["DATABASE_URL"] = custom
        try:
            led = CostLedger()
            assert led.db_path == custom
            led.record_cost("p1", CostRecord(job_id="j", provider="p", duration_sec=1.0, cost_usd=0.1))
            assert os.path.exists(custom)
        finally:
            os.environ.pop("DATABASE_URL", None)
    # default path uses video_agent.db
    led2 = CostLedger.__new__(CostLedger)
    import inspect
    sig = inspect.signature(CostLedger.__init__)
    default = sig.parameters["db_path"].default if "db_path" in sig.parameters else None
    assert default is None or "video_agent.db" in str(default)


def test_ledger_sqlite_url_prefix(tmp_path):
    from backend.app.cost.ledger import CostLedger
    from backend.app.agent.state import CostRecord
    target = str(tmp_path / "pref.db")
    os.environ["DATABASE_URL"] = f"sqlite:///{target}"
    try:
        led = CostLedger()
        assert led.db_path == target
    finally:
        os.environ.pop("DATABASE_URL", None)


def test_dispatcher_hmac_retry_models():
    from backend.app.delivery import dispatcher as d
    assert hasattr(d, "DeliveryTarget") and hasattr(d, "Receipt")
    assert hasattr(d, "sign_payload") and hasattr(d, "deliver")
    t = d.DeliveryTarget(url="http://example.com/hook", secret="s")
    assert t.url.startswith("http")
    # retry cap: max 2 retries => <=3 attempts even when endpoint dead
    r = d.deliver(t, b'{"a":1}', timeout_sec=0.5)
    assert isinstance(r, d.Receipt)
    assert r.attempts <= 3
    assert r.ok is False  # unroutable/dead endpoint in offline env


def test_dispatcher_sign_verify():
    from backend.app.delivery import dispatcher as d
    sig = d.sign_payload(b"hello", "secret")
    assert d.verify_signature(b"hello", sig, "secret") is True
    assert d.verify_signature(b"hello", sig, "wrong") is False


def test_server_list_status_reject_async_auth_deliver_subscribe():
    from starlette.testclient import TestClient
    import backend.app.api.server as srv
    c = TestClient(srv.app)
    # list projects
    r = c.get("/api/v1/projects")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    # create one for status/reject flow
    res = c.post("/api/v1/projects", json={"topic": "Hệ thống tưới cây tự động cho ban công"})
    assert res.status_code == 201
    pid = res.json()["project_id"]
    # list now contains it
    assert pid in c.get("/api/v1/projects").json()
    # status endpoint
    st = c.get(f"/api/v1/projects/{pid}/status")
    assert st.status_code == 200
    assert st.json()["project_id"] == pid
    assert "status" in st.json()
    # async job create + poll
    job = c.post("/api/v1/jobs", json={"prompt": "a calm lake", "duration_sec": 2.0})
    assert job.status_code in (200, 201, 202)
    jid = job.json()["job_id"]
    poll = c.get(f"/api/v1/jobs/{jid}")
    assert poll.status_code == 200
    # subscribe webhook
    sub = c.post("/api/v1/webhooks/subscribe", json={"url": "http://example.com/hook"})
    assert sub.status_code in (200, 201)
    subs = c.get("/api/v1/webhooks/subscriptions")
    assert subs.status_code == 200
    assert "http://example.com/hook" in str(subs.json())
    # deliver (offline target => ok False but well-formed receipt)
    dl = c.post("/api/v1/deliver", json={"project_id": pid, "targets": ["http://127.0.0.1:9/hook"]})
    assert dl.status_code == 200
    body = dl.json()
    assert "receipts" in body or "results" in body
    # reject flow
    rej = c.post(f"/api/v1/projects/{pid}/reject", json={"feedback": "not good"})
    assert rej.status_code == 200
    assert rej.json()["status"] == "FAILED"
    # auth: wrong key rejected when API_KEY set
    os.environ["API_KEY"] = "secret123"
    try:
        bad = c.post("/api/v1/deliver", json={"project_id": pid, "targets": []},
                     headers={"X-API-Key": "wrong"})
        assert bad.status_code == 401
        good = c.post("/api/v1/deliver", json={"project_id": pid, "targets": []},
                      headers={"X-API-Key": "secret123"})
        assert good.status_code == 200
    finally:
        os.environ.pop("API_KEY", None)


def test_requirements_has_deps():
    text = open("backend/requirements.txt").read()
    assert "huggingface_hub" in text
    assert "edge-tts" in text


def test_ci_has_mock_flags_and_manifest_assert():
    text = open(".github/workflows/ci.yml").read()
    assert "MOCK_VIDEO" in text and "MOCK_TTS" in text
    assert "render_manifest.json" in text
