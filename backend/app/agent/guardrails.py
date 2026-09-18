"""
Hard-coded tool guardrails and preflight checks for Video-Agent.
Enforces content safety, budget ceilings, and strict retry limits in code.
"""
from typing import List, Tuple, Optional, Any
from pydantic import BaseModel


PROHIBITED_KEYWORDS = {
    "nsfw", "violence", "blood", "kill", "suicide", "terror", "bomb",
    "hate", "weapon", "drugs", "illegal", "exploit", "nude", "porn"
}

DEFAULT_MAX_BUDGET_USD = 10.0
COST_PER_VIDEO_SECOND_ESTIMATE = 0.10  # ~$0.10 per second for 720p


class PreflightResult(BaseModel):
    passed: bool
    reason: str = "Passed"
    estimated_cost_usd: float = 0.0


class ToolExecutionResult(BaseModel):
    success: bool
    status: str  # SUCCESS, FAILED, MODERATION_BLOCKED
    data: Optional[Any] = None
    error: Optional[str] = None
    retry_allowed: bool = False
    attempts_made: int = 1


class PreflightGuard:
    """Preflight check executing BEFORE any generation API call."""

    @classmethod
    def validate_brief(
        cls,
        topic: str,
        target_duration_sec: float,
        max_budget_usd: float = DEFAULT_MAX_BUDGET_USD
    ) -> PreflightResult:
        # 1. Topic Keyword Scan
        topic_lower = topic.lower()
        for kw in PROHIBITED_KEYWORDS:
            if kw in topic_lower:
                return PreflightResult(
                    passed=False,
                    reason=f"Content Policy Preflight Violation: Prohibited keyword '{kw}' detected.",
                    estimated_cost_usd=0.0
                )

        # 2. Duration Sanity
        if target_duration_sec < 5.0 or target_duration_sec > 180.0:
            return PreflightResult(
                passed=False,
                reason=f"Invalid duration: {target_duration_sec}s. Target must be between 5s and 180s.",
                estimated_cost_usd=0.0
            )

        # 3. Budget Ceiling Check
        estimated_cost = round(target_duration_sec * COST_PER_VIDEO_SECOND_ESTIMATE, 2)
        if estimated_cost > max_budget_usd:
            return PreflightResult(
                passed=False,
                reason=f"Budget Cap Exceeded: Estimated cost ${estimated_cost} exceeds maximum allowed budget ${max_budget_usd}.",
                estimated_cost_usd=estimated_cost
            )

        return PreflightResult(passed=True, reason="Preflight passed", estimated_cost_usd=estimated_cost)

    @classmethod
    def validate_scene_prompt(cls, visual_prompt: str) -> Tuple[bool, Optional[str]]:
        prompt_lower = visual_prompt.lower()
        for kw in PROHIBITED_KEYWORDS:
            if kw in prompt_lower:
                return False, f"Prohibited keyword '{kw}' detected in visual prompt."
        return True, None


class HardToolGuard:
    """
    Hard-coded execution wrapper for generation tools.
    Prevents infinite LLM retry loops and stops compute waste.
    """
    MAX_5XX_RETRIES = 2
    BACKOFF_BASE_SEC = 1.0

    @classmethod
    def classify_error(cls, error_msg: str) -> str:
        msg = (error_msg or "").upper()
        if "POLICY_VIOLATION" in msg or "MODERATION" in msg or "CONTENT_POLICY" in msg:
            return "MODERATION_BLOCKED"
        if " 403" in msg or "403 " in msg or "HTTP 403" in msg or "FORBIDDEN" in msg or " 400" in msg or "HTTP 400" in msg or "BAD REQUEST" in msg:
            # Policy/moderation style 4xx: treated as moderation block, 0 retry.
            if "POLICY" in msg or "MODERATION" in msg or "BLOCK" in msg or "FORBIDDEN" in msg:
                return "MODERATION_BLOCKED"
            return "FATAL_4XX"
        if "HTTP 5" in msg or " 500" in msg or " 502" in msg or " 503" in msg or " 504" in msg or "TIMEOUT" in msg or "TIMED OUT" in msg or "TIME OUT" in msg or "CONNECTION" in msg or "OVERLOADED" in msg or "GATEWAY" in msg:
            return "RETRYABLE_5XX"
        if " 429" in msg or "429 " in msg or "HTTP 429" in msg or "TOO MANY" in msg or "RATE LIMIT" in msg or "RATE_LIMIT" in msg or "RATELIMIT" in msg:
            return "RETRYABLE_5XX"
        return "FATAL_4XX"

    @classmethod
    def backoff_delay(cls, attempt: int, base_sec: float = None) -> float:
        base = cls.BACKOFF_BASE_SEC if base_sec is None else base_sec
        return round(base * (2 ** max(0, attempt - 1)), 3)

    @classmethod
    def execute_with_guardrails(cls, provider_func, *args, **kwargs) -> ToolExecutionResult:
        import os
        import time
        backoff_base = float(os.getenv("GUARDRAIL_BACKOFF_BASE_SEC", str(cls.BACKOFF_BASE_SEC)))
        disable_sleep = os.getenv("PYTEST_CURRENT_TEST") is not None or backoff_base <= 0
        attempt = 0
        while attempt <= cls.MAX_5XX_RETRIES:
            attempt += 1
            try:
                result = provider_func(*args, **kwargs)
                return ToolExecutionResult(
                    success=True,
                    status="SUCCESS",
                    data=result,
                    retry_allowed=False,
                    attempts_made=attempt
                )
            except Exception as exc:
                error_msg = str(exc)
                kind = cls.classify_error(error_msg)
                # Content moderation / policy failure -> 0 retry
                if kind == "MODERATION_BLOCKED":
                    return ToolExecutionResult(
                        success=False,
                        status="MODERATION_BLOCKED",
                        error=error_msg,
                        retry_allowed=False,
                        attempts_made=attempt
                    )
                if kind == "FATAL_4XX":
                    return ToolExecutionResult(
                        success=False,
                        status="FAILED",
                        error=error_msg,
                        retry_allowed=False,
                        attempts_made=attempt
                    )
                # Transient 5xx / connection error
                if attempt > cls.MAX_5XX_RETRIES:
                    return ToolExecutionResult(
                        success=False,
                        status="FAILED",
                        error=f"Max retries ({cls.MAX_5XX_RETRIES}) exceeded: {error_msg}",
                        retry_allowed=False,
                        attempts_made=attempt
                    )
                if not disable_sleep:
                    time.sleep(cls.backoff_delay(attempt, base_sec=backoff_base))
                # Otherwise retry if attempts <= MAX_5XX_RETRIES
        return ToolExecutionResult(
            success=False,
            status="FAILED",
            error="Execution failed",
            retry_allowed=False,
            attempts_made=attempt
        )
