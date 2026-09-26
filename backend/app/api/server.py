"""
FastAPI Application Server for Video-Agent.
Provides REST endpoints for Project creation, HITL approval, Status polling, Cost Audit,
and the Semantic Workflow Canvas API.
"""
import asyncio
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import uuid4

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, status, Header, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.app.agent.state import VideoProjectState, AspectRatio, PipelineStatus
from backend.app.agent.graph import video_agent_graph
from backend.app.consistency.character_dna import CharacterDNAManager
from backend.app.cost.ledger import CostLedger
from backend.app.storage.factory import get_storage
from backend.app.providers.hf_llm import HuggingFaceScriptwriter
from backend.app.providers.image_providers import get_default_image_provider
from backend.app.config import cors_options, load_settings

BASE_DIR = Path(__file__).parent.parent.parent.parent
REMOTION_DIR = BASE_DIR / "remotion"
PUBLIC_DIR = REMOTION_DIR / "public"
OUT_DIR = Path(os.getenv("OUT_DIR", str(BASE_DIR / "out")))


def _out_dir() -> Path:
    """WP4: OUT_DIR cấu hình được qua env (default BASE_DIR/out)."""
    return Path(os.getenv("OUT_DIR", str(BASE_DIR / "out")))


def _write_artifact(key: str, data: bytes) -> None:
    """WP4: mọi artifact persist qua storage interface (local/s3mock/r2)."""
    get_storage().save(key, data)
DASHBOARD_DIR = BASE_DIR / "dashboard"

PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Video-Agent API & Canvas Studio",
    version="1.0.0",
    description="Autonomous AI Video Production & Semantic Workflow Canvas"
)

app.add_middleware(CORSMiddleware, **cors_options(load_settings()))

# Mount static asset folders
app.mount("/out", StaticFiles(directory=str(OUT_DIR)), name="out")
app.mount("/public-assets", StaticFiles(directory=str(PUBLIC_DIR)), name="public-assets")

# Durable SQLite store (replaces process-local dicts); cost ledger
def _durable_store():
    from backend.app.api.store import get_store
    return get_store()


PROJECTS_STORE: Dict[str, VideoProjectState] = {}
cost_ledger = CostLedger()

# Slice C stores: async jobs + webhook subscriptions + rate-limit buckets
# NOTE: JOBS_STORE / WEBHOOK_SUBSCRIPTIONS dicts are legacy mirrors only;
# the SQLite store (get_store()) is the source of truth.
JOBS_STORE: Dict[str, Dict[str, Any]] = {}
WEBHOOK_SUBSCRIPTIONS: List[Dict[str, Any]] = []
_RATE_BUCKETS: Dict[str, List[float]] = {}
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))


def _app_env() -> str:
    return os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()


