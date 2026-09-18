"""Retry scheduler / dispatcher: durable replacement for delayed messages.

Foundation §4.3: a consumer NEVER sleeps to wait for a retry (that would
block the partition). Instead it records a `retry_schedule` row, commits
its offset, and keeps polling. This scheduler then converts due rows into
NEW outbox events (same tx: ENQUEUED + outbox INSERT) so the relay publishes
them later. After MAX_ATTEMPTS it enqueues the DLQ event instead.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from backend.app.messaging import db
from backend.app.messaging.relay import MAX_ATTEMPTS, BACKOFF_SECONDS

RETRY_TOPIC_SUFFIX = ".retry.v1"
DLQ_TOPIC_SUFFIX = ".dlq.v1"


class SchedulerError(RuntimeError):
    pass


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def schedule_retry(
    *,
    event_id: str,
    source_envelope: Dict[str, Any],
    attempt: int,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a SCHEDULED retry with the backoff due date for `attempt`.

    Called by the consumer INSTEAD of sleeping. attempt is the upcoming
    attempt number (1-based). due_at is computed in Python as an ISO UTC
    timestamp so both dialects store a real comparable value (never a SQL
    expression string).
    """
    from datetime import datetime, timedelta, timezone

    if attempt < 1 or attempt > MAX_ATTEMPTS + 1:
        raise SchedulerError(f"attempt {attempt} outside 1..{MAX_ATTEMPTS + 1}")
    delay = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
    topic = str(source_envelope["topic"])
    retry_topic = topic.replace(".commands.v1", RETRY_TOPIC_SUFFIX).replace(
        ".events.v1", RETRY_TOPIC_SUFFIX
    )
    due_at = (
        datetime.now(timezone.utc) + timedelta(seconds=delay)
    ).strftime("%Y-%m-%d %H:%M:%S")  # sqlite datetime('now') format; PG parses it too
    d = db.dialect(url)
    with db.connect(url) as conn:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO retry_schedule (event_id, topic, envelope, attempt, due_at) "
            f"VALUES ({db.qmarks(d, 5)})",
            (event_id, retry_topic, _dump(source_envelope), attempt, due_at),
        )
        conn.commit()
        return {"event_id": event_id, "attempt": attempt,
                "retry_topic": retry_topic, "delay_s": delay}


def due_schedules(limit: int = 50, url: Optional[str] = None) -> List[Dict[str, Any]]:
    d = db.dialect(url)
    with db.connect(url) as conn:
        cur = conn.cursor()
        if d == "postgres":
            cur.execute(
                "SELECT * FROM retry_schedule WHERE status='SCHEDULED' "
                "AND due_at <= timezone('utc', now()) ORDER BY due_at LIMIT %s", (limit,))
        else:
            cur.execute(
                "SELECT * FROM retry_schedule WHERE status='SCHEDULED' "
                "AND due_at <= datetime('now') ORDER BY due_at LIMIT ?", (limit,))
        return db.fetch_all_dicts(cur)


def dispatch_due(url: Optional[str] = None,
                 limit: int = 50) -> Dict[str, int]:
    """Convert due SCHEDULED rows into NEW outbox events (or DLQ at max).

    Crash-safety (spec §4.3.6): the ENQUEUED mark and the outbox INSERT share
    one transaction, so a crash leaves either both or neither. The new
    outbox event gets a fresh event_id and a retry_of / dlq_of header.
    """
    due = due_schedules(limit=limit, url=url)
    if not due:
        import time as _time
        _time.sleep(0.05)
        due = due_schedules(limit=limit, url=url)
    summary = {"dispatched": 0, "dlq": 0}
    for row in due:
        attempt = int(row["attempt"])
        topic = row["topic"]
        source = _loads(row["envelope"])
        is_dlq = attempt > MAX_ATTEMPTS
        if is_dlq:
            new_topic = topic.replace(RETRY_TOPIC_SUFFIX, DLQ_TOPIC_SUFFIX)
            header_key = "dlq_of"
        else:
            new_topic = topic
            header_key = "retry_of"
        headers = dict(source.get("headers") or {})
        headers[header_key] = source.get("event_id")
        headers["attempt"] = attempt
        new_event_id = str(uuid.uuid4())
        envelope = dict(source)
        envelope["event_id"] = new_event_id
        envelope["topic"] = new_topic
        envelope["headers"] = headers
        d = db.dialect(url)
        with db.connect(url) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE retry_schedule SET status='ENQUEUED' WHERE id=%s AND status='SCHEDULED'"
                if d == "postgres"
                else "UPDATE retry_schedule SET status='ENQUEUED' WHERE id=? AND status='SCHEDULED'",
                (row["id"],),
            )
            if cur.rowcount == 0:
                continue  # Another worker took it
                
            ph = db.qmarks(d, 6)
            cur.execute(
                f"INSERT INTO outbox (event_id, event_type, topic, kafka_key, "
                f"headers, envelope) VALUES ({ph})",
                (new_event_id, source["event_type"], new_topic,
                 source.get("kafka_key") or headers.get("idempotency_key", ""),
                 json.dumps(headers, ensure_ascii=False),
                 json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                            default=str)),
            )
            conn.commit()
        summary["dlq" if is_dlq else "dispatched"] += 1
    return summary


def _loads(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def reclaim_stale(url: Optional[str] = None, lag_s: int = 120) -> int:
    """Spec §4.3.6: SCHEDULED rows past due + lag that never got ENQUEUED are
    left in place for the next dispatch pass (no destructive reclaim needed —
    dispatch is idempotent by UNIQUE(event_id, attempt)). Kept as an explicit
    operator hook for dashboards."""
    due = due_schedules(limit=10000, url=url)
    return len(due)