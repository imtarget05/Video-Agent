"""
Delivery dispatcher (Slice C + plan Task 4): HMAC-signed webhook fan-out,
max 2 retries, per-target secrets, SSRF-safe destinations, and durable
idempotent delivery receipts.
"""
import hashlib
import os
import time
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.app.api.webhooks import (
    WebhookSecurityError,
    resolve_target_secret,
    sign_payload,
    validate_webhook_url,
    verify_signature,
    dispatch_webhook,
)

__all__ = [
    "DeliveryTarget",
    "Receipt",
    "sign_payload",
    "verify_signature",
    "resolve_target_secret",
    "validate_webhook_url",
    "WebhookSecurityError",
    "deliver",
    "deliver_all",
    "deliver_idempotent",
    "MAX_RETRIES",
]

MAX_RETRIES = 2  # retries after the initial attempt (<=3 attempts total)


class DeliveryTarget(BaseModel):
    url: str
    secret: Optional[str] = None
    events: List[str] = Field(default_factory=list)


class Receipt(BaseModel):
    url: str
    ok: bool = False
    attempts: int = 0
    status_code: Optional[int] = None
    error: Optional[str] = None
    idempotency_key: Optional[str] = None
    replayed: bool = False


def deliver(target: DeliveryTarget, payload: bytes, timeout_sec: float = 10.0,
            validate: bool = True) -> Receipt:
    """Deliver with SSRF validation + per-target secret resolution."""
    try:
        if validate:
            validate_webhook_url(target.url)
        resolved_secret = resolve_target_secret(target.secret)
    except WebhookSecurityError as exc:
        return Receipt(url=target.url, ok=False, attempts=0, error=f"WEBHOOK_TARGET_REJECTED: {exc}")
    last_err: Optional[str] = None
    for attempt in range(1, MAX_RETRIES + 2):  # 1 initial + max 2 retries
        res = dispatch_webhook(target.url, payload, secret=resolved_secret,
                               timeout_sec=timeout_sec, validate=False)
        if res.get("ok"):
            return Receipt(url=target.url, ok=True, attempts=res.get("attempt", attempt),
                           status_code=res.get("status_code"))
        last_err = res.get("error", "delivery failed")
        if attempt <= MAX_RETRIES:
            time.sleep(min(2 ** (attempt - 1) * 0.1, 1.0))
    return Receipt(url=target.url, ok=False, attempts=MAX_RETRIES + 1, error=last_err)


def deliver_all(targets: List[DeliveryTarget], payload: bytes,
                timeout_sec: float = 10.0, validate: bool = True) -> List[Receipt]:
    return [deliver(t, payload, timeout_sec=timeout_sec, validate=validate) for t in targets]


def delivery_idempotency_key(url: str, event: str, payload: bytes) -> str:
    """Deterministic key: duplicate event delivery shares one receipt."""
    return hashlib.sha256(f"{url}|{event}|".encode() + payload).hexdigest()


def deliver_idempotent(target: DeliveryTarget, payload: bytes, event: str = "project.completed",
                       timeout_sec: float = 10.0, store=None) -> Receipt:
    """Deliver once per (url, event, payload); replay returns the same receipt."""
    from backend.app.api.store import get_store

    store = store or get_store()
    key = delivery_idempotency_key(target.url, event, payload)
    existing = store.get_receipt(key)
    if existing is not None:
        return Receipt(url=target.url, ok=bool(existing.get("ok")),
                       attempts=int(existing.get("attempts") or 0),
                       status_code=existing.get("status_code"),
                       error=existing.get("error"),
                       idempotency_key=key, replayed=True)
    receipt = deliver(target, payload, timeout_sec=timeout_sec)
    receipt.idempotency_key = key
    store.save_receipt({
        "idempotency_key": key,
        "url": target.url,
        "event": event,
        "ok": receipt.ok,
        "attempts": receipt.attempts,
        "status_code": receipt.status_code,
        "error": receipt.error,
    })
    return receipt
