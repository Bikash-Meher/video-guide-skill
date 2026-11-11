#!/usr/bin/env bash
# setup.sh — One-line environment setup for Linux / macOS / WSL
# Usage:
#   chmod +x setup.sh && ./setup.sh
#   OR: bash setup.sh

set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🎬  Video Guide Skill — setup.sh           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Python check ─────────────────────────────────────────────────────────────
PYTHON=$(command -v python3 || command -v python)
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  ✅  Python $PY_VERSION"

# ── Install uv ───────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  echo "  ℹ️   Installing uv..."
  if ! "$PYTHON" -m pip install --quiet uv 2>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
  fi
fi
echo "  ✅  uv $(uv --version)"

# ── Create venv + install ─────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "  ℹ️   Creating .venv..."
  uv venv .venv
fi
echo "  ℹ️   Installing dependencies..."
uv pip install --quiet -e .
echo "  ✅  Dependencies installed"

# ── Verify ───────────────────────────────────────────────────────────────────
.venv/bin/python -c "
from tool_executor import TOOLS
from auto_recipe import scaffold_recipe
print('  ✅  Tools verified:', list(TOOLS.keys()))
"

echo ""
echo "  🎉  Ready! Run: echo '{\"tool\":\"create_guide\",\"video_path\":\"rec.mp4\",\"output_path\":\"guide.mp4\"}' | python tool_executor.py"
echo ""
