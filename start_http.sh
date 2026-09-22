#!/usr/bin/env bash
set -euo pipefail

CONFIG="${READONLY_MCP_CONFIG:-./config.json}"

./.venv/bin/python ./server.py \
  --config "$CONFIG" \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000
