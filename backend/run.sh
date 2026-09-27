#!/usr/bin/env bash
# Starts the ML Forge API server (which also serves the built frontend).
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "No venv found. Run ./setup.sh first."
  exit 1
fi

# Render (and other PaaS targets) inject $PORT at runtime and expect the
# app to bind to it. Locally / on the LAN, nothing sets $PORT, so this
# falls back to 8000.
PORT="${PORT:-8000}"

exec venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
