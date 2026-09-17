from backend.app.providers.hf_llm import HuggingFaceScriptwriter
"""
LangGraph execution nodes for Video-Agent.
Encapsulates Director, Scriptwriter, Storyboarder, Preflight, Generation, Editorial Remotion, and QC.
"""
from typing import Dict, Any, List
from backend.app.agent.state import (
    VideoProjectState,
    PipelineStatus,
    Scene,
    CostRecord,
    WordTimestamp,
)
from backend.app.agent.guardrails import PreflightGuard, HardToolGuard
from backend.app.consistency.character_dna import CharacterDNAManager
from backend.app.providers.base import BaseVideoProvider, BaseTTSProvider
from backend.app.providers.mock_provider import MockVideoProvider, MockTTSProvider
from backend.app.cost.ledger import CostLedger


def director_node(state: VideoProjectState) -> Dict[str, Any]:
    """Director Agent: Validates incoming brief and initiates project arc."""
    target_duration = state.target_duration_sec or 30.0
    return {
        "status": PipelineStatus.INITIATED,
        "target_duration_sec": target_duration,
        "error_message": None
    }


def scriptwriter_node(state: VideoProjectState) -> Dict[str, Any]:
    """Scriptwriter Agent: Uses Hugging Face Qwen-72B to autonomously generate scenes."""
    topic = state.topic
    writer = HuggingFaceScriptwriter()
    raw_scenes = writer.generate_script(topic)
    scenes = []
    for s in raw_scenes:
        scenes.append(Scene(
            scene_id=s["scene_id"],
            title=s.get("title", f"Scene {s['scene_id']}"),
            visual_prompt=s.get("visual_prompt", f"Cinematic 8k view of {topic}"),
            voiceover_text=s.get("voiceover", ""),
            duration_sec=float(s.get("duration_sec", 5.0))
        ))
    return {
        "scenes": scenes,
        "status": PipelineStatus.SCRIPTED
    }


def storyboarder_node(state: VideoProjectState) -> Dict[str, Any]:
    """Storyboarder Agent: Embeds Character DNA and plans keyframe visuals before generation."""
    character = state.character_dna
    updated_scenes = []
    for scene in state.scenes:
        anchored_prompt = CharacterDNAManager.compose_consistent_prompt(
            character=character,
            scene_action_prompt=scene.visual_prompt
        )
        updated_scene = scene.model_copy()
        updated_scene.visual_prompt = anchored_prompt
        updated_scene.keyframe_image_url = f"/data/keyframes/kf_scene_{scene.scene_id}.png"
        updated_scenes.append(updated_scene)

    return {
        "scenes": updated_scenes,
        "status": PipelineStatus.STORYBOARDED
    }


def preflight_node(state: VideoProjectState) -> Dict[str, Any]:
    """Preflight Guardrail: Enforces keyword policy and budget ceilings."""
    result = PreflightGuard.validate_brief(
        topic=state.topic,
        target_duration_sec=state.target_duration_sec
    )
    if not result.passed:
        is_policy = "Policy" in result.reason
        return {
            "status": PipelineStatus.MODERATION_BLOCKED if is_policy else PipelineStatus.PREFLIGHT_FAILED,
            "error_message": result.reason,
            "estimated_cost_usd": result.estimated_cost_usd
        }

    # Verify each scene prompt
    for s in state.scenes:
        passed, reason = PreflightGuard.validate_scene_prompt(s.visual_prompt)
        if not passed:
            return {
                "status": PipelineStatus.MODERATION_BLOCKED,
                "error_message": reason,
                "estimated_cost_usd": result.estimated_cost_usd
            }

    return {
        "status": PipelineStatus.PREFLIGHT_PASSED,
        "estimated_cost_usd": result.estimated_cost_usd
    }


def hitl_checkpoint_node(state: VideoProjectState) -> Dict[str, Any]:
    """HITL Gate: Human supervisor sign-off on storyboard & estimated spend."""
    if not state.hitl_approved:
        return {"status": PipelineStatus.HITL_PENDING}
    return {"status": PipelineStatus.APPROVED}


