"""Docker compose tests for Video-Agent service."""

import pathlib

# Anchored to the repo root so the test does not depend on the caller's cwd.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_docker_compose_exists():
    """Test that the docker-compose.yml exists at the expected path."""
    compose_path = REPO_ROOT / "src" / "video_agent" / "docker-compose.yml"
    assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"


def test_dockerfile_has_healthcheck():
    """The service container declares a /health healthcheck."""
    text = (REPO_ROOT / "src" / "video_agent" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "/health" in text, "docker-compose.yml must healthcheck /health"