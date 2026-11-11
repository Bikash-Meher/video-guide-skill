"""
bootstrap.py — Universal one-command environment setup & cross-agent installer.

Run with system Python (no prior packages needed):
    python bootstrap.py
    python bootstrap.py --install-skill            # Also install skill into detected agent dirs
    python bootstrap.py --print-mcp                # Print ready-to-paste MCP configs with exact paths

What it does:
  1. Checks Python >= 3.11
  2. Installs `uv` if missing (pip -> official installer fallback)
  3. Creates `.venv` via `uv` and installs this package + all dependencies
  4. Verifies bundled FFmpeg binary + all 7 tools + CLI entrypoints
  5. Prints ready-to-use commands and optional MCP/Skill installation snippets

Works on: Windows (PowerShell / CMD), Linux, macOS.
Compatible with: Antigravity, Claude Code, OpenAI Codex, Cursor, Muse Code, Grok Code.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).parent.resolve()
VENV = HERE / ".venv"
IS_WIN = platform.system() == "Windows"
PYTHON = sys.executable

OK = "  [OK]"
FAIL = "  [FAIL]"
INFO = "  [INFO]"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


def run_silent(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Python >= 3.11
# ──────────────────────────────────────────────────────────────────────────────

def check_python() -> None:
    v = sys.version_info
    if v < (3, 11):
        print(f"{FAIL} Python {v.major}.{v.minor} found — need 3.11+")
        print("       Download from https://python.org/downloads/")
        sys.exit(1)
    print(f"{OK} Python {v.major}.{v.minor}.{v.micro}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Ensure uv
# ──────────────────────────────────────────────────────────────────────────────

def ensure_uv() -> str:
    """Return path to `uv`, installing it if missing."""
    uv = shutil.which("uv")
    if uv:
        print(f"{OK} uv found at {uv}")
        return uv

    print(f"{INFO} uv not found — installing...")

    # Method A: pip
    if run_silent([PYTHON, "-m", "pip", "install", "--quiet", "uv"]):
        uv = shutil.which("uv")
        if not uv:
            scripts = Path(PYTHON).parent / ("Scripts" if IS_WIN else "bin")
            for cand in [Path(PYTHON).parent / ("uv.exe" if IS_WIN else "uv"), scripts / ("uv.exe" if IS_WIN else "uv")]:
                if cand.exists():
                    uv = str(cand)
                    break
        if uv:
            print(f"{OK} uv installed via pip ({uv})")
            return uv

    # Method B: official Astral installer
    if IS_WIN:
        ok = run_silent([
            "powershell", "-ExecutionPolicy", "Bypass", "-Command",
            "irm https://astral.sh/uv/install.ps1 | iex",
        ])
    else:
        ok = run_silent(["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"])

    if ok:
        for extra in [
            Path.home() / ".cargo" / "bin",
            Path.home() / ".local" / "bin",
            Path.home() / "AppData" / "Local" / "Programs" / "uv",
        ]:
            if extra.exists():
                os.environ["PATH"] = str(extra) + os.pathsep + os.environ["PATH"]

    uv = shutil.which("uv")
    if uv:
        print(f"{OK} uv installed ({uv})")
        return uv

    print(f"{FAIL} Could not install uv automatically: https://docs.astral.sh/uv/")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Create .venv & install package editable + dependencies
# ──────────────────────────────────────────────────────────────────────────────

def setup_venv(uv: str) -> None:
    if VENV.exists():
        print(f"{OK} .venv already exists — syncing editable package & deps")
    else:
        print(f"{INFO} Creating .venv ...")
        run([uv, "venv", str(VENV), "--python", PYTHON])
        print(f"{OK} .venv created")

    print(f"{INFO} Installing package & dependencies (first run downloads ~90MB)...")
    run([uv, "pip", "install", "--quiet", "-e", str(HERE), "--python", str(VENV)])
    print(f"{OK} Dependencies installed")


# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Verify all 7 tools, FFmpeg, and console scripts
# ──────────────────────────────────────────────────────────────────────────────

def verify_all() -> None:
    venv_py = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
    code = (
        "import sys; sys.path.insert(0, '.'); "
        "import imageio_ffmpeg, cv2, edge_tts, numpy, mcp; "
        "from PIL import Image; "
        "ff = imageio_ffmpeg.get_ffmpeg_exe(); "
        "from tool_executor import TOOLS; "
        "from auto_recipe import analyze_video_frames, scaffold_recipe; "
        "from video_guide_skill.cli import main as _cli; "
        "from video_guide_skill.mcp_entry import main as _mcp; "
        "print('FFMPEG:', ff); "
        "print('TOOLS:', list(TOOLS.keys()))"
    )
    res = subprocess.run(
        [str(venv_py), "-c", code],
        capture_output=True, text=True, cwd=str(HERE), encoding="utf-8", errors="replace",
    )
    if res.returncode != 0:
        print(f"{FAIL} Verification failed:\n{res.stderr[-1200:]}")
        sys.exit(1)

    ff_line = next((l for l in res.stdout.splitlines() if l.startswith("FFMPEG:")), "FFMPEG: OK")
    tools_line = next((l for l in res.stdout.splitlines() if l.startswith("TOOLS:")), "TOOLS: OK")
    print(f"{OK} Bundled FFmpeg ready ({ff_line.split(':', 1)[1].strip()})")
    print(f"{OK} All 7 tools verified ({tools_line.split(':', 1)[1].strip()})")


# ──────────────────────────────────────────────────────────────────────────────
# Optional: Copy / Register Skill folder for Antigravity, Claude Code, Codex, Cursor
# ──────────────────────────────────────────────────────────────────────────────

def install_skill_to_agents(target: str = "all") -> None:
    """Install self-contained skill files into agent skill discovery folders."""
    home = Path.home()
    candidates = {
        "antigravity": home / ".gemini" / "config" / "skills" / "video-guide-maker",
        "claude": home / ".claude" / "skills" / "video-guide-maker",
        "codex": home / ".codex" / "skills" / "video-guide-maker",
        "cursor": home / ".cursor" / "skills" / "video-guide-maker",
    }

    selected = candidates.items() if target == "all" else [(target, candidates[target])]
    files_to_copy = [
        "SKILL.md", "AGENTS.md", "engine.py", "auto_recipe.py", "tool_executor.py",
        "mcp_server.py", "bootstrap.py", "pyproject.toml", "requirements.txt",
    ]
    dirs_to_copy = ["schemas", "examples", "video_guide_skill"]

    for agent_name, dest in selected:
        parent_root = dest.parent.parent
        # Only install globally for tools whose config dir exists (unless explicitly named)
        if target == "all" and not parent_root.exists() and agent_name != "antigravity":
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for fname in files_to_copy:
            src = HERE / fname
            if src.exists():
                shutil.copy2(src, dest / fname)
        for dname in dirs_to_copy:
            src_d = HERE / dname
            if src_d.exists():
                shutil.copytree(src_d, dest / dname, dirs_exist_ok=True)
        print(f"{OK} Installed skill for {agent_name} -> {dest}")


def print_mcp_snippets() -> None:
    venv_py = (VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")).as_posix()
    mcp_py = (HERE / "mcp_server.py").as_posix()
    print("\n--- Ready-to-Paste MCP Configuration (Claude Desktop / Claude Code / Cursor / Antigravity) ---")
    import json
    cfg = {
        "mcpServers": {
            "video-guide": {
                "command": venv_py,
                "args": [mcp_py],
            }
        }
    }
    print(json.dumps(cfg, indent=2))
    print("--------------------------------------------------------------------------------------------\n")


def print_cheatsheet() -> None:
    venv_py = ".venv\\Scripts\\python.exe" if IS_WIN else ".venv/bin/python"
    print(f"""
