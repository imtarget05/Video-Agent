"""V-3 acceptance: outbox writer + single-transaction render enqueue.

Offline (SQLite twin): asserts the Neon path's SQL works before any Neon
credentials exist. Verifies: atomic insert of render_jobs + outbox,
idempotency replay without a second outbox row, and status updates.
"""
import sqlite3

import pytest

from backend.app.messaging import db, outbox as ox
from backend.app.messaging import envelope as env


@pytest.fixture()
def memdb(monkeypatch, tmp_path):
    """Isolated file DB per test (":memory:" gives a fresh DB per connection)."""
    url = f"sqlite:///{tmp_path}/ev.db"
    monkeypatch.setenv("EVENTING_DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL", url)
    assert db.ensure_schema(url) == "sqlite"
    yield url


def _envelope(job_id="job_1", event_id="0193f7a2-4b5c-7d8e-9f01-23456789abcd"):
    payload = {"job_id": job_id, "project_id": "p1", "aspect_ratio": "9:16",
               "total_duration_sec": 4.0,
               "manifest_ref": {"store": "r2", "uri": "manifests/job_1.json",
                                "sha256": "a" * 64, "bytes": 120}}
    return env.build_envelope(
        event_type="video.render.requested",
        producer="video/api",
        app="video",
        env="staging",
        correlation_id="tr-1",
        idempotency_key="render:job_1",
        payload=payload,
        payload_ref=None,
        schema_ref="video.render.commands.v1-value:1",
        event_id=event_id,
    )


def _job(job_id="job_1", key="render:job_1"):
    return {"job_id": job_id, "project_id": "p1", "aspect_ratio": "9:16",
            "total_duration_sec": 4.0, "idempotency_key": key,
            "provider": "remotion", "manifest_r2_key": "manifests/job_1.json"}


def _count(table):
    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
        return dict(cur.fetchone())["n"]


def test_enqueue_writes_job_and_outbox_atomically(memdb):
    result = ox.enqueue_render_requested(job=_job(), envelope=_envelope())
    assert result == {"job_id": "job_1", "replay": False}
    assert _count("render_jobs") == 1
    assert _count("outbox") == 1
    with db.connect() as conn:
        row = db.fetch_one_dict(
            conn.execute("SELECT event_type, topic, kafka_key, status FROM outbox"))
    assert row == {"event_type": "video.render.requested",
                   "topic": "video.render.commands.v1",
                   "kafka_key": "job_1", "status": "PENDING"}


def test_duplicate_idempotency_key_replays_without_second_outbox(memdb):
    first = ox.enqueue_render_requested(job=_job(), envelope=_envelope())
    second = ox.enqueue_render_requested(
        job=_job(), envelope=_envelope(
            event_id="0193f7a2-4b5c-7d8e-9f01-23456789abce"))
    assert first["replay"] is False
    assert second == {"job_id": "job_1", "replay": True}
    assert _count("render_jobs") == 1
    assert _count("outbox") == 1  # no second publish row


def test_read_and_status_roundtrip(memdb):
    ox.enqueue_render_requested(job=_job(), envelope=_envelope())
    assert ox.read_render_job("job_1")["status"] == "PENDING"
    assert ox.read_render_job("nope") is None
    ox.set_render_status("job_1", "RUNNING")
    assert ox.read_render_job("job_1")["status"] == "RUNNING"


def test_invalid_envelope_never_touches_db(memdb):
    bad = _envelope()
    bad.pop("event_id")
    with pytest.raises(env.EnvelopeError):
        ox.enqueue_render_requested(job=_job(), envelope=bad)
    assert _count("render_jobs") == 0
    assert _count("outbox") == 0


def test_ensure_schema_builds_all_five_tables(tmp_path):
    path = str(tmp_path / "ev.db")
    assert db.ensure_schema(f"sqlite:///{path}") == "sqlite"
    with db.connect(f"sqlite:///{path}") as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"outbox", "consumed_events", "retry_schedule",
            "external_ops", "render_jobs"} <= tables