"""
End-to-End Demo Script for Video-Agent.
Demonstrates the full autonomous pipeline: Brief -> Character DNA -> Storyboard -> Preflight -> HITL -> Gen -> Remotion Manifest -> Cost Audit.
"""
import json
import sys
from pathlib import Path

# Add repo root to python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.agent.state import VideoProjectState, AspectRatio, PipelineStatus
from backend.app.agent.graph import video_agent_graph
from backend.app.consistency.character_dna import CharacterDNAManager
from backend.app.cost.ledger import CostLedger


def main():
    print("=" * 70)
    print("🎬 VIDEO-AGENT: AUTONOMOUS VIDEO PRODUCTION PIPELINE")
    print("=" * 70)

    # 1. Setup Character DNA (Visual Anchoring)
    print("\n[Phase 1] Initializing Character DNA & Visual Anchors...")
    character = CharacterDNAManager.create_character(
        character_id="char_linh_ai",
        name="Linh",
        prompt_prefix="Linh, 26yo Vietnamese tech entrepreneur, short bob hair, minimal silver necklace, modern minimalist studio",
        seed=2026
    )
    print(f"  ✓ Character Created: {character.name}")
    print(f"  ✓ Invariant Prompt Prefix: '{character.prompt_prefix}'")
    print(f"  ✓ 3-Angle Anchors: {character.reference_anchors}")

    # 2. Submit Project Brief
    print("\n[Phase 2] Submitting Project Brief to LangGraph Swarm...")
    initial_state = VideoProjectState(
        project_id="demo_shorts_001",
        topic="3 Bước Xây Dựng Hệ Thống Video AI Tự Động Hóa 2026",
        target_duration_sec=30.0,
        aspect_ratio=AspectRatio.PORTRAIT_9_16,
        character_dna=character
    )

    # 3. Execute Phase A: Director -> Scriptwriter -> Storyboarder -> Preflight -> HITL Checkpoint
    print("  ▶ Running Director & Scriptwriter agents...")
    print("  ▶ Anchoring character prompts & planning keyframes...")
    print("  ▶ Running Preflight safety & budget check...")
    res_a = video_agent_graph.invoke(initial_state)
    state_a = VideoProjectState(**res_a) if isinstance(res_a, dict) else res_a

    print(f"\n[Phase 3] Storyboard Planning Complete!")
    print(f"  Status: {state_a.status.value}")
    print(f"  Estimated Spend: ${state_a.estimated_cost_usd} USD")
    print(f"  Planned Scenes ({len(state_a.scenes)}):")
    for s in state_a.scenes:
        print(f"    - Scene #{s.scene_id} [{s.title}] ({s.duration_sec}s)")
        print(f"      Voiceover: '{s.voiceover_text}'")
        print(f"      Anchored Prompt: {s.visual_prompt[:75]}...")
        print(f"      Keyframe: {s.keyframe_image_url}")

    # 4. Human-in-the-Loop Sign-off
    print("\n[Phase 4] Human-in-the-Loop (HITL) Checkpoint:")
    print("  [Simulated Supervisor]: Storyboard and budget verified. Approving production!")
    state_b = state_a.model_copy()
    state_b.hitl_approved = True
    state_b.status = PipelineStatus.APPROVED

    # 5. Execute Phase B: Video Generation -> Remotion Manifest -> QC Audit
    print("\n[Phase 5] Executing Video Generation & Remotion Assembly...")
    res_b = video_agent_graph.invoke(state_b)
    final_state = VideoProjectState(**res_b) if isinstance(res_b, dict) else res_b

    print(f"  Status: {final_state.status.value}")
    print(f"  Actual Spend: ${final_state.actual_cost_usd} USD")
    print(f"  Cost Per Finished Minute (CPFM): ${final_state.cost_per_finished_minute}/min")

    # 6. Save Remotion Render Manifest
    manifest_path = Path("remotion/render_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(final_state.render_manifest, f, indent=2, ensure_ascii=False)
    print(f"\n[Phase 6] Remotion Timeline Manifest Generated:")
    print(f"  ✓ Saved to: {manifest_path}")
    print(f"  ✓ Aspect Ratio: {final_state.render_manifest['aspectRatio']}")
    print(f"  ✓ Total Video Duration: {final_state.render_manifest['totalDurationSec']}s")

    print("\n" + "=" * 70)
    print("🎉 PIPELINE RUN SUCCESSFUL! Ready for Remotion render.")
    print("=" * 70)


if __name__ == "__main__":
    main()
