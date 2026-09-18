# Video-Agent Production API and Job Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make project, rendering, provider, and webhook states durable and truthful; secure the API by default; and prevent simulated results from being mistaken for cloud production work.

**Architecture:** All projects, jobs, subscriptions, and receipts persist in storage. Provider status is polled from the real provider contract; mock/simulated results carry an explicit mode and cannot satisfy production. Expensive rendering runs through a durable worker/job state machine, while webhooks use allowlisted destinations and per-target secrets.

**Tech Stack:** Python, FastAPI, SQLite/S3-compatible storage, Remotion, HTTPX, pytest.

**Spec:** `docs/spec.md`

## Global Constraints

- Production requires API authentication and explicit CORS origins; no permissive fallback.
- Missing provider credentials or status must be `UNCONFIGURED`/`UNKNOWN`, never `SUCCEEDED`.
- A synchronous HTTP request must not perform a long Remotion render.
- Webhook targets must not reach loopback, private, link-local, or metadata IP ranges.

---

### Task 1: Secure API defaults and durable project/job records

**Files:**
- Modify: `backend/app/api/server.py`, `backend/app/api/store.py`, `backend/app/storage/*`, `.env.example`
- Create: `backend/tests/test_api_security.py`, `backend/tests/test_job_store.py`

- [ ] Write tests asserting production startup fails without API key/CORS allowlist, protected mutations reject missing/invalid keys, and project/job records survive a new application instance.
- [ ] Replace in-memory `PROJECTS_STORE`, `JOBS_STORE`, and webhook subscription list with persistent repositories backed by the configured storage/database interface.
- [ ] Apply authentication and rate-limit dependencies to every mutation and sensitive read endpoint; configure CORS from an explicit comma-separated origin allowlist.
- [ ] Return readiness with storage, queue, provider configuration, and auth status; never create directories or mutable artifacts at import time in production.
- [ ] Run `MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q backend/tests/test_api_security.py backend/tests/test_job_store.py backend/tests`.

### Task 2: Truthful provider state and production-mode boundary

**Files:**
- Modify: `backend/app/providers/kling_provider.py`, `backend/app/providers/private_gpu.py`, `backend/app/providers/hf_video.py`, `backend/app/providers/__init__.py`, `backend/app/agent/nodes.py`
- Test: `backend/tests/test_provider_status.py`, `backend/tests/test_private_gpu_provider.py`, `backend/tests/test_agent_graph.py`

- [ ] Write tests for missing credentials, provider submission response shape, pending/failed/succeeded polling, unreachable endpoint, and mock mode; assert costs and `execution_mode` match the actual path.
- [ ] Define a provider result contract with `job_id`, `status`, `execution_mode`, provider receipt, and actual/estimated cost fields.
- [ ] Implement provider-specific polling endpoints; remove unconditional `SUCCEEDED` responses and synthetic production URLs.
- [ ] Make production reject unconfigured/mock providers before generation; keep mock/simulation only with explicit development/test flags and label UI/API responses.
- [ ] Run `MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q backend/tests/test_provider_status.py backend/tests/test_private_gpu_provider.py backend/tests/test_agent_graph.py`.

### Task 3: Durable asynchronous render worker

**Files:**
- Create: `backend/app/jobs/render_worker.py`, `backend/app/jobs/repository.py`
- Modify: `backend/app/api/server.py`, `backend/app/agent/graph.py`, `backend/app/storage/*`
- Test: `backend/tests/test_render_jobs.py`, `backend/tests/test_slice_c_delivery.py`

- [ ] Write tests for submit/poll/cancel/retry idempotency, worker restart recovery, render failure capture, and artifact persistence.
- [ ] Replace direct `subprocess.run(npx remotion render...)` in request handlers with a queued render job state machine: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`.
- [ ] Implement a worker command that claims one job transactionally, renders with a bounded timeout, persists output/manifest/log reference, and records exit status.
- [ ] Change canvas render API to enqueue and return `202 {job_id,status_url}`; expose status and signed/downloadable completed artifact metadata.
- [ ] Run the render-job tests with mock providers and run the existing backend suite.

### Task 4: Safe, durable webhook delivery

**Files:**
- Modify: `backend/app/delivery/dispatcher.py`, `backend/app/api/webhooks.py`, `backend/app/api/server.py`
- Create: `backend/tests/test_webhook_security.py`

- [ ] Write tests rejecting localhost, private/metadata addresses, redirect-to-private destinations, absent secrets in production, duplicate subscriptions, and failed delivery retry/replay behavior.
- [ ] Validate and resolve targets before subscription and before delivery; require HTTPS in production and generate/store a per-target secret rather than falling back to `dev-secret`.
- [ ] Persist subscriptions and delivery receipts; enqueue fan-out delivery independently from request handling and add idempotency event ids.
- [ ] Run `MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q backend/tests/test_webhook_security.py backend/tests/test_slice_c_delivery.py`.

### Task 5: End-to-end operational evidence

**Files:**
- Modify: `README.md`, `docs/DEPLOYMENT_CLOUD_FIRST.md`, `.github/workflows/ci.yml`
- Test: `backend/tests/test_slice_c_delivery.py`

- [ ] Add CI checks for secure production configuration rejection, provider status contract, durable render recovery, and webhook SSRF protection.
- [ ] Document mock versus production modes, worker startup, provider credentials, key rotation, CORS, artifact retention, and recovery procedures.
- [ ] Run `MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q` and the Remotion bundle command; record the exact evidence in the deployment document.
