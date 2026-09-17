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

    def check_status(self, job_id: str):
        """Poll async generation job. Default: synchronous providers report SUCCEEDED."""
        from backend.app.agent.state import JobStatus
        return JobStatus.SUCCEEDED


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
