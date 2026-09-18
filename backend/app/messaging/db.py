"""Database access for the eventing path (foundation §2, plan §2, task V-3).

Dialect twins (repo convention): SQLite twin for tests/local, Postgres twin
for Neon. The DB itself guarantees exactly-once outbox semantics (SKIP LOCKED
claim, UNIQUE constraints); this module only adapts SQL text per dialect.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple


def eventing_db_url() -> str:
    """Dedicated URL for the eventing path; falls back to DATABASE_URL."""
    return (
        os.environ.get("EVENTING_DATABASE_URL", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
    )


def dialect(url: Optional[str] = None) -> str:
    url = (url if url is not None else eventing_db_url()).strip()
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgres"
    return "sqlite"


def sqlite_path(url: Optional[str] = None) -> str:
    url = (url if url is not None else eventing_db_url()).strip()
    if url.startswith("sqlite:////"):
        # Absolute path: sqlite:////tmp/x.db -> /tmp/x.db
        return "/" + url[len("sqlite:////"):].lstrip("/")
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    if url.startswith("sqlite://"):
        return url[len("sqlite://"):]
    if url == "sqlite:///:memory:":
        return ":memory:"
    if url and not url.startswith("sqlite"):
        return os.environ.get("SQLITE_FALLBACK_PATH", "data/video_eventing.db")
    return os.environ.get("EVENTING_DB_PATH", "data/video_eventing.db")


@contextmanager
def connect(url: Optional[str] = None) -> Iterator[Any]:
    """Yield a DB-API connection with dict-like rows on fetch."""
    if dialect(url) == "postgres":
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(url or eventing_db_url(), row_factory=dict_row)
        try:
            yield conn
        finally:
            conn.close()
        return
    path = sqlite_path(url)
    if path != ":memory:":
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def qmarks(d: str, n: int) -> str:
    return ", ".join(["%s"] * n) if d == "postgres" else ", ".join(["?"] * n)


def now_sql(d: str) -> str:
    return "now()" if d == "postgres" else "datetime('now')"


def fetch_all_dicts(cursor: Any) -> List[Dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def fetch_one_dict(cursor: Any) -> Optional[Dict[str, Any]]:
    row = cursor.fetchone()
    return dict(row) if row is not None else None


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
  seq              INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id         TEXT NOT NULL UNIQUE,
  event_type       TEXT NOT NULL,
  topic            TEXT NOT NULL,
  kafka_key        TEXT NOT NULL,
  headers          TEXT NOT NULL DEFAULT '{}',
  envelope         TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'PENDING'
                   CHECK (status IN ('PENDING','INFLIGHT','SENT','FAILED','DEAD')),
  publish_attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at  TEXT NOT NULL DEFAULT (datetime('now')),
  published_at     TEXT,
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS outbox_due_idx ON outbox (status, next_attempt_at, seq)
  WHERE status IN ('PENDING','FAILED');

CREATE TABLE IF NOT EXISTS consumed_events (
  event_id    TEXT PRIMARY KEY,
  event_type  TEXT NOT NULL,
  consumer    TEXT NOT NULL,
  consumed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS retry_schedule (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id   TEXT NOT NULL,
  topic      TEXT NOT NULL,
  envelope   TEXT NOT NULL,
  attempt    INTEGER NOT NULL,
  due_at     TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'SCHEDULED'
             CHECK (status IN ('SCHEDULED','ENQUEUED','CANCELLED')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  CONSTRAINT retry_schedule_event_attempt_key UNIQUE (event_id, attempt)
);
CREATE INDEX IF NOT EXISTS retry_due_idx ON retry_schedule (status, due_at)
  WHERE status = 'SCHEDULED';

CREATE TABLE IF NOT EXISTS external_ops (
  operation_key       TEXT PRIMARY KEY,
  event_id            TEXT NOT NULL,
  provider            TEXT NOT NULL,
  remote_operation_id TEXT,
  status              TEXT NOT NULL DEFAULT 'RESERVED'
                      CHECK (status IN ('RESERVED','SUCCEEDED','FAILED')),
  response_sha256     TEXT,
  reconcile_basis     TEXT,
  attempts            INTEGER NOT NULL DEFAULT 0,
  created_at          TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS external_ops_stuck_idx
  ON external_ops (status, updated_at) WHERE status = 'RESERVED';

CREATE TABLE IF NOT EXISTS render_jobs (
  job_id              TEXT PRIMARY KEY,
  project_id          TEXT NOT NULL,
  aspect_ratio        TEXT NOT NULL,
  total_duration_sec  REAL NOT NULL,
  idempotency_key     TEXT UNIQUE,
  status              TEXT NOT NULL CHECK (status IN
                        ('PENDING','RUNNING','SUCCEEDED','FAILED')),
  provider            TEXT NOT NULL DEFAULT 'remotion',
  remote_operation_id TEXT,
  manifest_r2_key     TEXT,
  artifact_key        TEXT,
  error               TEXT,
  created_at          TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS render_jobs_status_idx
  ON render_jobs (status, updated_at DESC);
"""


def ensure_schema(url: Optional[str] = None) -> str:
    """Create eventing tables via the committed migration (postgres) or twin.

    Postgres executes 001_eventing.sql VERBATIM so the live schema can never
    drift from the reviewed file. SQLite has no psql runner here, so it
    applies the equivalent twin DDL above (same 5 tables/constraints).
    """
    from pathlib import Path

    if dialect(url) == "postgres":
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations" / "001_eventing.sql"
        )
        with connect(url) as conn, conn.cursor() as cur:
            cur.execute(migration.read_text(encoding="utf-8"))
            conn.commit()
        return "postgres"
    with connect(url) as conn:
        conn.executescript(SQLITE_SCHEMA)
        conn.commit()
    return "sqlite"

