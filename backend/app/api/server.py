"""
FastAPI Application Server for Video-Agent.
Provides REST endpoints for Project creation, HITL approval, Status polling, Cost Audit,
and the Semantic Workflow Canvas API.
"""
import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.app.agent.state import VideoProjectState, AspectRatio, PipelineStatus
from backend.app.agent.graph import video_agent_graph
from backend.app.consistency.character_dna import CharacterDNAManager
from backend.app.cost.ledger import CostLedger
from backend.app.providers.hf_llm import HuggingFaceScriptwriter
from backend.app.providers.image_providers import get_default_image_provider

BASE_DIR = Path(__file__).parent.parent.parent.parent
REMOTION_DIR = BASE_DIR / "remotion"
PUBLIC_DIR = REMOTION_DIR / "public"
OUT_DIR = BASE_DIR / "out"
DASHBOARD_DIR = BASE_DIR / "dashboard"

PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Video-Agent API & Canvas Studio",
    version="1.0.0",
    description="Autonomous AI Video Production & Semantic Workflow Canvas"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static asset folders
app.mount("/out", StaticFiles(directory=str(OUT_DIR)), name="out")
app.mount("/public-assets", StaticFiles(directory=str(PUBLIC_DIR)), name="public-assets")

# In-memory session store & cost ledger
PROJECTS_STORE: Dict[str, VideoProjectState] = {}
cost_ledger = CostLedger()


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
def create_project(req: CreateProjectRequest):
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
def approve_project(project_id: str, req: ApproveProjectRequest):
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


@app.get("/api/v1/jobs/{job_id}", status_code=status.HTTP_200_OK)
def get_job_status(job_id: str, provider: str = "mock"):
    """Poll async generation job status (Slice A: mock/hf/kling backed)."""
    from backend.app.providers.mock_provider import MockVideoProvider
    from backend.app.providers.hf_video import HuggingFaceVideoProvider
    providers = {
        "mock": MockVideoProvider(),
        "hf": HuggingFaceVideoProvider(),
    }
    try:
        from backend.app.providers.kling_provider import KlingWanProvider
        providers["kling"] = KlingWanProvider()
    except Exception:
        pass
    prov = providers.get(provider, providers["mock"])
    job_status = prov.check_status(job_id)
    return {"job_id": job_id, "provider": provider, "status": str(job_status.value if hasattr(job_status, "value") else job_status)}


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
def canvas_decompose(req: CanvasDecomposeRequest):
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
async def canvas_generate_audio(req: CanvasGenerateAudioRequest):
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
def canvas_generate_image(req: CanvasGenerateImageRequest):
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


@app.post("/api/v1/canvas/render")
def canvas_render(req: CanvasRenderRequest):
    """Takes complete Canvas manifest and renders MP4 via Remotion CLI."""
    manifest = req.model_dump()

    # Ensure each scene has word-level subtitles for dynamic kinetic typography
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

    manifest_file = REMOTION_DIR / "render_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    composition_name = "Shorts916" if req.aspectRatio == "9:16" else "Landscape169"
    safe_id = re.sub(r'[^a-zA-Z0-9]', '_', req.projectId).lower()
    output_filename = f"{safe_id}_{req.aspectRatio.replace(':', '_')}.mp4"
    output_path = OUT_DIR / output_filename

    cmd = [
        "npx", "remotion", "render",
        "src/index.ts",
        composition_name,
        str(output_path),
        "--props=./render_manifest.json"
    ]

    res = subprocess.run(cmd, cwd=str(REMOTION_DIR), capture_output=True, text=True)
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Remotion Render Failed: {res.stderr}")

    return {
        "status": "COMPLETED",
        "videoUrl": f"/out/{output_filename}",
        "localPath": str(output_path.resolve()),
        "durationSec": req.totalDurationSec,
        "aspectRatio": req.aspectRatio
    }
