#!/usr/bin/env bash
# CareerPilot AI — Cloud Agent install (idempotent repository bootstrap).
# Prepares the Python backend venv, frontend node_modules, local env files,
# and the SQLite database so both services can start.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> CareerPilot install: repo root = $REPO_ROOT"

# --- Local env files (never overwrite existing) ---
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example"
fi
if [ ! -f frontend/.env.local ]; then
  cp frontend/.env.example frontend/.env.local
  echo "==> Created frontend/.env.local from frontend/.env.example"
fi

# --- System dependency: python venv support (default image lacks ensurepip) ---
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  echo "==> Installing python3-venv system package"
  PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  sudo apt-get update -y
  sudo apt-get install -y "python${PYVER}-venv" || sudo apt-get install -y python3-venv
fi

# --- Backend: Python venv + dependencies ---
if [ ! -d .venv ]; then
  echo "==> Creating Python venv (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

# --- Backend: initialize SQLite schema (idempotent; create_all is a no-op if present) ---
python -m backend.db.init_db

# --- Frontend: install node modules from lockfile ---
cd frontend
npm ci
cd "$REPO_ROOT"

echo "==> CareerPilot install complete"
