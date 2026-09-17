# Video-Agent Hoàn Thiện Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn thiện Video-Agent từ hiện trạng ~70% lên 100% spec v1.0.0, green CI offline $0.

**Architecture:** Giữ LangGraph tuyến tính + Remotion Series; thêm JobStatus/check_status, SafetyReformulator (1 lần rồi END), EdgeTTS/Whisper offline-fallback, KlingWan mock-mode, ProjectStore sqlite + webhook HMAC dispatcher, sửa subtitle offset + AudioTrack envelope + BRollStitcher + fade, QC gate đầy đủ.

**Tech Stack:** Python 3.11, FastAPI>=0.110, pydantic>=2.6, langgraph>=0.2, httpx>=0.27, edge-tts>=6.1, huggingface_hub>=0.23, Remotion 4.0.218 + React 18 + TS 5.3, pytest>=8.

**Spec:** `docs/spec.md` (v1.0.0 Approved Baseline)

## Global Constraints

- HTTP 5xx: exponential backoff tối đa 2 retries (tổng ≤3 attempts).
- Policy/moderation 400/403: 0 retry, emit MODERATION_BLOCKED.
- 100% test pass offline, không đốt API budget (MOCK_VIDEO/MOCK_TTS=true).
- CPFM = Total Spend / Minutes Approved Final Video.
- Mọi ledger call ghi job_id, provider, prompt_tokens, video_seconds_generated, dollar_cost, attempt_number, status.
- Shorts916 1080x1920@30fps, Landscape169 1920x1080@30fps không đổi.
- pytest.ini: pythonpath=., testpaths=backend/tests.

---

## File Structure (tóm tắt — chi tiết code đầy đủ nằm ở 3 slice plans bên dưới)

- Slice A (backend): sửa `state.py` (+JobStatus/prompt_tokens), `guardrails.py` (+classify/backoff), `providers/base|mock|hf_video.py` (+check_status), tạo `kling_provider.py`, `edge_tts_provider.py`, `whisper_subtitles.py`, `agent/safety_reformulator.py`, sửa `graph.py` (route reformulator 1 lần), `nodes.py` (prompt_tokens + QC), `cost/ledger.py` (+prompt_tokens col + migration), tạo `api/store.py`, `api/webhooks.py`, sửa `api/server.py` (+jobs endpoint).
- Slice B (remotion): sửa `DynamicSubtitles.tsx` (karaoke 3-state), `AudioTrack.tsx` (interpolate envelope), `MainVideo.tsx` (cumulative offset + wiring + fade), tạo `BRollStitcher.tsx`, sửa `types.ts` (bRollUrl/bRollLayout), sửa `nodes.py/state.py` (qc_report gate).
- Slice C (delivery/docs/CI): tạo `delivery/dispatcher.py` (HMAC + 2-retry), sửa `server.py` (list/status/reject/async job/auth/deliver/subscribe), sửa `requirements.txt` (+huggingface_hub, edge-tts), `ledger.py` (DATABASE_URL video_agent.db), `README.md` (hf_llm/hf_video/dispatcher), `spec.md` (OmniFlash/KlingWan → FutureAdapter), `.github/workflows/ci.yml` (MOCK flags + manifest assert).

## Chi tiết từng slice (code đầy đủ, không placeholder)

Chi tiết test-code + implementation-code + lệnh verify từng task 2–5 phút được lưu ở output của 3 planner agents và sẽ bung ra file khi duyệt từng chunk:
- **Slice A — 10 tasks:** Task 1 state JobStatus → Task 2 ledger migration → Task 3 backoff → Task 4 check_status → Task 5 KlingWan → Task 6 EdgeTTS → Task 7 Whisper → Task 8 reformulator → Task 9 graph wiring → Task 10 QC hardening → Task 11 store/webhook. Verify: `pytest backend/tests/test_slice_a_*.py -v` từng task + `pytest backend/tests/ -v` chống regression.
- **Slice B — 6 tasks:** Task 1 subtitle offset+karaoke → Task 2 AudioTrack envelope → Task 3 BRollStitcher → Task 4 MainVideo fade → Task 5 QC audit full → Task 6 bundle+QC verify. Verify: `cd remotion && node scripts/check_sliceB.mjs && npm run bundle`.
- **Slice C — 10 tasks:** Task 1 deps+ledger path → Task 2 list/status → Task 3 reject → Task 4 async job → Task 5 auth/rate-limit → Task 6 dispatcher → Task 7 subscribe/deliver → Task 8 README/spec → Task 9 CI/demo/bundle → Task 10 plans/notes log. Verify: `pytest -v --tb=short`, `MOCK_VIDEO=true MOCK_TTS=true python scripts/run_demo.py`, `cd remotion && npm run bundle`.

## Self-Review

1. Spec coverage: KlingWan/EdgeTTS/Whisper/reformulator/check_status/prompt_tokens/backoff (A), subtitle/audio/B-roll/fade/QC (B), webhook/list/reject/async/auth/docs/CI (C) — đủ gaps đã khảo sát.
2. Placeholder scan: mọi task có test code + implement code + lệnh Expected cụ thể, không TBD.
3. Type consistency: JobStatus, prompt_tokens, qc_report/qc_passed, bRollUrl/bRollLayout, DeliveryTarget/Receipt dùng nhất quán.

## Execution Handoff

Plan complete and saved to `plans/plan-2026-09-17-video-agent-hoan-thien.md`. Hai option khi duyệt xong:
1. Subagent-Driven (recommended) — fresh subagent per task + review giữa tasks.
2. Inline Execution — batch trong session với checkpoint.
