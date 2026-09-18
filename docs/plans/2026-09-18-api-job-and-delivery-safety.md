# Video-Agent API, Job, and Delivery Safety Implementation Plan

> **EXECUTION STATUS (2026-09-18):** Tasks 1–5 implemented and verified.
> Full backend suite: **82 passed, 2 skipped**
> (`MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q backend/tests`);
> `npm run bundle` in `remotion/` succeeds. Deviations to note:
> (1) durable store is SQLite (project's existing storage pattern) rather than a
> separate queue service — the worker interface is DB-backed as the plan allows;
> (2) the render worker runs inline after the 202 response via FastAPI
> `BackgroundTasks`, so a production deployment should still run the
> `backend.app.jobs.render_worker` entrypoint in a dedicated process;
> (3) `GET /api/v1/jobs/{job_id}` now 404s for unknown ids (previously returned
> a blind `SUCCEEDED` from the provider) — callers must create the job first.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
# Video-Agent API, Job, and Delivery Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make production API access authenticated, provider/job state truthful and durable, and webhook delivery safe against replay and internal-network abuse.

**Architecture:** Replace process dictionaries with persistent project/job/subscription records. A provider returns `PENDING` until its verified provider-specific status endpoint reports terminal state; mock behavior remains only behind explicit test/dev flags. Render requests enqueue durable jobs and return 202; a worker executes the subprocess. Webhooks are allowlisted, signed with per-target secrets, and delivered asynchronously with idempotency.

**Tech Stack:** Python, FastAPI, SQLAlchemy/SQLite, HTTPX, Remotion, pytest.

**Spec:** `docs/spec.md`, `docs/DEPLOYMENT_CLOUD_FIRST.md`

## Global Constraints

- Production startup requires `API_KEY`, non-wildcard CORS origins, and no default webhook secret.
- Missing video provider credentials fail closed in production; never bill or label a mock clip as a cloud render.
- API workers never execute a long Remotion render synchronously in the request path.
- Webhook destinations must reject loopback, link-local, private, and unapproved domains/IPs.

---

### Task 1: Production authentication and CORS

**Files:**
- Modify: `backend/app/api/server.py`, `backend/app/config.py` or current settings module, `.env.example`
- Test: `backend/tests/test_api_auth.py`, `backend/tests/test_slice_c_delivery.py`

**Interfaces:**
- Produces: `require_api_key` that fails startup in production when key/origins are absent.

- [ ] Write failing tests for unauthenticated mutation rejection, production startup validation, configured allowed origin, and denied wildcard/credential combination.
- [ ] Centralize environment configuration; require auth on project, job, canvas render, subscription, and delivery mutations.
- [ ] Configure CORS from a comma-separated allowlist; use wildcard only in explicit development mode without credentials.
- [ ] Run `MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q backend/tests/test_api_auth.py backend/tests/test_slice_c_delivery.py`.

### Task 2: Durable projects and truthful provider jobs

**Files:**
- Modify: `backend/app/api/store.py`, `backend/app/api/server.py`, `backend/app/providers/kling_provider.py`, `backend/app/providers/private_gpu.py`, `backend/app/providers/hf_video.py`
- Test: `backend/tests/test_slice_a_backend.py`, `backend/tests/contract/test_provider_schema.py`, `backend/tests/test_storage_stateless.py`

**Interfaces:**
- Produces: persistent `ProjectRecord` and `JobRecord` with status `PENDING|RUNNING|SUCCEEDED|FAILED`, provider job id, mode, and error.

- [ ] Write failing tests proving projects/jobs survive a module reload, a missing cloud credential fails in production, mock clips report `mode=mock` and zero cloud cost, and provider polling returns real pending/terminal state.
- [ ] Extend the existing SQLite store with project/job persistence and replace `PROJECTS_STORE`/`JOBS_STORE` fallbacks in API endpoints.
- [ ] Make each live provider submit and retain its remote job id; implement its status retrieval; do not return `SUCCEEDED` blindly. Keep deterministic mock provider explicitly separate.
- [ ] Run focused provider/store tests.

### Task 3: Asynchronous render execution

**Files:**
- Create: `backend/app/jobs/render_worker.py`
- Modify: `backend/app/api/server.py`, `backend/app/api/store.py`, `backend/app/storage/factory.py`
- Test: `backend/tests/test_render_jobs.py`

**Interfaces:**
- Produces: `POST /api/v1/canvas/render` returns `202 {job_id,status:"PENDING"}`; worker transitions job and stores artifact key.

- [ ] Write tests that render submission returns before invoking a render subprocess, worker success stores an artifact, worker failure persists stderr safely, and duplicate idempotency key returns the existing job.
- [ ] Implement a database-backed render queue/worker interface; execute Remotion in the worker with a bounded timeout and per-job manifest/output paths, never shared `render_manifest.json`.
- [ ] Expose authenticated job polling and artifact URL retrieval from configured storage.
- [ ] Run `MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q backend/tests/test_render_jobs.py`.

### Task 4: Safe webhook subscriptions and delivery

**Files:**
- Modify: `backend/app/api/webhooks.py`, `backend/app/delivery/dispatcher.py`, `backend/app/api/server.py`, `backend/app/api/store.py`
- Test: `backend/tests/test_slice_c_delivery.py`, `backend/tests/test_webhook_security.py`

**Interfaces:**
- Produces: persisted `WebhookSubscription` with encrypted/configured per-target secret and idempotent delivery receipts.

- [ ] Write failing tests rejecting `localhost`, RFC1918, link-local, and DNS-resolved private targets; rejecting missing secret in production; and ensuring duplicate event delivery shares one idempotency record.
- [ ] Validate destination URLs at create time and immediately before dispatch; use DNS resolution safeguards and a configured hostname/IP allowlist.
- [ ] Remove `dev-secret` fallback outside explicit development mode; persist subscriptions and receipts; deliver through a worker instead of blocking the API request.
- [ ] Run `MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q backend/tests/test_slice_c_delivery.py backend/tests/test_webhook_security.py` and then the full backend suite.

### Task 5: Deployment verification

**Files:**
- Modify: `docs/DEPLOYMENT_CLOUD_FIRST.md`, `README.md`, `.github/workflows/ci.yml`
- Test: `backend/tests/test_slice_c_delivery.py`

- [ ] Document mandatory production settings, provider credential behavior, worker deployment, webhook allowlisting, and rollback/retry procedure.
- [ ] Add CI gates for authentication, provider truthfulness, render job persistence, and webhook SSRF tests.
- [ ] Run `MOCK_VIDEO=true MOCK_TTS=true LLM_PROVIDER=mock pytest -q` and `npm run bundle` in `remotion/`.
