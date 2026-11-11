---
name: video-guide-maker
description: >-
  Turns any raw screen recording video (desktop app, website, web portal, SaaS, ERP)
  into a narrated, HUD-annotated MP4 user guide with synchronized SRT captions.
  The user ONLY supplies a video file path (plus optional editing flow notes or voice/tone
  preferences) — NEVER ask the user for a recipe JSON. Extracts 3 FPS frames via FFmpeg
  (e.g., ~630 frames for a 210s video), analyzes ALL frames first so the agent fully
  understands the workflow before editing, validates timing via --plan_only, and renders
  the final MP4 + SRT.
---

# Video Guide Maker Skill

Transform any raw screen recording into a polished, narrated, dynamically annotated user guide video (`.mp4` + `.srt`).

## Core Rules (Always Follow)

1. **Zero JSON / Zero Manual Prep from User:** The user only provides a recording path (e.g., `C:\recordings\demo.mp4` or a frames folder) and optional guide/flow notes. **You** extract frames, analyze the entire video, write the recipe JSON, validate timing, and render.
2. **Analyze ALL 3-FPS Frames Before Editing:** For example, a 210s recording yields **~630 frames @ 3 fps**. Extract every 3-fps frame via FFmpeg, scan all 630 frames, inspect **every generated Storyboard Contact Sheet** (`storyboard_*.png`), and inspect full-resolution `0NNN_frame.png` frames (or use `inspect_frame_slice`) before writing any recipe steps.
3. **Voice, Tone & Pre-Edit Plan Gate:** Before final rendering, run `validate_recipe` (`--plan_only`), present your editing plan (step count, duration, dock zones, narrations), and ask the user to confirm or choose **Voice** & **Tone** — **unless** the user explicitly ordered `"auto proceed"` (or `"just render"`).
4. **First-Run Auto-Setup:** If `.venv` is missing after cloning, run `python bootstrap.py` once (or run `tool_executor.py` directly, which auto-bootstraps).

---

## Step-by-Step Agent Workflow

### Stage 1 — Extract 3-FPS Frames & Analyze All Frames

Run `create_guide` (via MCP or CLI `tool_executor.py`):

```bash
# Via CLI / Codex / Cursor / Antigravity shell:
echo '{"tool":"create_guide","video_path":"<VIDEO_PATH>","user_flow_notes":"<OPTIONAL_NOTES>"}' | python tool_executor.py
```

This automatically:
1. Extracts `3 fps` frames (`0001_frame.png ... 0NNN_frame.png`, e.g., 630 frames for 210s) via bundled FFmpeg (`engine.py --extract_frames --fps_extracted 3`).
2. Scans **100% of extracted frames (`0 .. N-1`)** using both global diff and an `8×6` spatial block detector (so dropdowns, button clicks, checkboxes, and modals are never missed).
3. Emits:
   - `storyboard_01.png`, `storyboard_02.png`, ... — labeled contact sheets covering the entire video with `#frame`, timestamp, event tag (`PAGE_TRANSITION` / `UI_ACTION` / `IDLE_HOLD`), and cyan changed-region boxes.
   - `analysis_3fps.json` — full timeline segments + changed pixel bounding boxes `[x1, y1, x2, y2]` + `trim_candidate` idle holds.
   - `recipe_draft.json` — starter `engine.py` recipe schema.

---

### Stage 2 — Visually Inspect Storyboards & Key Frames (Mandatory)

1. Open and read **every** `storyboard_*.png` image listed in `storyboard_paths`.
2. Trace the user's complete journey from start to finish: note page loads, form fills, popups/modals, long dead pauses (`trim_candidate: true`), and any misclicks to cut out.
3. Open specific full-resolution `0NNN_frame.png` images from `frames_dir` for the steps you plan to highlight (and call `inspect_frame_slice` if an action happens quickly within a narrow frame range) so you can:
   - Read exact UI button/field/menu text.
   - Measure accurate `[x1, y1, x2, y2]` coordinates for `boxes`, `arrows`, `spotlight`, and `zoom`.

---

### Stage 3 — Author Final `recipe.json`

Save a clean `recipe.json` matching [schemas/recipe.schema.json](schemas/recipe.schema.json) (see real examples in [examples/recipe_create_exam.json](examples/recipe_create_exam.json)):

- **Required top-level fields:** `source_video`, `frames_dir`, `fps_extracted: 3.0`, `input_source: "auto"`, `branding_text`, `preset` (`tech_hud` | `clean_light` | `minimal` | `high_contrast`), `tone` (`friendly` | `professional` | `energetic` | `calm` | `corporate`), `default_voice`, `dock_mode: "auto"`, `total_duration: "auto"`, `audio_timing_mode: "auto_shift"`, `export_subtitles: true`.
  - *(Never set `"theme"` to a string — use `"preset"`.)*
- **`timeline_mapping`**: Map edited output segments cleanly to 3-FPS source frames (`start_sec`, `end_sec`, `source_frame_start_3fps`, `source_frame_end_3fps`) — skip boring pauses and speed through repetitive typing!
- **`steps`**: Synchronized entries (`id`, `start_time`, `active_start`, `active_end`, `step_num`, `step_title`, `narration`, `sub`, `boxes`, `arrows`, optional `spotlight` / `zoom`).
  - Keep `boxes[].label` off dense table headers where a pill could cover adjacent column labels.
  - Ensure `narration` fits comfortably in each step's `[active_start, active_end]` window.

---

### Stage 4 — Validate Plan & Confirm Voice/Tone

Run pre-flight validation (synthesizes Edge-TTS clips, checks `[AGENT:]` placeholders and overlaps, prints dynamic dock zones):

```bash
python tool_executor.py --args '{"tool":"validate_recipe","recipe_path":"<PATH_TO_RECIPE_JSON>"}'
```

**Voices:** `en-IN-NeerjaNeural` (IN Female), `en-IN-PrabhatNeural` (IN Male), `en-US-JennyNeural` (US Female), `en-US-GuyNeural` (US Male), `en-GB-SoniaNeural` (UK Female), `en-GB-RyanNeural` (UK Male).  
**Tones:** `friendly`, `professional`, `energetic`, `calm`, `corporate`.

- If any `[OVERLAP WARNING]` appears or `has_overlaps` is true, expand step windows / trim narration and re-validate until 0 overlaps.
- Unless user ordered auto-proceed, share the short Pre-Edit Plan and confirm Voice & Tone before rendering.

---

### Stage 5 — Render & Visually Verify Output

```bash
python tool_executor.py --args '{"tool":"render_guide","recipe_path":"<PATH_TO_RECIPE_JSON>","output_path":"<OUTPUT_MP4>","export_srt":true}'
```

Inspect 2–3 rendered frames via FFmpeg snapshot check to confirm boxes, arrows, branding pill, and HUD dock never collide with UI text, then deliver the `.mp4` and `.srt` paths.
