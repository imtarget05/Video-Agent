"""Consumer executor (plan V-5, foundation §4.2b).

Consumers decode one event, dedup via consumed_events, and commit their
offset ONLY after the side effect completed. For external operations
(render provider, webhook, etc.) the flow is:

    reserve operation + idempotency key in Neon
    → call external provider
    → persist outcome + consumed_event
    → commit offset

If the process crashed between execute and persist, a reconciler inspects
bag-of-envelopes and remote operation IDs rather than blindly retrying.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.app.messaging import db
from backend.app.messaging import outbox as ox


class ConsumerError(RuntimeError):
    pass


def mark_consumed(event_id: str, event_type: str, consumer: str,
                  url: Optional[str] = None) -> None:
    d = db.dialect(url)
    ph = "%s" if d == "postgres" else "?"
    with db.connect(url) as conn:
        cur = conn.execute(
            f"INSERT OR IGNORE INTO consumed_events (event_id, event_type, consumer) "
            f"VALUES ({ph}, {ph}, {ph})",
            (event_id, event_type, consumer),
        )
        conn.commit()


def already_consumed(event_id: str, url: Optional[str] = None) -> bool:
    d = db.dialect(url)
    ph = "%s" if d == "postgres" else "?"
    with db.connect(url) as conn:
        cur = conn.execute(
            f"SELECT 1 FROM consumed_events WHERE event_id = {ph} LIMIT 1",
            (event_id,),
        )
        return db.fetch_one_dict(cur) is not None


def process_render_requested(envelope: Dict[str, Any],
                             url: Optional[str] = None) -> Dict[str, Any]:
    job = _job_from_envelope(envelope)
    result = ox.enqueue_render_requested(job=job, envelope=envelope, url=url)
    return {"status": "queued", **result}


def _job_from_envelope(envelope: Dict[str, Any]) -> Dict[str, Any]:
    payload = envelope.get("payload") or {}
    headers = envelope.get("headers") or {}
    idempotency_key = headers.get("idempotency_key") or envelope.get("event_id")
    return {
        "job_id": payload.get("job_id") or f"job_{idempotency_key[:8]}",
        "project_id": payload.get("project_id", "p1"),
        "aspect_ratio": payload.get("aspect_ratio", "9:16"),
        "total_duration_sec": float(payload.get("total_duration_sec", 4.0)),
        "idempotency_key": idempotency_key,
        "provider": "remotion",
        "manifest_r2_key": (
            payload.get("manifest_ref", {}).get("uri")
            if payload.get("manifest_ref")
            else None
        ),
        "status": "PENDING",
    }


def process_dlq_event(envelope: Dict[str, Any],
                      url: Optional[str] = None) -> Dict[str, Any]:
    event_id = envelope.get("event_id")
    if not event_id:
        raise ConsumerError("dlq event missing event_id")
    d = db.dialect(url)
    ph = "%s" if d == "postgres" else "?"
    with db.connect(url) as conn:
        cur = conn.cursor()
        cur.execute(
            f"INSERT OR IGNORE INTO consumed_events (event_id, event_type, consumer) "
            f"VALUES ({ph}, {ph}, {ph})",
            (event_id, envelope.get("event_type"), "video-consumer"),
        )
        conn.commit()
        return {"status": "persisted", "event_id": event_id}


def consume_one(envelope: Dict[str, Any],
                url: Optional[str] = None) -> Dict[str, Any]:
    event_id = envelope.get("event_id")
    event_type = envelope.get("event_type")
    consumer = "video-consumer"
    if not event_id or not event_type:
        raise ConsumerError("envelope missing event_id or event_type")
    d = db.dialect(url)
    ph = "%s" if d == "postgres" else "?"
    with db.connect(url) as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM consumed_events WHERE event_id={ph} LIMIT 1", (event_id,))
        if db.fetch_one_dict(cur):
            result = {"status": "duplicate", "event_id": event_id}
            conn.commit()
            return result
        cur.execute(
            f"INSERT INTO consumed_events (event_id, event_type, consumer) "
            f"VALUES ({ph}, {ph}, {ph})",
            (event_id, event_type, consumer),
        )
        conn.commit()
    if event_type == "video.render.requested":
        return process_render_requested(envelope, url=url)
    elif event_type == "video.render.commands.dlq.v1":
        return process_dlq_event(envelope, url=url)
    else:
        raise ConsumerError(f"unknown event_type: {event_type}")
