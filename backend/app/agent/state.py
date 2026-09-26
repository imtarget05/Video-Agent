"""
Pydantic schemas and typed state definitions for Video-Agent.
"""
from enum import Enum
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import List, Optional, Dict, Any, Union
from typing_extensions import Annotated
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer
import math


#: Money is quantised to 4 decimal places (0.1-cent) -- finer than any provider
#: price this project bills at, coarse enough to be a stable storage precision.
MONEY_SCALE = Decimal("0.0001")


def _coerce_money(v: Any) -> Decimal:
    """Normalise a `Money` input to an exact Decimal.

    The float policy is an EXPLICIT decision, not an accident of pydantic's
    default coercion:

    * `Decimal` is the intended input and is carried through untouched.
    * `int` and `str` are exact decimal literals; they are accepted and
      HALF_UP-quantised to `MONEY_SCALE` (so "0.12345" -> Decimal("0.1235")).
    * `bool` is rejected outright.
    * `float` is accepted ONLY when `Decimal(str(v))` is already exact at
      `MONEY_SCALE`. A float needs rounding => it carries binary
      representation drift, and drift is rejected rather than silently
      absorbed. That is what makes the CPFM ledger's "no float drift" claim
      true end to end instead of only inside the ledger.

    Rejecting drift matters: `0.1 + 0.2` is 0.30000000000000004, and quietly
    rounding that to 0.3000 hides a real arithmetic bug upstream. Callers that
    genuinely need a repeating value must pass a `Decimal` or a string and say
    what precision they mean.
    """
    if isinstance(v, Decimal):
        d = v
    elif isinstance(v, bool):
        raise ValueError(f"invalid Money value: {v!r}")
    elif isinstance(v, int):
        d = Decimal(v)
    elif isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"invalid Money value: {v!r}")
        d = Decimal(str(v))
        if d != d.quantize(MONEY_SCALE, rounding=ROUND_HALF_UP):
            raise ValueError(
                f"Money float {v!r} is not exact at {MONEY_SCALE} precision "
                f"(binary drift); pass a Decimal or a str instead"
            )
    elif isinstance(v, str):
        s = v.strip()
        if not s:
            raise ValueError(f"invalid Money value: {v!r}")
        try:
            d = Decimal(s)
        except InvalidOperation:
            raise ValueError(f"invalid Money value: {v!r}")
        if d.is_nan() or d.is_infinite():
            raise ValueError(f"invalid Money value: {v!r}")
    else:
        raise ValueError(f"invalid Money value: {v!r}")
    if d.is_nan() or d.is_infinite():
        raise ValueError(f"invalid Money value: {v!r}")
    if d < 0:
        raise ValueError(f"Money must be non-negative: {v!r}")
    return d.quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)


Money = Annotated[
    Decimal,
    BeforeValidator(_coerce_money),
    PlainSerializer(lambda v: float(v), return_type=float),
]


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


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    MODERATION_BLOCKED = "MODERATION_BLOCKED"


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
    cost_usd: Money
    attempt_number: int = 1
    status: str = "SUCCESS"  # SUCCESS, FAILED, MODERATION_BLOCKED
    prompt_tokens: int = 0


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
    reformulated: bool = False
    reformulation_count: int = 0
    qc_passed: bool = False
    qc_report: Optional[Dict[str, Any]] = None
