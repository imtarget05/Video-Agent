"""
EdgeTTS voiceover provider with offline mock fallback (MOCK_TTS=true or missing edge-tts).
"""
import os
import re
from typing import Optional
from backend.app.providers.base import BaseTTSProvider, GeneratedAudio


class EdgeTTSProvider(BaseTTSProvider):
    def __init__(self, voice: Optional[str] = None):
        self.default_voice = voice or os.getenv("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural")

    @property
    def provider_name(self) -> str:
        return "EdgeTTS"

    def _mock_mode(self) -> bool:
        return os.getenv("MOCK_TTS", "false").lower() == "true"

    def generate_speech(self, text: str, voice: Optional[str] = None) -> GeneratedAudio:
        voice = voice or self.default_voice
        if self._mock_mode():
            return self._mock_speech(text, voice)
        try:
            import asyncio
            import edge_tts
            out_path = "/tmp/edge_tts_out.mp3"
            comm = edge_tts.Communicate(text, voice)
            asyncio.run(comm.save(out_path))
            words = self._mock_speech(text, voice).word_timestamps
            return GeneratedAudio(
                audio_url=out_path, duration_sec=words[-1]["end"] if words else 1.0,
                word_timestamps=words, cost_usd=0.0, provider_name=self.provider_name,
            )
        except Exception:
            return self._mock_speech(text, voice)

    def _mock_speech(self, text: str, voice: str) -> GeneratedAudio:
        words = re.findall(r"\w+", text, re.UNICODE)
        if not words:
            words = ["silent"]
        word_duration = 0.35
        total = max(1.0, round(len(words) * word_duration, 2))
        ts, t = [], 0.0
        for w in words:
            ts.append({"word": w, "start": round(t, 2), "end": round(t + word_duration, 2)})
            t += word_duration
        return GeneratedAudio(
            audio_url="/data/rendered/speech_edge_mock.mp3",
            duration_sec=total, word_timestamps=ts, cost_usd=0.0,
            provider_name=self.provider_name,
        )
