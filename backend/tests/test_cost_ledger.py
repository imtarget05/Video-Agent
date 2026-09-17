import pytest
import os
from backend.app.cost.ledger import CostLedger
from backend.app.agent.state import CostRecord


@pytest.fixture
def temp_ledger(tmp_path):
    db_file = tmp_path / "test_ledger.db"
    return CostLedger(db_path=str(db_file))


def test_record_cost_and_calculate_cpfm(temp_ledger):
    project_id = "proj_test_123"

    # Simulate 3 successful scene clips generated (total 15s)
    # Total spend: $1.50
    temp_ledger.record_cost(project_id, CostRecord(
        job_id="job_1", provider="MockVideo", duration_sec=5.0, cost_usd=0.50, attempt_number=1, status="SUCCESS"
    ))
    temp_ledger.record_cost(project_id, CostRecord(
        job_id="job_2", provider="MockVideo", duration_sec=5.0, cost_usd=0.50, attempt_number=1, status="SUCCESS"
    ))
    temp_ledger.record_cost(project_id, CostRecord(
        job_id="job_3", provider="MockVideo", duration_sec=5.0, cost_usd=0.50, attempt_number=1, status="SUCCESS"
    ))

    # Approved final video is 15s (0.25 minutes)
    metrics = temp_ledger.get_project_metrics(project_id=project_id, approved_final_seconds=15.0)

    assert metrics["total_spend_usd"] == 1.50
    assert metrics["gross_generated_seconds"] == 15.0
    assert metrics["approved_final_seconds"] == 15.0
    # CPFM: $1.50 / 0.25 min = $6.00 / finished minute
    assert metrics["cost_per_finished_minute"] == 6.00
    assert metrics["retry_ratio"] == 0.0
    assert metrics["gross_to_net_ratio"] == 1.0


def test_retry_ratio_and_gross_to_net_efficiency(temp_ledger):
    project_id = "proj_wasteful_456"

    # 1 retry failure + 1 success for same scene
    temp_ledger.record_cost(project_id, CostRecord(
        job_id="job_retry", provider="MockVideo", duration_sec=5.0, cost_usd=0.50, attempt_number=2, status="FAILED"
    ))
    temp_ledger.record_cost(project_id, CostRecord(
        job_id="job_ok", provider="MockVideo", duration_sec=5.0, cost_usd=0.50, attempt_number=1, status="SUCCESS"
    ))

    # Approved final is only 5.0 seconds, but 10.0 seconds were generated!
    metrics = temp_ledger.get_project_metrics(project_id=project_id, approved_final_seconds=5.0)

    assert metrics["total_spend_usd"] == 1.00
    assert metrics["gross_generated_seconds"] == 10.0
    assert metrics["gross_to_net_ratio"] == 2.0  # 2x compute used vs finished output
    assert metrics["retry_ratio"] == 0.5  # 1 out of 2 calls was a retry
