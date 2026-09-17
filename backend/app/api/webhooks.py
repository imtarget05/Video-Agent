"""
Webhook HMAC dispatcher (Slice A minimal): sign / verify / deliver with max 2 retries.
"""
import hashlib
import hmac
import os
from typing import Optional


def sign_payload(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature or "")


def dispatch_webhook(url: str, payload: bytes, secret: Optional[str] = None, timeout_sec: float = 10.0) -> dict:
    import httpx
    secret = secret or os.getenv("WEBHOOK_SECRET", "dev-secret")
    headers = {"X-Signature": sign_payload(payload, secret), "Content-Type": "application/json"}
    last_err: Optional[str] = None
    for attempt in range(1, 4):  # 1 initial + max 2 retries
        try:
            resp = httpx.post(url, content=payload, headers=headers, timeout=timeout_sec)
            resp.raise_for_status()
            return {"ok": True, "attempt": attempt, "status_code": resp.status_code}
        except Exception as exc:
            last_err = str(exc)
    return {"ok": False, "attempt": 3, "error": last_err}
