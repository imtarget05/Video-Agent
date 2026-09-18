"""Dockerfile tests for Video-Agent service."""

import pathlib

import pytest


def test_dockerfile_exists():
    """Test that the Dockerfile exists at the expected path."""
    dockerfile_path = pathlib.Path("src/video_agent/Dockerfile")
    assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"