def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Fail-closed API key check for every protected route.

    Three deliberate rules:

    1. An unset `API_KEY` is never a silent allow outside development. When the
       key is missing and `APP_ENV` is staging/production the request is refused
       with 503 and an explicit message, so "no key configured" can never be
       mistaken for "key supplied and correct".
    2. The comparison is `secrets.compare_digest`, so a wrong key cannot be
       recovered byte-by-byte from response timing.
    3. Development is the one documented exception: with no `API_KEY` set the
       protected routes stay open so the offline demo and the test suite run
       without provisioning a secret. Set `API_KEY` in development and you get
       the same enforcement as production.
    """
    expected = os.getenv("API_KEY", "").strip()
    if not expected:
        if _app_env() in ("production", "prod", "staging"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API_KEY is not configured; refusing request (fail-closed)",
            )
        return True
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def check_rate_limit(request: Request):
    """Simple in-memory per-IP rate limiter (generous default so offline tests never trip)."""
    import time as _time
    client = request.client.host if request.client else "unknown"
    now = _time.time()
    window = [t for t in _RATE_BUCKETS.get(client, []) if now - t < 60.0]
    if len(window) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    window.append(now)
    _RATE_BUCKETS[client] = window
    return True


@app.get("/")
@app.get("/canvas")
def get_canvas_page():
    index_file = DASHBOARD_DIR / "index.html"
    if not index_file.exists():
        return {"status": "Video-Agent Canvas API is running. Dashboard file not found."}
    return FileResponse(index_file)


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "healthy", "service": "video-agent", "version": "1.0.0"}


def _check_config_valid() -> None:
    """Non-mutating config probe: environment name must be known."""
    env = os.getenv("APP_ENV", "development").strip().lower()
    if env not in ("development", "staging", "production"):
        raise RuntimeError(f"unknown APP_ENV: {env}")


def _check_storage_configured() -> None:
    """Non-mutating config probe: storage backend selection must be valid.
    Opens no connections, creates no directories, writes nothing."""
    backend = os.getenv("STORAGE_BACKEND", "local").strip().lower()
    if backend not in ("local", "s3mock", "r2"):
        raise RuntimeError(f"unsupported STORAGE_BACKEND: {backend}")
    if backend == "r2" and not os.getenv("R2_ENDPOINT", "").strip():
        raise RuntimeError("R2_ENDPOINT missing for STORAGE_BACKEND=r2")


@app.get("/health/live", status_code=status.HTTP_200_OK)
def health_live():
    """Liveness: process can serve. No dependency checks."""
    return {"status": "ok", "service": "video-agent", "version": "1.0.0"}


@app.get("/health/ready")
def health_ready():
    """Readiness: config valid + storage backend configured. No writes."""
    checks: Dict[str, str] = {"config": "ok"}
    try:
        _check_config_valid()
    except Exception as exc:
        checks["config"] = f"not-ready: {exc}"
    try:
        _check_storage_configured()
        checks["storage"] = "ok"
    except Exception as exc:
        checks["storage"] = f"not-ready: {exc}"
    ready = all(value == "ok" for value in checks.values())
    return {"status": "ready" if ready else "not-ready", "checks": checks}


# -------------------------------------------------------------
# Standard Project Endpoints
# -------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    topic: str
    target_duration_sec: float = 30.0
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT_9_16
    character_name: Optional[str] = None
    character_prompt_prefix: Optional[str] = None


class ApproveProjectRequest(BaseModel):
    approved: bool = True
    feedback: Optional[str] = None


@app.post("/api/v1/projects", status_code=status.HTTP_201_CREATED)
def create_project(req: CreateProjectRequest, _auth: bool = Depends(require_api_key)):
    project_id = f"proj_{uuid4().hex[:8]}"

    char_dna = None
    if req.character_name and req.character_prompt_prefix:
        char_dna = CharacterDNAManager.create_character(
            character_id=f"char_{req.character_name.lower().replace(' ', '_')}",
            name=req.character_name,
            prompt_prefix=req.character_prompt_prefix
        )

    initial_state = VideoProjectState(
        project_id=project_id,
        topic=req.topic,
        target_duration_sec=req.target_duration_sec,
        aspect_ratio=req.aspect_ratio,
        character_dna=char_dna,
        status=PipelineStatus.INITIATED
    )

    result = video_agent_graph.invoke(initial_state)
    updated_state = VideoProjectState(**result) if isinstance(result, dict) else result
    PROJECTS_STORE[project_id] = updated_state

    return {
        "project_id": project_id,
        "status": updated_state.status,
        "estimated_cost_usd": updated_state.estimated_cost_usd,
        "scenes_count": len(updated_state.scenes),
        "scenes": [s.model_dump() for s in updated_state.scenes],
        "error_message": updated_state.error_message
    }


@app.post("/api/v1/projects/{project_id}/approve", status_code=status.HTTP_200_OK)
def approve_project(project_id: str, req: ApproveProjectRequest, _auth: bool = Depends(require_api_key)):
    if project_id not in PROJECTS_STORE:
        raise HTTPException(status_code=404, detail="Project not found")

    current_state = PROJECTS_STORE[project_id]

    if not req.approved:
        current_state.status = PipelineStatus.FAILED
        current_state.error_message = req.feedback or "Rejected by supervisor"
        PROJECTS_STORE[project_id] = current_state
        return {"project_id": project_id, "status": current_state.status}

    current_state.hitl_approved = True
    current_state.status = PipelineStatus.APPROVED

    result = video_agent_graph.invoke(current_state)
    final_state = VideoProjectState(**result) if isinstance(result, dict) else result
    PROJECTS_STORE[project_id] = final_state

    return {
        "project_id": project_id,
        "status": final_state.status,
        "actual_cost_usd": final_state.actual_cost_usd,
        "cost_per_finished_minute": final_state.cost_per_finished_minute,
        "render_manifest": final_state.render_manifest
    }


@app.get("/api/v1/projects", status_code=status.HTTP_200_OK)
def list_projects():
    """List all known project ids (in-memory + persisted store, best-effort)."""
    ids = set(PROJECTS_STORE.keys())
    try:
        from backend.app.api.store import ProjectStore
        ids.update(ProjectStore().list_ids())
    except Exception:
        pass
    return sorted(ids)


@app.get("/api/v1/projects/{project_id}", status_code=status.HTTP_200_OK)
def get_project(project_id: str):
    if project_id not in PROJECTS_STORE:
        raise HTTPException(status_code=404, detail="Project not found")
    return PROJECTS_STORE[project_id].model_dump()


@app.get("/api/v1/cost/audit/{project_id}", status_code=status.HTTP_200_OK)
def get_cost_audit(project_id: str):
    if project_id not in PROJECTS_STORE:
        raise HTTPException(status_code=404, detail="Project not found")
    state = PROJECTS_STORE[project_id]
    total_duration = sum(s.duration_sec for s in state.scenes)
    return cost_ledger.get_project_metrics(project_id, total_duration)


# NOTE: GET /api/v1/jobs/{job_id} is defined once below (durable-store backed);
# the legacy provider-blind poller was merged into it.


@app.get("/api/v1/projects/{project_id}/status", status_code=status.HTTP_200_OK)
def get_project_status(project_id: str):
    """Lightweight project status probe (Slice C)."""
    if project_id not in PROJECTS_STORE:
        raise HTTPException(status_code=404, detail="Project not found")
    st = PROJECTS_STORE[project_id]
    return {"project_id": project_id, "status": str(st.status.value if hasattr(st.status, "value") else st.status),
            "hitl_approved": st.hitl_approved, "scenes_count": len(st.scenes)}


class RejectProjectRequest(BaseModel):
    feedback: Optional[str] = None


@app.post("/api/v1/projects/{project_id}/reject", status_code=status.HTTP_200_OK)
def reject_project(project_id: str, req: RejectProjectRequest, _auth: bool = Depends(require_api_key)):
    """Explicit supervisor rejection (Slice C)."""
    if project_id not in PROJECTS_STORE:
        raise HTTPException(status_code=404, detail="Project not found")
    st = PROJECTS_STORE[project_id]
    st.status = PipelineStatus.FAILED
    st.error_message = req.feedback or "Rejected by supervisor"
    PROJECTS_STORE[project_id] = st
    return {"project_id": project_id, "status": str(st.status.value), "error_message": st.error_message}


class CreateJobRequest(BaseModel):
    prompt: str = "a calm lake"
    duration_sec: float = 4.0
    provider: str = "mock"
    idempotency_key: Optional[str] = None


@app.post("/api/v1/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_job(req: CreateJobRequest, request: Request,
               _auth: bool = Depends(require_api_key), _rl: bool = Depends(check_rate_limit)):
    """Create a durable generation job; poll via GET /api/v1/jobs/{job_id}.

    A provider-specific remote job id is submitted and retained; mock clips
    report mode=mock with zero cloud cost. Duplicate idempotency keys return
    the existing job instead of billing twice.
    """
    import os as _os

    from backend.app.providers.mock_provider import MockVideoProvider
    from backend.app.providers.hf_video import HuggingFaceVideoProvider

    env = _os.environ.get("APP_ENV", _os.environ.get("ENVIRONMENT", "development")).lower()
    name = (req.provider or "mock").lower()
    if name == "mock":
        provider, mode = MockVideoProvider(), "mock"
    elif name in ("hf", "huggingface"):
        provider, mode = HuggingFaceVideoProvider(), (
            "mock" if not HuggingFaceVideoProvider().hf_token
            or _os.environ.get("MOCK_VIDEO", "false").lower() == "true" else "live")
    elif name == "kling":
        from backend.app.providers.kling_provider import KlingWanProvider
        kling = KlingWanProvider()
        if env == "production" and not kling.api_key:
            raise HTTPException(status_code=503, detail="KLING_API_KEY is required in production")
        provider, mode = kling, ("mock" if kling._mock_mode() else "live")
    elif name == "private_gpu":
        from backend.app.providers.private_gpu import PrivateGPUProvider
        gpu = PrivateGPUProvider()
        provider, mode = gpu, ("mock" if not gpu.is_configured
                               or _os.environ.get("MOCK_VIDEO", "false").lower() == "true" else "live")
    else:
        raise HTTPException(status_code=400, detail=f"unknown provider: {req.provider}")
    submit = getattr(provider, "submit_job", None)
    if submit is None:
        raise HTTPException(status_code=500, detail="provider cannot submit jobs")
    try:
        submitted = submit(prompt=req.prompt, duration_sec=req.duration_sec)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    job_id = f"job_{uuid4().hex[:8]}"
    record = _durable_store().create_job({
        "job_id": job_id,
        "prompt": req.prompt,
        "duration_sec": req.duration_sec,
        "provider": name,
        "provider_job_id": submitted.get("provider_job_id"),
        "mode": submitted.get("mode", mode),
        "status": "PENDING",
        "idempotency_key": req.idempotency_key,
        "cost_usd": submitted.get("cost_usd", 0.0),
    })
    JOBS_STORE[job_id] = {"job_id": job_id, "status": record.get("status", "PENDING")}
    return {"job_id": job_id, "provider": name, "status": "PENDING",
            "mode": record.get("mode", mode), "cost_usd": record.get("cost_usd", 0.0)}


@app.get("/api/v1/jobs/{job_id}", status_code=status.HTTP_200_OK)
def get_async_job(job_id: str, provider: str = "mock"):
    """Poll a durable job; report the provider's real pending/terminal state."""
    stored = _durable_store().get_job(job_id) or JOBS_STORE.get(job_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Job not found")
    prov_name = stored.get("provider") or provider
    from backend.app.providers.mock_provider import MockVideoProvider
    from backend.app.providers.hf_video import HuggingFaceVideoProvider
    providers = {"mock": MockVideoProvider(), "hf": HuggingFaceVideoProvider()}
    try:
        from backend.app.providers.kling_provider import KlingWanProvider
        providers["kling"] = KlingWanProvider()
    except Exception:
        pass
    try:
        from backend.app.providers.private_gpu import PrivateGPUProvider
        providers["private_gpu"] = PrivateGPUProvider()
    except Exception:
        pass
    prov = providers.get(prov_name, providers["mock"])
    remote_id = stored.get("provider_job_id") or job_id
    job_status = prov.check_status(remote_id)
    live = str(job_status.value if hasattr(job_status, "value") else job_status)
    _durable_store().update_job(job_id, status=live)
    out = {"job_id": job_id, "provider": prov_name, "status": live,
           "mode": stored.get("mode", "mock"),
           "error": stored.get("error"),
           "artifact_key": stored.get("artifact_key"),
           "cost_usd": stored.get("cost_usd", 0.0)}
    return out


class SubscribeRequest(BaseModel):
    url: str
    events: Optional[List[str]] = None


@app.post("/api/v1/webhooks/subscribe", status_code=status.HTTP_201_CREATED)
def subscribe_webhook(req: SubscribeRequest, _auth: bool = Depends(require_api_key),
                      _rl: bool = Depends(check_rate_limit)):
    """Subscribe an SSRF-safe URL to project event webhooks (durable)."""
    from backend.app.api.webhooks import WebhookSecurityError, validate_webhook_url

    try:
        validate_webhook_url(req.url)
    except WebhookSecurityError as exc:
        raise HTTPException(status_code=400, detail=f"WEBHOOK_TARGET_REJECTED: {exc}")
    import os as _os

    env = _os.environ.get("APP_ENV", _os.environ.get("ENVIRONMENT", "development")).lower()
    if env in ("production", "prod", "staging") and not _os.environ.get("WEBHOOK_SECRET", "").strip():
        raise HTTPException(status_code=503, detail="WEBHOOK_SECRET is required in production")
    events = req.events or ["project.completed"]
    record = _durable_store().save_subscription(req.url, "configured", events)
    WEBHOOK_SUBSCRIPTIONS.clear()
    WEBHOOK_SUBSCRIPTIONS.extend(_durable_store().list_subscriptions())
    return {"subscribed": True, "subscription": record}


@app.get("/api/v1/webhooks/subscriptions", status_code=status.HTTP_200_OK)
def list_subscriptions():
    return _durable_store().list_subscriptions()


class DeliverRequest(BaseModel):
    project_id: str
    targets: List[str] = Field(default_factory=list)
    event: str = "project.completed"


@app.post("/api/v1/deliver", status_code=status.HTTP_200_OK)
def deliver_project(req: DeliverRequest, _auth: bool = Depends(require_api_key),
                    _rl: bool = Depends(check_rate_limit)):
    """Fan-out signed, idempotent delivery receipts (never blocks on render)."""
    from concurrent.futures import ThreadPoolExecutor

    from backend.app.delivery.dispatcher import DeliveryTarget, deliver_idempotent
    payload = json.dumps({"project_id": req.project_id, "event": req.event}).encode()
    urls = list(req.targets) or [s["url"] for s in _durable_store().list_subscriptions()]
    targets = [DeliveryTarget(url=u) for u in urls]
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(targets) or 1))) as pool:
        receipts = list(pool.map(
            lambda t: deliver_idempotent(t, payload, event=req.event, timeout_sec=2.0),
            targets))
    return {"project_id": req.project_id, "event": req.event,
            "receipts": [r.model_dump() for r in receipts]}


