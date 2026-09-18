"""
SQLite-backed durable records (Slice A jobs/projects + Slice C webhooks).

Replaces the process-local PROJECTS_STORE / JOBS_STORE dictionaries so
projects, jobs, subscriptions, and delivery receipts survive a module reload
or process restart. One table per record kind; JSON payload columns only
(no pickled executables).
"""
import json
import os
import sqlite3
import threading
from typing import Optional


def _db_path(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    if url.startswith("sqlite://"):
        return url[len("sqlite://"):]
    if url and not url.startswith("sqlite"):
        return os.environ.get("SQLITE_FALLBACK_PATH", "data/projects.db")
    return os.environ.get("PROJECTS_DB_PATH", "data/projects.db")


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


_lock = threading.Lock()


class ProjectStore:
    """Durable project/job/subscription/receipt records (SQLite, stdlib only)."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = _db_path(db_path)
        self._use_postgres = _db_backend(db_path) == "postgres"
        self._mem_conn = None
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    def _pg_conn(self):
        """Plan 02: Neon connection (DDL/init only; query-method port is Plan 03)."""
        import psycopg

        return psycopg.connect(os.environ["DATABASE_URL"])

    def _conn(self) -> sqlite3.Connection:
        if getattr(self, "_use_postgres", False):
            return self._pg_conn()
        if self.db_path == ":memory:":
            # sqlite creates an empty schema per connection for in-memory DBs;
            # keep one persistent connection so the singleton stays usable.
            if getattr(self, "_mem_conn", None) is None:
                self._mem_conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._mem_conn.row_factory = sqlite3.Row
            return self._mem_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _with_schema(self, fn):
        """Run a DB operation; self-heal once if the schema went missing."""
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            self._init_db()
            return fn()

    # Shared durable-ops tables (Plan 02 contract). The render-job `jobs`
    # table above IS this project's jobs table (Plan 03 adds lease columns
    # to it); the five tables below are the remaining shared names.
    _PG_SHARED_DDL = """
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
    CREATE INDEX IF NOT EXISTS idx_outbox_next_retry ON outbox_events (next_retry_at)
        WHERE delivered_at IS NULL;
    """

    def _init_db(self):
        if getattr(self, "_use_postgres", False):
            with _lock, self._pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(self._PG_SHARED_DDL)
                conn.commit()
            return
        with _lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL DEFAULT '',
                    duration_sec REAL NOT NULL DEFAULT 0,
                    provider TEXT NOT NULL DEFAULT 'mock',
                    provider_job_id TEXT,
                    mode TEXT NOT NULL DEFAULT 'mock',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    idempotency_key TEXT,
                    artifact_key TEXT,
                    error TEXT,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    lease_expires_at TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS dead_letters (
                    job_id TEXT PRIMARY KEY,
                    input_ref TEXT NOT NULL DEFAULT '',
                    diagnosis TEXT NOT NULL DEFAULT '',
                    owner TEXT NOT NULL DEFAULT '',
                    replay_decision TEXT NOT NULL DEFAULT 'pending'
                );
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id TEXT PRIMARY KEY,
                    destination TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT 'v1',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT NOT NULL DEFAULT '',
                    delivered_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS webhook_subscriptions (
                    url TEXT PRIMARY KEY,
                    secret_ref TEXT NOT NULL DEFAULT '',
                    events_json TEXT NOT NULL DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS delivery_receipts (
                    idempotency_key TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    event TEXT NOT NULL DEFAULT '',
                    ok INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    status_code INTEGER,
                    error TEXT,
                    delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            for col, ddl in (
                ("provider_job_id", "ALTER TABLE jobs ADD COLUMN provider_job_id TEXT"),
                ("mode", "ALTER TABLE jobs ADD COLUMN mode TEXT NOT NULL DEFAULT 'mock'"),
                ("idempotency_key", "ALTER TABLE jobs ADD COLUMN idempotency_key TEXT"),
                ("artifact_key", "ALTER TABLE jobs ADD COLUMN artifact_key TEXT"),
                ("error", "ALTER TABLE jobs ADD COLUMN error TEXT"),
                ("cost_usd", "ALTER TABLE jobs ADD COLUMN cost_usd REAL NOT NULL DEFAULT 0"),
                ("attempt", "ALTER TABLE jobs ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0"),
                ("lease_expires_at", "ALTER TABLE jobs ADD COLUMN lease_expires_at TEXT NOT NULL DEFAULT ''"),
            ):
                try:
                    if col not in cols:
                        conn.execute(ddl)
                except Exception:
                    pass
            conn.commit()

    # -- jobs ---------------------------------------------------------------
    def create_job(self, job: dict) -> dict:
        def _op():
            with _lock, self._conn() as conn:
                if job.get("idempotency_key"):
                    existing = conn.execute(
                        "SELECT * FROM jobs WHERE idempotency_key = ?;",
                        (job["idempotency_key"],)).fetchone()
                    if existing is not None:
                        return dict(existing)
                conn.execute(
                    """INSERT OR IGNORE INTO jobs
                       (job_id, prompt, duration_sec, provider, provider_job_id, mode,
                        status, idempotency_key, artifact_key, error, cost_usd)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (job.get("job_id"), job.get("prompt", ""), float(job.get("duration_sec", 0)),
                     job.get("provider", "mock"), job.get("provider_job_id"),
                     job.get("mode", "mock"), job.get("status", "PENDING"),
                     job.get("idempotency_key"), job.get("artifact_key"),
                     job.get("error"), float(job.get("cost_usd", 0))),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM jobs WHERE job_id = ?;",
                                   (job.get("job_id"),)).fetchone()
                return dict(row) if row else dict(job)
        return self._with_schema(_op)

    def get_job(self, job_id: str) -> Optional[dict]:
        def _op():
            with self._conn() as conn:
                row = conn.execute("SELECT * FROM jobs WHERE job_id = ?;", (job_id,)).fetchone()
            return dict(row) if row else None
        return self._with_schema(_op)

    def claim_job(self, lease_seconds: int = 60) -> Optional[dict]:
        """Atomically claim one PENDING job (or an expired lease). One winner.

        Render jobs are the only kind in this table. Uses a conditional
        UPDATE + rowcount check so concurrent claimants cannot double-claim.
        """
        import datetime as _dt

        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        lease = (
            _dt.datetime.now(_dt.timezone.utc)
            + _dt.timedelta(seconds=lease_seconds)
        ).isoformat()

        def _op():
            with _lock, self._conn() as conn:
                cand = conn.execute(
                    "SELECT job_id, attempt FROM jobs WHERE status = 'PENDING'"
                    " OR (status = 'RUNNING' AND lease_expires_at < ?)"
                    " ORDER BY created_at LIMIT 1;",
                    (now,),
                ).fetchone()
                if cand is None:
                    return None
                cur = conn.execute(
                    "UPDATE jobs SET status = 'RUNNING', attempt = attempt + 1,"
                    " lease_expires_at = ?, updated_at = CURRENT_TIMESTAMP"
                    " WHERE job_id = ? AND (status = 'PENDING'"
                    " OR (status = 'RUNNING' AND lease_expires_at < ?));",
                    (lease, cand["job_id"], now),
                )
                conn.commit()
                if cur.rowcount != 1:
                    return None
            return self.get_job(cand["job_id"])

        return self._with_schema(_op)

    def mark_dead(self, job_id: str, diagnosis: str, owner: str = "render-worker") -> Optional[dict]:
        """Terminal failure: status DEAD + dead_letters row + outbox event."""
        import json as _json

        def _op():
            with _lock, self._conn() as conn:
                conn.execute(
                    "UPDATE jobs SET status = 'DEAD', error = ?,"
                    " updated_at = CURRENT_TIMESTAMP WHERE job_id = ?;",
                    (diagnosis[:500], job_id),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO dead_letters"
                    " (job_id, input_ref, diagnosis, owner, replay_decision)"
                    " VALUES (?, ?, ?, ?, 'pending');",
                    (job_id, job_id, diagnosis[:500], owner),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO outbox_events"
                    " (event_id, destination, payload, version, attempts,"
                    " next_retry_at, delivered_at)"
                    " VALUES (?, 'render-jobs', ?, 'v1', 0, '', '');",
                    (
                        f"job-dead:{job_id}",
                        _json.dumps({"job_id": job_id, "diagnosis": diagnosis[:500]}),
                    ),
                )
                conn.commit()
            return self.get_job(job_id)

        return self._with_schema(_op)

    def record_outbox(self, event_id: str, destination: str, payload: dict) -> None:
        """Terminal-state outbox event (Plan 03)."""
        import json as _json

        def _op():
            with _lock, self._conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO outbox_events"
                    " (event_id, destination, payload, version, attempts,"
                    " next_retry_at, delivered_at)"
                    " VALUES (?, ?, ?, 'v1', 0, '', '');",
                    (event_id, destination, _json.dumps(payload, default=str)),
                )
                conn.commit()

        return self._with_schema(_op)

    def replay_job(self, job_id: str, operator: str) -> Optional[dict]:
        """Operator-only replay: DEAD -> PENDING with attempt reset,
        preserving the dead_letters evidence trail."""

        def _op():
            with _lock, self._conn() as conn:
                conn.execute(
                    "UPDATE dead_letters SET replay_decision = ? WHERE job_id = ?;",
                    (f"replayed:{operator}", job_id),
                )
                conn.execute(
                    "UPDATE jobs SET status = 'PENDING', attempt = 0,"
                    " error = '', updated_at = CURRENT_TIMESTAMP"
                    " WHERE job_id = ? AND status = 'DEAD';",
                    (job_id,),
                )
                conn.commit()
            return self.get_job(job_id)

        return self._with_schema(_op)

    def update_job(self, job_id: str, **fields) -> Optional[dict]:
        allowed = {"prompt", "duration_sec", "provider", "provider_job_id", "mode",
                   "status", "artifact_key", "error", "cost_usd",
                   "attempt", "lease_expires_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_job(job_id)

        def _op():
            with _lock, self._conn() as conn:
                conn.execute(
                    f"UPDATE jobs SET {', '.join(f'{k} = ?' for k in updates)},"
                    " updated_at = CURRENT_TIMESTAMP WHERE job_id = ?;",
                    (*updates.values(), job_id),
                )
                conn.commit()
            return self.get_job(job_id)
        return self._with_schema(_op)

    # -- webhook subscriptions ----------------------------------------------
    def save_subscription(self, url: str, secret_ref: str, events: list) -> dict:
        with _lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO webhook_subscriptions (url, secret_ref, events_json)
                   VALUES (?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET secret_ref = excluded.secret_ref,
                       events_json = excluded.events_json;""",
                (url, secret_ref, json.dumps(events or ["project.completed"])),
            )
            conn.commit()
        return {"url": url, "events": events or ["project.completed"]}

    def list_subscriptions(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT url, events_json FROM webhook_subscriptions;").fetchall()
        return [{"url": r["url"], "events": json.loads(r["events_json"])} for r in rows]

    # -- delivery receipts (idempotent) --------------------------------------
    def get_receipt(self, idempotency_key: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_receipts WHERE idempotency_key = ?;",
                (idempotency_key,)).fetchone()
        return dict(row) if row else None

    def save_receipt(self, receipt: dict) -> dict:
        with _lock, self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM delivery_receipts WHERE idempotency_key = ?;",
                (receipt.get("idempotency_key"),)).fetchone()
            if existing is not None:
                return dict(existing)
            conn.execute(
                """INSERT OR IGNORE INTO delivery_receipts
                   (idempotency_key, url, event, ok, attempts, status_code, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?);""",
                (receipt.get("idempotency_key"), receipt.get("url"),
                 receipt.get("event", ""), 1 if receipt.get("ok") else 0,
                 int(receipt.get("attempts", 0)), receipt.get("status_code"),
                 receipt.get("error")),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM delivery_receipts WHERE idempotency_key = ?;",
                (receipt.get("idempotency_key"),)).fetchone()
            return dict(row) if row else dict(receipt)


_store: Optional[ProjectStore] = None


def get_store() -> ProjectStore:
    """Process-wide singleton so API endpoints share one durable store."""
    global _store
    if _store is None:
        _store = ProjectStore()
    return _store


def reset_store(db_path: Optional[str] = None) -> ProjectStore:
    """Test hook: rebind the singleton (isolated DB per test)."""
    global _store
    _store = ProjectStore(db_path=db_path)
    return _store

    # -- projects (legacy contract preserved) ------------------------------
    def save(self, project_id: str, state_dict: dict) -> None:
        with _lock, self._conn() as conn:
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
