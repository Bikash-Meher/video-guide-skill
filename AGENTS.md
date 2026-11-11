# AGENTS.md — Instructions for AI Coding Agents

This repository provides a **zero-manual-recipe Video Guide Skill**.

## How to handle a user request

When a user provides a screen recording path (e.g., `C:\recordings\app.mp4`) and asks for a user guide / tutorial video:

1. **First-time setup (if `.venv` does not exist yet):**
   ```bash
   python bootstrap.py
   ```
2. **Never ask the user for a recipe JSON, frame numbers, or FFmpeg commands.**
   - Accept just the video path (and any optional editing guide/flow notes, voice, or tone preference).
3. **Extract 3-FPS frames via FFmpeg & analyze ALL extracted frames first:**
   - Call `create_guide(video_path="...")` (via MCP tool or `tool_executor.py`).
   - E.g. for a 210s recording -> extracts ~630 frames @ 3 fps (`0001_frame.png`..`0630_frame.png`), scans every single frame, builds chronological segments, and saves labeled `storyboard_*.png` sheets.
4. **Inspect the storyboards & key frames before authoring `recipe.json`:**
   - Read ALL `storyboard_*.png` contact sheets so you understand the entire end-to-end flow.
   - Read key full-res `0NNN_frame.png` frames (or use `inspect_frame_slice`) to get exact UI text and `[x1, y1, x2, y2]` coordinates.
5. **Follow the Pre-Edit Plan & Voice/Tone Gate:**
   - Author the full `engine.py` `recipe.json` (see `SKILL.md` and `schemas/recipe.schema.json`).
   - Run `validate_recipe` (`--plan_only`) to verify TTS timings and dock placement.
   - Present the plan + Voice/Tone choice before calling `render_guide`, unless the user asked for `"auto proceed"`.
6. **Follow [SKILL.md](SKILL.md)** for full details and command examples.