# -------------------------------------------------------------
# Semantic Workflow Canvas Specific Endpoints
# -------------------------------------------------------------

class CanvasDecomposeRequest(BaseModel):
    topic: str
    character_name: Optional[str] = "Minh Anh"
    character_description: Optional[str] = "25yo Vietnamese tech creator, professional casual attire, modern studio"
    world_style: Optional[str] = "Cinematic Photorealistic, 8k, warm modern studio lighting"
    aspect_ratio: Optional[str] = "9:16"


class CanvasGenerateAudioRequest(BaseModel):
    text: str
    voice: Optional[str] = "vi-VN-HoaiMyNeural"
    scene_id: int = 1


class CanvasGenerateImageRequest(BaseModel):
    prompt: str
    scene_id: int = 1
    aspect_ratio: Optional[str] = "9:16"


class CanvasRenderRequest(BaseModel):
    projectId: str = "canvas_project"
    aspectRatio: str = "9:16"
    totalDurationSec: float = 17.8
    bgMusicUrl: str = "audio/bg_music.wav"
    scenes: List[Dict[str, Any]]


@app.post("/api/v1/canvas/decompose")
def canvas_decompose(req: CanvasDecomposeRequest, _auth: bool = Depends(require_api_key)):
    """Uses Hugging Face Qwen-72B to build the complete semantic workflow canvas."""
    writer = HuggingFaceScriptwriter()
    raw_scenes = writer.generate_script(req.topic)

    ken_burns_options = ["zoomIn", "panLeft", "zoomOut"]
    scenes = []
    for idx, s in enumerate(raw_scenes, start=1):
        motion = ken_burns_options[(idx - 1) % len(ken_burns_options)]
        scenes.append({
            "sceneId": idx,
            "title": s.get("title", f"Shot {idx}"),
            "voiceover": s.get("voiceover", ""),
            "visualPrompt": f"{req.character_description}, {s.get('visual_prompt', '')}, {req.world_style}",
            "durationSec": float(s.get("duration_sec", 5.0)),
            "kenBurnsEffect": motion,
            "audioUrl": f"audio/speech_scene_{idx}.mp3",
            "imageUrl": f"images/scene_{idx}.jpg"
        })

    return {
        "character": {
            "name": req.character_name,
            "description": req.character_description,
            "anchors": [
                "/public-assets/images/scene_1.jpg",
                "/public-assets/images/scene_2.jpg",
                "/public-assets/images/scene_3.jpg"
            ]
        },
        "world": {
            "style": req.world_style,
            "aspectRatio": req.aspect_ratio,
            "bgMusic": "audio/bg_music.wav"
        },
        "scenes": scenes
    }


