"""
tool_executor.py — Thin wrapper that any agentic tool can shell-exec.
Accepts a JSON payload on stdin (or --args flag) and returns JSON on stdout.

Usage:
    echo '{"tool":"render_guide","recipe_json":"...","output_path":"out.mp4"}' | python tool_executor.py
    python tool_executor.py --args '{"tool":"validate_recipe","recipe_json":"..."}'
    python tool_executor.py --args '{"tool":"extract_frames","video_path":"vid.mp4","fps":3,"output_dir":"frames/"}'
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ── locate engine.py next to this file ────────────────────────────────────────
ENGINE = Path(__file__).parent / "engine.py"


def _uv_python() -> list[str]:
    """Return ['uv', 'run', '--with', '<deps>', 'python'] or plain ['python']."""
    deps = "opencv-python,pillow,imageio-ffmpeg,edge-tts,numpy"
    return ["uv", "run", "--with", deps, "python", str(ENGINE)]


def _run(cmd: list[str], timeout: int = 600) -> tuple[int, str, str]:
    """Run a subprocess, capture output."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


# ──────────────────────────────────────────────────────────────────────────────
# Tool implementations
# ──────────────────────────────────────────────────────────────────────────────

def validate_recipe(recipe_json: str | dict, **_) -> dict:
    """
    Run engine --plan_only on a recipe JSON string or dict.
    Returns {valid, warnings, plan_text, duration_s}.
    """
    if isinstance(recipe_json, dict):
        recipe_json = json.dumps(recipe_json, indent=2)

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                     encoding="utf-8", delete=False) as f:
        f.write(recipe_json)
        tmp = f.name

    try:
        cmd = _uv_python() + ["--recipe", tmp, "--plan_only"]
        rc, out, err = _run(cmd, timeout=120)
        warnings = [l for l in (out + err).splitlines() if "WARNING" in l or "OVERLAP" in l]
        return {
            "valid": rc == 0,
            "return_code": rc,
            "warnings": warnings,
            "plan_text": out or err,
        }
    finally:
        os.unlink(tmp)


def render_guide(recipe_json: str | dict, output_path: str,
                  export_srt: bool = True, **_) -> dict:
    """
    Full render: recipe → MP4 (+ optional SRT).
    Returns {mp4_path, srt_path, duration_s, size_mb}.
    """
    if isinstance(recipe_json, dict):
        recipe_json = json.dumps(recipe_json, indent=2)

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                     encoding="utf-8", delete=False) as f:
        f.write(recipe_json)
        tmp = f.name

    output_path = str(Path(output_path).resolve())
    try:
        cmd = _uv_python() + ["--recipe", tmp, "--output", output_path,
                               "--auto_proceed"]
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


def extract_frames(video_path: str, fps: float = 3.0,
                    output_dir: str | None = None, **_) -> dict:
    """
    Extract frames from a video at given FPS using bundled FFmpeg.
    Returns {frame_count, frames_dir}.
    """
    video_path = str(Path(video_path).resolve())
    if output_dir is None:
        stem = Path(video_path).stem.replace(" ", "_")
        output_dir = str(Path(video_path).parent / f"{stem}_frames")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    pattern = str(Path(output_dir) / "%04d_frame.png")

    # Use engine's extract path (--extract_frames flag)
    cmd = _uv_python() + [
        "--extract_frames", "--video", video_path,
        "--frames_dir", output_dir,
        "--fps", str(fps),
    ]
    rc, out, err = _run(cmd, timeout=600)
    if rc != 0:
        # Fallback: direct ffmpeg
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            ffmpeg = "ffmpeg"
        rc2, out2, err2 = _run(
            [ffmpeg, "-i", video_path, "-vf", f"fps={fps}", pattern], timeout=600
        )
        if rc2 != 0:
            return {"success": False, "error": err2}

    frames = sorted(Path(output_dir).glob("*_frame.png"))
    return {
        "success": True,
        "frames_dir": output_dir,
        "frame_count": len(frames),
        "fps_extracted": fps,
        "first_frame": str(frames[0]) if frames else None,
        "last_frame": str(frames[-1]) if frames else None,
    }


TOOLS = {
    "validate_recipe": validate_recipe,
    "render_guide": render_guide,
    "extract_frames": extract_frames,
}


def main():
    parser = argparse.ArgumentParser(description="Video Guide Skill Tool Executor")
    parser.add_argument("--args", help="JSON tool call arguments")
    args = parser.parse_args()

    if args.args:
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
            result = {"error": str(exc), "tool": tool_name}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
