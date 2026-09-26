# Standalone container for the src/video_agent scaffold service.
# Build context is src/ so the package can be laid out as /app/video_agent and
# really run as a module:
#   docker build -t video-agent-scaffold -f video_agent/Dockerfile src
# Run (or just use video_agent/docker-compose.yml):
#   docker run -p 8000:8000 video-agent-scaffold
# Health: curl http://localhost:8000/health
#
# This is NOT the deployed service image. The deployed image is the repo-root
# Dockerfile (see render.yaml), because the real API needs backend/, remotion/
# and dashboard/. This image contains only the standalone scaffold app in
# src/video_agent/main.py.
FROM python:3.11-slim

WORKDIR /app

COPY video_agent/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY video_agent/ ./video_agent/

EXPOSE 8000

# `USER nobody:nobody` looks right but python:3.11-slim has no group named
# `nobody` (the account is in `nogroup`), so the container failed to start with
# "unable to find group nobody". Naming the user alone resolves correctly.
USER nobody

CMD ["python", "-m", "video_agent"]