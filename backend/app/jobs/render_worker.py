"""Database-backed render queue worker (plan Task 3).

The API never executes a long Remotion render in the request path: it
enqueues a durable job and returns 202. The worker runs the subprocess with
a bounded timeout and writes per-job manifest/output paths - never the
shared `render_manifest.json`.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

RENDER_TIMEOUT_SEC = int(os.environ.get("RENDER_TIMEOUT_SEC", "600"))
RENDER_MAX_ATTEMPTS = int(os.environ.get("RENDER_MAX_ATTEMPTS", "3"))


def classify_render_error(error: str, attempt: int) -> str:
    """Plan 03 retry taxonomy: transient timeouts retry while attempts
    remain; anything else (or exhausted attempts) is terminal ('dead')."""
    if error.startswith("RENDER_TIMEOUT") and attempt < RENDER_MAX_ATTEMPTS:
        return "retry"
    return "dead"


def _remotion_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "remotion"


def _out_dir() -> Path:
    base = Path(__file__).resolve().parents[3]
    return Path(os.environ.get("OUT_DIR", str(base / "out")))


def run_render_job(
    job_id: str,
    manifest: Dict[str, Any],
    store=None,
    storage=None,
    timeout_sec: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute one durable render job; persist success artifact or safe stderr."""
    from backend.app.api.store import get_store

    store = store or get_store()
    timeout = timeout_sec or RENDER_TIMEOUT_SEC
    remotion_dir = _remotion_dir()
    out_root = _out_dir()
    out_root.mkdir(parents=True, exist_ok=True)

    per_job_manifest = remotion_dir / f"render_manifest_{job_id}.json"
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    per_job_manifest.write_bytes(manifest_bytes)

    aspect = str(manifest.get("aspectRatio", "9:16"))
    composition = "Shorts916" if aspect == "9:16" else "Landscape169"
    project = str(manifest.get("projectId", job_id))
    safe = "".join(c.lower() if c.isalnum() else "_" for c in project) or job_id
    output_filename = f"{safe}_{aspect.replace(':', '_')}_{job_id}.mp4"
    output_path = out_root / output_filename

    store.update_job(job_id, status="RUNNING")
    cmd = ["npx", "remotion", "render", "src/index.ts", composition,
           str(output_path), f"--props=./{per_job_manifest.name}"]
    try:
        proc = subprocess.run(cmd, cwd=str(remotion_dir), capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        safe_err = (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "timeout"
        return _finish_failed(store, storage, job_id,
                              f"RENDER_TIMEOUT: {safe_err}")
    if proc.returncode != 0:
        safe_err = (proc.stderr or "")[-2000:]
        return _finish_failed(store, storage, job_id,
                              f"REMOTION_FAILED: {safe_err}")
    artifact_key = f"renders/{output_filename}"
    if storage is not None and output_path.exists():
        storage.save(artifact_key, output_path.read_bytes())
    store.update_job(job_id, status="SUCCEEDED", artifact_key=artifact_key)
    store.record_outbox(f"job-done:{job_id}", "render-jobs",
                        {"job_id": job_id, "artifact_key": artifact_key})
    return {"job_id": job_id, "status": "SUCCEEDED", "artifact_key": artifact_key}


def _finish_failed(store, storage, job_id: str, error: str) -> Dict[str, Any]:
    """Plan 03 taxonomy: retryable errors requeue, terminal errors go DLQ."""
    current = store.get_job(job_id) or {}
    attempt = int(current.get("attempt", 0))
    if classify_render_error(error, attempt) == "retry":
        store.update_job(job_id, status="PENDING", error=error)
        return {"job_id": job_id, "status": "PENDING", "error": error}
    store.mark_dead(job_id, error)
    return {"job_id": job_id, "status": "DEAD", "error": error}


def compute_artifact_key(job_id: str, manifest: Dict[str, Any]) -> str:
    """Compute deterministic artifact key matching render output convention."""
    aspect = str(manifest.get("aspectRatio", "9:16"))
    project = str(manifest.get("projectId", job_id))
    safe = "".join(c.lower() if c.isalnum() else "_" for c in project) or job_id
    output_filename = f"{safe}_{aspect.replace(':', '_')}_{job_id}.mp4"
    return f"renders/{output_filename}"


def reconcile_render_job(job_id: str, manifest: Dict[str, Any], storage=None) -> Dict[str, Any]:
    """Plan 03 §6: Deterministic artifact reconciliation for Remotion crash recovery."""
    artifact_key = compute_artifact_key(job_id, manifest)
    out_root = _out_dir()
    output_filename = artifact_key.split("/", 1)[-1]
    output_path = out_root / output_filename

    if (storage is not None and hasattr(storage, "exists") and storage.exists(artifact_key)) or output_path.exists():
        return {
            "status": "SUCCEEDED",
            "artifact_key": artifact_key,
            "remote_operation_id": f"remotion-{job_id}",
        }
    return {"status": "NOT_FOUND"}