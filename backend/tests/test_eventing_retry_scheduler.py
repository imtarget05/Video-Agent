"""V-5 acceptance: retry scheduler + DLQ via outbox (foundation §4.3).

T4: three transient failures → SCHEDULED rows; scheduler enqueues NEW outbox
events (fresh event_id, retry_of header) — consumer never blocks.
T5: after MAX_ATTEMPTS the scheduler enqueues the DLQ event instead.
T12: scheduler crash safety — dispatch marks ENQUEUED and inserts outbox in
one transaction; a crash leaves either both or neither.
"""
import pytest

from backend.app.messaging import db, outbox as ox
from backend.app.messaging import envelope as env
from backend.app.messaging import relay, retry_scheduler as rs


@pytest.fixture()
def eventing_db(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path}/sched.db"
    monkeypatch.setenv("EVENTING_DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL", url)
    assert db.ensure_schema(url) == "sqlite"
    yield url


def _source_envelope(event_id="0193f7a2-4b5c-7d8e-9f01-23456789abcd"):
    return {
        "event_id": event_id,
        "event_type": "video.render.requested",
        "topic": "video.render.commands.v1",
        "kafka_key": "job_1",
        "headers": {"idempotency_key": "render:job_1"},
        "schema_ref": "video.render.commands.v1-value:1",
    }


def test_schedule_retry_records_scheduled_row(eventing_db):
    result = rs.schedule_retry(
        event_id=_source_envelope()["event_id"],
        source_envelope=_source_envelope(),
        attempt=1,
    )
    assert result["retry_topic"] == "video.render.retry.v1"
    assert result["delay_s"] == 1
    with db.connect() as conn:
        row = db.fetch_one_dict(conn.execute("SELECT * FROM retry_schedule"))
    assert row["status"] == "SCHEDULED"
    assert row["attempt"] == 1


def test_schedule_retry_rejects_attempt_beyond_max(eventing_db):
    with pytest.raises(rs.SchedulerError):
        rs.schedule_retry(event_id="0193f7a2-4b5c-7d8e-9f01-23456789abcd",
                          source_envelope=_source_envelope(), attempt=relay.MAX_ATTEMPTS + 2)


def _backdate(event_id):
    """Simulate elapsed backoff time (the scheduler only sees due rows)."""
    with db.connect() as conn:
        conn.execute("UPDATE retry_schedule SET due_at='2000-01-01 00:00:00' "
                     "WHERE event_id=?", (event_id,))
        conn.commit()


def test_due_dispatch_enqueues_new_outbox_with_retry_of(eventing_db):
    src = _source_envelope()
    rs.schedule_retry(event_id=src["event_id"], source_envelope=src, attempt=1)
    _backdate(src["event_id"])
    summary = rs.dispatch_due()
    assert summary == {"dispatched": 1, "dlq": 0}
    with db.connect() as conn:
        row = db.fetch_one_dict(conn.execute(
            "SELECT topic, kafka_key, status, envelope FROM outbox"))
        # ENQUEUED mark landed in the same dispatch pass
        scheduled = db.fetch_one_dict(conn.execute("SELECT status FROM retry_schedule"))
    assert row["topic"] == "video.render.retry.v1"
    assert row["kafka_key"] == "job_1"
    assert row["status"] == "PENDING"  # ready for the relay
    envelope = __import__("json").loads(row["envelope"])
    assert envelope["event_id"] != src["event_id"]  # NEW event_id
    assert scheduled["status"] == "ENQUEUED"


def test_max_attempt_dispatches_dlq_instead_of_retry(eventing_db):
    src = _source_envelope()
    rs.schedule_retry(event_id=src["event_id"], source_envelope=src,
                      attempt=relay.MAX_ATTEMPTS + 1)
    _backdate(src["event_id"])
    summary = rs.dispatch_due()
    assert summary == {"dispatched": 0, "dlq": 1}
    with db.connect() as conn:
        row = db.fetch_one_dict(conn.execute("SELECT topic FROM outbox"))
    assert row["topic"] == "video.render.dlq.v1"


def test_scheduler_crash_safety_no_duplicate_outbox(eventing_db):
    """T12: re-running dispatch on an ENQUEUED row is a no-op (no dup outbox)."""
    src = _source_envelope()
    rs.schedule_retry(event_id=src["event_id"], source_envelope=src, attempt=2)
    _backdate(src["event_id"])
    assert rs.dispatch_due() == {"dispatched": 1, "dlq": 0}
    assert rs.dispatch_due() == {"dispatched": 0, "dlq": 0}
    with db.connect() as conn:
        n = dict(conn.execute("SELECT COUNT(*) AS n FROM outbox").fetchone())["n"]
    assert n == 1
    with db.connect() as conn:
        scheduled = db.fetch_one_dict(
            conn.execute("SELECT status FROM retry_schedule"))
    assert scheduled["status"] == "ENQUEUED"


def test_dispatch_after_relay_roundtrip_reaches_retry_topic(eventing_db):
    """T4 end-to-end: schedule -> dispatch -> relay publishes to retry topic."""
    src = _source_envelope()
    rs.schedule_retry(event_id=src["event_id"], source_envelope=src, attempt=3)
    _backdate(src["event_id"])
    rs.dispatch_due()
    published = []
    summary = relay.run_once(lambda t, k, p, h: published.append((t, k)))
    assert summary["sent"] == 1
    assert published[0][0] == "video.render.retry.v1"
    assert published[0][1] == "job_1"