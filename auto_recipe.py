"""
auto_recipe.py — Full 3-FPS Video Analyzer, Storyboard Generator & Recipe Scaffolder.

Analyzes EVERY extracted 3-FPS frame of a screen recording (e.g., all ~630 frames of
a 210-second video) before editing begins so any AI agent can completely understand
the user workflow, trim idle pauses/mistakes, read exact UI text/coordinates, and
emit a valid `engine.py` recipe.json.

Pipeline:
  1. Scan ALL extracted 3-FPS frames (`0001_frame.png` .. `0NNN_frame.png`)
  2. Compute global diff + 8x6 spatial block-max diff + changed bounding boxes [x1,y1,x2,y2]
  3. Segment frames chronologically into PAGE_TRANSITION, UI_ACTION, and IDLE_HOLD spans
  4. Render labeled Storyboard Contact Sheets (`_storyboards/storyboard_01.png`, ...)
     covering the entire recording (zero blind gaps)
  5. Save detailed `analysis_3fps.json` report + valid `engine.py` draft `recipe_draft.json`

Usage:
    python auto_recipe.py --frames_dir frames/ --video_path rec.mp4 \
                          --out recipe_draft.json [--fps 3]
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ──────────────────────────────────────────────────────────────────────────────
# Natural Frame Ordering
# ──────────────────────────────────────────────────────────────────────────────

def get_sorted_frames(frames_dir: str | Path) -> list[Path]:
    """Return all image frames sorted naturally by frame number."""
    import re
    folder = Path(frames_dir)
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]

    def nkey(p: Path):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", p.name)]

    return sorted(files, key=nkey)


# ──────────────────────────────────────────────────────────────────────────────
# Exhaustive Frame-by-Frame Spatiotemporal Analyzer (scans ALL N frames)
# ──────────────────────────────────────────────────────────────────────────────

def _analyze_frame_pair(
    prev_small_gray: np.ndarray,
    curr_small_gray: np.ndarray,
    src_w: int,
    src_h: int,
    grid_cols: int = 8,
    grid_rows: int = 6,
    cell_active_thresh: float = 0.035,
) -> tuple[float, float, list[int] | None]:
    """
    Compare two 320x180 grayscale frames.
    Returns:
      - global_diff: normalized mean absolute diff [0..1]
      - block_max_diff: max normalized cell MAD across an 8x6 spatial grid [0..1]
      - changed_bbox_px: [x1, y1, x2, y2] in source pixel coords covering active cells (or None)
    """
    diff = np.abs(curr_small_gray.astype(np.float32) - prev_small_gray.astype(np.float32)) / 255.0
    global_diff = float(np.mean(diff))

    h, w = diff.shape
    cw = max(1, w // grid_cols)
    ch = max(1, h // grid_rows)

    block_max = 0.0
    active_cells: list[tuple[int, int]] = []
    for r in range(grid_rows):
        y0 = r * ch
        y1 = h if r == grid_rows - 1 else (r + 1) * ch
        for c in range(grid_cols):
            x0 = c * cw
            x1 = w if c == grid_cols - 1 else (c + 1) * cw
            c_diff = float(np.mean(diff[y0:y1, x0:x1]))
            if c_diff > block_max:
                block_max = c_diff
            if c_diff >= cell_active_thresh:
                active_cells.append((c, r))

    changed_bbox = None
    if active_cells:
        min_c = min(c for c, _ in active_cells)
        max_c = max(c for c, _ in active_cells)
        min_r = min(r for _, r in active_cells)
        max_r = max(r for _, r in active_cells)
        x1 = int(round((min_c / grid_cols) * src_w))
        y1 = int(round((min_r / grid_rows) * src_h))
        x2 = int(round(((max_c + 1) / grid_cols) * src_w))
        y2 = int(round(((max_r + 1) / grid_rows) * src_h))
        changed_bbox = [max(0, x1), max(0, y1), min(src_w, x2), min(src_h, y2)]

    return global_diff, block_max, changed_bbox


def _union_bbox(boxes: list[list[int] | None]) -> list[int] | None:
    valid = [b for b in boxes if b]
    if not valid:
        return None
    return [
        min(b[0] for b in valid),
        min(b[1] for b in valid),
        max(b[2] for b in valid),
        max(b[3] for b in valid),
    ]


def analyze_video_frames(
    frames_dir: str | Path,
    video_path: str | None = None,
    fps: float = 3.0,
    page_threshold: float = 0.055,
    ui_threshold: float = 0.095,
    min_idle_sec: float = 2.0,
    storyboard_dir: str | Path | None = None,
    cols: int = 4,
    rows: int = 4,
) -> dict:
    """
    Exhaustively analyze ALL extracted frames (e.g. 630 frames for 210s @ 3fps).

    Produces:
      - Full chronological frame-range segments (0 .. N-1) with NO blind spots
      - Detected changed UI region bounding boxes in native pixels [x1, y1, x2, y2]
      - Idle pause detection (trim candidates)
      - Labeled Storyboard Contact Sheets on disk (`storyboard_01.png`, ...)
      - `analysis_3fps.json` full trace saved alongside storyboards
    """
    frames_path = Path(frames_dir).resolve()
    frame_files = get_sorted_frames(frames_path)
    if not frame_files:
        return {"error": f"No image frames found in {frames_path}"}

    total_frames = len(frame_files)
    fps = float(fps) if fps and fps > 0 else 3.0
    duration_sec = round(total_frames / fps, 2)

    first = cv2.imread(str(frame_files[0]))
    if first is None:
        return {"error": f"Cannot decode first frame: {frame_files[0]}"}
    src_h, src_w = first.shape[:2]

    # ── Pass 1: Scan EVERY frame 0 .. N-1 ───────────────────────────────────
    frame_metrics: list[dict] = []
    prev_small = None
    for idx, fp in enumerate(frame_files):
        img = first if idx == 0 else cv2.imread(str(fp))
        if img is None:
            frame_metrics.append({
                "idx": idx,
                "time_sec": round(idx / fps, 2),
                "global_diff": 0.0,
                "block_max_diff": 0.0,
                "changed_bbox": None,
                "state": "idle",
            })
            continue

        small_gray = cv2.cvtColor(cv2.resize(img, (320, 180)), cv2.COLOR_BGR2GRAY)
        if prev_small is None:
            gdiff, bmax, bbox = 0.0, 0.0, None
            state = "page_transition"
        else:
            gdiff, bmax, bbox = _analyze_frame_pair(prev_small, small_gray, src_w, src_h)
            if gdiff >= page_threshold:
                state = "page_transition"
            elif bmax >= ui_threshold:
                state = "ui_action"
            else:
                state = "idle"
        prev_small = small_gray

        frame_metrics.append({
            "idx": idx,
            "time_sec": round(idx / fps, 2),
            "global_diff": round(gdiff, 4),
            "block_max_diff": round(bmax, 4),
            "changed_bbox": bbox,
            "state": state,
        })

    # ── Pass 2: Build continuous chronological segments across ALL frames ────
    min_idle_frames = max(2, int(round(min_idle_sec * fps)))
    segments: list[dict] = []

    def _emit_segment(s_idx: int, e_idx: int, seg_type: str):
        sub = frame_metrics[s_idx : e_idx + 1]
        peak_row = max(sub, key=lambda r: (r["global_diff"] * 1.5 + r["block_max_diff"]))
        # Pick settled keyframe slightly after transition start if action/page span has tail
        rep_idx = min(e_idx, s_idx + 1) if (e_idx - s_idx >= 2 and seg_type == "page_transition") else s_idx
        union_box = _union_bbox([r["changed_bbox"] for r in sub])
        dur = round((e_idx - s_idx + 1) / fps, 2)
        seg = {
            "segment_index": len(segments) + 1,
            "type": seg_type,
            "start_frame_3fps": s_idx,
            "end_frame_3fps": e_idx,
            "start_sec": round(s_idx / fps, 2),
            "end_sec": round((e_idx + 1) / fps, 2),
            "duration_sec": dur,
            "key_frame_3fps": rep_idx,
            "key_frame_file": frame_files[rep_idx].name,
            "key_frame_path": str(frame_files[rep_idx]),
            "start_frame_path": str(frame_files[s_idx]),
            "end_frame_path": str(frame_files[e_idx]),
            "changed_region_px": union_box,
            "peak_global_diff": max(r["global_diff"] for r in sub),
            "peak_block_diff": max(r["block_max_diff"] for r in sub),
            "trim_candidate": (seg_type == "IDLE_HOLD" and dur >= 4.0),
        }
        segments.append(seg)

    # Smooth micro-idle gaps (< min_idle_frames) between active frames into UI_ACTION spans
    raw_states = [m["state"] for m in frame_metrics]
    # Mark sustained idle runs vs active runs
    is_sustained_idle = [False] * total_frames
    run_start = None
    for i, st in enumerate(raw_states):
        if st == "idle":
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and (i - run_start) >= min_idle_frames:
                for k in range(run_start, i):
                    is_sustained_idle[k] = True
            run_start = None
    if run_start is not None and (total_frames - run_start) >= min_idle_frames:
        for k in range(run_start, total_frames):
            is_sustained_idle[k] = True

    cur_start = 0
    cur_type = "PAGE_TRANSITION"
    for i in range(1, total_frames):
        st = raw_states[i]
        if is_sustained_idle[i]:
            nxt_type = "IDLE_HOLD"
        elif st == "page_transition":
            nxt_type = "PAGE_TRANSITION"
        else:
            nxt_type = "UI_ACTION"

        # Break into a new segment on PAGE_TRANSITION or transition between active <-> IDLE_HOLD
        # Also split overly long UI_ACTION spans (> 8s) so agent gets clean granularity
        span_frames = i - cur_start
        should_split = (
            nxt_type == "PAGE_TRANSITION"
            or (nxt_type != cur_type and not (cur_type == "PAGE_TRANSITION" and nxt_type == "UI_ACTION" and span_frames < 3))
            or (cur_type != "IDLE_HOLD" and span_frames >= int(round(8.0 * fps)))
        )
        if should_split:
            _emit_segment(cur_start, i - 1, cur_type)
            cur_start = i
            cur_type = nxt_type

    _emit_segment(cur_start, total_frames - 1, cur_type)

    # ── Pass 3: Select Storyboard Keyframes covering 100% of timeline ────────
    # Guarantee no blind interval > 6 seconds anywhere in the video
    max_gap_frames = max(4, int(round(6.0 * fps)))
    sample_entries: list[dict] = []
    covered_indices: set[int] = set()

    for seg in segments:
        k = seg["key_frame_3fps"]
        if k not in covered_indices:
            sample_entries.append({
                "frame_idx": k,
                "time_sec": round(k / fps, 2),
                "tag": seg["type"],
                "segment_index": seg["segment_index"],
                "bbox": seg["changed_region_px"],
                "path": str(frame_files[k]),
            })
            covered_indices.add(k)
        # If segment has meaningful end change distinct from start, sample midpoint/end for long actions
        if seg["type"] != "IDLE_HOLD" and (seg["end_frame_3fps"] - seg["start_frame_3fps"]) >= int(round(4.0 * fps)):
            e_idx = seg["end_frame_3fps"]
            if e_idx not in covered_indices:
                sample_entries.append({
                    "frame_idx": e_idx,
                    "time_sec": round(e_idx / fps, 2),
                    "tag": "UI_SETTLED",
                    "segment_index": seg["segment_index"],
                    "bbox": seg["changed_region_px"],
                    "path": str(frame_files[e_idx]),
                })
                covered_indices.add(e_idx)

    # Fill any blind gap > max_gap_frames across 0..N-1
    sorted_k = sorted(covered_indices) if covered_indices else [0]
    checkpoints: list[int] = []
    prev_k = 0
    for k in sorted_k + [total_frames - 1]:
        while k - prev_k > max_gap_frames:
            prev_k += max_gap_frames
            if prev_k not in covered_indices:
                checkpoints.append(prev_k)
        prev_k = k

    for ck in checkpoints:
        covered_indices.add(ck)
        sample_entries.append({
            "frame_idx": ck,
            "time_sec": round(ck / fps, 2),
            "tag": "CHECKPOINT",
            "segment_index": None,
            "bbox": frame_metrics[ck]["changed_bbox"],
            "path": str(frame_files[ck]),
        })

    sample_entries.sort(key=lambda e: e["frame_idx"])

    # ── Pass 4: Render Labeled Storyboard Contact Sheets ─────────────────────
    sb_dir = Path(storyboard_dir).resolve() if storyboard_dir else (frames_path / "_storyboards")
    sb_dir.mkdir(parents=True, exist_ok=True)
    for old_sb in sb_dir.glob("storyboard_*.png"):
        try:
            old_sb.unlink()
        except OSError:
            pass

    storyboard_paths = _render_storyboard_sheets(
        sample_entries=sample_entries,
        out_dir=sb_dir,
        src_w=src_w,
        src_h=src_h,
        cols=cols,
        rows=rows,
    )

    report = {
        "source_video": str(video_path) if video_path else None,
        "frames_dir": str(frames_path),
        "fps_extracted": fps,
        "total_frames_analyzed": total_frames,
        "duration_sec": duration_sec,
        "resolution": {"width": src_w, "height": src_h},
        "segment_count": len(segments),
        "storyboard_count": len(storyboard_paths),
        "storyboard_paths": storyboard_paths,
        "sample_keyframes_count": len(sample_entries),
        "segments": segments,
    }

    report_path = sb_dir / "analysis_3fps.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["analysis_json_path"] = str(report_path)
    return report


def _load_label_font(size: int = 16):
    """Load a crisp TrueType font across OSes, with Pillow scalable default fallback."""
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for fp in candidates:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _render_storyboard_sheets(
    sample_entries: list[dict],
    out_dir: Path,
    src_w: int,
    src_h: int,
    cols: int = 4,
    rows: int = 4,
    prefix: str = "storyboard",
) -> list[str]:
    """Pack sampled keyframes into labeled high-res contact sheets for agent inspection."""
    if not sample_entries:
        return []

    per_sheet = max(1, cols * rows)
    tile_w = 480
    header_h = 38
    tile_img_h = max(160, int(round(tile_w * (src_h / float(max(1, src_w))))))
    tile_h = tile_img_h + header_h
    pad = 10

    sheet_w = cols * tile_w + (cols + 1) * pad
    sheet_h = rows * tile_h + (rows + 1) * pad

    font = _load_label_font(15)

    tag_colors = {
        "PAGE_TRANSITION": (0, 145, 255),
        "UI_ACTION": (245, 158, 11),
        "UI_SETTLED": (34, 197, 94),
        "IDLE_HOLD": (100, 116, 139),
        "CHECKPOINT": (168, 85, 247),
        "SLICE": (236, 72, 153),
    }

    sheet_paths: list[str] = []
    num_sheets = math.ceil(len(sample_entries) / per_sheet)

    for s_idx in range(num_sheets):
        chunk = sample_entries[s_idx * per_sheet : (s_idx + 1) * per_sheet]
        canvas = Image.new("RGB", (sheet_w, sheet_h), (12, 18, 32))
        draw = ImageDraw.Draw(canvas)

        for i, entry in enumerate(chunk):
            r = i // cols
            c = i % cols
            tx = pad + c * (tile_w + pad)
            ty = pad + r * (tile_h + pad)

            tag = entry.get("tag", "FRAME")
            hdr_color = tag_colors.get(tag, (59, 130, 246))

            # Header strip
            draw.rectangle([tx, ty, tx + tile_w, ty + header_h], fill=(20, 30, 52))
            draw.rectangle([tx, ty, tx + 8, ty + header_h], fill=hdr_color)

            frame_num_1based = entry["frame_idx"] + 1
            seg_str = f" | S{entry['segment_index']}" if entry.get("segment_index") else ""
            label = f"#{entry['frame_idx']:04d} (f{frame_num_1based:04d}) {entry['time_sec']:.2f}s [{tag}]{seg_str}"
            draw.text((tx + 14, ty + 10), label, fill=(240, 248, 255), font=font)

            # Frame image
            bgr = cv2.imread(entry["path"])
            if bgr is not None:
                rgb = cv2.cvtColor(cv2.resize(bgr, (tile_w, tile_img_h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
                tile_im = Image.fromarray(rgb)
                canvas.paste(tile_im, (tx, ty + header_h))

                # Subtle activity bbox hint on tile so agent sees active UI region
                bbox = entry.get("bbox")
                if bbox and len(bbox) == 4:
                    sx = tile_w / float(max(1, src_w))
                    sy = tile_img_h / float(max(1, src_h))
                    bx1 = tx + int(round(bbox[0] * sx))
                    by1 = ty + header_h + int(round(bbox[1] * sy))
                    bx2 = tx + int(round(bbox[2] * sx))
                    by2 = ty + header_h + int(round(bbox[3] * sy))
                    draw.rectangle([bx1, by1, bx2, by2], outline=(0, 220, 255), width=2)

            draw.rectangle([tx, ty, tx + tile_w, ty + tile_h], outline=(51, 65, 85), width=1)

        out_file = out_dir / f"{prefix}_{s_idx + 1:02d}.png"
        canvas.save(str(out_file), optimize=True)
        sheet_paths.append(str(out_file))

    return sheet_paths


def render_frame_slice(
    frames_dir: str | Path,
    start_frame: int,
    end_frame: int,
    fps: float = 3.0,
    stride: int = 1,
    cols: int = 4,
    rows: int = 4,
) -> dict:
    """
    Generate a zoomed-in storyboard sheet (or sheets) for EVERY frame in a narrow range
    [start_frame .. end_frame] (0-based 3fps indices). Lets agents drill into fast UI
    actions like opening dropdowns, clicking form buttons, or reading brief modals.
    """
    frames_path = Path(frames_dir).resolve()
    frame_files = get_sorted_frames(frames_path)
    if not frame_files:
        return {"success": False, "error": f"No frames found in {frames_path}"}

    total = len(frame_files)
    s_idx = max(0, int(start_frame))
    e_idx = min(total - 1, int(end_frame))
    if e_idx < s_idx:
        s_idx, e_idx = e_idx, s_idx

    first = cv2.imread(str(frame_files[s_idx]))
    if first is None:
        return {"success": False, "error": f"Cannot decode frame {frame_files[s_idx]}"}
    src_h, src_w = first.shape[:2]

    entries = []
    for idx in range(s_idx, e_idx + 1, max(1, int(stride))):
        entries.append({
            "frame_idx": idx,
            "time_sec": round(idx / float(fps or 3.0), 2),
            "tag": "SLICE",
            "segment_index": None,
            "bbox": None,
            "path": str(frame_files[idx]),
        })

    sb_dir = frames_path / "_storyboards"
    sb_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"slice_{s_idx:04d}_{e_idx:04d}"
    sheets = _render_storyboard_sheets(
        sample_entries=entries,
        out_dir=sb_dir,
        src_w=src_w,
        src_h=src_h,
        cols=cols,
        rows=rows,
        prefix=prefix,
    )
    return {
        "success": True,
        "start_frame": s_idx,
        "end_frame": e_idx,
        "frame_count": len(entries),
        "slice_sheet_paths": sheets,
        "frame_paths": [e["path"] for e in entries],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Engine-Compatible Recipe Scaffolder
# ──────────────────────────────────────────────────────────────────────────────

def scaffold_recipe(
    frames_dir: str,
    video_path: str | None = None,
    fps: float = 3.0,
    page_threshold: float = 0.055,
    ui_threshold: float = 0.095,
    voice: str = "en-IN-NeerjaNeural",
    tone: str = "friendly",
    app_name: str = "Application",
    user_flow_notes: str = "",
    # backward-compat alias
    sensitivity: float | None = None,
) -> dict:
    """
    Analyze ALL 3-FPS frames in `frames_dir` and emit a 100% engine.py-compatible
    starter recipe dict (with `timeline_mapping` + `steps`) plus storyboards.
    """
    if sensitivity is not None:
        # Honor older callers passing a single sensitivity parameter
        page_threshold = max(0.02, min(0.25, float(sensitivity) * 0.35))

    analysis = analyze_video_frames(
        frames_dir=frames_dir,
        video_path=video_path,
        fps=fps,
        page_threshold=page_threshold,
        ui_threshold=ui_threshold,
    )
    if "error" in analysis:
        return analysis

    segments = analysis["segments"]
    res = analysis["resolution"]
    src_w, src_h = res["width"], res["height"]

    # Build step candidates prioritizing meaningful UI/page segments (skip pure long idle gaps)
    active_segments = [s for s in segments if not s.get("trim_candidate")]
    if not active_segments:
        active_segments = segments

    # Coalesce consecutive minor segments into practical tutorial steps (~6..18 steps)
    grouped: list[dict] = []
    for seg in active_segments:
        if not grouped:
            grouped.append(dict(seg))
            continue
        prev = grouped[-1]
        gap = seg["start_frame_3fps"] - prev["end_frame_3fps"]
        combined_dur = (seg["end_frame_3fps"] - prev["start_frame_3fps"] + 1) / float(fps)
        # Keep PAGE_TRANSITION always distinct; merge adjacent short UI_ACTION micro-events < 4.5s
        if seg["type"] != "PAGE_TRANSITION" and prev["duration_sec"] < 4.5 and gap <= int(round(2.5 * fps)) and combined_dur <= 10.0:
            prev["end_frame_3fps"] = seg["end_frame_3fps"]
            prev["end_sec"] = seg["end_sec"]
            prev["duration_sec"] = round(prev["end_sec"] - prev["start_sec"], 2)
            prev["end_frame_path"] = seg["end_frame_path"]
            prev["changed_region_px"] = _union_bbox([prev.get("changed_region_px"), seg.get("changed_region_px")])
        else:
            grouped.append(dict(seg))

    # Cap if an extra-noisy recording generated > 20 steps (preserve first, last, and page transitions)
    if len(grouped) > 18:
        stride = max(2, len(grouped) // 14)
        reduced = []
        for idx, g in enumerate(grouped):
            if idx == 0 or idx == len(grouped) - 1 or g["type"] == "PAGE_TRANSITION" or idx % stride == 0:
                reduced.append(g)
        grouped = reduced

    # Emit authentic engine.py `timeline_mapping` + `steps`
    timeline_mapping: list[dict] = []
    steps: list[dict] = []
    cur_t = 0.0
    total_steps = len(grouped)

    for i, g in enumerate(grouped):
        seg_dur = max(5.0, min(10.0, round(g["duration_sec"], 2)))
        t_start = round(cur_t, 2)
        t_end = round(cur_t + seg_dur, 2)

        timeline_mapping.append({
            "start_sec": t_start,
            "end_sec": t_end,
            "source_frame_start_3fps": g["start_frame_3fps"],
            "source_frame_end_3fps": g["end_frame_3fps"],
        })

        if i == 0:
            step_id = "intro"
            step_num = "INTRO"
        elif i == total_steps - 1 and total_steps > 1:
            step_id = "complete"
            step_num = "COMPLETE"
        else:
            step_id = f"step{i}"
            step_num = f"STEP {i}"

        bbox = g.get("changed_region_px")
        starter_boxes = []
        if bbox and (bbox[2] - bbox[0]) < src_w * 0.85 and (bbox[3] - bbox[1]) < src_h * 0.85:
            starter_boxes.append({
                "rect": bbox,
                "color": [255, 180, 0],
                "glow": [0, 168, 255],
                "shape": "rounded_rect",
                "pulse": (i == 0 or i == total_steps - 1),
            })

        steps.append({
            "id": step_id,
            "start_time": round(t_start + 0.3, 2),
            "active_start": t_start,
            "active_end": t_end,
            "step_num": step_num,
            "step_title": f"[AGENT: Short title for {g['key_frame_file']}]",
            "narration": (
                f"[AGENT: View {g['key_frame_file']} ({g['start_sec']}s-{g['end_sec']}s) "
                f"and write clear voiceover narration for this step.]"
            ),
            "sub": f"[AGENT: 1-line HUD caption for {g['key_frame_file']}]",
            "boxes": starter_boxes,
            "arrows": [],
            "_ref_key_frame": g["key_frame_path"],
            "_ref_end_frame": g["end_frame_path"],
            "_ref_changed_bbox": bbox,
        })
        cur_t = t_end

    tone_presets = {
        "professional": "tech_hud",
        "energetic": "tech_hud",
        "calm": "clean_light",
        "corporate": "minimal",
        "friendly": "tech_hud",
    }

    recipe = {
        "source_video": str(video_path) if video_path else None,
        "frames_dir": str(Path(frames_dir).resolve()),
        "fps_extracted": float(fps),
        "input_source": "auto",
        "auto_extract_frames": True,
        "coord_mode": "auto",
        "reference_resolution": [src_w, src_h],
        "branding_text": f"{app_name} • User Guide",
        "preset": tone_presets.get(tone, "tech_hud"),
        "tone": tone,
        "default_voice": voice,
        "dock_mode": "auto",
        "dock_width_mode": "auto",
        "total_duration": "auto",
        "fps": 30,
        "audio_timing_mode": "auto_shift",
        "background_music": True,
        "export_subtitles": True,
        "timeline_mapping": timeline_mapping,
        "steps": steps,
    }

    draft_path = Path(frames_dir).resolve() / "_storyboards" / "recipe_draft.json"
    draft_path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")

    return {
        "success": True,
        "recipe": recipe,
        "draft_recipe_path": str(draft_path),
        "analysis_json_path": analysis["analysis_json_path"],
        "storyboard_paths": analysis["storyboard_paths"],
        "total_frames_analyzed": analysis["total_frames_analyzed"],
        "duration_sec": analysis["duration_sec"],
        "resolution": analysis["resolution"],
        "step_count": len(steps),
        "segment_count": analysis["segment_count"],
        "segments": segments,
        "user_flow_notes": user_flow_notes,
        "message": (
            f"Analyzed ALL {analysis['total_frames_analyzed']} frames ({analysis['duration_sec']}s @ {fps} fps), "
            f"generated {analysis['storyboard_count']} storyboard sheets, and scaffolded {len(steps)} draft steps."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Analyze ALL 3-FPS frames & scaffold a Video Guide recipe.")
    p.add_argument("--frames_dir", required=True)
    p.add_argument("--video_path", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--fps", type=float, default=3.0)
    p.add_argument("--voice", default="en-IN-NeerjaNeural")
    p.add_argument("--tone", default="friendly")
    p.add_argument("--app_name", default="Application")
    p.add_argument("--slice", nargs=2, type=int, metavar=("START", "END"),
                   help="Render dense storyboard slice for frame indices START..END (0-based)")
    args = p.parse_args()

    if args.slice:
        res = render_frame_slice(args.frames_dir, args.slice[0], args.slice[1], fps=args.fps)
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    result = scaffold_recipe(
        frames_dir=args.frames_dir,
        video_path=args.video_path,
        fps=args.fps,
        voice=args.voice,
        tone=args.tone,
        app_name=args.app_name,
    )
    if "error" in result:
        print("ERROR:", result["error"])
        return 1

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result["recipe"], indent=2), encoding="utf-8")
        print(f"Draft recipe written to: {out_path}")

    summary = {k: v for k, v in result.items() if k not in ("recipe", "segments")}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
