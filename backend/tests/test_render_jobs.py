"""Async render job queue tests (plan Task 3).

The render submission must return before invoking any render subprocess;
the worker stores an artifact on success and persists safe stderr on
failure; duplicate idempotency keys return the existing job.
"""
import pytest


@pytest.fixture()
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'va.db'}")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    import importlib

    from backend.app.api import store as store_mod

    importlib.reload(store_mod)
    store_mod.reset_store(str(tmp_path / "va.db"))
    yield store_mod
    store_mod.reset_store(":memory:")


def test_canvas_render_returns_202_without_rendering(monkeypatch, isolated_store):
    """POST /api/v1/canvas/render must 202 before any Remotion subprocess."""
    from starlette.testclient import TestClient

    import backend.app.api.server as srv

    calls = {"npx": 0}
    real_run = srv.subprocess.run

    def spy_run(*args, **kwargs):
        if args and isinstance(args[0], list) and "remotion" in args[0]:
            calls["npx"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(srv.subprocess, "run", spy_run)

    from backend.app.jobs import render_worker

    monkeypatch.setattr(render_worker, "run_render_job",
                        lambda job_id, manifest, **kw: isolated_store.get_store().update_job(
                            job_id, status="SUCCEEDED", artifact_key=f"renders/{job_id}.mp4"))

    client = TestClient(srv.app)
    res = client.post("/api/v1/canvas/render", json={
        "projectId": "proj_render_1",
        "aspectRatio": "9:16",
        "totalDurationSec": 4.0,
        "scenes": [{"sceneId": 1, "voiceover": "xin chao", "durationSec": 4.0}],
    })
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["status"] == "PENDING"
    assert calls["npx"] == 0

    record = isolated_store.get_store().get_job(body["job_id"])
    assert record is not None and record["status"] in ("PENDING", "RUNNING", "SUCCEEDED")


def test_canvas_render_duplicate_idempotency_key_returns_same_job(monkeypatch, isolated_store):
    from starlette.testclient import TestClient

    import backend.app.api.server as srv
    from backend.app.jobs import render_worker

    monkeypatch.setattr(render_worker, "run_render_job",
                        lambda job_id, manifest, **kw: {"job_id": job_id, "status": "SUCCEEDED"})

    client = TestClient(srv.app)
    payload = {
        "projectId": "proj_dup",
        "aspectRatio": "9:16",
        "totalDurationSec": 3.0,
        "scenes": [{"sceneId": 1, "voiceover": "a", "durationSec": 3.0}],
        "idempotency_key": "render-key-42",
    }
    first = client.post("/api/v1/canvas/render", json=payload)
    second = client.post("/api/v1/canvas/render", json=payload)
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]


def test_render_worker_success_stores_artifact(monkeypatch, isolated_store, tmp_path):
    """Worker success persists an artifact key through the storage interface."""
    from backend.app.jobs import render_worker
    from backend.app.api.store import get_store

    saved = {}

    class SpyStorage:
        def save(self, key, data):
            saved[key] = data

    job_id = "render_worker_ok"
    get_store().create_job({"job_id": job_id, "provider": "remotion", "mode": "render"})

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            returncode = 0
            stderr = ""

        out = render_worker._out_dir()
        out.mkdir(parents=True, exist_ok=True)
        (out / f"canvas_project_9_16_{job_id}.mp4").write_bytes(b"fake-mp4")
        return R()

    monkeypatch.setattr(render_worker.subprocess, "run", fake_run)
    result = render_worker.run_render_job(job_id, {"projectId": "canvas_project",
                                                   "aspectRatio": "9:16"},
                                          storage=SpyStorage(), timeout_sec=5)
    assert result["status"] == "SUCCEEDED"
    assert saved and list(saved)[0].startswith("renders/")
    job = get_store().get_job(job_id)
    assert job["status"] == "SUCCEEDED"
    assert job["artifact_key"].startswith("renders/")


