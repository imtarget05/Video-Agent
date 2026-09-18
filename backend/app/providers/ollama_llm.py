"""
Ollama local LLM Scriptwriter Provider (default, M1 Pro 16GB friendly).
Model: qwen2.5:3b (~2GB), JSON-only output, temp 0.7, num_predict 800.
Zero cloud cost. Requires `ollama serve` + `ollama pull qwen2.5:3b`.
"""
import json
import os
import re
from typing import List, Dict, Any

import httpx
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = (
    "Bạn là Giám đốc Sáng tạo (Creative Director Agent) chuyên sản xuất video ngắn triệu view (TikTok/Shorts).\n"
    "Nhiệm vụ: Dựa trên chủ đề của người dùng, hãy viết kịch bản 3 phân cảnh (Scene 1: Hook, Scene 2: Value Core, Scene 3: CTA).\n"
    "QUY TẮC BẮT BUỘC: Trả về DUY NHẤT một JSON hợp lệ dạng danh sách 3 objects theo schema:\n"
    "[\n"
    '  {"scene_id": 1, "title": "Hook", "voiceover": "Câu mở đầu giật gân, cuốn hút bằng tiếng Việt (15-20 từ)", "visual_prompt": "Chi tiết mô tả hình ảnh cinematic 8k bằng tiếng Anh cho AI tạo ảnh", "duration_sec": 5.0},\n'
    '  {"scene_id": 2, "title": "Value Core", "voiceover": "Nội dung giá trị cốt lõi bằng tiếng Việt (20-25 từ)", "visual_prompt": "Chi tiết mô tả hình ảnh cinematic 8k bằng tiếng Anh cho AI tạo ảnh", "duration_sec": 6.5},\n'
    '  {"scene_id": 3, "title": "CTA", "voiceover": "Kêu gọi hành động mạnh mẽ bằng tiếng Việt (15-20 từ)", "visual_prompt": "Chi tiết mô tả hình ảnh cinematic 8k bằng tiếng Anh cho AI tạo ảnh", "duration_sec": 5.0}\n'
    "]\n"
    "Chỉ trả về JSON thuần, không thêm lời chào hay giải thích."
)


def deterministic_fallback(topic: str) -> List[Dict[str, Any]]:
    return [
        {
            "scene_id": 1,
            "title": "Hook",
            "voiceover": f"Bạn có biết bí mật lớn nhất về {topic} năm 2026 không?",
            "visual_prompt": f"Cinematic close up of young Vietnamese creator looking amazed at futuristic AI technology related to {topic}, neon lighting, 8k",
            "duration_sec": 5.0,
        },
        {
            "scene_id": 2,
            "title": "Value Core",
            "voiceover": f"Đây là giải pháp công nghệ giúp bạn tự động hóa và tăng tốc vượt trội với {topic}.",
            "visual_prompt": f"High tech futuristic command center, glowing holographic charts and automation for {topic}, cybernetic lighting, 8k",
            "duration_sec": 6.5,
        },
        {
            "scene_id": 3,
            "title": "CTA",
            "voiceover": "Hãy theo dõi kênh ngay hôm nay để không bỏ lỡ các công cụ AI đột phá!",
            "visual_prompt": "Inspiring modern creative studio setting, presenter smiling, glowing subscribe button and follow icon in background, 8k",
            "duration_sec": 5.0,
        },
    ]


class OllamaScriptwriter:
    def __init__(self, model: str = None, base_url: str = None):
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")

    def generate_script(self, topic: str) -> List[Dict[str, Any]]:
        try:
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "format": "json",
                    "options": {"temperature": 0.7, "num_predict": 800},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Chủ đề video: {topic}"},
                    ],
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            raw_content = (data.get("message") or {}).get("content", "").strip()
            if not raw_content:
                raise ValueError("Empty Ollama response")
            match = re.search(r"\[\s*\{.*\}\s*\]", raw_content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return json.loads(raw_content)
        except Exception as err:
            print(f"  ⚠️ Ollama LLM fallback ({err}). Using deterministic fallback.")
            return deterministic_fallback(topic)
