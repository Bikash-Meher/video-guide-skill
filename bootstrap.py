"""
bootstrap.py — Universal one-command environment setup.

Run with the system Python (no prior install needed):
    python bootstrap.py

What it does:
  1. Checks Python >= 3.11
  2. Installs uv if missing (via pip or curl/powershell)
  3. Creates .venv via uv and installs all dependencies
  4. Verifies all 5 skill tools import correctly
  5. Prints a ready-to-use cheatsheet

Works on: Windows (PowerShell / CMD), Linux, macOS.
Agents: Antigravity, Claude Code, Cursor, Codex, Grok, Muse — any that can run python.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
VENV = HERE / ".venv"
IS_WIN = platform.system() == "Windows"
PYTHON = sys.executable

DEPS = [
    "opencv-python>=4.9",
    "pillow>=10.0",
    "imageio-ffmpeg>=0.4",
    "edge-tts>=6.1",
    "numpy>=1.26",
    "mcp>=1.0",
]

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║          🎬  Video Guide Skill — Bootstrap Setup             ║
╚══════════════════════════════════════════════════════════════╝
"""

OK   = "  ✅"
FAIL = "  ❌"
INFO = "  ℹ️ "


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


def run_silent(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Python version check
# ──────────────────────────────────────────────────────────────────────────────

def check_python() -> None:
    v = sys.version_info
    if v < (3, 11):
        print(f"{FAIL} Python {v.major}.{v.minor} found — need 3.11+")
        print(f"       Download from https://python.org/downloads/")
        sys.exit(1)
    print(f"{OK}  Python {v.major}.{v.minor}.{v.micro}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Install uv
# ──────────────────────────────────────────────────────────────────────────────

def ensure_uv() -> str:
    """Return path to uv binary, installing it if needed."""
    uv = shutil.which("uv")
    if uv:
        print(f"{OK}  uv found at {uv}")
        return uv

    print(f"{INFO} uv not found — installing...")

    # Try pip first (fastest, works everywhere)
    if run_silent([PYTHON, "-m", "pip", "install", "--quiet", "uv"]):
        uv = shutil.which("uv")
        if not uv:
            # pip installed it but not on PATH — find it
            scripts = Path(PYTHON).parent
            uv_bin = scripts / ("uv.exe" if IS_WIN else "uv")
            if uv_bin.exists():
                uv = str(uv_bin)
        if uv:
            print(f"{OK}  uv installed via pip")
            return uv

    # Fallback: official installer
    if IS_WIN:
        ps_cmd = (
            'powershell -ExecutionPolicy Bypass -Command '
            '"irm https://astral.sh/uv/install.ps1 | iex"'
        )
        ok = run_silent(ps_cmd.split())
    else:
        ok = run_silent(
            ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]
        )

    if ok:
        # Add ~/.cargo/bin or ~/.local/bin to PATH for this process
        for extra in [
            Path.home() / ".cargo" / "bin",
            Path.home() / ".local" / "bin",
        ]:
            if extra.exists():
                os.environ["PATH"] = str(extra) + os.pathsep + os.environ["PATH"]

    uv = shutil.which("uv")
    if uv:
        print(f"{OK}  uv installed via official installer")
        return uv

    print(f"{FAIL} Could not install uv automatically.")
    print("       Please install manually: https://docs.astral.sh/uv/")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Create venv + install deps
# ──────────────────────────────────────────────────────────────────────────────

def setup_venv(uv: str) -> None:
    if VENV.exists():
        print(f"{OK}  .venv already exists — syncing deps")
    else:
        print(f"{INFO} Creating .venv ...")
        run([uv, "venv", str(VENV), "--python", PYTHON])
        print(f"{OK}  .venv created")

    print(f"{INFO} Installing dependencies (may take a minute on first run)...")
    run([uv, "pip", "install", "--quiet", "-e", str(HERE),
         "--python", str(VENV)])
    print(f"{OK}  Dependencies installed")


# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Verify all 5 tools
# ──────────────────────────────────────────────────────────────────────────────

def verify_tools(uv: str) -> None:
    venv_python = (
        VENV / "Scripts" / "python.exe" if IS_WIN else VENV / "bin" / "python"
    )
    code = (
        "import sys; sys.path.insert(0, '.'); "
        "from tool_executor import TOOLS, extract_frames, scaffold_recipe, "
        "validate_recipe, render_guide, create_guide; "
        "from auto_recipe import scaffold_recipe as _sr; "
        "print('TOOLS:', list(TOOLS.keys()))"
    )
    result = subprocess.run(
        [str(venv_python), "-c", code],
        capture_output=True, text=True, cwd=str(HERE)
    )
    if result.returncode == 0:
        tools_line = [l for l in result.stdout.splitlines() if "TOOLS:" in l]
        print(f"{OK}  All tools verified — {tools_line[0] if tools_line else 'OK'}")
    else:
        print(f"{FAIL} Tool verification failed:")
        print(result.stderr[-1000:])
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Step 5: Print cheatsheet
# ──────────────────────────────────────────────────────────────────────────────

def print_cheatsheet() -> None:
    venv_python = (
        ".venv\\Scripts\\python" if IS_WIN else ".venv/bin/python"
    )
    uv_run_prefix = "uv run --with opencv-python,pillow,imageio-ffmpeg,edge-tts,numpy"

    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  ✅  Setup complete! Video Guide Skill is ready.                     ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  QUICKSTART — just drop a video path:                                ║
║                                                                      ║
║  echo '{"tool":"create_guide",                                       ║
║         "video_path":"C:/rec.mp4",                                   ║
║         "output_path":"C:/guide.mp4"}' | python tool_executor.py    ║
║                                                                      ║
║  MCP SERVER (Claude Code / Cursor):                                  ║
║    python mcp_server.py                                              ║
║                                                                      ║
║  DIRECT IMPORT (any Python script):                                  ║
║    from tool_executor import create_guide                            ║
║    result = create_guide("C:/rec.mp4", "C:/guide.mp4")              ║
║                                                                      ║
║  DOCS: README.md                                                     ║
╚══════════════════════════════════════════════════════════════════════╝
""")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(BANNER)
    check_python()
    uv = ensure_uv()
    setup_venv(uv)
    verify_tools(uv)
    print_cheatsheet()


if __name__ == "__main__":
    main()
