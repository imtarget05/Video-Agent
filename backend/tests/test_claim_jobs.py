"""Atomic claims, lease expiry, retry taxonomy, and DLQ for render jobs
(sqlite path; explicit tmp path forces sqlite per Plan 02 Task 6)."""
from backend.app.api.store import ProjectStore
from backend.app.jobs.render_worker import classify_render_error


def _store(tmp_path):
    return ProjectStore(db_path=str(tmp_path / "jobs.db"))


def _enqueue(store, job_id="job-1"):
    return store.create_job({"job_id": job_id, "prompt": "hi"})


def test_claim_empty_queue_returns_none(tmp_path):
    assert _store(tmp_path).claim_job(lease_seconds=60) is None


def test_claim_hands_out_lease_and_blocks_second_claim(tmp_path):
    store = _store(tmp_path)
    _enqueue(store)
    claimed = store.claim_job(lease_seconds=60)
    assert claimed["job_id"] == "job-1"
    assert claimed["status"] == "RUNNING"
    assert store.claim_job(lease_seconds=60) is None


def test_expired_lease_is_reclaimable(tmp_path):
    store = _store(tmp_path)
    _enqueue(store)
    store.claim_job(lease_seconds=60)
    store.update_job("job-1", lease_expires_at="2000-01-01T00:00:00+00:00")
    again = store.claim_job(lease_seconds=60)
    assert again is not None and again["job_id"] == "job-1"


def test_replay_resets_dead_to_pending(tmp_path):
    store = _store(tmp_path)
    _enqueue(store)
    store.mark_dead("job-1", "REMOTION_FAILED: oom", owner="test")
    assert store.get_job("job-1")["status"] == "DEAD"
    store.replay_job("job-1", operator="test")
    row = store.get_job("job-1")
    assert row["status"] == "PENDING"
    assert row["attempt"] == 0


def test_taxonomy_timeout_retries_then_dead():
    assert classify_render_error("RENDER_TIMEOUT: x", 1) == "retry"
    assert classify_render_error("RENDER_TIMEOUT: x", 3) == "dead"
    assert classify_render_error("REMOTION_FAILED: oom", 1) == "dead"
    assert classify_render_error("policy_violation: no", 1) == "dead"
