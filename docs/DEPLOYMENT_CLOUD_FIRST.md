# DEPLOYMENT CHỐT — Cloud-First GPU (Serverless)

> Chốt 2026-09-17. Deployment duy nhất: **Cloud-First**.
> Cập nhật 2026-09-18 (plan API/Job/Delivery Safety): API auth bắt buộc,
> job state bền vững, render async 202, webhook SSRF-safe.

- **Training = Zero Training** — chỉ API test, xem `colab/hf_inference_demo.ipynb`.
- **Orchestration:** LangGraph (`backend/app/agent/graph.py` + `nodes.py`).
- **Video render DUY NHẤT trên cloud** — API chuyên dụng:
  Kling / Wan2.1 / HF Inference / Fal.ai, serverless GPU burst
  **pay-per-second**, VRAM **24–80GB** class (A10G/L4/A100/H100 theo provider).
- **Local (Ollama `qwen2.5:3b`) CHỈ viết kịch bản text — KHÔNG render video local.**
- **Test $0 offline:** `MockVideoProvider` / `MockTTSProvider`
  (`MOCK_VIDEO=true MOCK_TTS=true`, `LLM_PROVIDER=mock` / `VIDEO_PROVIDER=mock`).
- **Không reranker** (video assembly pipeline).

## Bắt buộc production (fail-closed khi thiếu)

| Biến | Bắt buộc | Ý nghĩa |
|---|---|---|
| `API_KEY` | ✅ | Mọi mutation endpoint (projects/jobs/render/subscribe/deliver) yêu cầu `X-API-Key`. Thiếu → service từ chối khởi động ở production. |
| `CORS_ORIGINS` | ✅ | Danh sách origin cách nhau bởi dấu phẩy; wildcard `*` bị cấm ở production và không được pair với credentials. |
| `WEBHOOK_SECRET` | ✅ (khi có webhook) | HMAC per-target; **không còn fallback `dev-secret`** ngoài development. |
| Provider credential (`KLING_API_KEY` / `HF_TOKEN` / `PRIVATE_GPU_API_URL`) | ✅ (khi chọn provider đó) | Thiếu credential ở production → fail closed; mock clip luôn `mode=mock`, cost 0 — không bao giờ bị gắn nhãn cloud render. |

## Trạng thái job + render async

- Durable SQLite store (`backend/app/api/store.py`): projects/jobs/subscriptions/
  receipts survive restart; `PROJECTS_STORE`/`JOBS_STORE` chỉ còn là mirror.
- Job states: `PENDING | RUNNING | SUCCEEDED | FAILED` (+ provider job id, mode,
  error). Provider polling trả về trạng thái thật; không bao giờ blind-SUCCEEDED.
- `POST /api/v1/canvas/render` → `202 {job_id, status:"PENDING"}`; worker chạy
  subprocess Remotion với bounded timeout (`RENDER_TIMEOUT_SEC`) và manifest
  per-job (`render_manifest_{job_id}.json`) — không dùng shared manifest.
- Idempotency: duplicate `idempotency_key` trả về job cũ, không double-bill.

## Webhook an toàn

- Subscribe validate URL ngay: reject `localhost`, RFC1918/link-local,
  DNS-resolved private (DNS rebinding), scheme không http/https; allowlist qua
  `WEBHOOK_ALLOWED_HOSTS`.
- Delivery: HMAC-SHA256 (`X-Signature`), max 2 retries, **idempotent receipts**
  — duplicate event (url+event+payload) chia sẻ một bản ghi receipt.

## Khôi phục / rollback

- Job `FAILED` giữ stderr (giới hạn 2000 ký tự) trong `jobs.error`; retry =
  gọi lại render với `idempotency_key` mới.
- Rollback artifact: artifact key `renders/{file}` đọc lại qua storage interface
  (`STORAGE_BACKEND=local|s3mock|r2`).

## Cấu hình

```bash
LLM_PROVIDER=ollama      # local text-only (qwen2.5:3b) | mock ($0 CI) | hf-cloud (Qwen-72B serverless)
VIDEO_PROVIDER=mock      # mock ($0) | kling/cloud (Kling/Wan2.1 REST) | hf (HF Inference) | private_gpu
MOCK_VIDEO=true MOCK_TTS=true   # ép mock $0, không đốt API budget
WEBHOOK_SECRET=<openssl rand -hex 32>   # BẮT BUỘC production
WEBHOOK_ALLOWED_HOSTS=hooks.partner.example
RENDER_TIMEOUT_SEC=600
```

## Verify

```bash
grep -rn "Cloud-First\|serverless\|Mock" README.md docs/ backend/app/providers/ .env.example plans/ tasks/
MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q backend/tests
```
