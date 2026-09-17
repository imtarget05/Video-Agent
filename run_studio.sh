#!/usr/bin/env bash
# ==============================================================================
# Video-Agent Studio Launcher
# Starts FastAPI Canvas Studio Backend on Port 8000 and Remotion Preview on Port 3000
# ==============================================================================

set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "========================================================"
echo "🎬 Starting Video-Agent Semantic Workflow Canvas Studio"
echo "========================================================"
echo "• Backend & Canvas UI: http://localhost:8000 (and http://localhost:8000/canvas)"
echo "• Remotion Timeline Studio: http://localhost:3000"
echo "• Model Stack: Hugging Face Qwen-72B + Edge-TTS + Remotion React"
echo "========================================================"

# Activate virtualenv if available
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run Uvicorn server in foreground
exec python3 -m uvicorn backend.app.api.server:app --host 0.0.0.0 --port 8000 --reload
