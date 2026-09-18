"""
Abstract base classes for pluggable video and audio generation providers.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class GeneratedClip(BaseModel):
    clip_url: str
    duration_sec: float
    cost_usd: float
    provider_name: str
    metadata: Dict[str, Any] = {}


class GeneratedAudio(BaseModel):
    audio_url: str
    duration_sec: float
    word_timestamps: List[Dict[str, Any]]
    cost_usd: float
    provider_name: str


class BaseVideoProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def cost_per_second(self) -> float:
        pass

    @abstractmethod
    def generate_clip(
        self,
        prompt: str,
        duration_sec: float,
        reference_images: Optional[List[str]] = None,
        seed: int = 42
    ) -> GeneratedClip:
        pass

    def submit_job(
        self,
        prompt: str,
        duration_sec: float = 4.0,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Submit an async job; providers with live APIs must override this."""
        raise NotImplementedError(
            f"{self.provider_name} does not implement submit_job"
        )

    def check_status(self, job_id: str):
        """Poll async generation job. Unknown state defaults to PENDING.

        Never default to SUCCEEDED: a provider that cannot prove completion
        must not let the API report a finished render.
        """
        from backend.app.agent.state import JobStatus
        return JobStatus.PENDING


class BaseTTSProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def generate_speech(
        self,
        text: str,
        voice: Optional[str] = None
    ) -> GeneratedAudio:
        pass
