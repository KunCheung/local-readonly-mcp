#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3.10+ is required." >&2
  exit 1
fi

if [ ! -f "./config.json" ]; then
  cp "./config.example.json" "./config.json"
  echo "Created local config.json from config.example.json"
fi

"$PYTHON" -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

echo
echo "Setup complete."
echo "Edit ./config.json, then run:"
echo "  bash ./start_http.sh"