def video_generation_node(
    state: VideoProjectState,
    video_provider: BaseVideoProvider = None,
    tts_provider: BaseTTSProvider = None,
    cost_ledger: CostLedger = None
) -> Dict[str, Any]:
    """Video Generation Layer: Executes generation with hard tool guardrails."""
    if video_provider is None:
        video_provider = MockVideoProvider()
    if tts_provider is None:
        tts_provider = MockTTSProvider()
    if cost_ledger is None:
        cost_ledger = CostLedger()

    cost_records = list(state.cost_records)
    total_cost = state.actual_cost_usd
    updated_scenes = []

    for scene in state.scenes:
        # 1. Generate Voiceover TTS
        audio_res = tts_provider.generate_speech(text=scene.voiceover_text)
        word_ts = [WordTimestamp(**w) for w in audio_res.word_timestamps]

        # 2. Call Video Tool via HardToolGuard
        guard_res = HardToolGuard.execute_with_guardrails(
            video_provider.generate_clip,
            prompt=scene.visual_prompt,
            duration_sec=scene.duration_sec,
            reference_images=state.character_dna.reference_anchors if state.character_dna else None,
            seed=state.character_dna.seed if state.character_dna else 42
        )

        if not guard_res.success:
            return {
                "status": PipelineStatus.MODERATION_BLOCKED if guard_res.status == "MODERATION_BLOCKED" else PipelineStatus.GENERATION_FAILED,
                "error_message": guard_res.error
            }

        clip_data = guard_res.data
        prompt_tokens = len((scene.visual_prompt or "").split())
        rec = CostRecord(
            job_id=f"job_{state.project_id}_s{scene.scene_id}",
            provider=clip_data.provider_name,
            duration_sec=clip_data.duration_sec,
            cost_usd=clip_data.cost_usd,
            attempt_number=guard_res.attempts_made,
            status=guard_res.status,
            prompt_tokens=prompt_tokens
        )
        cost_records.append(rec)
        cost_ledger.record_cost(state.project_id, rec)
        total_cost += clip_data.cost_usd

        scene_copy = scene.model_copy()
        scene_copy.video_clip_url = clip_data.clip_url
        scene_copy.word_timestamps = word_ts
        updated_scenes.append(scene_copy)

    return {
        "scenes": updated_scenes,
        "cost_records": cost_records,
        "actual_cost_usd": round(total_cost, 3),
        "status": PipelineStatus.GENERATING
    }


def editorial_remotion_manifest_node(state: VideoProjectState) -> Dict[str, Any]:
    """Remotion Assembly Agent: Builds render manifest for Remotion timeline."""
    manifest_scenes = []
    total_duration = 0.0

    for s in state.scenes:
        manifest_scenes.append({
            "sceneId": s.scene_id,
            "title": s.title,
            "videoUrl": s.video_clip_url,
            "durationSec": s.duration_sec,
            "voiceover": s.voiceover_text,
            "subtitles": [w.model_dump() for w in s.word_timestamps],
            "audioDucking": {
                "musicVolumeNormal": 0.35,
                "musicVolumeDucked": 0.10,
                "duckDurationSec": s.duration_sec
            }
        })
        total_duration += s.duration_sec

    manifest = {
        "projectId": state.project_id,
        "aspectRatio": state.aspect_ratio.value,
        "totalDurationSec": total_duration,
        "scenes": manifest_scenes,
        "transitionType": "fade"
    }

    return {
        "render_manifest": manifest,
        "status": PipelineStatus.EDITING
    }


def qc_audit_node(
    state: VideoProjectState,
    cost_ledger: CostLedger = None
) -> Dict[str, Any]:
    """QC & Cost Audit: Verifies output integrity and computes CPFM."""
    if cost_ledger is None:
        cost_ledger = CostLedger()

    total_duration = sum(s.duration_sec for s in state.scenes)
    metrics = cost_ledger.get_project_metrics(
        project_id=state.project_id,
        approved_final_seconds=total_duration
    )

    checks = []
    # 1. Every scene must have a rendered clip.
    missing_clip = [s.scene_id for s in state.scenes if not s.video_clip_url]
    checks.append({"name": "clips_present", "passed": not missing_clip, "detail": f"missing={missing_clip}"})
    # 2. Subtitle coverage: each scene with voiceover should carry word timestamps.
    bad_subs = [s.scene_id for s in state.scenes if s.voiceover_text and not s.word_timestamps]
    checks.append({"name": "subtitle_coverage", "passed": not bad_subs, "detail": f"missing_subs={bad_subs}"})
    # 3. Word timestamp monotonicity (desync guard).
    desync = []
    for s in state.scenes:
        ts = s.word_timestamps or []
        for a, b in zip(ts, ts[1:]):
            if not (a.start <= a.end <= b.end and a.start <= b.start):
                desync.append(s.scene_id)
                break
    checks.append({"name": "av_sync_monotonic", "passed": not desync, "detail": f"desync={desync}"})
    # 4. Duration sanity (no black-frame zero scenes).
    bad_dur = [s.scene_id for s in state.scenes if s.duration_sec <= 0]
    checks.append({"name": "duration_sanity", "passed": not bad_dur, "detail": f"bad_duration={bad_dur}"})

    qc_passed = all(c["passed"] for c in checks)
    qc_report = {
        "project_id": state.project_id,
        "total_duration_sec": round(total_duration, 2),
        "checks": checks,
        "metrics": {
            "cost_per_finished_minute": metrics["cost_per_finished_minute"],
            "total_spend_usd": metrics["total_spend_usd"],
        },
    }
    return {
        "cost_per_finished_minute": metrics["cost_per_finished_minute"],
        "qc_passed": qc_passed,
        "qc_report": qc_report,
        "status": PipelineStatus.COMPLETED if qc_passed else PipelineStatus.FAILED,
    }
