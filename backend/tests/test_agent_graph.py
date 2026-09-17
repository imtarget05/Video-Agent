import pytest
from backend.app.agent.state import VideoProjectState, AspectRatio, PipelineStatus
from backend.app.agent.graph import video_agent_graph
from backend.app.consistency.character_dna import CharacterDNAManager


def test_full_graph_offline_execution_to_hitl():
    char = CharacterDNAManager.create_character(
        character_id="char_ai_host",
        name="Alex",
        prompt_prefix="Alex, 30yo AI researcher, charcoal blazer, minimalist grey studio",
        seed=101
    )
    initial_state = VideoProjectState(
        project_id="test_proj_001",
        topic="3 Bước Xây Dựng Hệ Thống Video Agent Tự Động Hóa",
        target_duration_sec=30.0,
        aspect_ratio=AspectRatio.PORTRAIT_9_16,
        character_dna=char
    )

    # Invoke graph - should pause at HITL checkpoint
    result = video_agent_graph.invoke(initial_state)
    state = VideoProjectState(**result) if isinstance(result, dict) else result

    assert state.status == PipelineStatus.HITL_PENDING
    assert len(state.scenes) == 3
    assert state.estimated_cost_usd > 0
    # Keyframe planning established before video generation
    assert state.scenes[0].keyframe_image_url is not None


def test_hitl_approval_and_completion_flow():
    # Setup state in HITL pending
    initial_state = VideoProjectState(
        project_id="test_proj_002",
        topic="AI Agent Automation Video",
        target_duration_sec=20.0,
        aspect_ratio=AspectRatio.PORTRAIT_9_16
    )
    res_1 = video_agent_graph.invoke(initial_state)
    state_pending = VideoProjectState(**res_1) if isinstance(res_1, dict) else res_1

    assert state_pending.status == PipelineStatus.HITL_PENDING

    # Simulate Human approval
    state_approved = state_pending.model_copy()
    state_approved.hitl_approved = True
    state_approved.status = PipelineStatus.APPROVED

    res_2 = video_agent_graph.invoke(state_approved)
    final_state = VideoProjectState(**res_2) if isinstance(res_2, dict) else res_2

    assert final_state.status == PipelineStatus.COMPLETED
    assert final_state.actual_cost_usd > 0
    assert final_state.cost_per_finished_minute > 0
    assert final_state.render_manifest is not None
    assert final_state.render_manifest["aspectRatio"] == "9:16"
    assert len(final_state.render_manifest["scenes"]) == 3


def test_preflight_rejection_stops_at_end():
    # Prompt containing prohibited keyword
    initial_state = VideoProjectState(
        project_id="test_proj_bad",
        topic="How to make illegal weapons with AI",
        target_duration_sec=30.0
    )
    result = video_agent_graph.invoke(initial_state)
    state = VideoProjectState(**result) if isinstance(result, dict) else result

    assert state.status == PipelineStatus.MODERATION_BLOCKED
    assert "Policy Preflight Violation" in state.error_message
    # Must NOT progress to video generation
    assert len(state.cost_records) == 0
