"""
tool_executor.py — Universal cross-agent tool dispatcher (JSON stdin / CLI / Python / MCP).

Designed so the END USER only needs to supply a screen recording video path
(plus optional editing flow notes or voice/tone preference — zero recipe JSON).
The AI agent handles extraction, full 3-FPS frame analysis, UI understanding,
recipe authoring, pre-flight validation, and rendering.

Tools
─────
  create_guide         MASTER START TOOL: given only `video_path` (and optional `user_flow_notes`),
                       extracts 3 FPS frames via FFmpeg (e.g., ~630 frames for 210s), analyzes ALL
                       extracted frames, creates labeled storyboard sheets + analysis_3fps.json +
                       starter engine.py recipe_draft.json.
  extract_frames       Extracts N-FPS PNG frames from video via bundled FFmpeg (`--fps_extracted`).
  analyze_frames       Scans ALL extracted frames, detects UI actions / transitions / idle holds,
                       computes changed pixel bounding boxes, and renders labeled storyboard sheets.
  inspect_frame_slice  Renders a dense storyboard strip for a narrow frame range [start..end].
  scaffold_recipe      Runs analyze_frames + generates an engine.py-compatible starter recipe.
  validate_recipe      Checks for unresolved [AGENT:] placeholders + runs engine.py --plan_only
                       (TTS duration & audio timing check + dynamic dock placement plan).
  render_guide         Renders final annotated MP4 + synchronized SRT captions via engine.py.

Usage
─────
    echo '{"tool":"create_guide","video_path":"C:/rec.mp4"}' | python tool_executor.py
    python tool_executor.py --args '{"tool":"validate_recipe","recipe_path":"recipe.json"}'
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
ENGINE = HERE / "engine.py"
VENV_PY = HERE / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


VOICE_CATALOG = [
    {"id": "en-IN-NeerjaNeural", "description": "Indian English Female (Warm, Articulate)"},
    {"id": "en-IN-PrabhatNeural", "description": "Indian English Male (Clear, Authoritative)"},
    {"id": "en-US-JennyNeural", "description": "US English Female (Friendly Corporate)"},
    {"id": "en-US-GuyNeural", "description": "US English Male (Confident Tutorial)"},
    {"id": "en-GB-SoniaNeural", "description": "UK English Female (Polished, Natural)"},
    {"id": "en-GB-RyanNeural", "description": "UK English Male (Crisp, Formal)"},
]

TONE_PRESETS = [
    {"id": "friendly", "description": "Approachable onboarding (+6% rate, +3Hz, tech_hud)"},
    {"id": "professional", "description": "Balanced tutorial pacing (+8% rate, tech_hud)"},
    {"id": "energetic", "description": "Upbeat walkthrough (+14% rate, +2Hz, tech_hud)"},
    {"id": "calm", "description": "Measured beginner pace (+0% rate, clean_light)"},
    {"id": "corporate", "description": "Formal enterprise guide (+5% rate, minimal HUD)"},
]


def _ensure_imports_path() -> None:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))


def _ensure_venv_if_needed() -> Path:
    """Guarantee a working Python executable with engine dependencies."""
    if VENV_PY.exists():
        return VENV_PY

    # Check if current interpreter already has required packages
    try:
        import cv2  # noqa: F401
        import imageio_ffmpeg  # noqa: F401
        import edge_tts  # noqa: F401
        from PIL import Image  # noqa: F401
        import numpy  # noqa: F401
        return Path(sys.executable)
    except ImportError:
        pass

    # Auto-run bootstrap.py seamlessly on first run
    bootstrap = HERE / "bootstrap.py"
    if bootstrap.exists():
        subprocess.run([sys.executable, str(bootstrap)], check=True, cwd=str(HERE))
        if VENV_PY.exists():
            return VENV_PY

    return Path(sys.executable)


def _engine_cmd() -> list[str]:
    """Return optimal command prefix to invoke engine.py."""
    if VENV_PY.exists():
        return [str(VENV_PY), "-u", str(ENGINE)]
    uv = shutil.which("uv")
    if uv:
        deps = "opencv-python,pillow,imageio-ffmpeg,edge-tts,numpy"
        return [uv, "run", "--with", deps, "python", "-u", str(ENGINE)]
    py = _ensure_venv_if_needed()
    return [str(py), "-u", str(ENGINE)]


def _run(cmd: list[str], timeout: int = 1800) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, encoding="utf-8", errors="replace")
    return result.returncode, result.stdout, result.stderr


def _resolve_recipe_file(recipe_json: str | dict | None, recipe_path: str | None) -> tuple[Path, dict, bool]:
    """
    Resolve recipe into an on-disk path + parsed dict.
    Returns (path, data, is_temp). Uses <frames_dir>/_work/ when possible so
    TTS audio_tracks/ are cached cleanly across validate -> render calls.
    """
    if recipe_path:
        p = Path(recipe_path).resolve()
        data = json.loads(p.read_text(encoding="utf-8"))
        return p, data, False

    if recipe_json is None:
        raise ValueError("Provide either 'recipe_path' or 'recipe_json'.")

    data = json.loads(recipe_json) if isinstance(recipe_json, str) else dict(recipe_json)

    frames_dir = data.get("frames_dir")
    if frames_dir and Path(frames_dir).exists():
        work_dir = Path(frames_dir).resolve() / "_work"
        work_dir.mkdir(parents=True, exist_ok=True)
        out_p = work_dir / "recipe_active.json"
        out_p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return out_p, data, False

    tmp = tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False)
    tmp.write(json.dumps(data, indent=2))
    tmp.close()
    return Path(tmp.name), data, True


# ──────────────────────────────────────────────────────────────────────────────
# Tool 1: extract_frames
# ──────────────────────────────────────────────────────────────────────────────

def extract_frames(
    video_path: str,
    fps: float = 3.0,
    output_dir: str | None = None,
    force: bool = False,
    **_,
) -> dict:
    """
    Extract all frames at `fps` (default 3.0 = 3 images/sec, e.g. ~630 frames for 210s)
    using engine.py's bundled FFmpeg extractor. Reuses existing frames unless force=True.
    """
    vpath = Path(video_path).resolve()
    if not vpath.exists():
        return {"success": False, "error": f"Video file not found: {vpath}"}

    if output_dir is None:
        stem = vpath.stem.replace(" ", "_")
        output_dir = str(vpath.parent / f"{stem}_frames")

    frames_dir = Path(output_dir).resolve()
    frames_dir.mkdir(parents=True, exist_ok=True)

    cmd = _engine_cmd() + [
        "--extract_frames",
        "--video", str(vpath),
        "--frames_dir", str(frames_dir),
        "--fps_extracted", str(fps),
        "--analyze",
    ]
    if force:
        cmd.append("--force_extract")

    rc, out, err = _run(cmd, timeout=900)
    if rc != 0:
        return {"success": False, "error": err or out, "return_code": rc}

    _ensure_imports_path()
    try:
        from auto_recipe import get_sorted_frames
        frames = get_sorted_frames(frames_dir)
    except Exception:
        frames = sorted(frames_dir.glob("*.png"))

    est_dur = round(len(frames) / float(fps or 3.0), 2)
    return {
        "success": True,
        "video_path": str(vpath),
        "frames_dir": str(frames_dir),
        "frame_count": len(frames),
        "fps_extracted": float(fps),
        "estimated_duration_sec": est_dur,
        "first_frame": str(frames[0]) if frames else None,
        "last_frame": str(frames[-1]) if frames else None,
        "engine_log": out[-1500:] if out else "",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tool 2: analyze_frames
# ──────────────────────────────────────────────────────────────────────────────

def analyze_frames(
    frames_dir: str,
    video_path: str | None = None,
    fps: float = 3.0,
    page_threshold: float = 0.055,
    ui_threshold: float = 0.095,
    min_idle_sec: float = 2.0,
    **_,
) -> dict:
    """
    Scan ALL extracted 3-FPS frames (`0 .. N-1`), build chronological timeline segments,
    compute changed bounding boxes [x1, y1, x2, y2], identify idle pauses to trim,
    and render labeled Storyboard Contact Sheets covering the entire recording.
    """
    _ensure_imports_path()
    _ensure_venv_if_needed()

    # Execute inside .venv if current Python lacks cv2/PIL/numpy
    try:
        from auto_recipe import analyze_video_frames
        result = analyze_video_frames(
            frames_dir=frames_dir,
            video_path=video_path,
            fps=float(fps),
            page_threshold=float(page_threshold),
            ui_threshold=float(ui_threshold),
            min_idle_sec=float(min_idle_sec),
        )
    except ImportError:
        py = _ensure_venv_if_needed()
        snippet = (
            "import json, sys; sys.path.insert(0, '.'); "
            "from auto_recipe import analyze_video_frames; "
            f"res = analyze_video_frames({frames_dir!r}, video_path={video_path!r}, fps={float(fps)!r}, "
            f"page_threshold={float(page_threshold)!r}, ui_threshold={float(ui_threshold)!r}, min_idle_sec={float(min_idle_sec)!r}); "
            "print(json.dumps(res))"
        )
        rc, out, err = _run([str(py), "-c", snippet], timeout=600)
        if rc != 0:
            return {"success": False, "error": err or out}
        result = json.loads(out)

    if "error" in result:
        return {"success": False, **result}

    segments_summary = [
        {
            "seg": s["segment_index"],
            "type": s["type"],
            "frames_3fps": f"{s['start_frame_3fps']}..{s['end_frame_3fps']}",
            "time": f"{s['start_sec']:.1f}s..{s['end_sec']:.1f}s ({s['duration_sec']:.1f}s)",
            "key_frame_file": s["key_frame_file"],
            "changed_bbox": s["changed_region_px"],
            "trim_candidate": s["trim_candidate"],
        }
        for s in result["segments"]
    ]

    return {
        "success": True,
        "frames_dir": result["frames_dir"],
        "fps_extracted": result["fps_extracted"],
        "total_frames_analyzed": result["total_frames_analyzed"],
        "duration_sec": result["duration_sec"],
        "resolution": result["resolution"],
        "segment_count": result["segment_count"],
        "storyboard_count": result["storyboard_count"],
        "storyboard_paths": result["storyboard_paths"],
        "analysis_json_path": result["analysis_json_path"],
        "segments_summary": segments_summary,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tool 3: inspect_frame_slice
# ──────────────────────────────────────────────────────────────────────────────

def inspect_frame_slice(
    frames_dir: str,
    start_frame: int,
    end_frame: int,
    fps: float = 3.0,
    stride: int = 1,
    **_,
) -> dict:
    """
    Generate a zoomed contact sheet for every consecutive frame in [start_frame..end_frame]
    (0-based 3 FPS indices) so the agent can inspect rapid UI interactions cleanly.
    """
    _ensure_imports_path()
    try:
        from auto_recipe import render_frame_slice
        return render_frame_slice(frames_dir, int(start_frame), int(end_frame), fps=float(fps), stride=int(stride))
    except ImportError:
        py = _ensure_venv_if_needed()
        cmd = [
            str(py), str(HERE / "auto_recipe.py"),
            "--frames_dir", str(frames_dir),
            "--fps", str(fps),
            "--slice", str(int(start_frame)), str(int(end_frame)),
        ]
        rc, out, err = _run(cmd, timeout=300)
        if rc != 0:
            return {"success": False, "error": err or out}
        return json.loads(out)


# ──────────────────────────────────────────────────────────────────────────────
# Tool 4: scaffold_recipe
# ──────────────────────────────────────────────────────────────────────────────

def scaffold_recipe(
    frames_dir: str,
    video_path: str | None = None,
    fps: float = 3.0,
    voice: str = "en-IN-NeerjaNeural",
    tone: str = "friendly",
    app_name: str = "Application",
    user_flow_notes: str = "",
    page_threshold: float = 0.055,
    ui_threshold: float = 0.095,
    **_,
) -> dict:
    """
    Analyze ALL 3-FPS frames and generate an engine.py-compatible starter recipe.json
    (with `timeline_mapping` + `steps`) plus Storyboard Contact Sheets.
    """
    _ensure_imports_path()
    try:
        from auto_recipe import scaffold_recipe as _scaffold
        result = _scaffold(
            frames_dir=frames_dir,
            video_path=video_path,
            fps=float(fps),
            page_threshold=float(page_threshold),
            ui_threshold=float(ui_threshold),
            voice=voice,
            tone=tone,
            app_name=app_name,
            user_flow_notes=user_flow_notes,
        )
    except ImportError:
        py = _ensure_venv_if_needed()
        snippet = (
            "import json, sys; sys.path.insert(0, '.'); "
            "from auto_recipe import scaffold_recipe; "
            f"res = scaffold_recipe({frames_dir!r}, video_path={video_path!r}, fps={float(fps)!r}, "
            f"page_threshold={float(page_threshold)!r}, ui_threshold={float(ui_threshold)!r}, "
            f"voice={voice!r}, tone={tone!r}, app_name={app_name!r}, user_flow_notes={user_flow_notes!r}); "
            "print(json.dumps(res))"
        )
        rc, out, err = _run([str(py), "-c", snippet], timeout=600)
        if rc != 0:
            return {"success": False, "error": err or out}
        result = json.loads(out)

    if "error" in result:
        return {"success": False, **result}

    segments_summary = [
        {
            "seg": s["segment_index"],
            "type": s["type"],
            "frames_3fps": f"{s['start_frame_3fps']}..{s['end_frame_3fps']}",
            "time": f"{s['start_sec']:.1f}s..{s['end_sec']:.1f}s ({s['duration_sec']:.1f}s)",
            "key_frame_file": s["key_frame_file"],
            "changed_bbox": s["changed_region_px"],
            "trim_candidate": s["trim_candidate"],
        }
        for s in result["segments"]
    ]

    return {
        "success": True,
        "draft_recipe_path": result["draft_recipe_path"],
        "analysis_json_path": result["analysis_json_path"],
        "storyboard_paths": result["storyboard_paths"],
        "total_frames_analyzed": result["total_frames_analyzed"],
        "duration_sec": result["duration_sec"],
        "resolution": result["resolution"],
        "step_count": result["step_count"],
        "segment_count": result["segment_count"],
        "segments_summary": segments_summary,
        "recipe_json": json.dumps(result["recipe"], indent=2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tool 5: validate_recipe
# ──────────────────────────────────────────────────────────────────────────────

def validate_recipe(recipe_json: str | dict | None = None, recipe_path: str | None = None, **_) -> dict:
    """
    Validate recipe completeness + run engine.py --plan_only (TTS + dock + timing checks).
    Rejects recipes that still contain unfinished [AGENT: ...] placeholders.
    """
    path, data, is_temp = _resolve_recipe_file(recipe_json, recipe_path)
    try:
        # 1. Schema / completeness validation before calling engine.py
        errors = []
        if not data.get("timeline_mapping"):
            errors.append("Missing non-empty 'timeline_mapping' list.")
        if not data.get("steps"):
            errors.append("Missing non-empty 'steps' list (engine.py requires 'steps' for HUD overlays & narration).")
        if isinstance(data.get("theme"), str):
            errors.append("'theme' must be a dict of color overrides (or omit it and use 'preset': 'tech_hud').")

        unresolved = []
        for st in data.get("steps", []):
            sid = st.get("id", "?")
            for field in ("step_title", "narration", "sub"):
                val = str(st.get(field, ""))
                if "[AGENT:" in val:
                    unresolved.append(f"{sid}.{field}")
        if unresolved:
            errors.append(
                f"Unresolved placeholder text in steps: {', '.join(unresolved)}. "
                "Inspect the storyboard & keyframe PNGs and replace all [AGENT:...] placeholders before validating."
            )

        if errors:
            return {"valid": False, "errors": errors, "warnings": [], "plan_text": ""}

        # 2. Run engine.py --plan_only
        cmd = _engine_cmd() + ["--recipe", str(path), "--plan_only"]
        rc, out, err = _run(cmd, timeout=300)
        combined = (out or "") + ("\n" + err if err else "")
        warnings = [line for line in combined.splitlines() if "WARNING" in line or "OVERLAP" in line]
        return {
            "valid": (rc == 0),
            "return_code": rc,
            "recipe_path": str(path) if not is_temp else None,
            "warnings": warnings,
            "has_overlaps": any("OVERLAP" in w for w in warnings),
            "plan_text": out or err,
        }
    finally:
        if is_temp and path.exists():
            try:
                path.unlink()
            except OSError:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Tool 6: render_guide
# ──────────────────────────────────────────────────────────────────────────────

def render_guide(
    output_path: str,
    recipe_json: str | dict | None = None,
    recipe_path: str | None = None,
    export_srt: bool = True,
    voice: str | None = None,
    tone: str | None = None,
    **_,
) -> dict:
    """
    Full render: completed recipe.json -> narrated, HUD-annotated MP4 + SRT captions.
    """
    precheck = validate_recipe(recipe_json=recipe_json, recipe_path=recipe_path)
    if not precheck.get("valid"):
        return {
            "success": False,
            "stage": "validation_failed",
            "errors": precheck.get("errors", []),
            "warnings": precheck.get("warnings", []),
            "plan_text": precheck.get("plan_text", ""),
        }

    path, _, is_temp = _resolve_recipe_file(recipe_json, recipe_path)
    out_mp4 = Path(output_path).resolve()
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    try:
        cmd = _engine_cmd() + [
            "--recipe", str(path),
            "--output", str(out_mp4),
            "--auto_proceed",
        ]
        if export_srt:
            cmd.append("--export_srt")
        if voice:
            cmd.extend(["--voice", voice])
        if tone:
            cmd.extend(["--tone", tone])

        t0 = time.time()
        rc, out, err = _run(cmd, timeout=3600)
        elapsed = round(time.time() - t0, 1)

        if rc != 0 or not out_mp4.exists():
            return {"success": False, "error": err or out, "return_code": rc}

        srt_file = out_mp4.with_suffix(".srt")
        size_mb = round(out_mp4.stat().st_size / 1_048_576, 2)
        return {
            "success": True,
            "mp4_path": str(out_mp4),
            "srt_path": str(srt_file) if srt_file.exists() else None,
            "size_mb": size_mb,
            "render_time_s": elapsed,
            "stdout": out[-3000:] if out else "",
        }
    finally:
        if is_temp and path.exists():
            try:
                path.unlink()
            except OSError:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Master Pipeline Tool: create_guide
# ──────────────────────────────────────────────────────────────────────────────

def create_guide(
    video_path: str,
    output_path: str | None = None,
    user_flow_notes: str = "",
    fps: float = 3.0,
    voice: str = "en-IN-NeerjaNeural",
    tone: str = "friendly",
    app_name: str | None = None,
    page_threshold: float = 0.055,
    ui_threshold: float = 0.095,
    **_,
) -> dict:
    """
    MASTER START TOOL — user only uploads `video_path` (plus optional flow notes).

    Runs:
      1. FFmpeg 3-FPS extraction (`extract_frames`): extracts ALL frames (e.g., 630 frames for 210s)
      2. Full-sequence analysis (`scaffold_recipe` -> `analyze_video_frames`): inspects EVERY extracted
         frame, segments pages / UI actions / idle pauses, detects active screen regions [x1,y1,x2,y2],
         and renders labeled Storyboard Contact Sheets + starter valid engine.py `recipe_draft.json`.

    Returns storyboard sheet image paths + analysis JSON + starter recipe so the AI agent can
    visually inspect ALL frames across the storyboards, understand the entire workflow BEFORE
    editing, author clean narrations & exact UI highlight boxes/arrows/zooms, run `validate_recipe`
    (pre-edit plan & voice/tone confirmation), and call `render_guide`.
    """
    vpath = Path(video_path).resolve()
    if not vpath.exists():
        return {"success": False, "error": f"Source video not found: {vpath}"}

    if not output_path:
        safe_stem = vpath.stem.replace(" ", "_")
        output_path = str(vpath.parent / f"{safe_stem}_User_Guide.mp4")

    if not app_name:
        app_name = vpath.stem.replace("_", " ").replace("-", " ").strip().title()

    ext_res = extract_frames(video_path=str(vpath), fps=fps)
    if not ext_res.get("success"):
        return {"success": False, "stage": "extract_frames", **ext_res}

    frames_dir = ext_res["frames_dir"]
    scaf_res = scaffold_recipe(
        frames_dir=frames_dir,
        video_path=str(vpath),
        fps=fps,
        voice=voice,
        tone=tone,
        app_name=app_name,
        user_flow_notes=user_flow_notes,
        page_threshold=page_threshold,
        ui_threshold=ui_threshold,
    )
    if not scaf_res.get("success"):
        return {"success": False, "stage": "analyze_frames", **scaf_res}

    return {
        "success": True,
        "stage": "awaiting_agent_understanding_and_recipe",
        "video_path": str(vpath),
        "frames_dir": frames_dir,
        "fps_extracted": float(fps),
        "total_frames_analyzed": scaf_res["total_frames_analyzed"],
        "duration_sec": scaf_res["duration_sec"],
        "resolution": scaf_res["resolution"],
        "segment_count": scaf_res["segment_count"],
        "step_count": scaf_res["step_count"],
        "storyboard_paths": scaf_res["storyboard_paths"],
        "analysis_json_path": scaf_res["analysis_json_path"],
        "draft_recipe_path": scaf_res["draft_recipe_path"],
        "suggested_output_path": str(Path(output_path).resolve()),
        "user_flow_notes": user_flow_notes,
        "segments_summary": scaf_res["segments_summary"],
        "available_voices": VOICE_CATALOG,
        "available_tones": TONE_PRESETS,
        "agent_workflow": [
            f"1. UNDERSTAND ALL {scaf_res['total_frames_analyzed']} FRAMES FIRST: Open and visually inspect EVERY image in 'storyboard_paths' (plus read full-res frames in 'frames_dir' or call 'inspect_frame_slice' on busy actions) to understand the complete UI flow from start to end.",
            "2. AUTHOR COMPLETE RECIPE: Edit 'draft_recipe_path' (or save a new recipe.json). Trim idle pauses in 'timeline_mapping', refine step timings, write clear human 'step_title' / 'narration' / 'sub', and set accurate pixel/normalized 'boxes', 'arrows', 'spotlight', and 'zoom'.",
            "3. VOICE, TONE & PRE-EDIT PLAN: Run 'validate_recipe' (`--plan_only`). Unless the user explicitly ordered auto-proceed, ask user to confirm/pick Voice & Tone and show the Pre-Edit Plan before rendering.",
            "4. RENDER: Call 'render_guide' with the final recipe and 'suggested_output_path' to produce the MP4 + SRT captions.",
        ],
    }


TOOLS = {
    "create_guide": create_guide,
    "extract_frames": extract_frames,
    "analyze_frames": analyze_frames,
    "inspect_frame_slice": inspect_frame_slice,
    "scaffold_recipe": scaffold_recipe,
    "validate_recipe": validate_recipe,
    "render_guide": render_guide,
}


def main():
    parser = argparse.ArgumentParser(description="Video Guide Skill Tool Executor")
    parser.add_argument("--args", help="JSON tool call arguments")
    parser.add_argument("--args-file", help="Path to JSON file containing tool call arguments")
    args = parser.parse_args()

    if args.args_file:
        payload = json.loads(Path(args.args_file).read_text(encoding="utf-8"))
    elif args.args:
        payload = json.loads(args.args)
    else:
        payload = json.load(sys.stdin)
    tool_name = payload.pop("tool", None)

    if tool_name not in TOOLS:
        result = {"error": f"Unknown tool: {tool_name!r}. Available: {list(TOOLS)}"}
    else:
        try:
            result = TOOLS[tool_name](**payload)
        except Exception as exc:
            import traceback
            result = {"error": str(exc), "traceback": traceback.format_exc(), "tool": tool_name}

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
