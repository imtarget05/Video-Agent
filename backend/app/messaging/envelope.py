"""Event envelope v1 (PLAN_VIDEO_AGENT_EVENTING_V1 §1 + foundation §1).

Pure Python, no third-party dependencies. All Kafka-safety rules are
structural (field presence, sizes, formats) so they hold in tests without
a broker or a schema registry.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

ENVELOPE_VERSION = "1"
MAX_INLINE_PAYLOAD_BYTES = 256 * 1024
VALID_ENVS = {"local", "staging", "prod"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
REQUIRED_FIELDS = (
    "event_id", "event_type", "schema_version", "occurred_at",
    "producer", "app", "env", "correlation_id", "idempotency_key",
    "payload_ref", "payload", "payload_sha256", "schema_ref",
)


import random
import time

class EnvelopeError(ValueError):
    """Raised when an envelope violates the v1 contract."""


def new_event_id() -> str:
    """RFC 9562 compliant UUIDv7 (time-ordered) for the system-wide dedupe key."""
    if hasattr(uuid, "uuid7"):
        return str(uuid.uuid7())
    ms = int(time.time() * 1000)
    rand_a = random.getrandbits(12)
    rand_b = random.getrandbits(62)

    int_val = (ms & 0xFFFFFFFFFFFF) << 80
    int_val |= (0x7 << 76)
    int_val |= (rand_a & 0x0FFF) << 64
    int_val |= (0b10 << 62)
    int_val |= (rand_b & 0x3FFFFFFFFFFFFFFF)

    return str(uuid.UUID(int=int_val))


def canonical_json(value: Any) -> bytes:
    """Deterministic bytes used for payload_sha256."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_envelope(
    *,
    event_type: str,
    producer: str,
    app: str,
    env: str,
    correlation_id: str,
    idempotency_key: str,
    payload: Optional[Dict[str, Any]],
    payload_ref: Optional[Dict[str, Any]],
    schema_ref: str,
    event_id: Optional[str] = None,
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a v1 envelope; exactly one of payload / payload_ref must be set."""
    if (payload is None) == (payload_ref is None):
        raise EnvelopeError("exactly one of payload / payload_ref must be set")
    if payload is not None and len(canonical_json(payload)) > MAX_INLINE_PAYLOAD_BYTES:
        raise EnvelopeError(
            f"inline payload exceeds {MAX_INLINE_PAYLOAD_BYTES} bytes; use payload_ref"
        )
    envelope = {
        "event_id": event_id or new_event_id(),
        "event_type": event_type,
        "schema_version": ENVELOPE_VERSION,
        "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
        "producer": producer,
        "app": app,
        "env": env,
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "payload_ref": payload_ref,
        "payload": payload,
        "payload_sha256": sha256_hex(
            canonical_json(payload) if payload is not None
            else canonical_json(payload_ref)
        ),
        "schema_ref": schema_ref,
    }
    validate_envelope(envelope)
    return envelope


def validate_envelope(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Structural validation of a v1 envelope; returns it unchanged."""
    if not isinstance(envelope, dict):
        raise EnvelopeError("envelope must be an object")
    missing = [f for f in REQUIRED_FIELDS if f not in envelope]
    if missing:
        raise EnvelopeError(f"missing envelope fields: {missing}")
    if envelope["schema_version"] != ENVELOPE_VERSION:
        raise EnvelopeError(
            f"unsupported schema_version: {envelope['schema_version']!r}"
        )
    if not UUID_RE.match(str(envelope["event_id"]).lower()):
        raise EnvelopeError("event_id must be a UUID")
    if not envelope.get("event_type") or "." not in str(envelope["event_type"]):
        raise EnvelopeError("event_type must be a dotted name")
    if not envelope.get("producer"):
        raise EnvelopeError("producer is required")
    if envelope.get("env") not in VALID_ENVS:
        raise EnvelopeError(f"env must be one of {sorted(VALID_ENVS)}")
    if not envelope.get("correlation_id"):
        raise EnvelopeError("correlation_id is required")
    if not envelope.get("idempotency_key"):
        raise EnvelopeError("idempotency_key is required for commands")
    if (envelope.get("payload") is None) == (envelope.get("payload_ref") is None):
        raise EnvelopeError("exactly one of payload / payload_ref must be set")
    if envelope.get("payload") is not None and (
        len(canonical_json(envelope["payload"])) > MAX_INLINE_PAYLOAD_BYTES
    ):
        raise EnvelopeError("inline payload exceeds 256 KiB; use payload_ref")
    if not SHA256_RE.match(str(envelope.get("payload_sha256", ""))):
        raise EnvelopeError("payload_sha256 must be 64 lowercase hex chars")
    if not envelope.get("schema_ref") or ":" not in str(envelope["schema_ref"]):
        raise EnvelopeError("schema_ref must be '<subject>:<version>'")
    try:
        datetime.fromisoformat(str(envelope["occurred_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnvelopeError(f"occurred_at is not RFC3339: {exc}") from exc
    return envelope