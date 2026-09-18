"""
Private GPU Provider for Video-Agent.

Targets a SELF-HOSTED inference endpoint (on-prem GPU box / private cluster),
NOT a public API. This is the hybrid-GPU-burst story: cloud providers
(Kling / HuggingFace serverless) absorb overflow, while the private endpoint
serves baseline traffic with no marginal per-second API cost.

Configuration (environment only — never hardcode endpoints/secrets):
    VIDEO_PROVIDER=private_gpu            # selects this provider in the registry
    PRIVATE_GPU_API_URL                   # e.g. http://10.0.0.5:8080/v1/generate
    PRIVATE_GPU_API_TOKEN                 # optional bearer token for the private box
    PRIVATE_GPU_COST_PER_SECOND           # CPFM attribution (default 0.0: owned hw)

When the endpoint is NOT configured (or MOCK_VIDEO=true), generation runs in
simulated mode (deterministic local artifact) so offline CI/CD and dev stay green.
When the endpoint IS configured but unreachable, the call RAISES — matching the
uniform retry/guard policy applied to cloud providers (0-retry for violations).
"""
import os
from typing import List, Optional
import httpx
from backend.app.providers.base import BaseVideoProvider, GeneratedClip
from backend.app.providers.mock_provider import MockVideoProvider


class PrivateGPUProvider(BaseVideoProvider):
    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        api_token: Optional[str] = None,
    ):
        self.endpoint_url = endpoint_url or os.getenv("PRIVATE_GPU_API_URL", "").strip()
        self.api_token = api_token or os.getenv("PRIVATE_GPU_API_TOKEN", "").strip()
        self._fallback_mock = MockVideoProvider()

    @property
    def provider_name(self) -> str:
        return "PrivateGPU-Engine"

    @property
    def cost_per_second(self) -> float:
        # Self-hosted hardware: no marginal API cost. Operators can tag an
        # electricity/amortization estimate via PRIVATE_GPU_COST_PER_SECOND so
        # CostLedger CPFM stays comparable across providers.
        try:
            return float(os.getenv("PRIVATE_GPU_COST_PER_SECOND", "0.0"))
        except ValueError:
            return 0.0

    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint_url)

    def generate_clip(
        self,
        prompt: str,
        duration_sec: float,
        reference_images: Optional[List[str]] = None,
        seed: int = 42
    ) -> GeneratedClip:
        # Simulated mode: no endpoint configured, or explicit test/dev override.
        if not self.is_configured or os.getenv("MOCK_VIDEO", "false").lower() == "true":
            return GeneratedClip(
                clip_url=f"/data/rendered/private_gpu_{seed}_{int(duration_sec)}.mp4",
                duration_sec=duration_sec,
                cost_usd=round(duration_sec * self.cost_per_second, 3),
                provider_name=self.provider_name,
                metadata={"mode": "simulated_private_gpu", "seed": seed}
            )

        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        # Unreachable endpoint raises — HardToolGuard/retry policy treats the
        # private model exactly like a cloud model (0-retry for violations).
        r = httpx.post(
            self.endpoint_url,
            headers=headers,
            json={
                "prompt": prompt,
                "duration_sec": duration_sec,
                "reference_images": reference_images or [],
                "seed": seed,
            },
            timeout=120.0,
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: Private GPU endpoint rejected generation request.")

        try:
            payload = r.json()
            clip_url = payload.get("clip_url") or payload.get("video_url") or ""
            if not clip_url:
                raise ValueError("missing clip_url in response")
        except Exception as e:
            raise RuntimeError(f"Invalid response from Private GPU endpoint: {e}")

        return GeneratedClip(
            clip_url=clip_url,
            duration_sec=duration_sec,
            cost_usd=round(duration_sec * self.cost_per_second, 3),
            provider_name=self.provider_name,
            metadata={"mode": "private_gpu_inference", "seed": seed}
        )

    def check_status(self, job_id: str):
        from backend.app.agent.state import JobStatus
        # Private-GPU jobs are synchronous inline work; pending until run.
        return JobStatus.PENDING

    def submit_job(
        self, prompt: str, duration_sec: float = 4.0, seed: int = 42,
    ) -> dict:
        """Private-GPU submit: mock unless a private endpoint is configured."""
        import os as _os

        if not self.is_configured or _os.environ.get("MOCK_VIDEO", "false").lower() == "true":
            return {
                "provider_job_id": None,
                "mode": "mock",
                "status": "PENDING",
                "clip_url": f"/data/rendered/private_gpu_{seed}_{int(duration_sec)}.mp4",
                "cost_usd": 0.0,
            }
        return {
            "provider_job_id": f"gpu-{seed}-{int(duration_sec)}",
            "mode": "live",
            "status": "PENDING",
            "clip_url": "",
            "cost_usd": round(duration_sec * self.cost_per_second, 3),
        }
