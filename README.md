# 🎬 Video Guide Skill

> **Turn any screen recording into a polished, narrated user-guide MP4** — in one tool call, from any agentic coding environment.

[![CI](https://github.com/YOUR_USERNAME/video-guide-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/video-guide-skill/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-stdio-green)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ What it does

You give the agent **only a screen recording path**. The skill does everything else:

```
[You] ──► video path only
  │
  ├─ 1. Extract frames at 3 fps   (FFmpeg, bundled — no install)
  ├─ 2. Detect UI scene changes   (histogram diff, automatic)
  ├─ 3. Scaffold draft recipe     (steps, timing, frame refs)
  ├─ 4. Agent inspects scenes     (vision → writes narrations)
  ├─ 5. Validate recipe           (TTS synthesis + timing check)
  └─ 6. Render MP4 + SRT          (h264, aac, captions)
```

| Feature | Detail |
|---|---|
| 🎙️ Narration | Microsoft Edge TTS — 6 voices, 5 tone presets |
| 🖥️ HUD overlays | Animated step counter + progress dock (8 placement zones) |
| 🔍 Zoom & click | Per-step zoom crops and animated click indicators |
| 🎵 Music | Auto-ducking background music |
| 📋 Captions | `.srt` subtitle file alongside every render |
| ⚡ Frame extraction | Built-in FFmpeg at 3 fps (configurable) |
| 🤖 Auto recipe | Scene detection → draft → agent fills narrations via vision |

Works for **any app, website, portal, SaaS, or web application**.

---

## 🚀 Setup — One Command, Any OS, Any Agent

> **Clone → run one command → ready. No manual pip, no PATH tweaks, no prior uv required.**

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/video-guide-skill.git
cd video-guide-skill

# 2. Auto-setup (works on Windows, Linux, macOS — Python 3.11+ only requirement)
python bootstrap.py
```

`bootstrap.py` automatically:
- ✅ Checks Python ≥ 3.11
- ✅ Installs `uv` if missing (via pip → then official installer fallback)
- ✅ Creates `.venv` and installs all dependencies
- ✅ Verifies all 5 tools import correctly
- ✅ Prints a ready-to-use cheatsheet

**OS-specific shortcuts (same result as bootstrap.py):**

| OS | Command |
|---|---|
| Windows (PowerShell) | `.\setup.ps1` |
| Linux / macOS / WSL | `bash setup.sh` |
| Any OS (universal) | `python bootstrap.py` |

**pip fallback (no uv needed):**
```bash
pip install -r requirements.txt
pip install -e .
```

**Requirements:** Python ≥ 3.11, internet (for TTS + first-time dep download). FFmpeg is bundled.

---

## 🤖 Usage by Agent Tool

> **In every tool below — the agent only needs the video path. No recipe writing, no manual steps.**

### Antigravity (Google Deepmind)

**Method 1 — Copy skill to Antigravity config:**
```bash
# Windows PowerShell
New-Item -ItemType Directory -Force "C:\Users\<you>\.gemini\config\skills\video-guide"
Copy-Item "antigravity\SKILL.md" "C:\Users\<you>\.gemini\config\skills\video-guide\SKILL.md"
```

**Invoke in chat — just paste the video path:**
```
Create a user guide from C:/recordings/my_app.mp4
```
Antigravity calls `create_guide`, inspects the returned thumbnails via its vision model,
writes narrations, validates, and renders — no manual input needed.

---

### Claude Code / Claude Desktop (Anthropic MCP)

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "video-guide": {
      "command": "uv",
      "args": [
        "run", "--with",
        "mcp,opencv-python,pillow,imageio-ffmpeg,edge-tts,numpy",
        "python",
        "/absolute/path/to/video-guide-skill/mcp_server.py"
      ]
    }
  }
}
```

Then in Claude Code:
```
Use the video-guide:extract_frames tool on /home/me/recordings/portal.mp4,
then validate and render a guide for the login flow.
```

---

### Cursor

Add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "video-guide": {
      "command": "uv",
      "args": [
        "run", "--with",
        "mcp,opencv-python,pillow,imageio-ffmpeg,edge-tts,numpy",
        "python",
        "/absolute/path/to/video-guide-skill/mcp_server.py"
      ],
      "transport": "stdio"
    }
  }
}
```

---

### OpenAI Codex / Grok Code / Muse Code

These tools use OpenAI-compatible function-calling. Add the tool definitions from `schemas/openai_tools.json` to your system configuration or agent tools array.

**Direct shell invocation (simplest integration):**
```bash
# 1. Extract frames
echo '{"tool":"extract_frames","video_path":"C:/rec.mp4","fps":3}' | python tool_executor.py

# 2. Validate recipe
echo '{"tool":"validate_recipe","recipe_json":"{...}"}' | python tool_executor.py

# 3. Render
echo '{"tool":"render_guide","recipe_json":"{...}","output_path":"C:/out/guide.mp4"}' | python tool_executor.py
```

**OpenAI Agents SDK:**
```python
from openai import OpenAI
import json, pathlib

tools = json.loads(pathlib.Path("schemas/openai_tools.json").read_text())["tools"]

