#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

echo
echo "=============================================================="
echo "  Atlansub - Persian subtitle generator"
echo "=============================================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.9+ first."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/3] Creating a virtual environment in .venv ..."
  python3 -m venv .venv
else
  echo "[1/3] Virtual environment: OK"
fi
PY=".venv/bin/python"

if ! "$PY" -c "import fastapi, uvicorn, multipart, faster_whisper, arabic_reshaper, bidi" >/dev/null 2>&1; then
  echo "[2/3] Installing Python dependencies. This can take a few minutes ..."
  "$PY" -m pip install --upgrade pip
  "$PY" -m pip install -r requirements.txt
else
  echo "[2/3] Python dependencies: OK"
fi

echo "[3/3] Checking ffmpeg and the speech model ..."
"$PY" -m app.setup

echo
echo "Starting Atlansub. Press Ctrl+C to stop the server."
echo
exec "$PY" -m app.server
