<div align="center">
  <h1>🎬 Video-Agent — Autonomous AI Video Production & Distribution System</h1>
  <p><strong>Enterprise-Grade Video Orchestration Agent with Keyframe-First Planning, Remotion Composition Engine & Hard-Coded Cost Guardrails</strong></p>

  [![Python 3.11](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
  [![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
  [![LangGraph](https://img.shields.io/badge/LangGraph-000000?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
  [![Remotion](https://img.shields.io/badge/Remotion-0B84F3?style=flat-square&logo=react&logoColor=white)](https://www.remotion.dev/)
  [![React 18](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
  [![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
  [![Tests](https://img.shields.io/badge/Tests-148%20passed-success?style=flat-square)](#)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
</div>

---

**Video-Agent** is an autonomous video production and orchestration system designed for high-throughput commercial and social media pipelines (TikTok, YouTube Shorts, Reels, and YouTube Explainers).

Unlike naive "prompt-and-pray" wrapper tools that treat AI models as a magic wand, **Video-Agent** is architected on real-world engineering constraints: **planning before generation, code-based editing with Remotion, character consistency via visual anchors, content moderation as a valid state, and deterministic cost accounting measured by Cost Per Finished Minute (CPFM)**.

---

## 💡 The 7 Core Production Lessons & Architecture Solutions

| # | Real-World Production Lesson | Naive "AI Washing" Approach | Video-Agent Engineering Architecture |
|---|---|---|---|
| **1** | **Model is just a swappable layer** | Prompts are the entire system; debate over which model is best | 3-Layer Architecture: (1) Storyboard planning via still keyframes, (2) Swappable video generator (Hugging Face FLUX.1 / Kling / Mock), (3) Remotion code assembly |
| **2** | **Cost per finished minute (CPFM)** | Only measures "cost per API call"; ignores silent retry burn | SQLite-backed `CostLedger` computing $\text{CPFM} = \frac{\text{Total Spend}}{\text{Finished Min}}$ and Gross-to-Net compute ratios |
| **3** | **Editing is the real bottleneck (80% value)** | Assumes AI generates a ready-to-publish 60s video | **Remotion (React/TS)** timeline engine: micro-take cuts, kinetic typography, dynamic audio ducking (music gain 0.35 -> 0.10, i.e. -10.9 dB under voiceover), transitions |
| **4** | **Hard tool guardrails > prompt pleading** | Tells LLM in prompt "please don't retry too many times" | Hard-coded tool limiter in Python: max 2 retries on 5xx, **0 retries** on policy violations; Preflight safety & budget checks |
| **5** | **Character consistency via visual anchors** | Vague descriptions in free text across prompts | `CharacterDNA` manager locking invariant prompt prefixes at position 0, 3-angle visual reference packs, and seed values |
| **6** | **Moderation as a first-class citizen** | Treats policy rejections as crashes or retries blindly | `MODERATION_BLOCKED` is a native state in LangGraph, routing to safety reformulators or human supervisors |
| **7** | **Zero-Cost Offline Testing (Anti-AI Washing)** | Cannot run tests without burning paid API credits | Native `MockVideoProvider` & `MockTTSProvider` so the whole suite and CI run offline at **$0 cost** (no coverage percentage is claimed; none is measured) |

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Layer1 ["1. Pre-Production & Visual Anchoring (Keyframe-First)"]
        Brief["Brief / Topic / Script"] --> DNA["Character DNA & Visual Anchor Pack (3 Góc tham chiếu)"]
        DNA --> Storyboard["Keyframe Planning (Sinh ảnh tĩnh giá rẻ trước)"]
        Storyboard --> Preflight["Preflight Guardrail (Policy Check + Budget Estimation)"]
        Preflight --> HITL["HITL Checkpoint 1 (Duyệt kịch bản + Keyframe + Ngân sách)"]
    end

    subgraph Layer2 ["2. Pluggable Generation & Hard Guardrails"]
        HITL -->|Approved| ModelRouter["LLM ModelRouter (Ollama qwen2.5:3b local default / hf-cloud Qwen-72B optional / mock CI $0) + Video Router (FLUX cloud-only / Mock)"]
        ModelRouter --> ToolGuard["Hard-coded Tool Guard (Max 2 Retries 5xx, 0 Retry Policy Reject)"]
        ToolGuard --> CostTracker["Cost Accounting Engine (Đo Cost-Per-Finished-Minute)"]
        ToolGuard --> TTS["TTS Engine (Edge-TTS / ElevenLabs) + Whisper Timestamps"]
    end

    subgraph Layer3 ["3. Editorial Agent & Remotion Assembly (80% Value Core)"]
        CostTracker & TTS --> EditAgent["Editorial Decision Agent (Take Selection, Cut, Pacing)"]
        EditAgent --> Remotion["Remotion Engine (React/TypeScript)"]
        Remotion --> Template916["Template 9:16 (Shorts/TikTok/Reels)"]
        Remotion --> Template169["Template 16:9 (YouTube/Landscape)"]
        Remotion --> Subtitles["Dynamic Word-by-Word Captions + Audio Ducking"]
    end

    subgraph Layer4 ["4. QC Audit & Delivery Automation"]
        Remotion --> QCAgent["Automated QC Agent (Black-frame, Desync, Audio Clip Check)"]
        QCAgent --> Output["Rendered Final MP4 + Decision Audit Slip"]
        Output --> Publish["Webhook / Multi-Platform Dispatcher"]
    end
```

---

## 📂 Project Structure

```text
Video-Agent/
├── .github/workflows/ci.yml    # CI/CD: Automated Pytest & Remotion bundle checks
├── docs/
│   └── spec.md                 # Baseline Technical Specification
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── state.py        # Pydantic schemas (Scene, CharacterDNA, CostRecord)
│   │   │   ├── guardrails.py   # Preflight checks & HardToolGuard limiter
│   │   │   ├── nodes.py        # LangGraph execution nodes (Director, Script, QC)
│   │   │   └── graph.py        # Compiled LangGraph StateGraph workflow
│   │   ├── consistency/
│   │   │   └── character_dna.py # Character DNA & Visual Anchor Manager
│   │   ├── cost/
│   │   │   └── ledger.py       # SQLite Cost Accounting & CPFM Ledger
│   │   ├── providers/
│   │   │   ├── base.py         # Abstract Base Provider interface (generate_clip + check_status)
│   │   │   ├── mock_provider.py # Zero-cost deterministic offline provider
│   │   │   ├── ollama_llm.py    # Default local scriptwriter (Ollama qwen2.5:3b ~2GB, M1 Pro 16GB, CI $0 fallback)
│   │   │   │   │   ├── hf_llm.py       # Qwen-72B optional hf-cloud only + get_scriptwriter() ModelRouter (ollama/mock/hf-cloud)
│   │   │   ├── hf_video.py     # Hugging Face open-weights video adapter (mock fallback)
│   │   │   ├── kling_provider.py # Kling/Wan2.1 REST adapter (FutureAdapter, mock-mode offline)
│   │   │   ├── edge_tts_provider.py # Edge-TTS voiceover adapter (offline mock fallback)
│   │   │   └── whisper_subtitles.py # Whisper word-timestamp extractor (offline fallback)
│   │   ├── delivery/
│   │   │   └── dispatcher.py   # HMAC-signed webhook fan-out (max 2 retries, DeliveryTarget/Receipt)
│   │   └── api/
│   │       ├── server.py       # FastAPI REST API (Projects, HITL, Jobs, Cost Audit, Deliver/Subscribe)
│   │       ├── store.py        # SQLite ProjectStore (list/status persistence)
│   │       └── webhooks.py     # HMAC sign/verify + dispatch (max 2 retries)
│   ├── tests/                  # Pytest unit & integration suite (150 tests)
│   └── requirements.txt        # Python backend dependencies
├── remotion/
│   ├── src/
│   │   ├── compositions/
│   │   │   └── MainVideo.tsx   # Core Remotion video layout & series sequence
│   │   ├── components/
│   │   │   ├── DynamicSubtitles.tsx # Kinetic word-level subtitle highlighter
│   │   │   └── AudioTrack.tsx  # Dynamic speech audio ducking component
│   │   ├── Root.tsx            # Composition registration (Shorts916 & Landscape169)
│   │   └── types.ts            # Manifest & scene interfaces
│   ├── scripts/
│   │   └── generate_placeholder_audio.mjs # Synthetic placeholder audio (NOT licensed media)
│   ├── package.json
│   └── remotion.config.ts
├── scripts/
│   └── run_demo.py             # End-to-End autonomous demo script
├── pytest.ini
├── .env.example
└── README.md
```

---

## ⚡ Quickstart Guide

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### 1b. LLM Config (M1 Pro 16GB personal, default $0 local)
```bash
# .env: LLM_PROVIDER=ollama, OLLAMA_MODEL=qwen2.5:3b (~2GB), OLLAMA_BASE_URL=http://localhost:11434
ollama serve & ollama pull qwen2.5:3b  # local only; Qwen-72B via HF là hf-cloud optional; FLUX cloud-only
```

### 2. ⚡ One-Command Studio Launch (Canvas UI + Remotion)
```bash
./run_studio.sh
```
- **Semantic Workflow Canvas UI**: `http://localhost:8000/` (or `http://localhost:8000/canvas`)
- **Remotion Timeline Studio**: `http://localhost:3000/`
- **FastAPI OpenAPI Swagger**: `http://localhost:8000/docs`

---

## 🎨 Semantic Workflow Canvas Studio (Chinese AI Studio Style)

Inspired by modern Asian AI creative platforms (Kling AI, Jimeng, LiblibAI, Jianying AI Workflows), the **Video-Agent Studio** provides a visual, node-based pipeline designed for YouTube (16:9) and TikTok/Shorts (9:16):

```text
[Input Prompt / Brief]
        ↓
[Node 1: Character Studio] ──→ Locks Face / Invariant DNA & 3 Visual Anchors
        ↓
[Node 2: World & Atmosphere] ──→ Art Style (Cinematic/Cyberpunk), Edge-TTS Voice, BGM Ducking
        ↓
[Node 3: Semantic Shot Sequence] ──→ 3-Act Breakdown (Hook ➜ Core ➜ CTA), Ken Burns motion
        ↓
[Node 4: Remotion Video Player] ──→ Real-time MP4 render, Karaoke Subtitles, Download
```

### 3. Backend Setup & Pytest Verification
```bash
# Clone and enter project directory
cd Video-Agent

# Setup Python Virtual Environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Run full test suite (Offline, $0 cost)
MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -v --tb=short
```

### 4. Remotion Video Composition Engine
```bash
cd remotion

# Install dependencies
npm install

# Verify Remotion bundle build
npm run bundle

# Open interactive Remotion preview in browser
npm run start
```

#### Render the demo video

```bash
cd remotion

# Synthesise the placeholder audio the default compositions reference
npm run placeholder-audio

# Render Shorts916 (534 frames @ 30fps) to an MP4
npm run build          # -> out/shorts.mp4 (repo root; served by the API at /out/shorts.mp4)
```

> **The audio in the default compositions is a placeholder, not media.**
> `remotion/public/audio/` is empty in a fresh clone because this project has no
> licence to redistribute third-party audio, so nothing is vendored. The default
> `Shorts916` / `Landscape169` manifests in `remotion/src/Root.tsx` need four
> files, and without them the render aborts on frame 1 with a 404 for
> `public/audio/bg_music.wav`.
>
> `npm run placeholder-audio` (`remotion/scripts/generate_placeholder_audio.mjs`,
> Node stdlib only) synthesises all four locally: a quiet three-note sine bed for
> `bg_music.wav` and a gated 130 Hz hum for each `speech_scene_N.wav`, purely so
> the audio-ducking envelope is audible in a demo. **It is synthetic tone, not
> music and not speech.** Drop real, licensed media into
> `remotion/public/audio/` under the same names and it is used instead — the
> generator never overwrites an existing file unless you pass `--force`. The WAVs
> are covered by `.gitignore`, so no binary media is committed. The live TTS
> path is unaffected: Edge-TTS still writes real `speech_scene_N.mp3`.

---

## 🛡️ Benchmark & Verification Results

Every number below was measured on the maintainer's machine on **2026-09-26**
(Windows 11, Node 24.19.0, Python 3.11.0, 4x render concurrency). They are
local measurements, not a published benchmark, and they will differ on other
hardware.

- **Backend Pytest Suite**: `148 passed, 2 skipped` out of **150 collected**, 0 failed.
- **Remotion Bundle** (`npx remotion bundle src/index.ts`): exit 0 in **5.4 s**, no
  TypeScript or runtime errors.
- **Video render** (`npm run build`, composition `Shorts916`): exit 0 in **49.9 s**,
  534/534 frames encoded, `out/shorts.mp4` = **~18.3 MB** (the exact
  byte count drifts by a few hundred between runs, which is normal for the h264
  encoder).
  CI runs this render on every push, so a render that cannot complete now fails
  the build instead of passing silently.
- **CPFM ledger precision**: `cost_usd` is stored as `TEXT` and every sum and
  divide runs in `decimal.Decimal` — never SQL `SUM()`, which would coerce the
  column back to `REAL` and reintroduce drift. Money fields accept `Decimal`,
  `int` and `str` exactly; a `float` is accepted **only** when it is already
  exact at 4 decimal places, so binary drift such as `0.1 + 0.2` is **rejected**
  rather than silently rounded. Proven in
  `backend/tests/test_decimal_precision.py`.
- **Cost Efficiency (CPFM)**: **unmeasured claim.** Keyframe-first planning is
  *designed* to cut CPFM by rejecting expensive clip generations before they are
  rendered, but no A/B run against a naive unanchored baseline has been
  performed, so **no "60%+ reduction" figure is asserted here**. What the repo
  does provide is the measurement instrument: `CostLedger` reports
  `cost_per_finished_minute`, `retry_ratio` and `gross_to_net_ratio` for whatever
  run you point it at. Comparing that against a naive baseline is left to you.

---

## 🚀 DEPLOYMENT CHỐT — Cloud-First GPU (Serverless)

> **Chốt kiến trúc:** Training = **Zero Training** (chỉ API test, xem `colab/hf_inference_demo.ipynb`).
> Deployment duy nhất: **Cloud-First** — LangGraph orchestration + API chuyên dụng
> (Kling / Wan2.1 / HF Inference / Fal.ai), serverless GPU burst **pay-per-second**
> (VRAM **24–80GB** class: A10G/L4/A100/H100 theo provider).
> **Local (Ollama `qwen2.5:3b`) chỉ viết kịch bản text — KHÔNG render video local.**
> Test offline $0 qua `MockVideoProvider` / `MockTTSProvider` (`MOCK_VIDEO=true MOCK_TTS=true`,
> `LLM_PROVIDER=mock`). Không reranker (video assembly pipeline).

| Môi trường | Vai trò | Provider |
|---|---|---|
| Cloud (duy nhất để render) | Video render GPU burst | `VIDEO_PROVIDER=kling/hf/cloud` (Kling/Wan2.1/HF Inference/Fal.ai), `KlingWanProvider` mock-mode khi thiếu key |
| Cloud (optional) | Scriptwriter 72B | `LLM_PROVIDER=hf-cloud` (`HuggingFaceScriptwriter`, Qwen2.5-72B-Instruct) |
| Local | Viết kịch bản text only | `LLM_PROVIDER=ollama` (`qwen2.5:3b` ~2GB, M1 Pro 16GB) — không render |
| CI/Offline | Test $0 | `LLM_PROVIDER=mock` + `MockVideo/MockTTS` (deterministic fallback) |

Chi tiết: xem `docs/DEPLOYMENT_CLOUD_FIRST.md`.

## 🛡️ API / Job / Delivery Safety (plan 2026-09-18)

- **Auth bắt buộc**: mọi mutation cần `X-API-Key` (`API_KEY`), so sánh bằng
  `secrets.compare_digest` (constant-time) chứ không phải `!=`. **Fail-closed
  ngoài development**: nếu `API_KEY` chưa set mà `APP_ENV` là
  `staging`/`production`, mọi protected request trả **503** kèm message rõ
  ràng thay vì mở cửa — trước đây thiếu key là `return True`, tức mọi route
  mở cho bất kỳ ai. `production` còn fail lúc khởi động nếu thiếu `API_KEY` hoặc
  `CORS_ORIGINS` (không wildcard + credentials). `development` là ngoại lệ
  **có chủ đích và được ghi rõ** để demo offline và test suite chạy không cần
  secret; đặt `API_KEY` trong development là enforce y hệt production.
- **Provider trung thực**: không còn `SUCCEEDED` mặc định. Mỗi provider submit
  và giữ remote job id; mock clip luôn `mode=mock` + cost 0, không bao giờ bị
  gắn nhãn cloud render.
- **Job bền vững**: SQLite store (`backend/app/api/store.py`) giữ
  projects/jobs/subscriptions/receipts qua restart; idempotency key tránh
  double-bill.
- **Render async**: `POST /api/v1/canvas/render` → `202 {job_id, PENDING}`;
  worker chạy Remotion với timeout (`RENDER_TIMEOUT_SEC`) và manifest per-job.
- **Webhook SSRF-safe**: reject loopback/RFC1918/link-local/DNS-private; HMAC
  per-target (`WEBHOOK_SECRET`, không còn `dev-secret` ở production) với
  idempotent delivery receipts.

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
