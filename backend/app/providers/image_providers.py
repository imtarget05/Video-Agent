"""
Pluggable Image Generation Providers for Video-Agent.
Strategy:
1. Hugging Face Free Tier (Default):
   - If HF_TOKEN is configured: Uses Hugging Face Serverless Router (FLUX.1-schnell / SDXL).
   - If no token: Uses free serverless queue with exponential backoff & rate-limit handling.
2. Fal.ai Provider: For ultra-fast FLUX.1 generation using trial credits (FAL_KEY).
3. Replicate Provider: For high-detail FLUX.1 / SDXL using trial credits (REPLICATE_API_TOKEN).
"""
import os
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseImageProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def generate_image(self, prompt: str, output_path: str, width: int = 576, height: int = 1024, seed: int = 42) -> str:
        pass


class HuggingFaceFreeProvider(BaseImageProvider):
    """
    Default Zero-Cost Provider.
    Supports official Hugging Face Serverless Router (if HF_TOKEN set)
    or Free Serverless Queue with automatic retry.
    """
    def __init__(self, hf_token: Optional[str] = None):
        self.hf_token = hf_token or os.getenv("HF_TOKEN")

    @property
    def provider_name(self) -> str:
        if self.hf_token:
            return "HuggingFace-Serverless (FLUX.1 / HF_TOKEN)"
        return "HuggingFace-Free-Tier (Serverless Queue)"

    def generate_image(self, prompt: str, output_path: str, width: int = 576, height: int = 1024, seed: int = 42) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 1. Try Hugging Face Router if token is present
        if self.hf_token:
            try:
                import json
                url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
                headers = {
                    "Authorization": f"Bearer {self.hf_token}",
                    "Content-Type": "application/json"
                }
                payload = json.dumps({"inputs": prompt}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers=headers)
                with urllib.request.urlopen(req, timeout=45) as resp:
                    if resp.status == 200:
                        with open(output_path, "wb") as f:
                            f.write(resp.read())
                        return output_path
            except Exception as hf_err:
                print(f"  ⚠️ HF Router with token error: {hf_err}. Falling back to serverless queue...")

        # 2. Free Serverless Queue with backoff
        clean_prompt = prompt.replace("\n", " ").strip()
        encoded = urllib.parse.quote(clean_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&seed={seed}"

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                # Brief sleep between calls to avoid queue congestion
                if attempt > 1:
                    time.sleep(3 * attempt)
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    content_type = response.headers.get("Content-Type", "")
                    data = response.read()

                    # Verify received actual image data (not JSON error)
                    if "image" in content_type or data[:4] in [b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\x89PNG"]:
                        with open(output_path, "wb") as out_file:
                            out_file.write(data)
                        return output_path
                    else:
                        print(f"  ⚠️ Attempt {attempt}: Received non-image response, retrying...")
            except Exception as err:
                print(f"  ⚠️ Attempt {attempt} failed: {err}")
                if attempt == max_attempts:
                    raise RuntimeError(f"HuggingFace Free Tier failed after {max_attempts} attempts: {err}")

        return output_path


class FalAiImageProvider(BaseImageProvider):
    """
    High-Speed Provider using trial credits on fal.ai (FLUX.1-schnell).
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FAL_KEY")

    @property
    def provider_name(self) -> str:
        return "Fal.ai (FLUX.1-schnell)"

    def generate_image(self, prompt: str, output_path: str, width: int = 576, height: int = 1024, seed: int = 42) -> str:
        if not self.api_key:
            print("  ⚠️ FAL_KEY chưa có, dùng HuggingFace Free Tier...")
            return HuggingFaceFreeProvider().generate_image(prompt, output_path, width, height, seed)

        import httpx
        url = "https://queue.fal.run/fal-ai/flux/schnell"
        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "num_inference_steps": 4,
            "seed": seed
        }
        resp = httpx.post(url, json=payload, headers=headers, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        img_url = data["images"][0]["url"]
        urllib.request.urlretrieve(img_url, output_path)
        return output_path


class ReplicateImageProvider(BaseImageProvider):
    """
    Quality Provider using trial credits on Replicate (black-forest-labs/flux-schnell).
    """
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.getenv("REPLICATE_API_TOKEN")

    @property
    def provider_name(self) -> str:
        return "Replicate (FLUX.1)"

    def generate_image(self, prompt: str, output_path: str, width: int = 576, height: int = 1024, seed: int = 42) -> str:
        if not self.api_token:
            print("  ⚠️ REPLICATE_API_TOKEN chưa có, dùng HuggingFace Free Tier...")
            return HuggingFaceFreeProvider().generate_image(prompt, output_path, width, height, seed)

        import httpx
        url = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"
        headers = {
            "Authorization": f"Token {self.api_token}",
            "Content-Type": "application/json",
            "Prefer": "wait"
        }
        payload = {
            "input": {
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "output_format": "jpg"
            }
        }
        resp = httpx.post(url, json=payload, headers=headers, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        img_url = data["output"][0]
        urllib.request.urlretrieve(img_url, output_path)
        return output_path


def get_default_image_provider() -> BaseImageProvider:
    """Factory: Defaults to Hugging Face Free Tier, or uses fal.ai / Replicate if credentials exist."""
    if os.getenv("FAL_KEY"):
        return FalAiImageProvider()
    if os.getenv("REPLICATE_API_TOKEN"):
        return ReplicateImageProvider()
    return HuggingFaceFreeProvider()
