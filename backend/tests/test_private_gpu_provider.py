"""Tests for the PrivateGPUProvider (self-hosted GPU endpoint stub).

Covers: registry selection, simulated (offline) mode, CPFM cost attribution,
and the live-endpoint HTTP path including uniform error handling.
"""
import os
import pytest
from backend.app.providers import get_video_provider
from backend.app.providers.private_gpu import PrivateGPUProvider
from backend.app.providers.base import BaseVideoProvider


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate tests from operator env: no endpoint, no mock override."""
    monkeypatch.delenv("PRIVATE_GPU_API_URL", raising=False)
    monkeypatch.delenv("PRIVATE_GPU_API_TOKEN", raising=False)
    monkeypatch.delenv("PRIVATE_GPU_COST_PER_SECOND", raising=False)
    monkeypatch.delenv("MOCK_VIDEO", raising=False)


def test_registry_selects_private_gpu_provider(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "private_gpu")
    provider = get_video_provider()
    assert isinstance(provider, PrivateGPUProvider)
    assert isinstance(provider, BaseVideoProvider)


def test_registry_hf_flag_no_longer_maps_to_private_gpu(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "hf")
    from backend.app.providers.hf_video import HuggingFaceVideoProvider
    assert isinstance(get_video_provider(), HuggingFaceVideoProvider)


def test_simulated_mode_when_endpoint_not_configured():
    provider = PrivateGPUProvider()
    assert provider.is_configured is False
    clip = provider.generate_clip(prompt="a red fox", duration_sec=4.0, seed=7)
    assert clip.provider_name == "PrivateGPU-Engine"
    assert clip.duration_sec == 4.0
    assert clip.metadata["mode"] == "simulated_private_gpu"
    assert clip.metadata["seed"] == 7


def test_cost_attribution_default_zero_and_env_override(monkeypatch):
    provider = PrivateGPUProvider()
    assert provider.cost_per_second == 0.0
    clip = provider.generate_clip(prompt="x", duration_sec=10.0, seed=1)
    assert clip.cost_usd == 0.0

    monkeypatch.setenv("PRIVATE_GPU_COST_PER_SECOND", "0.02")
    provider2 = PrivateGPUProvider()
    clip2 = provider2.generate_clip(prompt="x", duration_sec=10.0, seed=1)
    assert provider2.cost_per_second == 0.02
    assert clip2.cost_usd == 0.2


def test_mock_video_override_forces_simulated_mode(monkeypatch):
    monkeypatch.setenv("MOCK_VIDEO", "true")
    provider = PrivateGPUProvider(endpoint_url="http://10.0.0.5:8080/v1/generate")
    clip = provider.generate_clip(prompt="x", duration_sec=2.0, seed=3)
    assert clip.metadata["mode"] == "simulated_private_gpu"


def test_live_endpoint_success(monkeypatch):
    class FakeResponse:
        status_code = 200
        def json(self):
            return {"clip_url": "/data/rendered/local_job_42.mp4"}

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("backend.app.providers.private_gpu.httpx.post", fake_post)
    provider = PrivateGPUProvider(
        endpoint_url="http://10.0.0.5:8080/v1/generate",
        api_token="secret-token",
    )
    clip = provider.generate_clip(prompt="a blue whale", duration_sec=5.0, seed=42)
    assert clip.clip_url == "/data/rendered/local_job_42.mp4"
    assert clip.provider_name == "PrivateGPU-Engine"
    assert clip.metadata["mode"] == "private_gpu_inference"
    assert captured["url"] == "http://10.0.0.5:8080/v1/generate"
    assert captured["json"]["prompt"] == "a blue whale"
    assert captured["headers"]["Authorization"] == "Bearer secret-token"


def test_live_endpoint_http_error_raises(monkeypatch):
    class FakeResponse:
        status_code = 500
        def json(self):
            return {}

    monkeypatch.setattr(
        "backend.app.providers.private_gpu.httpx.post",
        lambda *a, **k: FakeResponse(),
    )
    provider = PrivateGPUProvider(endpoint_url="http://10.0.0.5:8080/v1/generate")
    with pytest.raises(RuntimeError, match="HTTP 500"):
        provider.generate_clip(prompt="x", duration_sec=2.0, seed=1)


def test_live_endpoint_missing_clip_url_raises(monkeypatch):
    class FakeResponse:
        status_code = 200
        def json(self):
            return {"unexpected": "payload"}

    monkeypatch.setattr(
        "backend.app.providers.private_gpu.httpx.post",
        lambda *a, **k: FakeResponse(),
    )
    provider = PrivateGPUProvider(endpoint_url="http://10.0.0.5:8080/v1/generate")
    with pytest.raises(RuntimeError, match="Invalid response"):
        provider.generate_clip(prompt="x", duration_sec=2.0, seed=1)
