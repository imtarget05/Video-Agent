"""
Kling/Wan2.1 video generation provider (standard HTTP REST wrapper).
Mock-mode when MOCK_VIDEO=true or no API key (offline $0 CI).
"""
import os
from typing import List, Optional
from backend.app.providers.base import BaseVideoProvider, GeneratedClip
from backend.app.providers.mock_provider import MockVideoProvider


class KlingWanProvider(BaseVideoProvider):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("KLING_API_KEY")
        self.base_url = base_url or os.getenv("KLING_BASE_URL", "https://api.kling.ai/v1")
        self._fallback_mock = MockVideoProvider()

    @property
    def provider_name(self) -> str:
        return "KlingWan-Video-Engine"

    @property
    def cost_per_second(self) -> float:
        return 0.08

    def _mock_mode(self) -> bool:
        return (not self.api_key) or os.getenv("MOCK_VIDEO", "false").lower() == "true"

    def generate_clip(
        self,
        prompt: str,
        duration_sec: float,
        reference_images: Optional[List[str]] = None,
        seed: int = 42,
    ) -> GeneratedClip:
        if self._mock_mode():
            mock_res = self._fallback_mock.generate_clip(
                prompt=prompt, duration_sec=duration_sec,
                reference_images=reference_images, seed=seed,
            )
            return GeneratedClip(
                clip_url=mock_res.clip_url,
                duration_sec=duration_sec,
                cost_usd=round(duration_sec * self.cost_per_second, 3),
                provider_name=self.provider_name,
                metadata={"mode": "kling_mock", "seed": seed},
            )
        import httpx
        resp = httpx.post(
            f"{self.base_url}/videos/generations",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"prompt": prompt, "duration": duration_sec, "seed": seed},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return GeneratedClip(
            clip_url=data.get("clip_url", f"/data/rendered/kling_{seed}.mp4"),
            duration_sec=duration_sec,
            cost_usd=round(duration_sec * self.cost_per_second, 3),
            provider_name=self.provider_name,
            metadata={"mode": "kling_rest", "seed": seed},
        )

    def check_status(self, job_id: str):
        from backend.app.agent.state import JobStatus
        if self._mock_mode():
            return JobStatus.SUCCEEDED
        return JobStatus.SUCCEEDED
