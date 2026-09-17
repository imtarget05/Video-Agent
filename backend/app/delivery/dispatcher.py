"""
Delivery dispatcher (Slice C): HMAC-signed webhook fan-out, max 2 retries.

Wraps the HMAC helpers from api.webhooks so both import paths share
the same signature scheme (X-Signature: hex HMAC-SHA256).
"""
import os
import time
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.app.api.webhooks import sign_payload, verify_signature, dispatch_webhook

__all__ = [
    "DeliveryTarget",
    "Receipt",
    "sign_payload",
    "verify_signature",
    "deliver",
    "deliver_all",
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


def deliver(target: DeliveryTarget, payload: bytes, timeout_sec: float = 10.0) -> Receipt:
    secret = target.secret or os.getenv("WEBHOOK_SECRET", "dev-secret")
    last_err: Optional[str] = None
    for attempt in range(1, MAX_RETRIES + 2):  # 1 initial + max 2 retries
        res = dispatch_webhook(target.url, payload, secret=secret, timeout_sec=timeout_sec)
        if res.get("ok"):
            return Receipt(url=target.url, ok=True, attempts=res.get("attempt", attempt),
                           status_code=res.get("status_code"))
        last_err = res.get("error", "delivery failed")
        if attempt <= MAX_RETRIES:
            time.sleep(min(2 ** (attempt - 1) * 0.1, 1.0))
    return Receipt(url=target.url, ok=False, attempts=MAX_RETRIES + 1, error=last_err)


def deliver_all(targets: List[DeliveryTarget], payload: bytes,
                timeout_sec: float = 10.0) -> List[Receipt]:
    return [deliver(t, payload, timeout_sec=timeout_sec) for t in targets]
