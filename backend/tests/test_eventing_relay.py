"""V-4 acceptance: relay claim/publish/mark semantics (foundation §2.3).

Deterministic fake publisher; no broker. Asserts: success path claims and
marks SENT; publisher exceptions become FAILED with backoff then DEAD at
MAX_ATTEMPTS; INFLIGHT reclaim; replay copies (never modifies) SENT rows.
"""
import pytest

from backend.app.messaging import db, outbox as ox
from backend.app.messaging import envelope as env
from backend.app.messaging import relay


@pytest.fixture()
def eventing_db(monkeypatch, tmp_path):
    """Isolated eventing DB per test (fixture is REQUESTED by name)."""
    url = f"sqlite:///{tmp_path}/relay.db"
    monkeypatch.setenv("EVENTING_DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL", url)
    assert db.ensure_schema(url) == "sqlite"
    yield url


def _envelope(event_id, job_id="job_1"):
    payload = {"job_id": job_id, "project_id": "p1", "aspect_ratio": "9:16",
               "total_duration_sec": 4.0,
               "manifest_ref": {"store": "r2", "uri": "manifests/job_1.json",
                                "sha256": "a" * 64, "bytes": 120}}
    return env.build_envelope(
        event_type="video.render.requested", producer="video/api", app="video",
        env="staging", correlation_id="tr-1", idempotency_key=f"render:{job_id}",
        payload=payload, payload_ref=None,
        schema_ref="video.render.commands.v1-value:1", event_id=event_id)


def _job(job_id="job_1", key="render:job_1"):
    return {"job_id": job_id, "project_id": "p1", "aspect_ratio": "9:16",
            "total_duration_sec": 4.0, "idempotency_key": key,
            "provider": "remotion", "manifest_r2_key": "manifests/job_1.json"}


def _seed(n=2):
    ids = [f"0193f7a2-4b5c-7d8e-9f01-23456789abc{i}" for i in range(n)]
    for i, event_id in enumerate(ids):
        ox.enqueue_render_requested(
            job=_job(f"job_{i}", f"render:job_{i}"),
            envelope=_envelope(event_id, f"job_{i}"))
    return ids


def _row(event_id):
    with db.connect() as conn:
        return db.fetch_one_dict(conn.execute(
            "SELECT status, publish_attempts FROM outbox WHERE event_id=?",
            (event_id,)))


def test_run_once_publishes_with_topic_key_and_headers(eventing_db):
    _seed(2)
    calls = []

    def fake_publish(topic, key, payload, headers):
        calls.append((topic, key, payload, headers))

    summary = relay.run_once(fake_publish)
    assert summary == {"claimed": 2, "sent": 2, "failed": 0, "dead": 0}
    assert calls[0][0] == "video.render.commands.v1"
    assert calls[0][1] == "job_0"
    assert calls[0][3]["idempotency_key"] == "render:job_0"
    assert all(_row(e)["status"] == "SENT" for e in
               ["0193f7a2-4b5c-7d8e-9f01-23456789abc0",
                "0193f7a2-4b5c-7d8e-9f01-23456789abc1"])


def test_publisher_timeout_still_counts_as_claimed_then_failed(eventing_db):
    """A timeout AFTER the broker actually wrote is harmless: consumer dedupes."""
    ids = _seed(1)

    def flaky(topic, key, payload, headers):
        raise TimeoutError("broker ack lost")

    summary = relay.run_once(flaky)
    assert summary == {"claimed": 1, "sent": 0, "failed": 1, "dead": 0}
    assert _row(ids[0]) == {"status": "FAILED", "publish_attempts": 1}


def test_ten_failures_mark_dead(eventing_db):
    """Relay retries with backoff; the 11th attempt (attempt == MAX) is DEAD."""
    _seed(1)

    def always_fail(topic, key, payload, headers):
        raise ConnectionError("broker down")

    # Drive attempts 1..10 deterministically through mark_failed (no waiting).
    for attempt in range(1, 11):
        state = relay.mark_failed(1, attempt)
    assert state == {"status": "DEAD", "attempts": 10}
    with db.connect() as conn:
        row = db.fetch_one_dict(conn.execute("SELECT status FROM outbox"))
    assert row["status"] == "DEAD"
    # A relay pass over a DEAD row claims nothing (terminal state).
    assert relay.run_once(always_fail) == {
        "claimed": 0, "sent": 0, "failed": 0, "dead": 0
    }


def test_reclaim_inflight_after_crash(eventing_db):
    _seed(1)
    with db.connect() as conn:
        conn.execute("UPDATE outbox SET status='INFLIGHT', "
                     "created_at=datetime('now', '-10 minutes')")
        conn.commit()
    assert relay.reclaim_inflight() == 1
    with db.connect() as conn:
        row = db.fetch_one_dict(conn.execute("SELECT status FROM outbox"))
    assert row["status"] == "PENDING"


def test_replay_copies_sent_row_with_new_id_and_headers(eventing_db):
    ids = _seed(1)
    relay.run_once(lambda t, k, p, h: None)
    result = relay.replay_event(ids[0], approver="ops", reason="re-drive test")
    assert result["replay_of"] == ids[0]
    assert result["event_id"] != ids[0]
    with db.connect() as conn:
        rows = db.fetch_all_dicts(conn.execute(
            "SELECT event_id, status FROM outbox ORDER BY seq"))
    assert [r["status"] for r in rows] == ["SENT", "PENDING"]
    assert _row(ids[0])["status"] == "SENT"  # original untouched
    with pytest.raises(relay.RelayError):
        relay.replay_event("00000000-0000-0000-0000-000000000000",
                           approver="ops", reason="x")
