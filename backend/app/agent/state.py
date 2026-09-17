"""
Pydantic schemas and typed state definitions for Video-Agent.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AspectRatio(str, Enum):
    PORTRAIT_9_16 = "9:16"
    LANDSCAPE_16_9 = "16:9"


class PipelineStatus(str, Enum):
    INITIATED = "INITIATED"
    SCRIPTED = "SCRIPTED"
    STORYBOARDED = "STORYBOARDED"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    HITL_PENDING = "HITL_PENDING"
    APPROVED = "APPROVED"
    GENERATING = "GENERATING"
    GENERATION_FAILED = "GENERATION_FAILED"
    EDITING = "EDITING"
    QC_PENDING = "QC_PENDING"
    COMPLETED = "COMPLETED"
    MODERATION_BLOCKED = "MODERATION_BLOCKED"
    FAILED = "FAILED"


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float


class Scene(BaseModel):
    scene_id: int
    title: str = ""
    visual_prompt: str
    voiceover_text: str
    duration_sec: float = 4.0
    keyframe_image_url: Optional[str] = None
    video_clip_url: Optional[str] = None
    word_timestamps: List[WordTimestamp] = Field(default_factory=list)
    is_b_roll: bool = False


class CharacterDNA(BaseModel):
    character_id: str
    name: str
    prompt_prefix: str
    reference_anchors: List[str] = Field(default_factory=list)
    seed: int = 42


class CostRecord(BaseModel):
    job_id: str
    provider: str
    duration_sec: float
    cost_usd: float
    attempt_number: int = 1
    status: str = "SUCCESS"  # SUCCESS, FAILED, MODERATION_BLOCKED


class VideoProjectState(BaseModel):
    project_id: str
    topic: str
    target_duration_sec: float = 30.0
    aspect_ratio: AspectRatio = AspectRatio.PORTRAIT_9_16
    character_dna: Optional[CharacterDNA] = None
    scenes: List[Scene] = Field(default_factory=list)
    status: PipelineStatus = PipelineStatus.INITIATED
    cost_records: List[CostRecord] = Field(default_factory=list)
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    cost_per_finished_minute: float = 0.0
    error_message: Optional[str] = None
    render_manifest: Optional[Dict[str, Any]] = None
    hitl_approved: bool = False
