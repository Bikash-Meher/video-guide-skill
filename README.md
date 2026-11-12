# 🎬 Video Guide Skill

> **Drop a screen recording video path — let ANY AI coding agent turn it into a narrated, HUD-annotated user guide MP4.**

[![CI](https://github.com/Bikash-Meher/video-guide-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/Bikash-Meher/video-guide-skill/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Agent Skills](https://img.shields.io/badge/Agent_Skill-SKILL.md-purple)](SKILL.md)
[![MCP](https://img.shields.io/badge/MCP-stdio-green)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Works seamlessly across **Antigravity**, **Claude Code**, **OpenAI Codex**, **Cursor**, **Muse Code**, **Grok Code**, and any tool supporting `SKILL.md`, `AGENTS.md`, CLI JSON tools, or **MCP**.

---

## ✨ What it does (Zero Recipe JSON Needed from User!)

You supply **only your screen recording path** (and optionally any guide/flow notes).  
The skill guides your AI agent to do **100% of the heavy lifting**:

```
[You] ──► "C:/recordings/erp.mp4 — edit this into a user guide"
  │
  ├─ 1. FFmpeg 3-FPS Extraction    (e.g., ~630 PNGs for a 210s video; FFmpeg bundled)
  ├─ 2. Full-Sequence Frame Scan   (analyzes EVERY extracted frame 0..N-1 for UI & page cuts)
  ├─ 3. Labeled Storyboards        (generates high-res storyboard sheets + changed pixel bboxes)
  ├─ 4. Agent Visual Understanding (reads storyboards + key frames before editing)
  ├─ 5. Dynamic Recipe Synthesis   (trims idle pauses, authors narration, boxes, arrows, zoom)
  ├─ 6. Voice / Tone & Plan Gate   (Edge-TTS check + `--plan_only` preview before render)
  └─ 7. Final Render               (1080p+ H.264 MP4, sidechain-ducked music, `.srt` captions)
```

| Capability | Detail |
|---|---|
| 🎙️ **Voiceover** | Microsoft Edge TTS — 6 voices + custom IDs, 5 tone presets, auto-shift or overlap check |
| 🖥️ **8-Zone Adaptive HUD Dock** | Auto-wraps captions, extends bottom stage on cropped wide videos, avoids UI buttons cleanly |
| 🔍 **Smooth Zoom & Spotlight** | Region zoom transitions + background dim spotlight masks |
| 🎯 **Boxes & Pulsing Arrows** | `rect`, `rounded_rect`, `circle`, `pill`, `underline` highlights + auto-angled vector arrows |
| 🎨 **4 Themes** | `tech_hud`, `clean_light`, `minimal`, `high_contrast` |
| 📋 **Captions & Audio** | `.srt` subtitle export, auto-ducked synth/custom music, optional source audio mix |

---

## 🚀 Auto Environment Setup on Clone

Clone the repository and run **one command** — Python `>= 3.11` is the only prerequisite:

```bash
git clone https://github.com/Bikash-Meher/video-guide-skill.git
cd video-guide-skill

# Universal (Windows / macOS / Linux)
python bootstrap.py

# Or install globally into Antigravity / Claude Code / Codex / Cursor skill folders too:
python bootstrap.py --install-skill --print-mcp
```

**OS shortcuts:**
- Windows PowerShell: `.\setup.ps1` (or `.\setup.ps1 -InstallSkill -PrintMcp`)
- Linux / macOS / WSL: `bash setup.sh` (or `bash setup.sh --install-skill --print-mcp`)

> Also works automatically without running setup manually: calling `python tool_executor.py` auto-bootstraps `.venv` on first invocation.

---

## 🤖 Using Across Every Agentic Tool

In every tool below, **just give the recording path** (and optional flow instructions):

### 1. Antigravity / OpenAI Codex / Claude Code Skills (`SKILL.md` & `AGENTS.md`)

Run:
```bash
python bootstrap.py --install-skill
```
This installs the self-contained skill (`SKILL.md`, `engine.py`, `auto_recipe.py`, `tool_executor.py`, schemas, examples) into your agent's `skills/` directory (`~/.gemini/config/skills/`, `~/.claude/skills/`, `~/.codex/skills/`, `~/.cursor/skills/`). Or simply open this cloned repo directly (`AGENTS.md` + `SKILL.md` are discovered automatically!).

**Prompt example:**
```text
C:/recordings/Recording_2026-11-10.mp4 — extract 3 fps frames, analyze all frames, and edit this into a user guide video.
```

---

### 2. Claude Code / Claude Desktop / Cursor / Antigravity MCP

Run `python bootstrap.py --print-mcp` to get the exact JSON with your system's `.venv` paths, or configure:

```json
{
  "mcpServers": {
    "video-guide": {
      "command": "/path/to/video-guide-skill/.venv/bin/python",
      "args": ["/path/to/video-guide-skill/mcp_server.py"]
    }
  }
}
```
*(Windows: use `.venv/Scripts/python.exe` — see `python bootstrap.py --print-mcp`.)*

Cursor project config goes in `.cursor/mcp.json`.

---

### 3. Grok Code / Muse Code / OpenAI Function-Calling SDK

Load `tools[]` from [`schemas/openai_tools.json`](schemas/openai_tools.json) and execute via `tool_executor.py`:

```bash
# Step 1: Extract 3 FPS frames + analyze ALL frames + create storyboards & starter draft
echo '{"tool":"create_guide","video_path":"C:/rec.mp4","user_flow_notes":"Create exam walkthrough"}' | .venv/bin/python tool_executor.py

# Step 2 (Agent inspects storyboards + key frames, writes recipe.json, then validates):
.venv/bin/python tool_executor.py --args '{"tool":"validate_recipe","recipe_path":"C:/rec_frames/_work/recipe.json"}'

# Step 3 (Render final MP4 + SRT):
.venv/bin/python tool_executor.py --args '{"tool":"render_guide","recipe_path":"C:/rec_frames/_work/recipe.json","output_path":"C:/out/Guide.mp4"}'
```

---

## 🛠️ Seven Agent Tools

| Tool | Purpose |
|---|---|
| ⭐ **`create_guide`** | Start here with just `video_path`: extracts 3-FPS frames via FFmpeg, analyzes all `N` frames (`0..N-1`), renders labeled `storyboard_*.png` contact sheets + `analysis_3fps.json` + starter `recipe_draft.json` |
| `extract_frames` | Bundled FFmpeg frame extraction (`--fps_extracted 3` = 3 images/sec) |
| `analyze_frames` | Exhaustive spatiotemporal frame scan + `8×6` UI change bbox detector + contact sheets |
| `inspect_frame_slice` | Zooms into every consecutive frame in `[start_frame..end_frame]` for fast UI clicks |
| `scaffold_recipe` | Emits an `engine.py`-compatible starter `recipe.json` from analyzed frames |
| `validate_recipe` | Blocks leftover `[AGENT:]` placeholders + runs `engine.py --plan_only` |
| `render_guide` | Renders final 1080p+ H.264 `.mp4` + `.srt` captions via `engine.py` |

---

## 🎙️ Voice & Tone Presets

| Voice ID | Description | Tone Preset | Speed / Style |
|---|---|---|---|
| `en-IN-NeerjaNeural` | Indian English Female | `friendly` | `+6%`, warm `tech_hud` |
| `en-IN-PrabhatNeural` | Indian English Male | `professional` | `+8%`, balanced `tech_hud` |
| `en-US-JennyNeural` | US English Female | `calm` | `+0%`, light `clean_light` |
| `en-US-GuyNeural` | US English Male | `energetic` | `+14%`, upbeat `tech_hud` |
| `en-GB-SoniaNeural` | UK English Female | `corporate` | `+5%`, sleek `minimal` |
| `en-GB-RyanNeural` | UK English Male | *(any custom Edge-TTS voice also works)* | |

---

## 📁 Repository Structure

```text
video-guide-skill/
├── SKILL.md                   # Agent Skills Open Standard prompt & workflow
├── AGENTS.md                  # Cross-agent instructions (Codex, Cursor, Muse, Grok)
├── bootstrap.py               # Universal 1-command auto-setup + --install-skill
├── setup.ps1 / setup.sh       # OS setup wrappers
├── engine.py                  # Core video compositor, FFmpeg 3-FPS extractor & Edge-TTS mixer
├── auto_recipe.py             # Exhaustive 3-FPS frame analyzer, storyboards & recipe scaffolder
├── tool_executor.py           # JSON-in/JSON-out dispatcher (7 tools)
├── mcp_server.py              # MCP stdio server
├── video_guide_skill/         # Python package entrypoints (`video-guide`, `video-guide-mcp`)
├── schemas/
│   ├── recipe.schema.json     # Full engine.py recipe JSON schema
│   └── openai_tools.json      # OpenAI function-calling schema
├── examples/
│   ├── recipe_create_exam.json    # Real 12-step ERP exam creation guide
│   └── recipe_student_sale.json   # Real 15-step sales workflow guide
└── .github/workflows/ci.yml   # Windows + Linux + macOS E2E 3-FPS CI
```

---

## 📜 License

MIT — see [LICENSE](LICENSE).
