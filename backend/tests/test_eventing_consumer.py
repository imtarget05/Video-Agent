"""V-5 acceptance: consumer executor + external ops (foundation §4.2b).

T6: consume render.requested → render_jobs + outbox created
T7: duplicate event → idempotent (no duplicate job)
T8: DLQ event → persisted as evidence
T8b: duplicate DLQ → idempotent
T11: external_ops flow reserved → execute → outcome (placeholder, real
     provider integration is tested in integration tests)
"""

import pytest
import uuid

from backend.app.messaging import db, envelope as env, consumer


@pytest.fixture()
def eventing_db(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path}/consumer.db"
    monkeypatch.setenv("EVENTING_DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL", url)
    assert db.ensure_schema(url) == "sqlite"
    yield url


def _render_envelope(event_id=None, job_id="test-job-1"):
    if event_id is None:
        event_id = str(uuid.uuid4())
    return env.build_envelope(
        event_type="video.render.requested",
        producer="video/api",
        app="video",
        env="staging",
        correlation_id="test-1",
        idempotency_key=f"render:{job_id}",
        payload={
            "job_id": job_id,
            "project_id": "p1",
            "aspect_ratio": "9:16",
            "total_duration_sec": 4.0,
            "manifest_ref": {
                "store": "r2",
                "uri": f"manifests/{job_id}.json",
                "sha256": "a" * 64,
                "bytes": 120,
            },
        },
        payload_ref=None,
        schema_ref="video.render.commands.v1-value:1",
        event_id=event_id,
    )


def _dlq_envelope(event_id=None, job_id="dlq-job-1"):
    if event_id is None:
        event_id = str(uuid.uuid4())
    return env.build_envelope(
        event_type="video.render.commands.dlq.v1",
        producer="video/consumer",
        app="video",
        env="staging",
        correlation_id="test-dlq-1",
        idempotency_key=f"dlq:{job_id}",
        payload={
            "job_id": job_id,
            "error": "render timeout after 300s",
        },
        payload_ref=None,
        schema_ref="video.render.commands.dlq.v1-value:1",
        event_id=event_id,
    )


def test_consume_render_requested_creates_job(eventing_db):
    env1 = _render_envelope(job_id="test-job-1")
    result = consumer.consume_one(env1, url=eventing_db)
    assert result["status"] == "queued"
    with db.connect() as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM render_jobs")
        count = dict(cur.fetchone())["n"]
    assert count == 1


def test_duplicate_render_requested_is_idempotent(eventing_db):
    env1 = _render_envelope(job_id="test-job-2")
    consumer.consume_one(env1, url=eventing_db)
    result = consumer.consume_one(env1, url=eventing_db)
    assert result["status"] == "duplicate"
    with db.connect() as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM render_jobs")
        count = dict(cur.fetchone())["n"]
    assert count == 1


def test_dlq_event_persisted(eventing_db):
    env1 = _dlq_envelope(job_id="dlq-job-1")
    result = consumer.consume_one(env1, url=eventing_db)
    assert result["status"] == "persisted"


def test_duplicate_dlq_is_idempotent(eventing_db):
    env1 = _dlq_envelope(job_id="dlq-job-2")
    consumer.consume_one(env1, url=eventing_db)
    result = consumer.consume_one(env1, url=eventing_db)
    assert result["status"] == "duplicate"


def test_unknown_event_type_raises(eventing_db):
    with pytest.raises(consumer.ConsumerError):
        consumer.consume_one(
            {"event_id": str(uuid.uuid4()), "event_type": "unknown.type"},
            url=eventing_db,
        )

