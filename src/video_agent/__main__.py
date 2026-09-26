"""Entry point for ``python -m video_agent``.

The scaffold Dockerfile runs the app as a module, so this module starts
uvicorn against ``video_agent.main:app``. Without it ``python -m
video_agent`` dies with "No module named video_agent.__main__", which is
what made the image unrunnable even once it built.
"""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "video_agent.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()