client = OpenAI()
# Pass `tools=tools` in your chat.completions.create() call.
# When the model calls extract_frames / validate_recipe / render_guide,
# dispatch to tool_executor.py via subprocess.
```

---

## 📄 Recipe JSON Format

A **recipe** tells the engine what to show, say, and annotate at each step.

**Minimal example:**
```json
{
  "title": "My App Login Guide",
  "frames_dir": "C:/recordings/my_app_frames",
  "default_voice": "en-IN-NeerjaNeural",
  "tone": "friendly",
  "output_resolution": {"width": 1920, "height": 1080},
  "total_duration": 30.0,
  "timeline_mapping": [
    {
      "step": 1,
      "label": "Open Login Page",
      "active_start": 0.0,
      "active_end": 8.0,
      "source_frame": "C:/recordings/my_app_frames/0001_frame.png",
      "narration": "Open your browser and navigate to the login page.",
      "highlight_boxes": [
        {"x": 400, "y": 300, "w": 500, "h": 60, "color": "#00C4FF", "label": "URL Bar"}
      ]
    },
    {
      "step": 2,
      "label": "Enter Credentials",
      "active_start": 8.0,
      "active_end": 18.0,
      "source_frame": "C:/recordings/my_app_frames/0025_frame.png",
      "narration": "Enter your username and password, then click Sign In.",
      "click_indicator": {"x": 760, "y": 480}
    }
  ]
}
```

**Available voices:**

| Voice ID | Description |
|---|---|
| `en-IN-NeerjaNeural` | Indian English Female — Warm, Articulate |
| `en-IN-PrabhatNeural` | Indian English Male — Clear, Authoritative |
| `en-US-JennyNeural` | US English Female — Friendly Corporate |
| `en-US-GuyNeural` | US English Male — Confident Tutorial |
| `en-GB-SoniaNeural` | UK English Female — Polished, Natural |
| `en-GB-RyanNeural` | UK English Male — Crisp, Formal |

**Tone presets:** `professional` · `energetic` · `calm` · `corporate` · `friendly`

**HUD dock positions:** `below` · `above` · `left` · `right` · `bottom-left` · `bottom-right` · `top-left` · `top-right`

Full schema: [`schemas/recipe.schema.json`](schemas/recipe.schema.json)

---

## 🛠️ Five Tools — Start with `create_guide`

| Tool | Input required | Does |
|---|---|---|
| ⭐ **`create_guide`** | `video_path`, `output_path` | Full auto pipeline — just drop a video |
| `scaffold_recipe` | `frames_dir` | Scene detect → draft recipe + thumbnails for agent |
| `validate_recipe` | `recipe_json` | TTS + timing check, returns warnings |
| `render_guide` | `recipe_json`, `output_path` | Full MP4 render |
| `extract_frames` | `video_path` | FFmpeg extraction only |

---

## 📁 Repository Structure

```
video-guide-skill/
├── bootstrap.py           # 🔧 Universal auto-setup (run this after clone)
├── setup.ps1              # 🔧 Windows PowerShell setup shortcut
├── setup.sh               # 🔧 Linux / macOS setup shortcut
├── engine.py              # Core rendering engine (CV2 + Pillow + Edge TTS)
├── auto_recipe.py         # Scene detection + recipe scaffolder
├── tool_executor.py       # JSON-in / JSON-out tool dispatcher (5 tools)
├── mcp_server.py          # MCP stdio server (Claude Code, Cursor)
├── skill_manifest.json    # Unified skill manifest
├── pyproject.toml         # pip/uv installable package
├── requirements.txt       # pip fallback (no uv needed)
├── .python-version        # Pins Python 3.11 for uv
├── schemas/
│   ├── recipe.schema.json # JSON Schema for recipe validation
│   └── openai_tools.json  # OpenAI function-calling definitions
├── examples/
│   ├── recipe_create_exam.json    # 12-step ERP exam creation guide
│   └── recipe_student_sale.json   # 15-step student sale workflow
├── antigravity/
│   └── SKILL.md           # Antigravity skill definition
└── .github/workflows/
    └── ci.yml             # CI: bootstrap on Windows + Linux + macOS
```

---

## 🔄 Agent Workflow — Zero Manual Input

```
User: "Create a user guide from C:/recordings/portal.mp4"

Agent calls: create_guide(video_path="portal.mp4", output_path="guide.mp4")

  Internally:
    ► extract_frames  → 300 frames at 3 fps
    ► detect scenes   → 8 UI transition points found
    ► scaffold recipe → draft JSON + 8 thumbnails returned

Agent: inspects thumbnails via vision model
       writes narration for each step
       fills highlight_boxes for key UI elements

Agent calls: validate_recipe(recipe_json="<filled>")   → 0 warnings
Agent calls: render_guide(recipe_json="<filled>", output_path="guide.mp4")

Done → guide.mp4 (narrated, HUD, captions) + guide.srt
```

---

## 📜 License

MIT — see [LICENSE](LICENSE).

---

## 🤝 Contributing

PRs welcome! Please open an issue first for large changes.
Topics: `mcp` · `agent-skill` · `video-guide` · `llm-tool` · `tutorial-automation`
