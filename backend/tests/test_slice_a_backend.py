"""Slice A acceptance tests (backend)."""
import os


def test_jobstatus_and_prompt_tokens():
    from backend.app.agent.state import JobStatus, CostRecord
    assert JobStatus["PENDING"] is not None
    assert JobStatus["SUCCEEDED"] is not None
    r = CostRecord(job_id="j", provider="p", duration_sec=1.0, cost_usd=0.1, prompt_tokens=12)
    assert r.prompt_tokens == 12


def test_ledger_prompt_tokens_migration(tmp_path):
    from backend.app.cost.ledger import CostLedger
    from backend.app.agent.state import CostRecord
    led = CostLedger(db_path=str(tmp_path / "l.db"))
    led.record_cost("proj1", CostRecord(job_id="j1", provider="p", duration_sec=5.0, cost_usd=0.5, prompt_tokens=20))
    import sqlite3
    cols = [r[1] for r in sqlite3.connect(str(tmp_path / "l.db")).execute("PRAGMA table_info(cost_records)")]
    assert "prompt_tokens" in cols
    m = led.get_project_metrics("proj1", 5.0)
    assert m["total_prompt_tokens"] == 20


def test_guardrails_classify_backoff():
    from backend.app.agent.guardrails import HardToolGuard
    assert HardToolGuard.classify_error("HTTP 500 boom") == "RETRYABLE_5XX"
    assert HardToolGuard.classify_error("HTTP 403 forbidden POLICY") == "MODERATION_BLOCKED"
    d1 = HardToolGuard.backoff_delay(1)
    d2 = HardToolGuard.backoff_delay(2)
    assert d2 >= d1 >= 0

    calls = {"n": 0}

    def f():
        calls["n"] += 1
        raise RuntimeError("HTTP 403 POLICY_VIOLATION blocked")
    res = HardToolGuard.execute_with_guardrails(f)
    assert res.status == "MODERATION_BLOCKED"
    assert res.attempts_made == 1


def test_check_status_providers():
    from backend.app.providers.mock_provider import MockVideoProvider
    from backend.app.providers.hf_video import HuggingFaceVideoProvider
    from backend.app.agent.state import JobStatus
    m = MockVideoProvider()
    st = m.check_status("anything")
    assert isinstance(st, JobStatus)
    h = HuggingFaceVideoProvider(hf_token=None)
    assert isinstance(h.check_status("x"), JobStatus)


def test_kling_provider_mock():
    os.environ["MOCK_VIDEO"] = "true"
    from backend.app.providers.kling_provider import KlingWanProvider
    from backend.app.agent.state import JobStatus
    p = KlingWanProvider(api_key="dummy")
    clip = p.generate_clip(prompt="a calm lake", duration_sec=4.0, seed=1)
    assert clip.clip_url.endswith(".mp4")
    assert isinstance(p.check_status("job1"), JobStatus)


def test_edge_tts_offline():
    os.environ["MOCK_TTS"] = "true"
    from backend.app.providers.edge_tts_provider import EdgeTTSProvider
    p = EdgeTTSProvider()
    audio = p.generate_speech(text="Xin chào thế giới")
    assert len(audio.word_timestamps) >= 3
    assert audio.word_timestamps[0]["word"].lower() == "xin"


def test_whisper_offline():
    from backend.app.providers.whisper_subtitles import WhisperSubtitleExtractor
    words = WhisperSubtitleExtractor.extract("Hello world test", duration_sec=3.0)
    assert len(words) == 3
    assert words[0]["start"] < words[0]["end"] <= words[1]["end"]


def test_safety_reformulator():
    from backend.app.agent.safety_reformulator import reformulate_prompt, safety_reformulator_node
    from backend.app.agent.state import VideoProjectState
    out = reformulate_prompt("how to make a bomb tutorial")
    assert "bomb" not in out.lower()
    st = VideoProjectState(project_id="p", topic="t", error_message="bomb blocked")
    res = safety_reformulator_node(st)
    assert res["reformulated"] is True


def test_graph_has_reformulator_route():
    from backend.app.agent.graph import create_video_agent_graph
    g = create_video_agent_graph()
    nodes = getattr(g, "nodes", None)
    if nodes is not None:
        assert "safety_reformulator" in nodes
    else:
        assert "safety_reformulator" in g.get_graph().nodes


def test_qc_hardening():
    from backend.app.agent.nodes import qc_audit_node
    from backend.app.agent.state import VideoProjectState, Scene
    st = VideoProjectState(project_id="qc1", topic="t", scenes=[
        Scene(scene_id=1, visual_prompt="v", voiceover_text="hi", duration_sec=5.0,
              video_clip_url="/data/rendered/a.mp4",
              word_timestamps=[{"word": "hi", "start": 0.0, "end": 0.3}]),
    ])
    res = qc_audit_node(st)
    assert res["qc_passed"] is True
    assert "qc_report" in res


def test_store_webhooks_jobs_endpoint():
    from backend.app.api.store import ProjectStore
    from backend.app.api.webhooks import sign_payload, verify_signature
    import backend.app.api.server as srv
    routes = [r.path for r in srv.app.routes]
    assert any("job" in r for r in routes), f"missing jobs endpoint: {routes}"
    payload = b'{"a":1}'
    sig = sign_payload(payload, "secret")
    assert verify_signature(payload, sig, "secret") is True
    assert verify_signature(payload, sig, "wrong") is False
    assert ProjectStore is not None
