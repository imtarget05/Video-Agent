"""Relay: PENDING outbox -> Kafka publish -> SENT/DEAD (foundation §2.3, V-4).

The publisher is injected, so unit tests run with a deterministic double and
NO broker is required. Relay dedupes on outbox.event_id UNIQUE: a timeout
that actually wrote is harmless because the consumer dedupes by event_id
(foundation §2.3.4).

Only this module may call `produce()` — see spec §2.4 no-dual-write rule.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from backend.app.messaging import db

MAX_ATTEMPTS = 10
BACKOFF_SECONDS = (1, 5, 30, 300, 1800)
INFLIGHT_TIMEOUT_SECONDS = 300

Publisher = Callable[[str, str, bytes, Dict[str, str]], None]


class RelayError(RuntimeError):
    pass


def _loads(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _backoff(attempts: int) -> float:
    return BACKOFF_SECONDS[min(max(attempts - 1, 0), len(BACKOFF_SECONDS) - 1)]


def claim_batch(limit: int = 50, url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Claim due rows. Postgres uses SKIP LOCKED; sqlite demo is single-process."""
    d = db.dialect(url)
    ph = "%s" if d == "postgres" else "?"
    with db.connect(url) as conn:
        cur = conn.cursor()
        if d == "postgres":
            cur.execute(
                "SELECT * FROM outbox "
                "WHERE status IN ('PENDING','FAILED') AND next_attempt_at <= now() "
                "ORDER BY seq LIMIT %s FOR UPDATE SKIP LOCKED",
                (limit,),
            )
        else:
            cur.execute(
                "SELECT * FROM outbox "
                "WHERE status IN ('PENDING','FAILED') "
                "AND next_attempt_at <= datetime('now') "
                "ORDER BY seq LIMIT ?",
                (limit,),
            )
        rows = db.fetch_all_dicts(cur)
        if not rows:
            return []
        ids = [r["seq"] for r in rows]
        marks = ", ".join([ph] * len(ids))
        cur.execute(
            f"UPDATE outbox SET status = {ph} WHERE seq IN ({marks})",
            (["INFLIGHT", *ids]),
        )
        conn.commit()
        return rows


def mark_sent(seq: int, url: Optional[str] = None) -> None:
    d = db.dialect(url)
    with db.connect(url) as conn:
        if d == "postgres":
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE outbox SET status='SENT', published_at=now() "
                    "WHERE seq=%s", (seq,),
                )
        else:
            conn.execute(
                "UPDATE outbox SET status='SENT', "
                "published_at=datetime('now') WHERE seq=?", (seq,),
            )
        conn.commit()


def mark_failed(seq: int, attempts: int, url: Optional[str] = None) -> Dict[str, Any]:
    """Backoff, or DEAD after MAX_ATTEMPTS. Returns the row's next state."""
    d = db.dialect(url)
    if attempts >= MAX_ATTEMPTS:
        with db.connect(url) as conn:
            ph = "%s" if d == "postgres" else "?"
            if d == "postgres":
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE outbox SET status={ph} WHERE seq={ph}",
                        ("DEAD", seq),
                    )
            else:
                conn.execute(
                    "UPDATE outbox SET status=? WHERE seq=?", ("DEAD", seq),
                )
            conn.commit()
        return {"status": "DEAD", "attempts": attempts}
    delay = _backoff(attempts)
    with db.connect(url) as conn:
        if d == "postgres":
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE outbox SET status='FAILED', publish_attempts=%s, "
                    "next_attempt_at=now() + make_interval(secs => %s) "
                    "WHERE seq=%s",
                    (attempts, delay, seq),
                )
        else:
            conn.execute(
                "UPDATE outbox SET status='FAILED', publish_attempts=?, "
                f"next_attempt_at=datetime('now', '+{delay:.0f} seconds') "
                "WHERE seq=?",
                (attempts, seq),
            )
        conn.commit()
    return {"status": "FAILED", "attempts": attempts, "backoff_s": delay}


def reclaim_inflight(url: Optional[str] = None,
                     timeout_s: int = INFLIGHT_TIMEOUT_SECONDS) -> int:
    """Crash recovery: INFLIGHT older than timeout goes back to PENDING."""
    d = db.dialect(url)
    with db.connect(url) as conn:
        if d == "postgres":
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE outbox SET status='PENDING' "
                    "WHERE status='INFLIGHT' "
                    "AND created_at < now() - make_interval(secs => %s)",
                    (timeout_s,),
                )
                n = cur.rowcount
        else:
            cur = conn.execute(
                "UPDATE outbox SET status='PENDING' "
                "WHERE status='INFLIGHT' "
                f"AND created_at < datetime('now', '-{timeout_s:.0f} seconds')",
            )
            n = cur.rowcount
        conn.commit()
        return n


def run_once(publish: Publisher, limit: int = 50,
             url: Optional[str] = None) -> Dict[str, int]:
    """One relay pass: claim -> publish -> mark. Returns a summary.

    `publish(topic, key, payload_bytes, headers)` may raise; failures are
    recorded as FAILED/DEAD, never lost, never half-marked.
    """
    claimed = claim_batch(limit=limit, url=url)
    summary = {"claimed": len(claimed), "sent": 0, "failed": 0, "dead": 0}
    for row in claimed:
        try:
            headers = _loads(row["headers"])
            payload = row["envelope"]
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            publish(row["topic"], row["kafka_key"], payload, headers)
        except Exception:
            state = mark_failed(row["seq"], int(row["publish_attempts"]) + 1, url=url)
            summary["failed" if state["status"] == "FAILED" else "dead"] += 1
            continue
        mark_sent(row["seq"], url=url)
        summary["sent"] += 1
    return summary


def replay_event(event_id: str, approver: str, reason: str,
                 url: Optional[str] = None) -> Dict[str, Any]:
    """Safe re-publish: copy a SENT row into a NEW outbox row (spec §2.3.5).

    Fresh event_id + replay_of header; the original row is never modified.
    """
    import uuid

    from backend.app.messaging import envelope as env

    d = db.dialect(url)
    ph = "%s" if d == "postgres" else "?"
    with db.connect(url) as conn:
        cur = conn.cursor() if d == "sqlite" else conn.cursor()
        cur.execute(f"SELECT * FROM outbox WHERE event_id = {ph}", (event_id,))
        source = db.fetch_one_dict(cur)
        if source is None or source["status"] != "SENT":
            raise RelayError(f"only SENT rows can be replayed: {event_id}")
        new_id = str(uuid.uuid4())
        headers = _loads(source["headers"])
        headers.update({"replay_of": event_id, "approved_by": approver,
                        "replay_reason": reason,
                        "replayed_at": datetime.now(timezone.utc).isoformat()})
        cur.execute(
            f"INSERT INTO outbox (event_id, event_type, topic, kafka_key, "
            f"headers, envelope) VALUES "
            f"({', '.join([ph] * 6)})",
            (new_id, source["event_type"], source["topic"], source["kafka_key"],
             json.dumps(headers), source["envelope"]),
        )
        conn.commit()
        audit = {"event_id": env.new_event_id(), "action": "outbox_replay",
                 "event_ref": new_id, "approver": approver, "reason": reason}
        return {"event_id": new_id, "replay_of": event_id, "audit": audit}