"""
tool_executor.py — Thin wrapper that any agentic tool can shell-exec or import.
Accepts a JSON payload on stdin (or --args flag) and returns JSON on stdout.

Tools
─────
  extract_frames    Video → PNG frames at N fps
  scaffold_recipe   Frames → auto-detected scene cuts → draft recipe JSON
                    (agent must inspect returned scene_frames and fill narrations)
  validate_recipe   Recipe JSON → plan-only TTS+timing check
  render_guide      Recipe JSON → final MP4 + SRT
  create_guide      ONE-CALL PIPELINE: video_path → MP4
                    Extracts frames, scaffolds recipe, returns frames for agent
                    to fill narrations, then validates + renders.
                    Designed so the agent only needs: video_path + output_path.

Usage
─────
    # stdin JSON
    echo '{"tool":"create_guide","video_path":"C:/rec.mp4","output_path":"C:/out.mp4"}' | python tool_executor.py

    # --args flag
    python tool_executor.py --args '{"tool":"scaffold_recipe","frames_dir":"C:/frames"}'

    # import
    from tool_executor import create_guide
    result = create_guide(video_path="C:/rec.mp4", output_path="C:/out.mp4")
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENGINE = Path(__file__).parent / "engine.py"
AUTO_RECIPE = Path(__file__).parent / "auto_recipe.py"


def _uv_engine() -> list[str]:
    deps = "opencv-python,pillow,imageio-ffmpeg,edge-tts,numpy"
    return ["uv", "run", "--with", deps, "python", str(ENGINE)]


def _run(cmd: list[str], timeout: int = 1800) -> tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def _read_frame_b64(path: str, max_size: int = 320) -> str | None:
    """Return a tiny base64 JPEG thumbnail so agents with vision can inspect frames."""
    try:
        import cv2
        img = cv2.imread(path)
        if img is None:
            return None
        h, w = img.shape[:2]
        scale = max_size / max(h, w)
        thumb = cv2.resize(img, (int(w * scale), int(h * scale)))
        import tempfile, base64
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            cv2.imwrite(f.name, thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
            data = base64.b64encode(Path(f.name).read_bytes()).decode()
        os.unlink(f.name)
        return data
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Tool: extract_frames
# ──────────────────────────────────────────────────────────────────────────────

def extract_frames(video_path: str, fps: float = 3.0,
                   output_dir: str | None = None, **_) -> dict:
    """Extract frames from a video at given FPS using bundled FFmpeg."""
    video_path = str(Path(video_path).resolve())
    if output_dir is None:
        stem = Path(video_path).stem.replace(" ", "_")
        output_dir = str(Path(video_path).parent / f"{stem}_frames")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    pattern = str(Path(output_dir) / "%04d_frame.png")

    # Try engine's built-in extract path first
    cmd = _uv_engine() + ["--extract_frames", "--video", video_path,
                          "--frames_dir", output_dir, "--fps", str(fps)]
    rc, out, err = _run(cmd, timeout=600)

    if rc != 0:
        # Fallback: direct imageio-ffmpeg
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            ffmpeg = "ffmpeg"
        rc2, out2, err2 = _run(
            [ffmpeg, "-i", video_path, "-vf", f"fps={fps}", pattern], 600
        )
        if rc2 != 0:
            return {"success": False, "error": err2 or err}

    frames = sorted(Path(output_dir).glob("*_frame.png"))
    return {
        "success": True,
        "frames_dir": output_dir,
        "frame_count": len(frames),
        "fps_extracted": fps,
        "first_frame": str(frames[0]) if frames else None,
        "last_frame": str(frames[-1]) if frames else None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tool: scaffold_recipe
# ──────────────────────────────────────────────────────────────────────────────

def scaffold_recipe(
    frames_dir: str,
    video_path: str | None = None,
    fps: float = 3.0,
    sensitivity: float = 0.18,
    voice: str = "en-IN-NeerjaNeural",
    tone: str = "friendly",
    app_name: str = "Application",
    include_thumbnails: bool = True,
    **_,
) -> dict:
    """
    Auto-detect scene cuts → draft recipe JSON.
    Returns:
      recipe_json   — string ready for validate_recipe / render_guide
                      (contains [AGENT:...] placeholder narrations)
      scene_frames  — list of frame file paths for the agent to inspect visually
      thumbnails    — list of base64 JPEG thumbnails (if include_thumbnails=True)
      step_count    — number of detected scenes/steps
      instructions  — what the agent must do next
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from auto_recipe import scaffold_recipe as _scaffold

    result = _scaffold(
        frames_dir=frames_dir,
        video_path=video_path,
        fps=fps,
        sensitivity=sensitivity,
        voice=voice,
        tone=tone,
        app_name=app_name,
    )

    if "error" in result:
        return {"success": False, **result}

    recipe = result["recipe"]
    scene_frames: list[str] = result["scene_frames"]

    thumbnails: list[dict] = []
    if include_thumbnails:
        for i, fp in enumerate(scene_frames):
            b64 = _read_frame_b64(fp)
            thumbnails.append({
                "step": i + 1,
                "frame_path": fp,
                "thumbnail_base64_jpg": b64,  # None if cv2 not available
            })

    return {
        "success": True,
        "recipe_json": json.dumps(recipe, indent=2),
        "scene_frames": scene_frames,
        "thumbnails": thumbnails,
        "step_count": result["step_count"],
        "total_duration_s": result["total_duration_s"],
        "total_frames_scanned": result["total_frames_scanned"],
        "instructions": (
            "AGENT ACTION REQUIRED:\n"
            "1. Inspect each frame in scene_frames (or thumbnails) using your vision capability.\n"
            "2. For each step in recipe_json, replace the [AGENT:...] narration with a "
            "   real description of what the user should do or see at that step.\n"
            "3. Optionally add highlight_boxes coordinates for important UI elements.\n"
            "4. Call validate_recipe(recipe_json=<updated_json>) to check timing.\n"
            "5. Call render_guide(recipe_json=<updated_json>, output_path=<mp4_path>) to render."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tool: validate_recipe
# ──────────────────────────────────────────────────────────────────────────────

def validate_recipe(recipe_json: str | dict, **_) -> dict:
    """Run engine --plan_only. Returns {valid, warnings, plan_text}."""
    if isinstance(recipe_json, dict):
        recipe_json = json.dumps(recipe_json, indent=2)

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                     encoding="utf-8", delete=False) as f:
        f.write(recipe_json)
        tmp = f.name
    try:
        cmd = _uv_engine() + ["--recipe", tmp, "--plan_only"]
        rc, out, err = _run(cmd, timeout=120)
        warnings = [l for l in (out + err).splitlines()
                    if "WARNING" in l or "OVERLAP" in l]
        return {
            "valid": rc == 0,
            "return_code": rc,
            "warnings": warnings,
            "plan_text": out or err,
        }
    finally:
        os.unlink(tmp)


# ──────────────────────────────────────────────────────────────────────────────
# Tool: render_guide
# ──────────────────────────────────────────────────────────────────────────────

def render_guide(recipe_json: str | dict, output_path: str,
                 export_srt: bool = True, **_) -> dict:
    """Full render: recipe → MP4 (+ optional SRT)."""
    if isinstance(recipe_json, dict):
        recipe_json = json.dumps(recipe_json, indent=2)

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                     encoding="utf-8", delete=False) as f:
        f.write(recipe_json)
        tmp = f.name

    output_path = str(Path(output_path).resolve())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        cmd = _uv_engine() + ["--recipe", tmp, "--output", output_path, "--auto_proceed"]
        if export_srt:
            cmd.append("--export_srt")
        t0 = time.time()
        rc, out, err = _run(cmd, timeout=1800)
        elapsed = round(time.time() - t0, 1)

        if rc != 0:
            return {"success": False, "error": err or out, "return_code": rc}

        mp4 = Path(output_path)
        srt = mp4.with_suffix(".srt")
        size_mb = round(mp4.stat().st_size / 1_048_576, 2) if mp4.exists() else 0
        return {
            "success": True,
            "mp4_path": str(mp4),
            "srt_path": str(srt) if srt.exists() else None,
            "size_mb": size_mb,
            "render_time_s": elapsed,
            "stdout": out[-3000:] if out else "",
        }
    finally:
        os.unlink(tmp)


