"""
auto_recipe.py — Fully automatic recipe scaffolder.

Given extracted frames, detects UI scene transitions via histogram diff
and pixel-change thresholds, then emits a draft recipe.json with:
  - representative frame per detected scene
  - placeholder narration (agent fills this in via vision)
  - estimated timing from frame indices
  - highlight_boxes: empty list (agent fills via vision)

Usage:
    python auto_recipe.py --frames_dir frames/ --video_path rec.mp4 \
                          --out recipe_draft.json [--fps 3] [--sensitivity 0.18]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np


# ──────────────────────────────────────────────────────────────────────────────
# Scene detection
# ──────────────────────────────────────────────────────────────────────────────

def _histogram_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Return normalised histogram distance [0..1] between two BGR frames."""
    score = 0.0
    for ch in range(3):
        ha = cv2.calcHist([a], [ch], None, [64], [0, 256])
        hb = cv2.calcHist([b], [ch], None, [64], [0, 256])
        cv2.normalize(ha, ha)
        cv2.normalize(hb, hb)
        score += cv2.compareHist(ha, hb, cv2.HISTCMP_BHATTACHARYYA)
    return score / 3.0


def detect_scenes(frame_paths: list[Path], sensitivity: float = 0.18,
                  min_gap: int = 3) -> list[int]:
    """
    Return list of frame indices where a scene cut is detected.
    Always includes index 0 (first scene).
    sensitivity: Bhattacharyya distance threshold [0..1]; lower = more sensitive.
    min_gap: minimum frames between consecutive cuts.
    """
    cuts = [0]
    prev = cv2.imread(str(frame_paths[0]))
    if prev is None:
        return cuts

    last_cut = 0
    for i, fp in enumerate(frame_paths[1:], start=1):
        curr = cv2.imread(str(fp))
        if curr is None:
            continue
        # Resize to small thumbnail for speed
        a = cv2.resize(prev, (160, 90))
        b = cv2.resize(curr, (160, 90))
        diff = _histogram_diff(a, b)
        if diff > sensitivity and (i - last_cut) >= min_gap:
            cuts.append(i)
            last_cut = i
        prev = curr

    return cuts


# ──────────────────────────────────────────────────────────────────────────────
# Recipe scaffolding
# ──────────────────────────────────────────────────────────────────────────────

def scaffold_recipe(
    frames_dir: str,
    video_path: str | None = None,
    output_path: str | None = None,
    fps: float = 3.0,
    sensitivity: float = 0.18,
    voice: str = "en-IN-NeerjaNeural",
    tone: str = "friendly",
    output_resolution: dict | None = None,
    min_step_duration: float = 5.0,
    app_name: str = "Application",
) -> dict:
    """
    Auto-detect scene cuts in a frames folder and emit a draft recipe dict.

    Returns a dict with:
      - recipe: the draft recipe JSON (ready to serialise)
      - scene_frames: list of representative frame paths (agent should view these)
      - step_count: number of detected steps
      - message: human-readable summary
    """
    frames_dir = Path(frames_dir)
    frame_paths = sorted(frames_dir.glob("*_frame.png"))
    if not frame_paths:
        return {"error": f"No *_frame.png files found in {frames_dir}"}

    total_frames = len(frame_paths)

    # Detect scene cuts
    cut_indices = detect_scenes(frame_paths, sensitivity=sensitivity)

    # Merge cuts that are too close to produce enough step duration
    min_frames = max(1, int(min_step_duration * fps))
    merged: list[int] = [cut_indices[0]]
    for idx in cut_indices[1:]:
        if idx - merged[-1] >= min_frames:
            merged.append(idx)
    cut_indices = merged

    # Determine output resolution from first frame if not given
    if output_resolution is None:
        first = cv2.imread(str(frame_paths[0]))
        if first is not None:
            h, w = first.shape[:2]
            output_resolution = {"width": w, "height": h}
        else:
            output_resolution = {"width": 1920, "height": 1080}

    # Build timeline_mapping
    steps: list[dict] = []
    for step_num, (start_idx, end_idx) in enumerate(
        zip(cut_indices, cut_indices[1:] + [total_frames - 1]), start=1
    ):
        t_start = round(start_idx / fps, 2)
        t_end   = round(min(end_idx / fps, (start_idx + 60) / fps), 2)
        # Ensure minimum window
        if t_end - t_start < min_step_duration:
            t_end = round(t_start + min_step_duration, 2)

        rep_frame = frame_paths[start_idx]

        steps.append({
            "step": step_num,
            "label": f"Step {step_num}",
            "active_start": t_start,
            "active_end": t_end,
            "source_frame": str(rep_frame),
            "source_frame_start_3fps": start_idx + 1,  # 1-based
            "source_frame_end_3fps": end_idx + 1,
            # Agent MUST replace this with real narration after viewing the frame
            "narration": f"[AGENT: Describe what happens in step {step_num} based on the frame.]",
            "highlight_boxes": [],   # Agent fills after viewing frame
            "click_indicator": None, # Agent fills after viewing frame
            "hud_dock": {"position": "below"},
        })

    total_duration = round(steps[-1]["active_end"] + 1.0, 2) if steps else 10.0

    recipe = {
        "title": f"{app_name} User Guide",
        "source_video": str(video_path) if video_path else None,
        "frames_dir": str(frames_dir),
        "source_frame_fps": fps,
        "input_source": "frames",
        "default_voice": voice,
        "tone": tone,
        "output_resolution": output_resolution,
        "total_duration": total_duration,
        "audio_tracks_dir": str(frames_dir.parent / "audio_tracks"),
        "timeline_mapping": steps,
    }

    scene_frames = [steps[s]["source_frame"] for s in range(len(steps))]

    return {
        "recipe": recipe,
        "scene_frames": scene_frames,
        "step_count": len(steps),
        "total_duration_s": total_duration,
        "total_frames_scanned": total_frames,
        "message": (
            f"Detected {len(steps)} scenes from {total_frames} frames at {fps} fps. "
            f"Agent must inspect scene_frames and replace [AGENT:...] narrations "
            f"before calling validate_recipe / render_guide."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Auto-scaffold a Video Guide recipe from frames.")
    p.add_argument("--frames_dir", required=True)
    p.add_argument("--video_path", default=None)
    p.add_argument("--out", default="recipe_draft.json")
    p.add_argument("--fps", type=float, default=3.0)
    p.add_argument("--sensitivity", type=float, default=0.18,
                   help="Scene-cut sensitivity 0-1 (lower = more cuts)")
    p.add_argument("--voice", default="en-IN-NeerjaNeural")
    p.add_argument("--tone", default="friendly")
    p.add_argument("--app_name", default="Application")
    args = p.parse_args()

    result = scaffold_recipe(
        frames_dir=args.frames_dir,
        video_path=args.video_path,
        fps=args.fps,
        sensitivity=args.sensitivity,
        voice=args.voice,
        tone=args.tone,
        app_name=args.app_name,
    )

    if "error" in result:
        print("ERROR:", result["error"])
        return 1

    out_path = Path(args.out)
    out_path.write_text(json.dumps(result["recipe"], indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "recipe"}, indent=2))
    print(f"\nDraft recipe written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
