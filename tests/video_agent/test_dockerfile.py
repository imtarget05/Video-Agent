"""Dockerfile tests for Video-Agent service."""

import pathlib

# Anchored to the repo root so the test does not depend on the caller's cwd.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_dockerfile_exists():
    """Test that the Dockerfile exists at the expected path."""
    dockerfile_path = REPO_ROOT / "src" / "video_agent" / "Dockerfile"
    assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"


def test_root_dockerfile_exists():
    """The deployed service image is built from the repo-root Dockerfile."""
    dockerfile_path = REPO_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"