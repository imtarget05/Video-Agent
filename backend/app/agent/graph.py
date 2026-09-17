"""
LangGraph StateGraph orchestration for Video-Agent.
Orchestrates the entire lifecycle: Brief -> Storyboard -> Preflight -> HITL -> Gen -> Remotion Assembly -> QC.
"""
from langgraph.graph import StateGraph, START, END
from backend.app.agent.state import VideoProjectState, PipelineStatus
from backend.app.agent.nodes import (
    director_node,
    scriptwriter_node,
    storyboarder_node,
    preflight_node,
    hitl_checkpoint_node,
    video_generation_node,
    editorial_remotion_manifest_node,
    qc_audit_node,
)
from backend.app.agent.safety_reformulator import safety_reformulator_node


def create_video_agent_graph():
    """Builds and compiles the Video-Agent LangGraph StateGraph."""
    workflow = StateGraph(VideoProjectState)

    # 1. Add all functional nodes
    workflow.add_node("director", director_node)
    workflow.add_node("scriptwriter", scriptwriter_node)
    workflow.add_node("storyboarder", storyboarder_node)
    workflow.add_node("preflight", preflight_node)
    workflow.add_node("hitl_checkpoint", hitl_checkpoint_node)
    workflow.add_node("video_generation", video_generation_node)
    workflow.add_node("editorial_assembly", editorial_remotion_manifest_node)
    workflow.add_node("qc_audit", qc_audit_node)
    workflow.add_node("safety_reformulator", safety_reformulator_node)

    # 2. Linear early-phase edges
    workflow.add_edge(START, "director")
    workflow.add_edge("director", "scriptwriter")
    workflow.add_edge("scriptwriter", "storyboarder")
    workflow.add_edge("storyboarder", "preflight")

    # 3. Conditional routing from Preflight (single-pass reformulator, then END)
    def route_after_preflight(state: VideoProjectState) -> str:
        if state.status == PipelineStatus.MODERATION_BLOCKED and not state.reformulated:
            return "safety_reformulator"
        if state.status in [PipelineStatus.PREFLIGHT_FAILED, PipelineStatus.MODERATION_BLOCKED]:
            return END
        return "hitl_checkpoint"

    workflow.add_conditional_edges(
        "preflight",
        route_after_preflight,
        {"hitl_checkpoint": "hitl_checkpoint", "safety_reformulator": "safety_reformulator", END: END}
    )
    workflow.add_edge("safety_reformulator", END)

    # 4. Conditional routing from HITL Gate
    def route_after_hitl(state: VideoProjectState) -> str:
        if state.status == PipelineStatus.HITL_PENDING:
            return END
        return "video_generation"

    workflow.add_conditional_edges(
        "hitl_checkpoint",
        route_after_hitl,
        {"video_generation": "video_generation", END: END}
    )

    # 5. Conditional routing from Video Generation (single-pass reformulator, then END)
    def route_after_generation(state: VideoProjectState) -> str:
        if state.status == PipelineStatus.MODERATION_BLOCKED and not state.reformulated:
            return "safety_reformulator"
        if state.status in [PipelineStatus.GENERATION_FAILED, PipelineStatus.MODERATION_BLOCKED]:
            return END
        return "editorial_assembly"

    workflow.add_conditional_edges(
        "video_generation",
        route_after_generation,
        {"editorial_assembly": "editorial_assembly", "safety_reformulator": "safety_reformulator", END: END}
    )

    # 6. Assembly -> QC -> End
    workflow.add_edge("editorial_assembly", "qc_audit")
    workflow.add_edge("qc_audit", END)

    return workflow.compile()


# Canonical compiled graph
video_agent_graph = create_video_agent_graph()
