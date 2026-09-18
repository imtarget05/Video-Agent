"""Provider contract tests (ai-testing-beyond-mock).

- $0 unit CI: MockVideoProvider (+ mock-mode Kling/HF) — no network, no cost.
- Schema contract: every video provider result exposes {clip_url|video_url, status}.
- Kling API timeout/429 fallback: respx-mocked HTTP, asserts retryable
  classification + guardrailed fallback. Skips gracefully if respx missing.
"""
import os

import pytest

from backend.app.agent.state import JobStatus


def _clip_url(clip) -> str:
    """Contract: result must expose clip_url (preferred) or video_url alias."""
    for attr in ("clip_url", "video_url"):
        val = getattr(clip, attr, None)
        if val:
            return val
    # dict-style fallback
    if isinstance(clip, dict):
        for key in ("clip_url", "video_url"):
            if clip.get(key):
                return clip[key]
    raise AssertionError(
        f"provider result missing contract field {{clip_url|video_url}}: {clip!r}"
    )


def _all_video_providers():
    from backend.app.providers.mock_provider import MockVideoProvider
    from backend.app.providers.kling_provider import KlingWanProvider
    from backend.app.providers.hf_video import HuggingFaceVideoProvider

    os.environ["MOCK_VIDEO"] = "true"
    yield MockVideoProvider()
    yield KlingWanProvider(api_key="dummy")
    yield HuggingFaceVideoProvider(hf_token=None)


def test_provider_schema_clip_url_and_status():
    """Every provider: generate_clip -> {clip_url|video_url}, check_status -> JobStatus."""
    for provider in _all_video_providers():
        clip = provider.generate_clip(prompt="a calm lake", duration_sec=4.0, seed=1)
        url = _clip_url(clip)
        assert isinstance(url, str) and url.endswith(".mp4"), f"bad clip url: {url!r}"
        status = provider.check_status("job1")
        assert isinstance(status, JobStatus), f"bad status: {status!r}"
        assert status.value in {s.value for s in JobStatus}


def test_mock_provider_stays_zero_cost_offline():
    """MockVideoProvider must remain deterministic + offline ($0 CI)."""
    from backend.app.providers.mock_provider import MockVideoProvider

    p = MockVideoProvider()
    clip = p.generate_clip(prompt="unit test", duration_sec=2.0, seed=7)
    assert _clip_url(clip).endswith(".mp4")
    assert p.check_status("anything") == JobStatus.SUCCEEDED


def _require_respx():
    return pytest.importorskip("respx", reason="respx not installed; skipping HTTP contract test")


def _live_kling_provider(monkeypatch, tmp_base_url="https://api.kling.ai/v1"):
    """Kling provider forced into live-REST path (respx intercepts HTTP)."""
    from backend.app.providers.kling_provider import KlingWanProvider

    monkeypatch.delenv("MOCK_VIDEO", raising=False)
    return KlingWanProvider(api_key="test-key", base_url=tmp_base_url)


def test_kling_429_falls_back_retryable(monkeypatch):
    """Kling 429 -> raise with 429 signal; guardrail classifies RETRYABLE (fallback: retry, no crash)."""
    respx = _require_respx()
    import httpx

    from backend.app.agent.guardrails import HardToolGuard

    provider = _live_kling_provider(monkeypatch)
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{provider.base_url}/videos/generations").mock(
            return_value=httpx.Response(429, json={"error": "rate limited"})
        )
        with pytest.raises(Exception) as exc_info:
            provider.generate_clip(prompt="a calm lake", duration_sec=4.0, seed=1)
        assert "429" in str(exc_info.value), f"expected 429 signal, got: {exc_info.value!r}"
        assert HardToolGuard.classify_error(str(exc_info.value)) == "RETRYABLE_5XX"

        # Guardrailed fallback: retries then returns FAILED (never raises, never hangs)
        result = HardToolGuard.execute_with_guardrails(
            provider.generate_clip, prompt="a calm lake", duration_sec=4.0, seed=1
        )
        assert result.status == "FAILED"
        assert result.attempts_made > 1


def test_kling_timeout_falls_back_retryable(monkeypatch):
    """Kling timeout -> raise with TIMEOUT signal; guardrail classifies RETRYABLE."""
    respx = _require_respx()
    import httpx

    from backend.app.agent.guardrails import HardToolGuard

    provider = _live_kling_provider(monkeypatch)
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{provider.base_url}/videos/generations").mock(
            side_effect=httpx.ConnectTimeout("connection timed out")
        )
        with pytest.raises(Exception) as exc_info:
            provider.generate_clip(prompt="a calm lake", duration_sec=4.0, seed=1)
        assert "TIMEOUT" in str(exc_info.value).upper(), f"expected TIMEOUT signal, got: {exc_info.value!r}"
        assert HardToolGuard.classify_error(str(exc_info.value)) == "RETRYABLE_5XX"
