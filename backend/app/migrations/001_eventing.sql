-- V-1 — Video-Agent eventing schema (foundation spec §2.2, §4.2b.5, §4.3.3)
-- Target: Neon Postgres branch `staging` (project videoagent).
-- Idempotent: safe to re-run. Apply with:
--   psql "$NEON_STAGING_URL" -f backend/app/migrations/001_eventing.sql
--
-- Relationship to the legacy Plan 02 tables (already created by
-- backend/app/api/store.py::_PG_SHARED_DDL): `outbox_events`/`dead_letters`
-- are the pre-Kafka durable-ops tables and are NOT reused here. The
-- foundation contract owns `outbox` (Kafka publish queue). `audit_events`
-- IS reused (no new audit table).
--
-- Rollback (staging only, before any traffic):
--   DROP TABLE render_jobs, external_ops, retry_schedule,
--              consumed_events, outbox CASCADE;

-- ---------------------------------------------------------------------------
-- 1. Outbox (foundation §2.2) — producer publishes ONLY from here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox (
  seq              BIGSERIAL PRIMARY KEY,
  event_id         UUID NOT NULL UNIQUE,
  event_type       TEXT NOT NULL,
  topic            TEXT NOT NULL,
  kafka_key        TEXT NOT NULL,
  headers          JSONB NOT NULL DEFAULT '{}'::jsonb,
  envelope         JSONB NOT NULL,
  status           TEXT NOT NULL DEFAULT 'PENDING'
                   CHECK (status IN ('PENDING','INFLIGHT','SENT','FAILED','DEAD')),
  publish_attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outbox_due_idx ON outbox (status, next_attempt_at, seq)
  WHERE status IN ('PENDING','FAILED');
CREATE INDEX IF NOT EXISTS outbox_inflight_idx ON outbox (status, created_at)
  WHERE status = 'INFLIGHT';

-- ---------------------------------------------------------------------------
-- 2. Consumer inbox dedupe (foundation §2.2, §4.2a)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consumed_events (
  event_id    UUID PRIMARY KEY,
  event_type  TEXT NOT NULL,
  consumer    TEXT NOT NULL,
  consumed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 3. Retry schedule (foundation §4.3.3) — replaces Kafka delayed messages.
--    UNIQUE(event_id, attempt) is the crash-safety rail (§4.3.6).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS retry_schedule (
  id         BIGSERIAL PRIMARY KEY,
  event_id   UUID NOT NULL,
  topic      TEXT NOT NULL,
  envelope   JSONB NOT NULL,
  attempt    INTEGER NOT NULL,
  due_at     TIMESTAMPTZ NOT NULL,
  status     TEXT NOT NULL DEFAULT 'SCHEDULED'
             CHECK (status IN ('SCHEDULED','ENQUEUED','CANCELLED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT retry_schedule_event_attempt_key UNIQUE (event_id, attempt)
);
CREATE INDEX IF NOT EXISTS retry_due_idx ON retry_schedule (status, due_at)
  WHERE status = 'SCHEDULED';

-- ---------------------------------------------------------------------------
-- 4. External operations (foundation §4.2b.5) — reserve → execute → persist.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS external_ops (
  operation_key       TEXT PRIMARY KEY,
  event_id            UUID NOT NULL,
  provider            TEXT NOT NULL,
  remote_operation_id TEXT,
  status              TEXT NOT NULL DEFAULT 'RESERVED'
                      CHECK (status IN ('RESERVED','SUCCEEDED','FAILED')),
  response_sha256     TEXT,
  reconcile_basis     TEXT,
  attempts            INTEGER NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS external_ops_stuck_idx ON external_ops (status, updated_at)
  WHERE status = 'RESERVED';

-- ---------------------------------------------------------------------------
-- 5. Domain table: render_jobs (plan §2). The Postgres backend does not own
--    the SQLite `jobs` table, so the render path gets its own Neon table.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS render_jobs (
  job_id              TEXT PRIMARY KEY,
  project_id          TEXT NOT NULL,
  aspect_ratio        TEXT NOT NULL,
  total_duration_sec  DOUBLE PRECISION NOT NULL,
  idempotency_key     TEXT UNIQUE,
  status              TEXT NOT NULL CHECK (status IN
                        ('PENDING','RUNNING','SUCCEEDED','FAILED')),
  provider            TEXT NOT NULL DEFAULT 'remotion',
  remote_operation_id TEXT,
  manifest_r2_key     TEXT,
  artifact_key        TEXT,
  error               TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS render_jobs_status_idx
  ON render_jobs (status, updated_at DESC);