@app.post("/api/v1/canvas/generate_audio")
async def canvas_generate_audio(req: CanvasGenerateAudioRequest, _auth: bool = Depends(require_api_key)):
    """Generates Edge-TTS speech and measures actual duration."""
    import edge_tts
    audio_filename = f"speech_scene_{req.scene_id}.mp3"
    audio_path = PUBLIC_DIR / "audio" / audio_filename
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    comm = edge_tts.Communicate(req.text, req.voice)
    await comm.save(str(audio_path))

    duration = 4.0
    try:
        res = subprocess.run(["afinfo", str(audio_path)], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if "estimated duration" in line:
                duration = float(line.split(":")[1].strip().split()[0])
                break
    except Exception:
        words = len(req.text.split())
        duration = max(2.5, round(words * 0.35, 2))

    return {
        "audioUrl": f"audio/{audio_filename}",
        "webUrl": f"/public-assets/audio/{audio_filename}",
        "durationSec": round(duration + 0.5, 2)
    }


@app.post("/api/v1/canvas/generate_image")
def canvas_generate_image(req: CanvasGenerateImageRequest, _auth: bool = Depends(require_api_key)):
    """Generates an image matching the scene prompt via Hugging Face provider."""
    image_filename = f"scene_{req.scene_id}.jpg"
    image_path = PUBLIC_DIR / "images" / image_filename
    image_path.parent.mkdir(parents=True, exist_ok=True)

    provider = get_default_image_provider()
    w = 576 if req.aspect_ratio == "9:16" else 1024
    h = 1024 if req.aspect_ratio == "9:16" else 576

    provider.generate_image(
        prompt=req.prompt,
        output_path=str(image_path),
        width=w,
        height=h,
        seed=1000 + req.scene_id
    )

    return {
        "imageUrl": f"images/{image_filename}",
        "webUrl": f"/public-assets/images/{image_filename}"
    }


class CanvasRenderRequest(BaseModel):
    projectId: str = "canvas_project"
    aspectRatio: str = "9:16"
    totalDurationSec: float = 17.8
    bgMusicUrl: str = "audio/bg_music.wav"
    scenes: List[Dict[str, Any]]
    idempotency_key: Optional[str] = None


def _prepare_canvas_manifest(req: "CanvasRenderRequest") -> Dict[str, Any]:
    """Normalize a canvas manifest (subtitles etc.) without touching disk."""
    manifest = req.model_dump()
    total_dur = 0.0
    for s in manifest.get("scenes", []):
        dur = float(s.get("durationSec", 5.0))
        total_dur += dur
        if not s.get("subtitles") and s.get("voiceover"):
            words = [w.strip() for w in s["voiceover"].strip().split() if w.strip()]
            if words:
                step = max(0.2, (dur - 0.5) / max(1, len(words)))
                s["subtitles"] = [
                    {
                        "word": w.upper(),
                        "start": round(0.15 + i * step, 2),
                        "end": round(0.15 + (i + 0.85) * step, 2)
                    }
                    for i, w in enumerate(words)
                ]
    manifest["totalDurationSec"] = round(total_dur, 2)
    return manifest


@app.post("/api/v1/canvas/render", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def canvas_render(req: CanvasRenderRequest, _auth: bool = Depends(require_api_key),
                  background: BackgroundTasks = None):
    """Enqueue a durable render job; never run Remotion in the request path.

    Returns 202 {job_id, status:"PENDING"}; the worker executes the render
    subprocess with a per-job manifest/output (never the shared
    render_manifest.json). A duplicate idempotency key returns the existing job.
    """
    manifest = _prepare_canvas_manifest(req)
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    _write_artifact(f"manifests/render_manifest_{req.projectId}.json", manifest_bytes)

    if os.environ.get("EVENTING_ENABLED") == "1":
        try:
            from backend.app.messaging import outbox as ox, envelope as env
            job_id = f"render_{uuid4().hex[:8]}"
            idem_key = req.idempotency_key or f"render:{job_id}"
            envelope = env.build_envelope(
                event_type="video.render.requested",
                producer="video/api",
                app="video",
                env=os.getenv("APP_ENV", "local"),
                correlation_id=f"tr-{job_id}",
                idempotency_key=idem_key,
                payload={
                    "job_id": job_id,
                    "project_id": req.projectId,
                    "aspect_ratio": req.aspectRatio,
                    "total_duration_sec": req.totalDurationSec,
                },
                payload_ref=None,
                schema_ref="video.render.commands.v1-value:1",
            )
            res = ox.enqueue_render_requested(
                job={
                    "job_id": job_id,
                    "project_id": req.projectId,
                    "aspect_ratio": req.aspectRatio,
                    "total_duration_sec": req.totalDurationSec,
                    "idempotency_key": idem_key,
                    "provider": "remotion",
                    "manifest_r2_key": f"manifests/render_manifest_{req.projectId}.json",
                },
                envelope=envelope,
            )
            return {"job_id": res["job_id"], "status": "PENDING"}
        except Exception:
            pass  # Fallback to local durable store if eventing DB blips

    record = _durable_store().create_job({
        "job_id": f"render_{uuid4().hex[:8]}",
        "prompt": f"canvas:{req.projectId}",
        "duration_sec": req.totalDurationSec,
        "provider": "remotion",
        "mode": "render",
        "status": "PENDING",
        "idempotency_key": req.idempotency_key,
        "cost_usd": 0.0,
    })
    job_id = record["job_id"]

    def _run() -> None:
        from backend.app.jobs.render_worker import run_render_job

        try:
            run_render_job(job_id, manifest)
        except Exception as exc:  # never crash the API worker thread
            _durable_store().update_job(job_id, status="FAILED", error=str(exc))

    if background is not None:
        background.add_task(_run)
    return {"job_id": job_id, "status": "PENDING"}
