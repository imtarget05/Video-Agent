"""Outbox writer: render_jobs + outbox rows in ONE transaction (plan §7, spec §2).

Callers pass an envelope built by messaging.envelope. This writer never
touches the network: publishing is the relay's job (foundation §2.3).
Relay deduplicates on outbox.event_id UNIQUE, so enqueue is safe to retry.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from backend.app.messaging import db


class OutboxError(RuntimeError):
    pass


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def enqueue_render_requested(
    *,
    job: Dict[str, Any],
    envelope: Dict[str, Any],
    topic: str = "video.render.commands.v1",
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert render_jobs + outbox(video.render.requested) atomically.

    Returns {"job_id", "replay": bool}. Duplicate idempotency_key returns the
    existing job WITHOUT writing a second outbox row (plan §9, T9 evidence).
    """
    from backend.app.messaging.envelope import validate_envelope

    validate_envelope(envelope)
    d = db.dialect(url)
    ph = db.qmarks(d, 1).split(", ")[0]
    with db.connect(url) as conn:
        cur = conn.cursor()
        existing = None
        if job.get("idempotency_key"):
            cur.execute(
                f"SELECT * FROM render_jobs WHERE idempotency_key = {ph}",
                (job["idempotency_key"],),
            )
            existing = db.fetch_one_dict(cur)
        if existing is not None:
            conn.rollback() if hasattr(conn, "rollback") else None
            return {"job_id": existing["job_id"], "replay": True}
        cols = (
            "job_id", "project_id", "aspect_ratio", "total_duration_sec",
            "idempotency_key", "status", "provider", "manifest_r2_key",
        )
        cur.execute(
            f"INSERT INTO render_jobs ({', '.join(cols)}) "
            f"VALUES ({db.qmarks(d, len(cols))})",
            (job["job_id"], job["project_id"], job["aspect_ratio"],
             float(job["total_duration_sec"]), job.get("idempotency_key"),
             "PENDING", job.get("provider", "remotion"),
             job.get("manifest_r2_key")),
        )
        cur.execute(
            f"INSERT INTO outbox "
            f"(event_id, event_type, topic, kafka_key, headers, envelope) "
            f"VALUES ({db.qmarks(d, 6)})",
            (envelope["event_id"], envelope["event_type"], topic,
             job["job_id"], _dump({"event_id": envelope["event_id"],
                                   "idempotency_key": envelope["idempotency_key"]}),
             _dump(envelope)),
        )
        conn.commit()
    return {"job_id": job["job_id"], "replay": False}


def read_render_job(job_id: str, url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Read a Neon render job; None when absent (API falls back to legacy)."""
    from backend.app.messaging import db as _db

    d = _db.dialect(url)
    ph = _db.qmarks(d, 1).split(", ")[0]
    with _db.connect(url) as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM render_jobs WHERE job_id = {ph}", (job_id,))
        return _db.fetch_one_dict(cur)


def set_render_status(job_id: str, status: str, *,
                      error: Optional[str] = None,
                      artifact_key: Optional[str] = None,
                      url: Optional[str] = None) -> None:
    d = db.dialect(url)
    ph = db.qmarks(d, 1).split(", ")[0]
    with db.connect(url) as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE render_jobs SET status = {ph}, error = {ph}, "
            f"artifact_key = {ph} WHERE job_id = {ph}",
            (status, error, artifact_key, job_id),
        )
        conn.commit()