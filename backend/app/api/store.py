"""
SQLite-backed project store (Slice A minimal).
"""
import json
import os
import sqlite3
from typing import Optional


def _db_backend(explicit: Optional[str] = None) -> str:
    """Plan 02: 'postgres' when no explicit path is given and DATABASE_URL
    is a postgres URL; explicit file paths (tests, local tools) always stay
    on SQLite."""
    if explicit:
        return "sqlite"
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgres"
    return "sqlite"


class ProjectStore:
    def __init__(self, db_path: Optional[str] = None):
        self._use_postgres = _db_backend(db_path) == "postgres"
        if self._use_postgres:
            self.db_path = os.environ["DATABASE_URL"]
        else:
            self.db_path = db_path or "data/projects.db"
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_db()

    def _pg_conn(self):
        """Plan 02: Neon connection (DDL/init only; query-method port is Plan 03)."""
        import psycopg

        return psycopg.connect(os.environ["DATABASE_URL"])

    def _conn(self) -> sqlite3.Connection:
        if self._use_postgres:
            return self._pg_conn()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # Shared durable-ops tables (Plan 02 contract). NOTE for WIP owners:
    # the render-job `jobs` table from in-flight work must reuse/extend this
    # generic `jobs` table in Plan 03 rather than redefining it.
    _PG_SHARED_DDL = """
    CREATE TABLE IF NOT EXISTS projects (
        project_id TEXT PRIMARY KEY,
        state_json TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS jobs (
        job_id           TEXT PRIMARY KEY,
        kind             TEXT NOT NULL DEFAULT '',
        status           TEXT NOT NULL DEFAULT 'queued',
        attempt          INTEGER NOT NULL DEFAULT 0,
        lease_expires_at TIMESTAMPTZ,
        input_ref        TEXT NOT NULL DEFAULT '',
        result_ref       TEXT NOT NULL DEFAULT '',
        error_class      TEXT NOT NULL DEFAULT '',
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS idempotency_keys (
        caller_scope TEXT NOT NULL,
        idem_key     TEXT NOT NULL,
        fingerprint  TEXT NOT NULL DEFAULT '',
        status       TEXT NOT NULL DEFAULT 'pending',
        response     TEXT NOT NULL DEFAULT '',
        expires_at   TIMESTAMPTZ,
        PRIMARY KEY (caller_scope, idem_key)
    );
    CREATE TABLE IF NOT EXISTS outbox_events (
        event_id      TEXT PRIMARY KEY,
        destination   TEXT NOT NULL DEFAULT '',
        payload       TEXT NOT NULL DEFAULT '',
        version       TEXT NOT NULL DEFAULT 'v1',
        attempts      INTEGER NOT NULL DEFAULT 0,
        next_retry_at TIMESTAMPTZ,
        delivered_at  TIMESTAMPTZ
    );
    CREATE TABLE IF NOT EXISTS dead_letters (
        job_id          TEXT PRIMARY KEY,
        input_ref       TEXT NOT NULL DEFAULT '',
        diagnosis       TEXT NOT NULL DEFAULT '',
        owner           TEXT NOT NULL DEFAULT '',
        replay_decision TEXT NOT NULL DEFAULT 'pending'
    );
    CREATE TABLE IF NOT EXISTS audit_events (
        id         BIGSERIAL PRIMARY KEY,
        actor      TEXT NOT NULL DEFAULT '',
        action     TEXT NOT NULL DEFAULT '',
        object     TEXT NOT NULL DEFAULT '',
        request_id TEXT NOT NULL DEFAULT '',
        outcome    TEXT NOT NULL DEFAULT '',
        reason     TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS model_registry (
        version        TEXT PRIMARY KEY,
        fingerprint    TEXT NOT NULL DEFAULT '',
        corpus_version TEXT NOT NULL DEFAULT '',
        status         TEXT NOT NULL DEFAULT 'staged',
        promoted_at    TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
    CREATE INDEX IF NOT EXISTS idx_outbox_next_retry ON outbox_events (next_retry_at)
        WHERE delivered_at IS NULL;
    """

    def _init_db(self):
        if self._use_postgres:
            with self._pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(self._PG_SHARED_DDL)
                conn.commit()
            return
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    def save(self, project_id: str, state_dict: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO projects (project_id, state_json) VALUES (?, ?);",
                (project_id, json.dumps(state_dict, default=str)),
            )
            conn.commit()

    def load(self, project_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT state_json FROM projects WHERE project_id = ?;", (project_id,)).fetchone()
        return json.loads(row["state_json"]) if row else None

    def list_ids(self) -> list:
        with self._conn() as conn:
            return [r[0] for r in conn.execute("SELECT project_id FROM projects;").fetchall()]
