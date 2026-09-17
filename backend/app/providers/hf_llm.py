"""
Hugging Face LLM Scriptwriter Provider.
Uses Hugging Face Serverless Inference (Qwen/Qwen2.5-72B-Instruct) for autonomous narrative generation.
Zero Gemini dependencies.
"""
import json
import os
import re
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()


class HuggingFaceScriptwriter:
    def __init__(self, hf_token: Optional[str] = None):
        self.hf_token = hf_token or os.getenv("HF_TOKEN")
        self.client = InferenceClient(api_key=self.hf_token)
        self.model = os.getenv("HF_LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct")

    def generate_script(self, topic: str) -> List[Dict[str, Any]]:
        """
        Calls Hugging Face LLM to decompose the topic into 3 viral short-video scenes:
        Scene 1: Hook (3-5s) - Attention grabber
        Scene 2: Value Core (5-7s) - Main insight / actionable solution
        Scene 3: CTA (4-5s) - Strong call to action
        """
        system_prompt = (
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

        try:
            res = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Chủ đề video: {topic}"}
                ],
                max_tokens=800,
                temperature=0.7
            )
            raw_content = res.choices[0].message.content.strip()

            # Parse JSON from response
            match = re.search(r"\[\s*\{.*\}\s*\]", raw_content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return json.loads(raw_content)
        except Exception as err:
            print(f"  ⚠️ HF LLM Parsing Error: {err}. Using deterministic fallback.")
            return [
                {
                    "scene_id": 1,
                    "title": "Hook",
                    "voiceover": f"Bạn có biết bí mật lớn nhất về {topic} năm 2026 không?",
                    "visual_prompt": f"Cinematic close up of young Vietnamese creator looking amazed at futuristic AI technology related to {topic}, neon lighting, 8k",
                    "duration_sec": 5.0
                },
                {
                    "scene_id": 2,
                    "title": "Value Core",
                    "voiceover": f"Đây là giải pháp công nghệ giúp bạn tự động hóa và tăng tốc vượt trội với {topic}.",
                    "visual_prompt": f"High tech futuristic command center, glowing holographic charts and automation for {topic}, cybernetic lighting, 8k",
                    "duration_sec": 6.5
                },
                {
                    "scene_id": 3,
                    "title": "CTA",
                    "voiceover": "Hãy theo dõi kênh ngay hôm nay để không bỏ lỡ các công cụ AI đột phá!",
                    "visual_prompt": "Inspiring modern creative studio setting, presenter smiling, glowing subscribe button and follow icon in background, 8k",
                    "duration_sec": 5.0
                }
            ]
