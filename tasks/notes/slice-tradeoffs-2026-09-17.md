# Tradeoffs & Decisions — Video-Agent hoàn thiện (2026-09-17)

Nguồn skill: `Vide coding/superpowers/skills/writing-plans/SKILL.md` + `repo-harness/.../repo-harness-plan/SKILL.md` + `references/create.md`. Spec duyệt: `docs/spec.md` v1.0.0.

## Quyết định

1. **Plan location:** skill mặc định `docs/superpowers/plans/` nhưng user lệnh `/vibe-plan` yêu cầu `plans/plan-*.md` → ưu tiên user, lưu `plans/plan-2026-09-17-video-agent-hoan-thien.md`. [ASSUMED — user override thắng skill default]
2. **Reformulator 1 lần rồi END:** tránh vòng lặp vô hạn moderation; lần 2 cần human. Tradeoff: tốn 1 generation call nhưng rẻ hơn blind retry.
3. **KlingWan/EdgeTTS/Whisper offline-fallback deterministic:** CI $0, không SDK mới ngoài edge-tts/huggingface_hub. Live mode chỉ khi có key.
4. **PROJECTS_STORE vẫn in-memory + JOBS_STORE BackgroundTasks:** YAGNI, chưa引入 Celery/Redis. Ledger đã sqlite. Persist full defer.
5. **Audio -18dB:** manifest (0.35→0.10 ≈ -10.9dB) làm source-of-truth, envelope interpolate fade 0.5s; không hardcode tỉ số 0.126 để tránh lệch manifest.
6. **Subtitle:** giữ prop sceneOffsetSec tương thích, chuyển sang sequence-relative frame + cumulative computeSceneOffsets; karaoke 3-state past/active/future.
7. **B-roll overlay/PiP + fade 15 frames:** không thêm @remotion/transitions (YAGNI), dùng opacity interpolate.
8. **OmniFlash/KlingWan trong spec:** đánh dấu FutureAdapter, không block slice này; adapter hiện tại: Mock + hf_video + image_providers.
9. **API_KEY optional (open khi rỗng):** CI green, prod set secret. Rate-limit in-memory 60/min.
10. **TikTok/YouTube upload:** webhook stub + header note manual upload, không SDK keys ở slice này.
11. **LLM-local chốt (M1 Pro 16GB, cấm >4GB):** default LLM_PROVIDER=ollama (qwen2.5:3b ~2GB, temp 0.7/800 JSON-only, timeout 120); MockVideo/MockTTS=true CI $0; Qwen-72B hf-cloud optional; FLUX cloud-only; get_scriptwriter() mock->None/hf-cloud->HF/còn lại->Ollama.
12. **DEPLOYMENT CHỐT Cloud-First GPU Serverless (2026-09-17):** Training = Zero Training (chỉ API test, `colab/hf_inference_demo.ipynb`); deployment duy nhất Cloud-First — LangGraph + API chuyên dụng (Kling/Wan2.1/HF Inference/Fal.ai), serverless GPU burst pay-per-second, VRAM 24–80GB; local (qwen2.5:3b) chỉ viết kịch bản text, KHÔNG render video local; Mock provider test $0 offline; không reranker. Chi tiết: `docs/DEPLOYMENT_CLOUD_FIRST.md`.

## Unknowns (non-blocking)

- `src/index.ts` có re-export Root đúng bundle entry không — Task B6 sẽ báo.
- HF_TOKEN/fal keys ở prod — demo tokenless qua pollinations fallback.