def test_render_worker_failure_persists_safe_stderr(monkeypatch, isolated_store):
    """Worker failure records a bounded error message, never a fake success."""
    from backend.app.jobs import render_worker
    from backend.app.api.store import get_store

    job_id = "render_worker_fail"
    get_store().create_job({"job_id": job_id, "provider": "remotion", "mode": "render"})

    class R:
        returncode = 1
        stderr = "x" * 5000

    monkeypatch.setattr(render_worker.subprocess, "run", lambda *a, **k: R())
    result = render_worker.run_render_job(job_id, {"projectId": "p", "aspectRatio": "9:16"},
                                          timeout_sec=5)
    # Plan 03 taxonomy: REMOTION_FAILED is terminal -> DEAD + DLQ row (was FAILED).
    assert result["status"] == "DEAD"
    record = get_store().get_job(job_id)
    assert record["status"] == "DEAD"
    assert record["error"].startswith("REMOTION_FAILED")
    assert len(record["error"]) <= 2500


def test_render_worker_uses_per_job_manifest(monkeypatch, isolated_store):
    """The worker must never reuse the shared render_manifest.json path."""
    from backend.app.jobs import render_worker

    seen_cmds = []

    class R:
        returncode = 1
        stderr = "stop"

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        seen_cmds.append(list(cmd))
        return R()

    monkeypatch.setattr(render_worker.subprocess, "run", fake_run)
    render_worker.run_render_job("render_manifest_check", {"projectId": "p",
                                                           "aspectRatio": "16:9"},
                                 timeout_sec=5)
    joined = " ".join(seen_cmds[0])
    assert "render_manifest_render_manifest_check.json" in joined
    assert "--props=./render_manifest.json" not in joined


def test_render_poll_reports_durable_state_and_artifact(monkeypatch, isolated_store):
    from starlette.testclient import TestClient

    import backend.app.api.server as srv

    client = TestClient(srv.app)
    created = client.post("/api/v1/canvas/render", json={
        "projectId": "proj_poll",
        "aspectRatio": "9:16",
        "totalDurationSec": 2.0,
        "scenes": [{"sceneId": 1, "voiceover": "hi", "durationSec": 2.0}],
    })
    job_id = created.json()["job_id"]
    isolated_store.get_store().update_job(job_id, status="SUCCEEDED",
                                          artifact_key="renders/proj_poll.mp4")
    polled = client.get(f"/api/v1/jobs/{job_id}")
    assert polled.status_code == 200
    body = polled.json()
    assert body["status"] == "SUCCEEDED"
    assert body["artifact_key"] == "renders/proj_poll.mp4"


def test_job_endpoint_404_for_unknown_job(monkeypatch, isolated_store):
    from starlette.testclient import TestClient

    import backend.app.api.server as srv

    client = TestClient(srv.app)
    assert client.get("/api/v1/jobs/render_never_created").status_code == 404


def test_canvas_render_with_eventing_enabled(monkeypatch, tmp_path, isolated_store):
    """When EVENTING_ENABLED=1, canvas_render writes render_jobs and outbox atomically."""
    from starlette.testclient import TestClient
    import backend.app.api.server as srv
    from backend.app.messaging import db

    ev_url = f"sqlite:///{tmp_path / 'ev_api.db'}"
    monkeypatch.setenv("EVENTING_ENABLED", "1")
    monkeypatch.setenv("EVENTING_DATABASE_URL", ev_url)
    db.ensure_schema(ev_url)

    client = TestClient(srv.app)
    res = client.post("/api/v1/canvas/render", json={
        "projectId": "proj_eventing_test",
        "aspectRatio": "9:16",
        "totalDurationSec": 5.0,
        "scenes": [{"sceneId": 1, "voiceover": "eventing", "durationSec": 5.0}],
        "idempotency_key": "idem-eventing-test-1",
    })
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "PENDING"
    job_id = body["job_id"]

    # Verify both render_jobs and outbox were written in the eventing db
    with db.connect(ev_url) as conn:
        job = conn.execute("SELECT * FROM render_jobs WHERE job_id=?", (job_id,)).fetchone()
        assert job is not None
        outbox = conn.execute("SELECT * FROM outbox WHERE event_type='video.render.requested'").fetchall()
        assert len(outbox) == 1
        assert outbox[0]["kafka_key"] == job_id