# ──────────────────────────────────────────────────────────────────────────────
# Tool: create_guide  ← THE MASTER ONE-CALL PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def create_guide(
    video_path: str,
    output_path: str,
    fps: float = 3.0,
    voice: str = "en-IN-NeerjaNeural",
    tone: str = "friendly",
    app_name: str | None = None,
    sensitivity: float = 0.18,
    export_srt: bool = True,
    **_,
) -> dict:
    """
    MASTER PIPELINE — agent needs only video_path + output_path.

    Internally:
      Step A: extract_frames(video_path, fps)
      Step B: scaffold_recipe(frames_dir)   → draft recipe + scene thumbnails
      Step C: [returns to agent]            ← agent fills narrations via vision
      Step D: validate_recipe(filled_recipe)
      Step E: render_guide(filled_recipe, output_path)

    Because step C requires the agent's vision to inspect frames, this tool
    returns after step B with the draft recipe and thumbnails.
    The agent must:
      1. View the returned scene_frames / thumbnails
      2. Fill in narrations in recipe_json
      3. Call validate_recipe + render_guide  (or call create_guide_render)
    """
    video_path = str(Path(video_path).resolve())
    app_name = app_name or Path(video_path).stem.replace("_", " ").replace("-", " ").title()

    # ── A: Extract frames ────────────────────────────────────────────────────
    extract_result = extract_frames(video_path=video_path, fps=fps)
    if not extract_result.get("success"):
        return {"success": False, "stage": "extract_frames",
                "error": extract_result.get("error")}

    frames_dir = extract_result["frames_dir"]
    frame_count = extract_result["frame_count"]

    # ── B: Scaffold recipe ───────────────────────────────────────────────────
    scaffold_result = scaffold_recipe(
        frames_dir=frames_dir,
        video_path=video_path,
        fps=fps,
        sensitivity=sensitivity,
        voice=voice,
        tone=tone,
        app_name=app_name,
        include_thumbnails=True,
    )
    if not scaffold_result.get("success"):
        return {"success": False, "stage": "scaffold_recipe",
                "error": scaffold_result.get("error")}

    return {
        "success": True,
        "stage": "awaiting_agent_narrations",
        "frames_dir": frames_dir,
        "frame_count": frame_count,
        "step_count": scaffold_result["step_count"],
        "total_duration_s": scaffold_result["total_duration_s"],
        # Draft recipe — agent MUST replace [AGENT:...] narrations
        "recipe_json": scaffold_result["recipe_json"],
        # Thumbnails for agent vision inspection
        "scene_frames": scaffold_result["scene_frames"],
        "thumbnails": scaffold_result["thumbnails"],
        # Pre-filled output path for the agent to use in next call
        "suggested_output_path": output_path,
        "next_steps": [
            "1. View each thumbnail (or open scene_frames paths) with your vision capability.",
            "2. For each step in recipe_json, replace [AGENT:...] narration with real descriptive text.",
            "3. Optionally add highlight_boxes: [{x,y,w,h,color,label}] for key UI elements.",
            "4. Call validate_recipe(recipe_json=<updated>) — fix any OVERLAP warnings.",
            "5. Call render_guide(recipe_json=<updated>, output_path=suggested_output_path).",
        ],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────────────

TOOLS = {
    "extract_frames": extract_frames,
    "scaffold_recipe": scaffold_recipe,
    "validate_recipe": validate_recipe,
    "render_guide": render_guide,
    "create_guide": create_guide,
}


def main():
    parser = argparse.ArgumentParser(description="Video Guide Skill Tool Executor")
    parser.add_argument("--args", help="JSON tool call arguments")
    args = parser.parse_args()

    payload = json.loads(args.args) if args.args else json.load(sys.stdin)
    tool_name = payload.pop("tool", None)

    if tool_name not in TOOLS:
        result = {"error": f"Unknown tool: {tool_name!r}. Available: {list(TOOLS)}"}
    else:
        try:
            result = TOOLS[tool_name](**payload)
        except Exception as exc:
            import traceback
            result = {"error": str(exc), "traceback": traceback.format_exc(), "tool": tool_name}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
