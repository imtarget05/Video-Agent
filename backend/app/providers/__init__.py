import os
from backend.app.providers.base import BaseVideoProvider, BaseTTSProvider
from backend.app.providers.mock_provider import MockVideoProvider, MockTTSProvider
from backend.app.providers.kling_provider import KlingWanProvider
from backend.app.providers.hf_video import HuggingFaceVideoProvider
from backend.app.providers.private_gpu import PrivateGPUProvider
from backend.app.providers.edge_tts_provider import EdgeTTSProvider

def get_video_provider() -> BaseVideoProvider:
    provider = os.getenv("VIDEO_PROVIDER", "mock").lower()
    if provider == "kling" or provider == "cloud":
        return KlingWanProvider()
    elif provider == "private_gpu":
        return PrivateGPUProvider()
    elif provider == "hf":
        return HuggingFaceVideoProvider()
    else:
        return MockVideoProvider()

def get_tts_provider() -> BaseTTSProvider:
    provider = os.getenv("TTS_PROVIDER", "mock").lower()
    if provider == "edge":
        return EdgeTTSProvider()
    else:
        return MockTTSProvider()