========================================================================
  Setup complete! Video Guide Skill is ready.
========================================================================

  END-USER INPUT NEEDED: Just the video path (+ optional flow notes).
  No manual recipe JSON!

  START PIPELINE (extracts 3 FPS frames + analyzes all frames + storyboards):
    echo '{{"tool":"create_guide","video_path":"C:/rec.mp4"}}' | {venv_py} tool_executor.py

  START MCP SERVER (Claude Code / Cursor / Antigravity):
    {venv_py} mcp_server.py

  INSTALL SKILL TO GLOBAL AGENT DIRS:
    {venv_py} bootstrap.py --install-skill

  PRINT EXACT MCP JSON CONFIG:
    {venv_py} bootstrap.py --print-mcp
========================================================================
""")


def main() -> None:
    parser = argparse.ArgumentParser(description="Video Guide Skill Bootstrap Setup")
    parser.add_argument(
        "--install-skill",
        nargs="?",
        const="all",
        choices=["all", "antigravity", "claude", "codex", "cursor"],
        help="Copy skill + scripts into agent skill folders (~/.gemini, ~/.claude, ~/.codex, ~/.cursor)",
    )
    parser.add_argument("--print-mcp", action="store_true", help="Print MCP config JSON with resolved paths")
    args = parser.parse_args()

    print("\n=== Video Guide Skill — Bootstrap Setup ===\n")
    check_python()
    uv = ensure_uv()
    setup_venv(uv)
    verify_all()
    if args.install_skill:
        install_skill_to_agents(args.install_skill)
    if args.print_mcp:
        print_mcp_snippets()
    print_cheatsheet()


if __name__ == "__main__":
    main()
