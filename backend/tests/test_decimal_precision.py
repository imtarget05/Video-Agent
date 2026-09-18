"""WP1-T1 RED: decimal precision failing tests.

Spec: CostRecord Decimal + ledger TEXT + CPFM quantize HALF_UP.
These tests MUST FAIL on the current float implementation.
"""
from decimal import Decimal, ROUND_HALF_UP

import pytest
from pydantic import ValidationError

from backend.app.agent.state import CostRecord
from backend.app.cost.ledger import CostLedger


def _make_record(job_id: str, cost: Decimal) -> CostRecord:
    return CostRecord(
        job_id=job_id,
        provider="MockVideo",
        duration_sec=5.0,
        cost_usd=cost,
        attempt_number=1,
        status="SUCCESS",
    )


def test_decimal_accumulation_no_float_drift(tmp_path):
    """Record 3x Decimal 0.10, expect total exactly Decimal 0.30."""
    ledger = CostLedger(db_path=str(tmp_path / "decimal.db"))
    project_id = "proj_decimal_01x3"

    for i in range(3):
        ledger.record_cost(project_id, _make_record(f"job_{i}", Decimal("0.10")))

    metrics = ledger.get_project_metrics(
        project_id=project_id, approved_final_seconds=15.0
    )
    total = metrics["total_spend_usd"]

    # Internal total must be exact Decimal, not float drift (0.30000000000000004).
    assert isinstance(total, Decimal), f"expected Decimal, got {type(total)}: {total!r}"
    assert total == Decimal("0.30"), f"expected Decimal 0.30, got {total!r}"


def test_cpfm_quantize_half_up(tmp_path):
    """CPFM 1.005 must quantize HALF_UP to Decimal 1.01."""
    ledger = CostLedger(db_path=str(tmp_path / "cpfm.db"))
    project_id = "proj_cpfm_half_up"

    # Total $2.01 over 2 finished minutes => CPFM raw 1.005 => HALF_UP 1.01.
    ledger.record_cost(project_id, _make_record("job_cpfm", Decimal("2.01")))

    metrics = ledger.get_project_metrics(
        project_id=project_id, approved_final_seconds=120.0
    )
    cpfm = metrics["cost_per_finished_minute"]

    assert isinstance(cpfm, Decimal), f"expected Decimal, got {type(cpfm)}: {cpfm!r}"
    expected = (Decimal("2.01") / Decimal("2")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    assert expected == Decimal("1.01")
    assert cpfm == Decimal("1.01"), f"expected Decimal 1.01, got {cpfm!r}"


def test_money_coercion_float_str_int():
    """WP1-T2: CostRecord.cost_usd coerces float/str/int -> Decimal quantized 4dp, dumps float."""
    r_float = CostRecord(
        job_id="j1", provider="MockVideo", duration_sec=5.0, cost_usd=0.5
    )
    assert isinstance(r_float.cost_usd, Decimal)
    assert r_float.cost_usd == Decimal("0.5000")

    r_str = CostRecord(
        job_id="j2", provider="MockVideo", duration_sec=5.0, cost_usd="0.12345"
    )
    assert r_str.cost_usd == Decimal("0.1235")  # HALF_UP to 4dp

    r_int = CostRecord(
        job_id="j3", provider="MockVideo", duration_sec=5.0, cost_usd=1
    )
    assert r_int.cost_usd == Decimal("1.0000")

    # PlainSerializer keeps float contract on dump.
    dumped = r_float.model_dump()
    assert isinstance(dumped["cost_usd"], float)
    assert dumped["cost_usd"] == 0.5


def test_money_reject_nan_inf_negative():
    """WP1-T2: NaN/inf/negative cost_usd must raise ValidationError."""
    for bad in (float("nan"), float("inf"), float("-inf"), -0.01, "-5", "nan", "Infinity"):
        with pytest.raises(ValidationError):
            CostRecord(
                job_id="bad",
                provider="MockVideo",
                duration_sec=5.0,
                cost_usd=bad,
            )


def test_server_boundary_float_backcompat(tmp_path):
    """WP1-T5: Decimal internals must keep the float contract for server.py.

    Every value the API layer consumes (metrics dicts, state cost fields) must
    still be convertible with plain float() without raising or losing shape.
    """
    ledger = CostLedger(db_path=str(tmp_path / "backcompat.db"))
    project_id = "proj_backcompat"

    for i in range(3):
        ledger.record_cost(project_id, _make_record(f"job_{i}", Decimal("0.10")))

    metrics = ledger.get_project_metrics(project_id=project_id, approved_final_seconds=15.0)

    # server.py serializes these as JSON numbers (float contract).
    assert isinstance(float(metrics["total_spend_usd"]), float)
    assert float(metrics["total_spend_usd"]) == pytest.approx(0.30)
    assert isinstance(float(metrics["cost_per_finished_minute"]), float)
    assert float(metrics["cost_per_finished_minute"]) == pytest.approx(1.20)  # 0.30 / 0.25 min

    # State fields stay float (VideoProjectState.actual_cost_usd: float).
    from backend.app.agent.state import VideoProjectState

    state = VideoProjectState(project_id=project_id, topic="t")
    state.actual_cost_usd = float(metrics["total_spend_usd"])
    assert isinstance(state.actual_cost_usd, float)

    # Legacy REAL rows (pre-WP1 DBs) still read back exactly as Decimal.
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "legacy.db"))
    conn.execute(
        "CREATE TABLE cost_records (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, job_id TEXT,"
        " provider TEXT, duration_sec REAL, cost_usd REAL, attempt_number INTEGER, status TEXT,"
        " prompt_tokens INTEGER DEFAULT 0)"
    )
    conn.execute(
        "INSERT INTO cost_records (project_id, job_id, provider, duration_sec, cost_usd,"
        " attempt_number, status) VALUES ('legacy', 'j1', 'MockVideo', 5.0, 0.1, 1, 'SUCCESS')"
    )
    conn.commit()
    conn.close()

    legacy = CostLedger(db_path=str(tmp_path / "legacy.db"))
    legacy_metrics = legacy.get_project_metrics(project_id="legacy", approved_final_seconds=15.0)
    assert legacy_metrics["total_spend_usd"] == Decimal("0.1000")
