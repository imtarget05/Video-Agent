# Video-Agent — Ghi chú Colab (KHÔNG train)

> **Video-Agent KHÔNG cần train / finetune bất kỳ weight nào.**
> Mọi thử nghiệm trên Colab (nếu có) chỉ là **inference qua API**, không update trọng số model.

## 1. Vì sao không cần train?

| Component | Bản chất | Ghi chú |
|---|---|---|
| **CharacterDNA** (`backend/app/consistency/character_dna.py`, `backend/app/agent/state.py`) | **Prompt-anchor**: struct dữ liệu khóa tạo hình nhân vật (seed, reference anchors) để `compose_consistent_prompt()` giữ nhất quán giữa các scene. Không phải embedding học được, không có weight để train. | Xem `backend/tests/test_character_dna.py` — test thuần prompt-locking, không cần GPU. |
| **QC** (`backend/app/agent/nodes.py::qc_...`, graph `Assembly → QC → End`) | **Gate kiểm định**: audit tính toàn vẹn output + tính CPFM (cost). Là rule-check sau generation, không phải model. | Không có gì để train. |
| **Scriptwriter** (default local) | `OllamaScriptwriter` — model **`qwen2.5:3b`** chạy local qua `ollama serve` (`backend/app/providers/ollama_llm.py`). Dùng **inference**, không train. | Máy cá nhân cấm model local > 4GB. |
| **Scriptwriter** (optional cloud) | `HuggingFaceScriptwriter` — **`Qwen/Qwen2.5-72B-Instruct`** qua Hugging Face Serverless Inference (`backend/app/providers/hf_llm.py`, chọn bằng `LLM_PROVIDER=hf-cloud`). Dùng **cloud inference**, không train. | Cần `HF_TOKEN`. Có deterministic fallback khi parse lỗi. |

Router chọn provider: `get_scriptwriter()` — `mock` → fallback $0 offline (CI) · `hf-cloud` → Qwen-72B cloud · còn lại → Ollama `qwen2.5:3b` local.

## 2. Nếu muốn thử nghiệm generation trên Colab: dùng HF Inference API (không train weight)

- Colab chỉ gọi `InferenceClient` (text-generation / chat-completions) với `Qwen/Qwen2.5-72B-Instruct` — giống hệt `HuggingFaceScriptwriter.generate_script()`.
- **Tuyệt đối không** chạy training/finetune (Trainer, LoRA, v.v.) — không cần thiết cho pipeline này.
- Bảo mật: lưu token trong **Colab Secrets** (`HF_TOKEN`), không hardcode vào notebook.

Notebook optional: [`hf_inference_demo.ipynb`](./hf_inference_demo.ipynb) — mở trên Colab và chạy 1 cell duy nhất.

## 3. Cell mẫu (copy vào Colab nếu không dùng file ipynb)

```python
# !pip install -q huggingface_hub
import json, os, re
from google.colab import userdata
from huggingface_hub import InferenceClient

os.environ["HF_TOKEN"] = userdata.get("HF_TOKEN")  # set trong Colab Secrets
client = InferenceClient(api_key=os.environ["HF_TOKEN"])
MODEL = "Qwen/Qwen2.5-72B-Instruct"  # cùng default với backend/app/providers/hf_llm.py

topic = "AI giúp freelancer tăng thu nhập"
res = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "Bạn là Creative Director chuyên video ngắn TikTok/Shorts. Chỉ trả về JSON thuần: list 3 objects {scene_id, title, voiceover, visual_prompt, duration_sec}, không giải thích."},
        {"role": "user", "content": f"Chủ đề video: {topic}"},
    ],
    max_tokens=800,
    temperature=0.7,
)
raw = res.choices[0].message.content.strip()
m = re.search(r"\[\s*\{.*\}\s*\]", raw, re.DOTALL)
scenes = json.loads(m.group(0)) if m else json.loads(raw)
print(json.dumps(scenes, indent=2, ensure_ascii=False))
```

Kết quả `scenes` có cùng schema 3-scene (Hook / Value Core / CTA) mà agent `scriptwriter` node dùng, nên có thể paste thẳng vào pipeline local để test storyboard → generation → QC mà không cần GPU hay train gì thêm.
