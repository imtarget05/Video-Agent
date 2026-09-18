"""Docker compose tests for Video-Agent service."""

import pathlib

import pytest


def test_docker_compose_exists():
    """Test that the docker-compose.yml exists at the expected path."""
    compose_path = pathlib.Path("src/video_agent/docker-compose.yml")
    assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"