"""Render domain event schemas (plan §1 + §4, foundation §1/§3.4).

Hand-rolled structural schemas with zero third-party dependencies: each
schema lists required fields per envelope section so unit tests can assert
contract conformance without a Schema Registry or broker.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Subject naming: <full-topic>-value, compatibility BACKWARD (spec §3.4).
SUBJECTS = {
    "video.render.requested": "video.render.commands.v1-value",
    "video.render.accepted": "video.render.events.v1-value",
    "video.render.started": "video.render.events.v1-value",
    "video.render.succeeded": "video.render.events.v1-value",
    "video.render.failed": "video.render.events.v1-value",
}

SCHEMA_VERSIONS = {name: 1 for name in SUBJECTS}


class SchemaError(ValueError):
    """Raised when a payload violates its domain schema."""


def _require(payload: Dict[str, Any], fields: List[str], event_type: str) -> None:
    missing = [f for f in fields if f not in payload]
    if missing:
        raise SchemaError(f"{event_type}: missing payload fields {missing}")
    unknown = [k for k in payload if k not in _PAYLOAD_FIELDS[event_type]]
    if unknown:
        raise SchemaError(f"{event_type}: unknown payload fields {unknown}")


_PAYLOAD_FIELDS = {
    "video.render.requested": [
        "job_id", "project_id", "aspect_ratio",
        "total_duration_sec", "manifest_ref",
    ],
    "video.render.accepted": ["job_id", "external_ops_key", "provider"],
    "video.render.started": ["job_id", "remote_operation_id"],
    "video.render.succeeded": ["job_id", "artifact_key", "artifact_sha256", "duration_sec"],
    "video.render.failed": ["job_id", "error_code", "error_sha256"],
}


def schema_ref_for(event_type: str) -> str:
    """Canonical '<subject>:<version>' reference for an event type."""
    if event_type not in SUBJECTS:
        raise SchemaError(f"unknown event_type: {event_type}")
    return f"{SUBJECTS[event_type]}:{SCHEMA_VERSIONS[event_type]}"


def validate_render_payload(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a render-domain payload; returns it unchanged."""
    if event_type not in _PAYLOAD_FIELDS:
        raise SchemaError(f"unknown event_type: {event_type}")
    if not isinstance(payload, dict):
        raise SchemaError(f"{event_type}: payload must be an object")
    _require(payload, _PAYLOAD_FIELDS[event_type], event_type)
    job_id = payload.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise SchemaError(f"{event_type}: job_id must be a non-empty string")
    if event_type == "video.render.requested":
        ref = payload.get("manifest_ref")
        if not isinstance(ref, dict) or ref.get("store") != "r2":
            raise SchemaError(
                "video.render.requested: manifest MUST travel as "
                "manifest_ref {store:'r2', uri, sha256, bytes}"
            )
        for key in ("uri", "sha256", "bytes"):
            if key not in ref:
                raise SchemaError(f"video.render.requested: manifest_ref missing {key}")
    if event_type == "video.render.succeeded":
        for key in ("artifact_sha256",):
            value = str(payload.get(key, ""))
            if len(value) != 64 or any(
                c not in "0123456789abcdef" for c in value.lower()
            ):
                raise SchemaError(f"video.render.succeeded: {key} must be 64 hex chars")
    return payload


def validate_message(event_type: str, envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Validate envelope + domain payload together (consumer entry point)."""
    from backend.app.messaging.envelope import validate_envelope

    validate_envelope(envelope)
    if envelope.get("event_type") != event_type:
        raise SchemaError(
            f"envelope event_type {envelope.get('event_type')!r} "
            f"does not match expected {event_type!r}"
        )
    expected_ref = schema_ref_for(event_type)
    if envelope.get("schema_ref") != expected_ref:
        raise SchemaError(
            f"schema_ref {envelope.get('schema_ref')!r} "
            f"does not match registered {expected_ref!r}"
        )
    if envelope.get("payload") is None and event_type == "video.render.requested":
        raise SchemaError("video.render.requested: payload must be inline-capable")
    validate_render_payload(event_type, envelope.get("payload") or {})
    return envelope


def list_event_types() -> List[str]:
    return sorted(SUBJECTS)
