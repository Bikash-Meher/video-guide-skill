#!/usr/bin/env bash
# setup.sh — One-command environment setup for Linux / macOS / WSL
# Usage:
#   bash setup.sh [--install-skill] [--print-mcp]

set -euo pipefail
cd "$(dirname "$0")"

PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
  echo "[FAIL] Python 3.11+ not found. Please install Python 3.11+ first."
  exit 1
fi

exec "$PYTHON" bootstrap.py "$@"
