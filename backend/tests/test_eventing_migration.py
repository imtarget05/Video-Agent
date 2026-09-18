"""V-1 acceptance: migration SQL declares the foundation contract.

Offline structural test: this machine has no psql/Neon credentials, so the
SQL is asserted for the exact tables/constraints/columns the foundation
spec requires. Running it against a real branch is a manual staging step
(recorded in docs/evidence/).
"""
import re
from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[1] / "app" / "migrations" / "001_eventing.sql"
SQL = MIGRATION.read_text(encoding="utf-8")


def _table_block(name: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {name} \((.*?)\n\);", SQL, re.DOTALL
    )
    assert match, f"missing CREATE TABLE for {name}"
    return match.group(1)


def test_migration_file_exists_and_is_idempotent():
    assert MIGRATION.is_file()
    assert SQL.count("CREATE TABLE IF NOT EXISTS") == 5
    assert "DROP TABLE" in SQL  # rollback documented in header


def test_foundation_tables_present():
    for table in ("outbox", "consumed_events", "retry_schedule",
                  "external_ops", "render_jobs"):
        assert f"CREATE TABLE IF NOT EXISTS {table} (" in SQL, table


def test_outbox_shape_matches_foundation_2_2():
    block = _table_block("outbox")
    for column in ("event_id", "event_type", "topic", "kafka_key", "headers",
                   "envelope", "status", "publish_attempts", "next_attempt_at",
                   "published_at"):
        assert column in block, column
    assert "event_id         UUID NOT NULL UNIQUE" in block
    assert "'PENDING','INFLIGHT','SENT','FAILED','DEAD'" in block


def test_retry_schedule_has_crash_safety_unique_constraint():
    block = _table_block("retry_schedule")
    assert "UNIQUE (event_id, attempt)" in block
    assert "'SCHEDULED','ENQUEUED','CANCELLED'" in block


def test_external_ops_matches_foundation_4_2b():
    block = _table_block("external_ops")
    for column in ("operation_key", "event_id", "provider",
                   "remote_operation_id", "response_sha256", "attempts"):
        assert column in block, column
    assert "'RESERVED','SUCCEEDED','FAILED'" in block


def test_consumed_events_is_an_inbox_keyed_by_event_id():
    block = _table_block("consumed_events")
    assert "event_id    UUID PRIMARY KEY" in block
    assert "consumer" in block


def test_render_jobs_matches_plan_section_2():
    block = _table_block("render_jobs")
    for column in ("job_id", "project_id", "aspect_ratio", "total_duration_sec",
                   "idempotency_key", "status", "provider",
                   "remote_operation_id", "manifest_r2_key", "artifact_key",
                   "error"):
        assert column in block, column
    assert "'PENDING','RUNNING','SUCCEEDED','FAILED'" in block
    assert "idempotency_key     TEXT UNIQUE" in block


def test_due_indexes_exist_for_relay_scheduler_and_stuck_ops():
    assert "outbox_due_idx" in SQL
    assert "retry_due_idx" in SQL
    assert "external_ops_stuck_idx" in SQL


def test_legacy_plan02_tables_are_not_redefined():
    """`outbox_events`/`dead_letters` belong to store._PG_SHARED_DDL."""
    assert "CREATE TABLE IF NOT EXISTS outbox_events" not in SQL
    assert "CREATE TABLE IF NOT EXISTS dead_letters" not in SQL
    # audit_events is reused from store._PG_SHARED_DDL, never re-created here.
    assert "CREATE TABLE IF NOT EXISTS audit_events" not in SQL