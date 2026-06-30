#!/usr/bin/env bash
#
# Boot the Counter-Swarm Sandbox: the engine bridge (FastAPI) + the dashboard (Vite).
# First run also sets up the Python venv and installs deps if they're missing.
#
#   ./run.sh
#
# Then open http://localhost:5173. Press Ctrl+C once to stop both processes.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PYTHON="${PYTHON:-python3}"

# --- Python environment -------------------------------------------------------
if [ ! -d "$VENV" ]; then
  echo "[setup] creating virtualenv (.venv)"
  "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

if ! python -c "import fastapi, uvicorn, pydantic, yaml" >/dev/null 2>&1; then
  echo "[setup] installing Python deps (engine + server)"
  pip install -q -e ".[dev,server]"
fi

# --- Frontend dependencies ----------------------------------------------------
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "[setup] installing frontend deps (npm install)"
  (cd "$ROOT/frontend" && npm install)
fi

# --- Engine bridge ------------------------------------------------------------
BRIDGE_PID=""
if curl -s http://127.0.0.1:8000/api/catalog >/dev/null 2>&1; then
  echo "[run] bridge already running on http://127.0.0.1:8000 - reusing it"
else
  echo "[run] starting engine bridge on http://127.0.0.1:8000"
  python server.py &
  BRIDGE_PID=$!
fi

cleanup() {
  if [ -n "$BRIDGE_PID" ]; then
    echo ""
    echo "[stop] shutting down engine bridge (pid $BRIDGE_PID)"
    kill "$BRIDGE_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

# Give the bridge a moment to come up.
sleep 1

# --- Dashboard (foreground; Ctrl+C stops everything) --------------------------
echo "[run] starting dashboard on http://localhost:5173  (Ctrl+C to stop)"
cd "$ROOT/frontend"
npm run dev
