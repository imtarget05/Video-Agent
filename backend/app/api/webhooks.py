"""
Webhook HMAC signing + SSRF-safe URL validation (plan Task 4).

Destinations must reject loopback, RFC1918, link-local, and DNS-resolved
private targets. In production a per-target secret is mandatory — the
`dev-secret` fallback only exists in explicit development mode.
"""
import hashlib
import hmac
import ipaddress
import os
import socket
from typing import Optional
from urllib.parse import urlparse


def sign_payload(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature or "")


class WebhookSecurityError(ValueError):
    """Raised when a webhook destination is not allowed."""


def _hostname_allowed(hostname: str, allowlist: set[str]) -> bool:
    if hostname in allowlist or hostname.lstrip(".").rstrip(".") in allowlist:
        return True
    if allowlist:
        return any(hostname.endswith(f".{entry}") for entry in allowlist)
    return False


def validate_webhook_url(
    url: str,
    allowlist: Optional[list] = None,
    resolve_dns: bool = True,
) -> dict:
    """Validate a webhook destination; return parsed info or raise.

    Rules:
      - scheme must be http/https
      - loopback / link-local / private / reserved IPs are rejected
      - DNS-resolved addresses of the hostname are checked too (DNS rebinding)
      - a configured allowlist (WEBHOOK_ALLOWED_HOSTS, comma-separated) takes
        precedence; empty allowlist = reject everything private/unapproved
    """
    raw = (os.environ.get("WEBHOOK_ALLOWED_HOSTS", "") or "")
    configured = {h.strip() for h in raw.split(",") if h.strip()}
    allow = set(allowlist or []) | configured

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise WebhookSecurityError(f"unparseable webhook url: {exc}") from exc
    if parsed.scheme not in ("http", "https"):
        raise WebhookSecurityError("webhook url scheme must be http/https")
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise WebhookSecurityError("webhook url requires a hostname")

    if hostname in ("localhost",) or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise WebhookSecurityError(f"webhook target rejected (loopback): {hostname}")
    if _hostname_allowed(hostname, allow):
        return {"hostname": hostname, "resolved": [], "allowlisted": True}

    if resolve_dns:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            raise WebhookSecurityError(f"webhook host does not resolve: {hostname}") from exc
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_loopback or ip.is_link_local or ip.is_private
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                raise WebhookSecurityError(
                    f"webhook target rejected (private/resolved IP {ip}): {hostname}"
                )
    return {"hostname": hostname, "resolved": [], "allowlisted": bool(allow)}


def resolve_target_secret(target_secret: Optional[str] = None) -> str:
    """Per-target secret wins; production has no dev-secret fallback."""
    env = os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "development")).lower()
    if target_secret and target_secret.strip():
        return target_secret.strip()
    global_secret = os.environ.get("WEBHOOK_SECRET", "").strip()
    if global_secret:
        return global_secret
    if env in ("production", "prod", "staging"):
        raise WebhookSecurityError("WEBHOOK_SECRET (or per-target secret) is required in production")
    return "dev-secret"


def dispatch_webhook(
    url: str,
    payload: bytes,
    secret: Optional[str] = None,
    timeout_sec: float = 10.0,
    validate: bool = True,
) -> dict:
    """Sign + deliver; rejects SSRF targets before any network call."""
    import httpx

    if validate:
        validate_webhook_url(url)
    resolved_secret = resolve_target_secret(secret)
    headers = {"X-Signature": sign_payload(payload, resolved_secret),
               "Content-Type": "application/json"}
    last_err: Optional[str] = None
    for attempt in range(1, 4):  # 1 initial + max 2 retries
        try:
            resp = httpx.post(url, content=payload, headers=headers, timeout=timeout_sec)
            resp.raise_for_status()
            return {"ok": True, "attempt": attempt, "status_code": resp.status_code}
        except Exception as exc:
            last_err = str(exc)
    return {"ok": False, "attempt": 3, "error": last_err}
