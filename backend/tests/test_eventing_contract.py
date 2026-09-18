"""V-2 acceptance: envelope + domain-schema contract (plan §1, §4).

Pure unit tests (no broker, no registry, no DB). Wire into the existing
suite via testpaths=backend/tests.
"""
import json

import pytest

from backend.app.messaging import envelope as env
from backend.app.messaging import render_schemas as rs


def _base(**overrides):
    payload = {"job_id": "job_1", "project_id": "p1"}
    body = {
        "event_id": "0193f7a2-4b5c-7d8e-9f01-23456789abcd",
        "event_type": "video.render.requested",
        "schema_version": "1",
        "occurred_at": "2026-09-18T10:00:00+00:00",
        "producer": "video/api",
        "app": "video",
        "env": "staging",
        "correlation_id": "tr-1",
        "idempotency_key": "render:job_1",
        "payload_ref": None,
        "payload": payload,
        "payload_sha256": env.sha256_hex(env.canonical_json(payload)),
        "schema_ref": "video.render.commands.v1-value:1",
    }
    body.update(overrides)
    return body


def test_envelope_requires_all_13_fields():
    body = _base()
    body.pop("correlation_id")
    with pytest.raises(env.EnvelopeError):
        env.validate_envelope(body)


def test_envelope_rejects_placeholder_checksum():
    with pytest.raises(env.EnvelopeError):
        env.validate_envelope(_base(payload_sha256="e3b0…"))


def test_envelope_rejects_oversize_inline_payload(monkeypatch):
    monkeypatch.setattr(env, "MAX_INLINE_PAYLOAD_BYTES", 16)
    with pytest.raises(env.EnvelopeError):
        env.build_envelope(
            event_type="video.render.requested",
            producer="video/api",
            app="video",
            env="staging",
            correlation_id="tr-1",
            idempotency_key="render:job_1",
            payload={"job_id": "job_1", "blob": "x" * 64},
            payload_ref=None,
            schema_ref="video.render.commands.v1-value:1",
        )


def test_envelope_allows_r2_ref_for_large_manifest():
    body = env.build_envelope(
        event_type="video.render.requested",
        producer="video/api",
        app="video",
        env="staging",
        correlation_id="tr-1",
        idempotency_key="render:job_1",
        payload=None,
        payload_ref={"store": "r2", "uri": "manifests/j1.json",
                     "sha256": "a" * 64, "bytes": 999999},
        schema_ref="video.render.commands.v1-value:1",
    )
    assert body["payload"] is None
    assert body["payload_ref"]["store"] == "r2"


def test_spec_example_hash_is_a_valid_64_hex_checksum():
    # sha256('{"aspect_ratio":"9:16","project_id":"proj_abc"}'), canonical form.
    assert (
        "9ece93489b6495a00dc8081e053720b2bb25816d78d36a960e3ca991ef166efb"
        == env.sha256_hex(b'{"aspect_ratio":"9:16","project_id":"proj_abc"}')
    )


def test_render_requested_requires_manifest_ref_not_inline_manifest():
    with pytest.raises(rs.SchemaError):
        rs.validate_render_payload(
            "video.render.requested",
            {"job_id": "j", "project_id": "p", "aspect_ratio": "9:16",
             "total_duration_sec": 4.0,
             "manifest_ref": {"store": "local", "uri": "x"}},
        )


def test_render_failed_bounds_error_evidence():
    payload = {"job_id": "j", "error_code": "REMOTION_FAILED",
               "error_sha256": "b" * 64}
    assert rs.validate_render_payload("video.render.failed", payload) == payload
    with pytest.raises(rs.SchemaError):
        rs.validate_render_payload(
            "video.render.failed",
            {"job_id": "j", "error_code": "X", "error_sha256": "short",
             "stderr": "raw-should-never-be-here"},
        )


def test_message_validation_binds_envelope_to_subject():
    payload = {"job_id": "j", "external_ops_key": "op:1", "provider": "remotion"}
    body = _base(
        event_type="video.render.accepted",
        payload=payload,
        payload_sha256=env.sha256_hex(env.canonical_json(payload)),
        schema_ref="video.render.events.v1-value:1",
    )
    assert rs.validate_message("video.render.accepted", body) == body
    with pytest.raises(rs.SchemaError):
        rs.validate_message(
            "video.render.accepted",
            dict(body, schema_ref="video.render.commands.v1-value:1"),
        )


def test_unknown_event_types_rejected():
    with pytest.raises(rs.SchemaError):
        rs.schema_ref_for("video.unknown.thing")
    with pytest.raises(rs.SchemaError):
        rs.validate_render_payload("video.unknown.thing", {})


def test_all_five_subjects_registered():
    assert rs.list_event_types() == [
        "video.render.accepted",
        "video.render.failed",
        "video.render.requested",
        "video.render.started",
        "video.render.succeeded",
    ]
    assert json.dumps(rs.SUBJECTS, sort_keys=True)  # serializable for CI evidence
