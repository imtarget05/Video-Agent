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

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    @property
    def provider_name(self) -> str:
        return "KlingWan-Video-Engine"

    @property
    def cost_per_second(self) -> float:
        return 0.08

    def _mock_mode(self) -> bool:
        return (not self.api_key) or os.getenv("MOCK_VIDEO", "false").lower() == "true"

    def submit_job(
        self, prompt: str, duration_sec: float = 4.0, seed: int = 42,
    ) -> dict:
        """Submit a live job and retain the provider-specific remote job id.

        In production without credentials this fails closed — it never bills
        or labels a mock clip as a cloud render.
        """
        import os as _os

        if self._mock_mode():
            return {
                "provider_job_id": None,
                "mode": "mock",
                "status": "PENDING",
                "clip_url": f"/data/rendered/kling_mock_{seed}_{int(duration_sec)}.mp4",
                "cost_usd": 0.0,
            }
        import httpx

        env = _os.environ.get("APP_ENV", _os.environ.get("ENVIRONMENT", "development")).lower()
        if env == "production" and not self.api_key:
            raise RuntimeError("KLING_API_KEY is required in production")
        try:
            resp = httpx.post(
                f"{self.base_url}/videos/generations",
                headers=self._auth(),
                json={"prompt": prompt, "duration": duration_sec, "seed": seed},
                timeout=60.0,
            )
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"TIMEOUT calling Kling API: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise RuntimeError(f"HTTP {status} calling Kling API: {exc}") from exc
        data = resp.json()
        return {
            "provider_job_id": str(data.get("id") or data.get("job_id") or ""),
            "mode": "live",
            "status": "PENDING",
            "clip_url": data.get("clip_url", ""),
            "cost_usd": round(duration_sec * self.cost_per_second, 3),
        }

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
        try:
            resp = httpx.post(
                f"{self.base_url}/videos/generations",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"prompt": prompt, "duration": duration_sec, "seed": seed},
                timeout=60.0,
            )
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"TIMEOUT calling Kling API: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise RuntimeError(f"HTTP {status} calling Kling API: {exc}") from exc
        data = resp.json()
        return GeneratedClip(
            clip_url=data.get("clip_url", f"/data/rendered/kling_{seed}.mp4"),
            duration_sec=duration_sec,
            cost_usd=round(duration_sec * self.cost_per_second, 3),
            provider_name=self.provider_name,
            metadata={"mode": "kling_rest", "seed": seed},
        )

    def check_status(self, job_id: str):
        """Live status lookup for the provider-specific job id."""
        from backend.app.agent.state import JobStatus

        if self._mock_mode():
            return JobStatus.PENDING
        import httpx

        try:
            resp = httpx.get(f"{self.base_url}/videos/{job_id}", headers=self._auth(), timeout=15.0)
        except httpx.TimeoutException:
            return JobStatus.FAILED
        if resp.status_code == 404:
            return JobStatus.FAILED
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            return JobStatus.FAILED
        state = str(resp.json().get("status", "")).upper()
        mapping = {
            "QUEUED": JobStatus.PENDING, "PENDING": JobStatus.PENDING,
            "PROCESSING": JobStatus.RUNNING, "RUNNING": JobStatus.RUNNING,
            "COMPLETED": JobStatus.SUCCEEDED, "SUCCEEDED": JobStatus.SUCCEEDED,
            "SUCCESS": JobStatus.SUCCEEDED, "FAILED": JobStatus.FAILED,
        }
        return mapping.get(state, JobStatus.RUNNING)
