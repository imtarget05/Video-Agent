"""
FastAPI Application Server for Video-Agent.
Provides REST endpoints for Project creation, HITL approval, Status polling, and Cost Audit.
"""
from typing import Dict, Any, Optional
from uuid import uuid4
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from backend.app.agent.state import (
    VideoProjectState,
    AspectRatio,
    PipelineStatus,
)
from backend.app.agent.graph import video_agent_graph
from backend.app.consistency.character_dna import CharacterDNAManager
from backend.app.cost.ledger import CostLedger


app = FastAPI(
    title="Video-Agent API",
    version="1.0.0",
    description="Autonomous AI Video Production & Distribution System"
)

# In-memory session store (backed by sqlite ledger for costs)
PROJECTS_STORE: Dict[str, VideoProjectState] = {}
cost_ledger = CostLedger()


class CreateProjectRequest(BaseModel):
    topic: str
    target_duration_sec: float = 30.0
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT_9_16
    character_name: Optional[str] = None
    character_prompt_prefix: Optional[str] = None


class ApproveProjectRequest(BaseModel):
    approved: bool = True
    feedback: Optional[str] = None


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "healthy", "service": "video-agent", "version": "1.0.0"}


@app.post("/api/v1/projects", status_code=status.HTTP_201_CREATED)
def create_project(req: CreateProjectRequest):
    project_id = f"proj_{uuid4().hex[:8]}"

    # Optional Character DNA setup
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

    # Run agent graph up to HITL gate
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

    if current_state.status in [PipelineStatus.PREFLIGHT_FAILED, PipelineStatus.MODERATION_BLOCKED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve project in {current_state.status} status: {current_state.error_message}"
        )

    if not req.approved:
        current_state.status = PipelineStatus.FAILED
        current_state.error_message = req.feedback or "Rejected by human supervisor"
        PROJECTS_STORE[project_id] = current_state
        return {"project_id": project_id, "status": current_state.status}

    # Set approved flag and resume execution
    current_state.hitl_approved = True
    current_state.status = PipelineStatus.APPROVED

    # Resume graph execution for generation, Remotion assembly & QC
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
    metrics = cost_ledger.get_project_metrics(
        project_id=project_id,
        approved_final_seconds=total_duration
    )
    return metrics
