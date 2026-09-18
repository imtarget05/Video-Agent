"""WP2 (Video) — State trimming tests.

RED until backend.app.agent.context_trim implements:
  trim_scenes (keep last 5, truncate long fields)
  trim_cost_records (keep last 20, drop raw payload)
  build_trimmed_context (token budget 2000)
  + nodes._llm_context wiring (prompt uses trimmed copy, original state intact)
"""
import pytest

from backend.app.agent.context_trim import (  # noqa: F401
    build_trimmed_context,
    estimate_tokens,
    trim_cost_records,
    trim_scenes,
    truncate,
)


def _scenes(n: int, pad: int = 900) -> list[dict]:
    return [
        {
            "scene_id": i,
            "title": f"s{i}",
            "script": "x" * pad,
            "narration": "y" * pad,
            "prompt": "p" * pad,
            "description": "d" * pad,
            "visual_prompt": "v" * pad,
            "voiceover_text": "w" * pad,
        }
        for i in range(n)
    ]


def test_trim_scenes_keeps_last_5():
    out = trim_scenes(_scenes(10))
    assert len(out) == 5
    assert [s["scene_id"] for s in out] == [5, 6, 7, 8, 9]
    for s in out:
        for key in ("script", "narration", "prompt", "description", "visual_prompt", "voiceover_text"):
            assert len(s[key]) <= 500 + len("...[truncated]")


def test_trim_cost_records_keeps_20_drops_raw():
    records = [
        {"job_id": f"j{i}", "cost_usd": 0.1, "detail": "z" * 800, "notes": "n" * 800, "raw_response": "RAW" * 400}
        for i in range(30)
    ]
    out = trim_cost_records(records)
    assert len(out) == 20
    assert [r["job_id"] for r in out] == [f"j{i}" for i in range(10, 30)]
    assert all("raw_response" not in r for r in out)
    for r in out:
        assert len(r["detail"]) <= 300 + len("...[truncated]")


def test_build_trimmed_context_respects_budget():
    big_scenes = _scenes(10, pad=5000)
    big_records = [
        {"job_id": f"j{i}", "detail": "z" * 5000} for i in range(25)
    ]
    ctx = build_trimmed_context(big_scenes, big_records)
    assert estimate_tokens(str(ctx)) <= 2000
    # state gốc không bị đụng vào
    assert len(big_scenes) == 10 and len(big_records) == 25
    assert len(big_scenes[0]["script"]) == 5000


def test_nodes_uses_trimmed_context(monkeypatch):
    """V-T3: scriptwriter prompt dùng bản trimmed; state gốc intact."""
    from backend.app.agent import nodes as nodes_mod
    from backend.app.agent.state import CostRecord, Scene, VideoProjectState

    scenes = [
        Scene(scene_id=i, title=f"s{i}", visual_prompt="v" * 1500, voiceover_text="w" * 1500)
        for i in range(10)
    ]
    records = [
        CostRecord(job_id=f"j{i}", provider="MockVideo", duration_sec=5.0, cost_usd=0.10)
        for i in range(25)
    ]
    state = VideoProjectState(project_id="p_trim", topic="trim topic", scenes=scenes, cost_records=records)

    captured: dict = {}

    class CaptureWriter:
        def generate_script(self, topic: str):
            captured["topic"] = topic
            return [
                {"scene_id": 1, "title": "Hook", "visual_prompt": "vp", "voiceover": "vo", "duration_sec": 5.0}
            ]

    monkeypatch.setattr(nodes_mod, "get_scriptwriter", lambda: CaptureWriter())
    nodes_mod.scriptwriter_node(state)

    topic = captured["topic"]
    assert "trim topic" in topic
    # trimmed: chỉ ≤5 scenes gần nhất, không raw payload
    assert '"scene_id": 9' in topic or '"scene_id":9' in topic
    for old in range(0, 5):
        assert f'"scene_id": {old},' not in topic
    # state gốc intact
    assert len(state.scenes) == 10
    assert len(state.scenes[0].visual_prompt) == 1500
    assert len(state.cost_records) == 25
