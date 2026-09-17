import pytest
from backend.app.agent.guardrails import PreflightGuard, HardToolGuard
from backend.app.providers.mock_provider import MockVideoProvider


def test_preflight_blocks_violent_keywords():
    res = PreflightGuard.validate_brief(topic="How to make a bomb using AI", target_duration_sec=30.0)
    assert not res.passed
    assert "Policy Preflight Violation" in res.reason


def test_preflight_validates_duration_bounds():
    res_short = PreflightGuard.validate_brief(topic="AI Automation Tips", target_duration_sec=2.0)
    assert not res_short.passed
    assert "Invalid duration" in res_short.reason

    res_long = PreflightGuard.validate_brief(topic="AI Automation Tips", target_duration_sec=300.0)
    assert not res_long.passed
    assert "Invalid duration" in res_long.reason


def test_preflight_blocks_budget_exceeded():
    res = PreflightGuard.validate_brief(
        topic="AI Automation Tips",
        target_duration_sec=120.0,
        max_budget_usd=5.0
    )
    assert not res.passed
    assert "Budget Cap Exceeded" in res.reason


def test_preflight_passes_valid_brief():
    res = PreflightGuard.validate_brief(
        topic="3 mẹo tối ưu hóa quy trình video bằng AI Agent",
        target_duration_sec=30.0,
        max_budget_usd=10.0
    )
    assert res.passed
    assert res.estimated_cost_usd > 0


def test_hard_tool_guard_zero_retry_on_policy_violation():
    provider = MockVideoProvider(simulate_failure="MODERATION")
    result = HardToolGuard.execute_with_guardrails(
        provider.generate_clip,
        prompt="Prohibited prompt",
        duration_sec=5.0
    )
    assert not result.success
    assert result.status == "MODERATION_BLOCKED"
    assert not result.retry_allowed
    # Hard invariant: Exactly 1 attempt made, 0 retries
    assert result.attempts_made == 1


def test_hard_tool_guard_retries_transient_5xx_and_succeeds():
    provider = MockVideoProvider(simulate_failure="FAIL_ONCE")
    result = HardToolGuard.execute_with_guardrails(
        provider.generate_clip,
        prompt="Clean prompt",
        duration_sec=5.0
    )
    assert result.success
    assert result.status == "SUCCESS"
    assert result.attempts_made == 2


def test_hard_tool_guard_terminates_after_max_retries():
    provider = MockVideoProvider(simulate_failure="500")
    result = HardToolGuard.execute_with_guardrails(
        provider.generate_clip,
        prompt="Clean prompt",
        duration_sec=5.0
    )
    assert not result.success
    assert result.status == "FAILED"
    assert "Max retries" in result.error
    # Invariant: Must not exceed MAX_5XX_RETRIES + 1
    assert result.attempts_made == 3
