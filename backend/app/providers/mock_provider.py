"""
Mock zero-cost video and audio providers for local dev, offline CI/CD, and regression tests.
"""
import os
import re
from typing import List, Optional, Dict, Any
from backend.app.providers.base import (
    BaseVideoProvider,
    BaseTTSProvider,
    GeneratedClip,
    GeneratedAudio,
)


class MockVideoProvider(BaseVideoProvider):
    def __init__(self, simulate_failure: Optional[str] = None):
        self.simulate_failure = simulate_failure
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "MockVideo-Engine"

    @property
    def cost_per_second(self) -> float:
        return 0.10

    def generate_clip(
        self,
        prompt: str,
        duration_sec: float,
        reference_images: Optional[List[str]] = None,
        seed: int = 42
    ) -> GeneratedClip:
        self.call_count += 1

        if self.simulate_failure == "MODERATION":
            raise RuntimeError("CONTENT_POLICY_VIOLATION: Image contains prohibited subject matter.")
        elif self.simulate_failure == "500":
            raise RuntimeError("HTTP 500: Server overloaded, please retry later.")
        elif self.simulate_failure == "FAIL_ONCE" and self.call_count == 1:
            raise RuntimeError("HTTP 503: Transient gateway timeout.")

        cost = round(duration_sec * self.cost_per_second, 3)
        clip_id = f"clip_{seed}_{int(duration_sec)}"
        clip_path = f"/data/rendered/{clip_id}.mp4"

        return GeneratedClip(
            clip_url=clip_path,
            duration_sec=duration_sec,
            cost_usd=cost,
            provider_name=self.provider_name,
            metadata={
                "seed": seed,
                "prompt": prompt,
                "reference_count": len(reference_images) if reference_images else 0,
                "simulated": True
            }
        )


class MockTTSProvider(BaseTTSProvider):
    @property
    def provider_name(self) -> str:
        return "MockTTS-Edge"

    def generate_speech(
        self,
        text: str,
        voice: Optional[str] = "vi-VN-HoaiMyNeural"
    ) -> GeneratedAudio:
        words = re.findall(r"\w+", text)
        if not words:
            words = ["silent"]

        # Approximate speech duration: ~0.35s per word
        word_duration = 0.35
        total_duration = max(1.0, round(len(words) * word_duration, 2))

        word_timestamps = []
        current_time = 0.0
        for w in words:
            start = round(current_time, 2)
            end = round(current_time + word_duration, 2)
            word_timestamps.append({"word": w, "start": start, "end": end})
            current_time = end

        return GeneratedAudio(
            audio_url="/data/rendered/speech_mock.mp3",
            duration_sec=total_duration,
            word_timestamps=word_timestamps,
            cost_usd=0.0,  # Edge TTS is free
            provider_name=self.provider_name
        )
