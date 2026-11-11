import argparse
import asyncio
import glob
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from collections import OrderedDict

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Locate bundled FFmpeg binary (no global PATH install required)
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

VOICE_CATALOG = [
    ("en-IN-PrabhatNeural", "Indian English Male (Clear, Authoritative)"),
    ("en-IN-NeerjaNeural", "Indian English Female (Warm, Articulate)"),
    ("en-US-GuyNeural", "US English Male (Confident Tutorial)"),
    ("en-US-JennyNeural", "US English Female (Friendly Corporate)"),
    ("en-GB-RyanNeural", "UK English Male (Crisp, Formal)"),
    ("en-GB-SoniaNeural", "UK English Female (Polished, Natural)"),
]

TONE_PRESETS = {
    "professional": {
        "description": "Balanced, clear tutorial pacing (+8% rate, subtle dark HUD)",
        "rate": "+8%",
        "pitch": "+0Hz",
        "music_base_gain": 0.065,
        "music_duck_gain": 0.025,
        "preset": "tech_hud",
    },
    "energetic": {
        "description": "Upbeat product walkthrough (+14% rate, higher energy)",
        "rate": "+14%",
        "pitch": "+2Hz",
        "music_base_gain": 0.080,
        "music_duck_gain": 0.030,
        "preset": "tech_hud",
    },
    "calm": {
        "description": "Measured, beginner-friendly pace (+0% rate, clean light theme)",
        "rate": "+0%",
        "pitch": "-2Hz",
        "music_base_gain": 0.055,
        "music_duck_gain": 0.020,
        "preset": "clean_light",
    },
    "corporate": {
        "description": "Formal enterprise guide (+5% rate, minimal HUD)",
        "rate": "+5%",
        "pitch": "+0Hz",
        "music_base_gain": 0.050,
        "music_duck_gain": 0.018,
        "preset": "minimal",
    },
    "friendly": {
        "description": "Approachable onboarding style (+6% rate, warm tone)",
        "rate": "+6%",
        "pitch": "+3Hz",
        "music_base_gain": 0.070,
        "music_duck_gain": 0.028,
        "preset": "tech_hud",
    },
}

THEME_PRESETS = {
    "tech_hud": {
        "stage_bg": [10, 16, 32],
        "stage_divider": [0, 132, 255],
        "dock_bg": [10, 16, 32, 240],
        "dock_border": [0, 168, 255, 195],
        "badge_bg": [0, 132, 255, 255],
        "badge_complete_bg": [46, 213, 115, 255],
        "badge_text": [255, 255, 255, 255],
        "title_text": [255, 255, 255, 255],
        "sub_text": [215, 230, 255, 245],
        "branding_bg": [15, 23, 42, 222],
        "branding_border": [255, 255, 255, 70],
        "branding_text": [200, 225, 255, 245],
        "box_color": [255, 180, 0],
        "box_glow": [0, 168, 255],
        "box_label_bg": [15, 23, 42, 235],
        "box_label_border": [0, 200, 255, 210],
        "box_label_text": [0, 220, 255, 255],
        "arrow_color": [255, 55, 55, 255],
        "arrow_tag_bg": [255, 50, 50, 240],
        "arrow_tag_border": [255, 255, 255, 180],
        "arrow_tag_text": [255, 255, 255, 255],
        "complete_keywords": ["COMPLETE", "SUCCESS", "DONE"],
    },
    "clean_light": {
        "stage_bg": [241, 245, 249],
        "stage_divider": [203, 213, 225],
        "dock_bg": [255, 255, 255, 244],
        "dock_border": [99, 102, 241, 180],
        "badge_bg": [79, 70, 229, 255],
        "badge_complete_bg": [16, 185, 129, 255],
        "badge_text": [255, 255, 255, 255],
        "title_text": [15, 23, 42, 255],
        "sub_text": [51, 65, 85, 250],
        "branding_bg": [255, 255, 255, 235],
        "branding_border": [148, 163, 184, 150],
        "branding_text": [30, 41, 59, 255],
        "box_color": [79, 70, 229],
        "box_glow": [99, 102, 241],
        "box_label_bg": [30, 41, 59, 240],
        "box_label_border": [99, 102, 241, 220],
        "box_label_text": [224, 231, 255, 255],
        "arrow_color": [239, 68, 68, 255],
        "arrow_tag_bg": [220, 38, 38, 242],
        "arrow_tag_border": [255, 255, 255, 200],
        "arrow_tag_text": [255, 255, 255, 255],
        "complete_keywords": ["COMPLETE", "SUCCESS", "DONE"],
    },
    "minimal": {
        "stage_bg": [24, 24, 27],
        "stage_divider": [63, 63, 70],
        "dock_bg": [24, 24, 27, 230],
        "dock_border": [255, 255, 255, 65],
        "badge_bg": [63, 63, 70, 255],
        "badge_complete_bg": [34, 197, 94, 255],
        "badge_text": [255, 255, 255, 255],
        "title_text": [250, 250, 250, 255],
        "sub_text": [212, 212, 216, 245],
        "branding_bg": [24, 24, 27, 210],
        "branding_border": [255, 255, 255, 50],
        "branding_text": [228, 228, 231, 240],
        "box_color": [56, 189, 248],
        "box_glow": [56, 189, 248],
        "box_label_bg": [24, 24, 27, 235],
        "box_label_border": [161, 161, 170, 180],
        "box_label_text": [244, 244, 245, 255],
        "arrow_color": [249, 115, 22, 255],
        "arrow_tag_bg": [234, 88, 12, 240],
        "arrow_tag_border": [255, 255, 255, 160],
        "arrow_tag_text": [255, 255, 255, 255],
        "complete_keywords": ["COMPLETE", "SUCCESS", "DONE"],
    },
    "high_contrast": {
        "stage_bg": [0, 0, 0],
        "stage_divider": [250, 204, 21],
        "dock_bg": [0, 0, 0, 248],
        "dock_border": [250, 204, 21, 255],
        "badge_bg": [37, 99, 235, 255],
        "badge_complete_bg": [22, 163, 74, 255],
        "badge_text": [255, 255, 255, 255],
        "title_text": [255, 255, 255, 255],
        "sub_text": [254, 240, 138, 255],
        "branding_bg": [0, 0, 0, 245],
        "branding_border": [250, 204, 21, 220],
        "branding_text": [254, 240, 138, 255],
        "box_color": [250, 204, 21],
        "box_glow": [250, 204, 21],
        "box_label_bg": [0, 0, 0, 245],
        "box_label_border": [250, 204, 21, 255],
        "box_label_text": [250, 204, 21, 255],
        "arrow_color": [255, 45, 85, 255],
        "arrow_tag_bg": [225, 29, 72, 255],
        "arrow_tag_border": [255, 255, 255, 240],
        "arrow_tag_text": [255, 255, 255, 255],
        "complete_keywords": ["COMPLETE", "SUCCESS", "DONE"],
    },
}


def resolve_theme(recipe):
    """Merge selected theme preset with custom recipe theme overrides."""
    preset_name = recipe.get("preset", "tech_hud")
    tone_name = recipe.get("tone")
    if "preset" not in recipe and tone_name in TONE_PRESETS:
        preset_name = TONE_PRESETS[tone_name].get("preset", "tech_hud")
    base = dict(THEME_PRESETS.get(preset_name, THEME_PRESETS["tech_hud"]))
    for key, val in recipe.get("theme", {}).items():
        base[key] = val
    return base


def compute_ui_scale(canvas_w, canvas_h, recipe=None):
    """Compute resolution-independent UI scale factor anchored at 1920x1080."""
    recipe = recipe or {}
    base_scale = min(canvas_w / 1920.0, canvas_h / 1080.0)
    clamped = max(0.55, min(2.2, base_scale))
    return clamped * float(recipe.get("ui_scale", 1.0))


def _find_font_path(custom_path=None):
    """Locate a cross-platform bold/sans-serif TTF/TTC font file."""
    candidates = []
    if custom_path:
        candidates.append(custom_path)
    candidates.extend([
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\calibrib.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ])
    return next((p for p in candidates if p and os.path.exists(p)), None)


def _make_font(font_path, size):
    """Instantiate TrueType font at integer pixel size or fall back safely."""
    px = max(10, int(round(size)))
    if font_path:
        try:
            return ImageFont.truetype(font_path, px)
        except OSError:
            pass
    return ImageFont.load_default()


def load_fonts(ui_scale=1.0, recipe=None):
    """Load scaled typography hierarchy across platforms."""
    recipe = recipe or {}
    font_scale = float(recipe.get("font_scale", 1.0)) * ui_scale
    bold_path = _find_font_path(recipe.get("font_path"))
    reg_path = _find_font_path(recipe.get("font_regular_path")) or bold_path

    return {
        "title": _make_font(bold_path, 23 * font_scale),
        "step": _make_font(bold_path, 19 * font_scale),
        "sub": _make_font(reg_path, 23 * font_scale),
        "tag": _make_font(bold_path, 18 * font_scale),
        "card_tag": _make_font(bold_path, 17 * font_scale),
        "_bold_path": bold_path,
        "_reg_path": reg_path,
    }


def _text_size(font, text):
    """Measure pixel (width, height) of single-line text safely."""
    if not text:
        return (0, 0)
    bbox = font.getbbox(text)
    return (max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1]))


def _draw_text_in_box(draw, x, y, w, h, text, font, fill, align="center", pad_x=0):
    """Draw text vertically centered inside box [x, y, x+w, y+h] using true glyph bounds."""
    if not text:
        return
    bbox = font.getbbox(text)
    gw = max(0, bbox[2] - bbox[0])
    gh = max(0, bbox[3] - bbox[1])
    ty = y + (h - gh) // 2 - bbox[1]
    if align == "center":
        tx = x + (w - gw) // 2 - bbox[0]
    else:
        tx = x + pad_x - bbox[0]
    draw.text((tx, ty), text, font=font, fill=fill)


def _fit_font_for_width(text, base_font, max_width, min_size=13):
    """Shrink font size until single-line text fits max_width."""
    w, _ = _text_size(base_font, text)
    if w <= max_width or max_width <= 0:
        return base_font
    font_path = getattr(base_font, "path", None)
    size = getattr(base_font, "size", 24)
    if not font_path:
        return base_font
    while size > min_size:
        size -= 1
        candidate = _make_font(font_path, size)
        cw, _ = _text_size(candidate, text)
        if cw <= max_width:
            return candidate
    return _make_font(font_path, min_size)


def _wrap_text(text, font, max_width, max_lines=2):
    """Word-wrap text cleanly to fit max_width within max_lines; returns (lines, truncated)."""
    if not text:
        return [""], False
    words = text.split()
    if not words:
        return [""], False

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_size(font, candidate)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break

    if len(lines) < max_lines:
        lines.append(current)
        if _text_size(font, lines[-1])[0] <= max_width:
            return lines, False
        last = lines[-1]
        while _text_size(font, last)[0] > max_width and len(last) > 4:
            last = last[:-4].rstrip() + "..."
        lines[-1] = last
        return lines, True

    used = sum(len(l.split()) for l in lines)
    leftover = " ".join(words[used:])
    last = f"{lines[-1]} {leftover}".strip() if leftover else lines[-1]
    truncated = bool(leftover)
    while _text_size(font, last)[0] > max_width and len(last) > 4:
        last = last[:-4].rstrip() + "..."
        truncated = True
    lines[-1] = last
    return lines, truncated


def _scale_coord_pair(pt, src_w, src_h, recipe):
    """Convert pixel, normalized [0..1], or reference-resolution coordinates to source pixels."""
    x, y = pt[0], pt[1]
    mode = recipe.get("coord_mode", "auto")
    if mode == "normalized":
        return [int(round(x * src_w)), int(round(y * src_h))]
    if mode == "auto":
        is_norm = (
            0.0 <= float(x) <= 1.0
            and 0.0 <= float(y) <= 1.0
            and (isinstance(x, float) or isinstance(y, float))
            and (x not in (0, 1) or y not in (0, 1))
        )
        if is_norm:
            return [int(round(x * src_w)), int(round(y * src_h))]

    ref = recipe.get("reference_resolution")
    if ref and len(ref) == 2 and ref[0] > 0 and ref[1] > 0:
        return [int(round(x * src_w / float(ref[0]))), int(round(y * src_h / float(ref[1])))]
    return [int(round(x)), int(round(y))]


def _scale_rect(rect, src_w, src_h, recipe):
    """Scale [x1, y1, x2, y2] rect according to coord_mode or reference_resolution."""
    p1 = _scale_coord_pair([rect[0], rect[1]], src_w, src_h, recipe)
    p2 = _scale_coord_pair([rect[2], rect[3]], src_w, src_h, recipe)
    return [min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1])]


def _transform_point_for_zoom(pt, zoom_rect, src_w, src_h):
    """Map source-pixel point into zoomed viewport coordinates."""
    zx1, zy1, zx2, zy2 = zoom_rect
    zw = max(1.0, float(zx2 - zx1))
    zh = max(1.0, float(zy2 - zy1))
    return [int(round((pt[0] - zx1) * src_w / zw)), int(round((pt[1] - zy1) * src_h / zh))]


def _transform_rect_for_zoom(rect, zoom_rect, src_w, src_h):
    """Map source-pixel rect into zoomed viewport coordinates."""
    p1 = _transform_point_for_zoom([rect[0], rect[1]], zoom_rect, src_w, src_h)
    p2 = _transform_point_for_zoom([rect[2], rect[3]], zoom_rect, src_w, src_h)
    return [p1[0], p1[1], p2[0], p2[1]]


def _rects_overlap(a, b, pad=8):
    return not (a[2] + pad < b[0] or a[0] - pad > b[2] or a[3] + pad < b[1] or a[1] - pad > b[3])


def _overlap_area(a, b, pad=6):
    """Compute intersection area between two boxes expanded by pad."""
    ix1 = max(a[0] - pad, b[0])
    iy1 = max(a[1] - pad, b[1])
    ix2 = min(a[2] + pad, b[2])
    iy2 = min(a[3] + pad, b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0
    return (ix2 - ix1) * (iy2 - iy1)


def _resolve_branding_rect(branding_text, fonts, canvas_w, canvas_h, source_h, ui_scale, recipe_cfg, has_logo=False):
    """Compute bounding rect for branding pill in any corner."""
    pos = recipe_cfg.get("branding_position", "top-right")
    if (not branding_text and not has_logo) or pos == "hidden":
        return None
    tw, th = _text_size(fonts["tag"], branding_text)
    pad_x = int(round(18 * ui_scale))
    logo_extra = int(round(32 * ui_scale)) if has_logo else 0
    pill_w = max(int(round(160 * ui_scale)), tw + pad_x * 2 + logo_extra)
    pill_h = max(int(round(34 * ui_scale)), th + int(round(14 * ui_scale)))
    margin_x = int(round(20 * ui_scale))
    default_y = int(round((8 if source_h < 1000 else 18) * ui_scale))
    y_override = recipe_cfg.get("branding_y")
    margin_y = int(y_override) if y_override is not None else default_y

    if "left" in pos:
        x1 = margin_x
    else:
        x1 = max(margin_x, canvas_w - pill_w - margin_x)

    if "bottom" in pos:
        y1 = max(8, canvas_h - pill_h - margin_y)
    else:
        y1 = max(8, margin_y)

    return [x1, y1, x1 + pill_w, y1 + pill_h]


def _layout_dock_content(spec, fonts, target_w, ui_scale, max_sub_lines=2):
    """Compute wrapped subtitle lines, dynamic height, and fitted width for HUD dock."""
    step_text = spec.get("step_num", "")
    title_text = spec.get("step_title", "")
    sub_text = spec.get("sub", "")

    pad_x = int(round(20 * ui_scale))
    pad_y = int(round(12 * ui_scale))
    gap_y = int(round(8 * ui_scale))
    gap_x = int(round(14 * ui_scale))

    badge_pad_x = int(round(22 * ui_scale))
    badge_h = max(int(round(28 * ui_scale)), _text_size(fonts["step"], step_text or "STEP")[1] + int(round(12 * ui_scale)))
    badge_w = (_text_size(fonts["step"], step_text)[0] + badge_pad_x) if step_text else 0

    title_avail = max(140, target_w - pad_x * 2 - (badge_w + gap_x if badge_w else 0))
    title_font = _fit_font_for_width(title_text, fonts["title"], title_avail, min_size=max(12, int(round(15 * ui_scale))))
    title_w, title_h = _text_size(title_font, title_text)

    row1_h = max(badge_h if step_text else 0, title_h)
    row1_content_w = (badge_w + (gap_x if step_text and title_text else 0) + title_w)

    sub_avail = max(160, target_w - pad_x * 2)
    min_sub_sz = max(12, int(round(15 * ui_scale)))
    sub_font = fonts["sub"]
    sub_lines = []
    if sub_text:
        sub_lines, was_truncated = _wrap_text(sub_text, sub_font, sub_avail, max_lines=max_sub_lines)
        font_path = getattr(sub_font, "path", None)
        cur_sz = getattr(sub_font, "size", 22)
        while font_path and cur_sz > min_sub_sz and was_truncated:
            cur_sz -= 2
            cand = _make_font(font_path, cur_sz)
            cand_lines, cand_trunc = _wrap_text(sub_text, cand, sub_avail, max_lines=max_sub_lines)
            if not cand_trunc or cur_sz <= min_sub_sz:
                sub_font = cand
                sub_lines = cand_lines
                break

    line_h = _text_size(sub_font, "Ag")[1] + int(round(5 * ui_scale)) if sub_lines else 0
    sub_block_h = line_h * len(sub_lines) if sub_lines else 0
    max_sub_line_w = max((_text_size(sub_font, l)[0] for l in sub_lines), default=0)

    content_w = max(row1_content_w, max_sub_line_w) + pad_x * 2
    dock_h = pad_y * 2 + row1_h + (gap_y + sub_block_h if row1_h and sub_block_h else sub_block_h)
    dock_h = max(int(round(64 * ui_scale)), dock_h)

    return {
        "target_w": target_w,
        "content_w": min(target_w, max(int(round(300 * ui_scale)), content_w)),
        "dock_h": dock_h,
        "pad_x": pad_x,
        "pad_y": pad_y,
        "gap_x": gap_x,
        "gap_y": gap_y,
        "badge_w": badge_w,
        "badge_h": badge_h,
        "row1_h": row1_h,
        "title_font": title_font,
        "sub_font": sub_font,
        "sub_lines": sub_lines,
        "line_h": line_h,
    }


def _collect_colliders(spec, src_w, src_h, ui_scale, branding_rect, recipe, zoom_rect=None):
    """Collect active boxes, labels, arrows (including bounce range), branding, and avoid_rects."""
    colliders = []
    for b in spec.get("boxes", []):
        r = _scale_rect(b["rect"], src_w, src_h, recipe)
        if zoom_rect is not None:
            r = _transform_rect_for_zoom(r, zoom_rect, src_w, src_h)
        colliders.append(r)
        if b.get("label"):
            lh = int(round(30 * ui_scale))
            colliders.append([r[0], max(0, r[1] - lh - 4), r[0] + int(round(180 * ui_scale)), r[1]])

    for a in spec.get("arrows", []):
        p_from = _scale_coord_pair(a["from"], src_w, src_h, recipe)
        p_to = _scale_coord_pair(a["to"], src_w, src_h, recipe)
        if zoom_rect is not None:
            p_from = _transform_point_for_zoom(p_from, zoom_rect, src_w, src_h)
            p_to = _transform_point_for_zoom(p_to, zoom_rect, src_w, src_h)
        bounce_pad = int(round(a.get("bounce_amp", 5.0) * ui_scale)) + int(round(24 * ui_scale))
        colliders.append([
            min(p_from[0], p_to[0]) - bounce_pad,
            min(p_from[1], p_to[1]) - bounce_pad,
            max(p_from[0], p_to[0]) + bounce_pad,
            max(p_from[1], p_to[1]) + bounce_pad,
        ])
        if a.get("tag"):
            tp = a.get("tag_pos")
            if tp and tp != "auto":
                tp_px = _scale_coord_pair(tp, src_w, src_h, recipe)
                if zoom_rect is not None:
                    tp_px = _transform_point_for_zoom(tp_px, zoom_rect, src_w, src_h)
            else:
                dx = p_to[0] - p_from[0]
                dy = p_to[1] - p_from[1]
                length = max(1e-5, math.hypot(dx, dy))
                ux, uy = dx / length, dy / length
                tp_px = [int(round(p_from[0] - ux * 60 * ui_scale)), int(round(p_from[1] - uy * 26 * ui_scale))]
            colliders.append([
                tp_px[0] - int(round(90 * ui_scale)),
                tp_px[1] - int(round(24 * ui_scale)),
                tp_px[0] + int(round(90 * ui_scale)),
                tp_px[1] + int(round(24 * ui_scale)),
            ])

    for ar in spec.get("avoid_rects", []):
        r = _scale_rect(ar, src_w, src_h, recipe)
        if zoom_rect is not None:
            r = _transform_rect_for_zoom(r, zoom_rect, src_w, src_h)
        colliders.append(r)

    if branding_rect:
        colliders.append(branding_rect)

    return colliders


def _resolve_dock_placement(
    spec,
    canvas_w,
    canvas_h,
    stage_x,
    stage_y,
    src_w,
    src_h,
    pad_bottom,
    fonts,
    ui_scale,
    branding_rect,
    recipe,
    zoom_rect=None,
):
    """Choose optimal non-overlapping dock size and placement across 8 screen zones."""
    if not spec or spec.get("hide_dock"):
        return None, None, "hidden"
    pos = spec.get("dock_position", recipe.get("dock_position", "auto"))
    if pos == "hidden":
        return None, None, "hidden"
    if not (spec.get("step_num") or spec.get("step_title") or spec.get("sub")):
        return None, None, "hidden"

    margin_x = max(12, int(round(24 * ui_scale)))
    margin_y = max(10, int(round(14 * ui_scale)))
    max_sub_lines = int(spec.get("max_sub_lines", recipe.get("max_sub_lines", 2)))
    width_mode = spec.get("dock_width_mode", recipe.get("dock_width_mode", "auto"))
    explicit_w = spec.get("dock_w", recipe.get("dock_w"))
    explicit_x = spec.get("dock_x", recipe.get("dock_x"))
    explicit_y = spec.get("dock_y", recipe.get("dock_y"))

    wide_cap = min(int(round(1320 * max(ui_scale, canvas_w / 1920.0))), max(320, canvas_w - margin_x * 2))
    if explicit_w is not None:
        wide_w = max(280, min(int(explicit_w), canvas_w - margin_x * 2))
    else:
        wide_w = wide_cap

    # Dedicated bottom stage bar (never collides with app UI)
    if pad_bottom > 0 and pos in ("auto", "bottom", "below"):
        layout = _layout_dock_content(spec, fonts, wide_w, ui_scale, max_sub_lines=max_sub_lines)
        dock_w = layout["content_w"] if (width_mode == "auto" and explicit_w is None) else wide_w
        dock_w = max(min(wide_w, int(round(480 * ui_scale))), dock_w)
        dock_h = layout["dock_h"]
        stage_bottom_start = stage_y + src_h
        dock_y = stage_bottom_start + max(6, (pad_bottom - dock_h) // 2)
        dock_x = int(explicit_x) if explicit_x is not None else (canvas_w - dock_w) // 2
        dock_x = max(margin_x, min(dock_x, canvas_w - dock_w - margin_x))
        return [dock_x, dock_y, dock_x + dock_w, dock_y + dock_h], layout, "below-stage"

    # Overlay mode: compute colliders shifted by stage offset
    raw_colliders = _collect_colliders(spec, src_w, src_h, ui_scale, None, recipe, zoom_rect=zoom_rect)
    colliders = [[c[0] + stage_x, c[1] + stage_y, c[2] + stage_x, c[3] + stage_y] for c in raw_colliders]
    if branding_rect:
        colliders.append(branding_rect)

    # Explicit X/Y placement
    if explicit_y is not None:
        layout = _layout_dock_content(spec, fonts, wide_w, ui_scale, max_sub_lines=max_sub_lines)
        dock_w = layout["content_w"] if (width_mode == "auto" and explicit_w is None) else wide_w
        dock_h = layout["dock_h"]
        dock_x = int(explicit_x) if explicit_x is not None else (canvas_w - dock_w) // 2
        dock_x = max(margin_x, min(dock_x, canvas_w - dock_w - margin_x))
        dock_y = max(margin_y, min(int(explicit_y), canvas_h - dock_h - margin_y))
        return [dock_x, dock_y, dock_x + dock_w, dock_y + dock_h], layout, "explicit"

    wide_layout = _layout_dock_content(spec, fonts, wide_w, ui_scale, max_sub_lines=max_sub_lines)
    compact_cap = max(int(round(360 * ui_scale)), int(canvas_w * 0.46))
    compact_w = min(wide_w, compact_cap)
    compact_layout = _layout_dock_content(spec, fonts, compact_w, ui_scale, max_sub_lines=max_sub_lines + 1)

    def make_candidate(zone_name):
        is_compact = zone_name.endswith("-left") or zone_name.endswith("-right")
        lay = compact_layout if is_compact else wide_layout
        dw = lay["content_w"] if (width_mode == "auto" and explicit_w is None) else lay["target_w"]
        if not is_compact:
            dw = max(min(wide_w, int(round(480 * ui_scale))), dw)
        dh = lay["dock_h"]

        if zone_name.endswith("-left"):
            dx = margin_x
        elif zone_name.endswith("-right"):
            dx = canvas_w - dw - margin_x
        else:
            dx = (canvas_w - dw) // 2

        if zone_name.startswith("top"):
            dy = margin_y
        elif zone_name.startswith("mid"):
            dy = max(margin_y, (canvas_h - dh) // 2)
        else:
            dy = max(margin_y, canvas_h - dh - margin_y)

        if explicit_x is not None:
            dx = max(margin_x, min(int(explicit_x), canvas_w - dw - margin_x))
        return [dx, dy, dx + dw, dy + dh], lay, zone_name

    zone_order = [
        "bottom-center",
        "top-center",
        "bottom-left",
        "bottom-right",
        "top-left",
        "top-right",
        "mid-left",
        "mid-right",
    ]
    if pos in zone_order:
        zone_order = [pos] + [z for z in zone_order if z != pos]
    elif pos == "bottom":
        pass
    elif pos == "top":
        zone_order = ["top-center", "top-left", "top-right", "bottom-center", "bottom-left", "bottom-right", "mid-left", "mid-right"]

    best = None
    best_area = None
    for z in zone_order:
        rect, lay, name = make_candidate(z)
        total_area = sum(_overlap_area(rect, c, pad=int(round(8 * ui_scale))) for c in colliders)
        if total_area == 0:
            return rect, lay, name
        if best is None or total_area < best_area:
            best = (rect, lay, name)
            best_area = total_area

    return best


def _ease_in_out(progress):
    p = max(0.0, min(1.0, progress))
    return p * p * (3.0 - 2.0 * p)


def _compute_active_zoom_rect(spec, t, src_w, src_h, recipe):
    """Interpolate smooth zoom crop rectangle if step defines a zoom block."""
    zoom = spec.get("zoom") if spec else None
    if not zoom or "rect" not in zoom:
        return None
    target_rect = _scale_rect(zoom["rect"], src_w, src_h, recipe)
    # Keep aspect ratio matched to source frame to prevent stretching
    tx1, ty1, tx2, ty2 = target_rect
    tw = max(40, tx2 - tx1)
    th = max(40, ty2 - ty1)
    src_ar = src_w / float(max(1, src_h))
    if tw / float(th) > src_ar:
        new_h = int(round(tw / src_ar))
        cy = (ty1 + ty2) // 2
        ty1, ty2 = cy - new_h // 2, cy + new_h // 2
    else:
        new_w = int(round(th * src_ar))
        cx = (tx1 + tx2) // 2
        tx1, tx2 = cx - new_w // 2, cx + new_w // 2

    tw = min(src_w, tx2 - tx1)
    th = min(src_h, ty2 - ty1)
    tx1 = max(0, min(tx1, src_w - tw))
    ty1 = max(0, min(ty1, src_h - th))
    fitted = [tx1, ty1, tx1 + tw, ty1 + th]

    trans = float(zoom.get("transition_sec", 0.45))
    start_t = float(spec.get("active_start", t))
    if trans <= 0 or not zoom.get("ease", True):
        return fitted
    prog = _ease_in_out((t - start_t) / trans)
    return [
        int(round(0 + prog * fitted[0])),
        int(round(0 + prog * fitted[1])),
        int(round(src_w + prog * (fitted[2] - src_w))),
        int(round(src_h + prog * (fitted[3] - src_h))),
    ]


def compute_canvas_geometry(source_w, source_h, recipe, max_dock_h=92):
    """Compute target canvas dimensions, bottom stage pad, and framing offsets."""
    dock_mode = recipe.get("dock_mode", "auto")
    aspect_ratio = source_w / float(max(1, source_h))
    ui_scale = compute_ui_scale(source_w, source_h, recipe)
    margin_y = max(12, int(round(16 * ui_scale)))

    if "pad_bottom" in recipe:
        pad_bottom = int(recipe["pad_bottom"])
    elif dock_mode == "below" or (dock_mode == "auto" and aspect_ratio > 1.85):
        needed_pad = max_dock_h + margin_y * 2
        if source_w == 1920 and 860 <= source_h <= 960 and recipe.get("snap_1080", True):
            pad_bottom = max(needed_pad, 1080 - source_h)
        else:
            pad_bottom = needed_pad
    else:
        pad_bottom = 0

    base_w = source_w
    base_h = source_h + pad_bottom
    target_aspect = recipe.get("target_aspect", "native")
    aspect_map = {"16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "1:1": 1.0}

    canvas_w, canvas_h = base_w, base_h
    stage_x, stage_y = 0, 0
    if target_aspect in aspect_map:
        desired_ar = aspect_map[target_aspect]
        cur_ar = base_w / float(max(1, base_h))
        if cur_ar < desired_ar - 1e-3:
            canvas_w = int(math.ceil(base_h * desired_ar))
            canvas_w += canvas_w % 2
            stage_x = (canvas_w - base_w) // 2
        elif cur_ar > desired_ar + 1e-3:
            canvas_h = int(math.ceil(base_w / desired_ar))
            canvas_h += canvas_h % 2
            stage_y = (canvas_h - base_h) // 2

    # Ensure even dimensions for x264 yuv420p compatibility
    canvas_w += canvas_w % 2
    canvas_h += canvas_h % 2
    return {
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "stage_x": stage_x,
        "stage_y": stage_y,
        "pad_bottom": pad_bottom,
    }


def _draw_spotlight_dim(overlay_draw, canvas_w, canvas_h, boxes, dim_opacity):
    """Draw semi-transparent dim mask over canvas with cutouts for active highlights."""
    alpha = max(0, min(230, int(round(dim_opacity * 255))))
    mask = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, alpha))
    mdraw = ImageDraw.Draw(mask)
    for b in boxes:
        r = b["_screen_rect"]
        shape = b.get("shape", "rect")
        pad = 6
        cr = [r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad]
        if shape == "circle":
            cx, cy = (cr[0] + cr[2]) // 2, (cr[1] + cr[3]) // 2
            rad = max(cr[2] - cr[0], cr[3] - cr[1]) // 2
            mdraw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(0, 0, 0, 0))
        elif shape == "pill":
            rad = max(8, min(cr[2] - cr[0], cr[3] - cr[1]) // 2)
            mdraw.rounded_rectangle(cr, radius=rad, fill=(0, 0, 0, 0))
        else:
            mdraw.rounded_rectangle(cr, radius=12, fill=(0, 0, 0, 0))
    return mask


def draw_hud_overlay(
    base_rgb,
    spec,
    t,
    fonts,
    branding_text,
    geometry,
    theme,
    recipe,
    ui_scale,
    logo_img=None,
):
    """Composite dynamic branding, spotlight, highlights, arrows, and collision-free dock."""
    src_h, src_w = base_rgb.shape[:2]
    zoom_rect = _compute_active_zoom_rect(spec, t, src_w, src_h, recipe)
    work_rgb = base_rgb
    if zoom_rect is not None:
        zx1, zy1, zx2, zy2 = zoom_rect
        crop = base_rgb[zy1:zy2, zx1:zx2]
        if crop.size > 0:
            work_rgb = cv2.resize(crop, (src_w, src_h), interpolation=cv2.INTER_LANCZOS4)

    canvas_w = geometry["canvas_w"]
    canvas_h = geometry["canvas_h"]
    stage_x = geometry["stage_x"]
    stage_y = geometry["stage_y"]
    pad_bottom = geometry["pad_bottom"]

    stage_bg = tuple(theme.get("stage_bg", [10, 16, 32])[:3])
    if canvas_w != src_w or canvas_h != src_h:
        canvas = np.full((canvas_h, canvas_w, 3), stage_bg, dtype=np.uint8)
        canvas[stage_y : stage_y + src_h, stage_x : stage_x + src_w, :] = work_rgb
        if pad_bottom > 0:
            div_color = tuple(theme.get("stage_divider", [0, 132, 255])[:3])
            div_y = stage_y + src_h
            canvas[div_y : min(div_y + 2, canvas_h), stage_x : stage_x + src_w, :] = div_color
        im = Image.fromarray(canvas)
    else:
        im = Image.fromarray(work_rgb)

    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Branding Pill (+ optional PNG logo)
    branding_rect = _resolve_branding_rect(
        branding_text, fonts, canvas_w, canvas_h, src_h, ui_scale, recipe, has_logo=(logo_img is not None)
    )

    # Prepare scaled screen coordinates for boxes
    prepared_boxes = []
    if spec:
        for b in spec.get("boxes", []):
            r = _scale_rect(b["rect"], src_w, src_h, recipe)
            if zoom_rect is not None:
                r = _transform_rect_for_zoom(r, zoom_rect, src_w, src_h)
            sr = [r[0] + stage_x, r[1] + stage_y, r[2] + stage_x, r[3] + stage_y]
            b_copy = dict(b)
            b_copy["_screen_rect"] = sr
            prepared_boxes.append(b_copy)

    # Optional Spotlight dimming around target boxes
    use_spotlight = (spec.get("spotlight") if spec and "spotlight" in spec else recipe.get("spotlight", False))
    if use_spotlight and prepared_boxes:
        dim_op = float((spec or {}).get("dim_opacity", recipe.get("dim_opacity", 0.45)))
        mask = _draw_spotlight_dim(draw, canvas_w, canvas_h, prepared_boxes, dim_op)
        overlay = Image.alpha_composite(overlay, mask)
        draw = ImageDraw.Draw(overlay)

    # Draw Highlights (rect, circle, pill, underline)
    for b in prepared_boxes:
        r = b["_screen_rect"]
        color = b.get("color", theme["box_color"])
        glow = b.get("glow", theme["box_glow"])
        shape = b.get("shape", "rect")
        stroke_w = max(2, int(round(b.get("width", 4) * ui_scale)))
        glow_layers = int(b.get("glow_layers", 5))
        pulse_mult = (0.65 + 0.35 * math.sin(t * 5.0)) if b.get("pulse", False) else 1.0

        if shape == "underline":
            uy = r[3] + int(round(3 * ui_scale))
            for i in range(glow_layers, 0, -1):
                alpha = int(32 * (glow_layers + 1 - i) / max(1, glow_layers) * pulse_mult)
                draw.line([(r[0], uy + i), (r[2], uy + i)], fill=(glow[0], glow[1], glow[2], alpha), width=stroke_w + i * 2)
            draw.line([(r[0], uy), (r[2], uy)], fill=(color[0], color[1], color[2], 255), width=stroke_w)
        elif shape == "circle":
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            rad = max(10, max(r[2] - r[0], r[3] - r[1]) // 2 + int(round(4 * ui_scale)))
            for i in range(glow_layers, 0, -1):
                alpha = int(30 * (glow_layers + 1 - i) / max(1, glow_layers) * pulse_mult)
                er = rad + i * int(round(2 * ui_scale))
                draw.ellipse([cx - er, cy - er, cx + er, cy + er], outline=(glow[0], glow[1], glow[2], alpha), width=2)
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(color[0], color[1], color[2], 255), width=stroke_w)
        else:
            rad = max(6, min(r[2] - r[0], r[3] - r[1]) // 2) if shape == "pill" else int(round(b.get("radius", 10) * ui_scale))
            for i in range(glow_layers, 0, -1):
                alpha = int(30 * (glow_layers + 1 - i) / max(1, glow_layers) * pulse_mult)
                step_px = max(1, int(round(2 * ui_scale))) * i
                draw.rounded_rectangle(
                    [r[0] - step_px, r[1] - step_px, r[2] + step_px, r[3] + step_px],
                    radius=rad + int(round(4 * ui_scale)),
                    outline=(glow[0], glow[1], glow[2], alpha),
                    width=max(1, int(round(2 * ui_scale))),
                )
            draw.rounded_rectangle(r, radius=rad, outline=(color[0], color[1], color[2], 255), width=stroke_w)

        if b.get("label"):
            lbl = b["label"]
            lw_txt, lh_txt = _text_size(fonts["card_tag"], lbl)
            lw = lw_txt + int(round(24 * ui_scale))
            lh = max(int(round(26 * ui_scale)), lh_txt + int(round(10 * ui_scale)))
            lx1 = max(4, min(r[0] + int(round(12 * ui_scale)), canvas_w - lw - 4))
            ly1 = r[1] - lh - 4 if r[1] >= lh + 8 else r[1] + 6
            draw.rounded_rectangle(
                [lx1, ly1, lx1 + lw, ly1 + lh],
                radius=max(4, int(round(6 * ui_scale))),
                fill=tuple(theme["box_label_bg"]),
                outline=tuple(theme["box_label_border"]),
                width=1,
            )
            _draw_text_in_box(draw, lx1, ly1, lw, lh, lbl, fonts["card_tag"], tuple(theme["box_label_text"]), align="center")

    # Pulsing Directional & Arbitrary-Angle Arrows
    if spec:
        for a in spec.get("arrows", []):
            p_from = _scale_coord_pair(a["from"], src_w, src_h, recipe)
            p_to = _scale_coord_pair(a["to"], src_w, src_h, recipe)
            if zoom_rect is not None:
                p_from = _transform_point_for_zoom(p_from, zoom_rect, src_w, src_h)
                p_to = _transform_point_for_zoom(p_to, zoom_rect, src_w, src_h)
            p_from = [p_from[0] + stage_x, p_from[1] + stage_y]
            p_to = [p_to[0] + stage_x, p_to[1] + stage_y]

            direction = a.get("dir", "auto")
            dx = p_to[0] - p_from[0]
            dy = p_to[1] - p_from[1]
            if direction == "left":
                ux, uy = -1.0, 0.0
            elif direction == "right":
                ux, uy = 1.0, 0.0
            elif direction == "up":
                ux, uy = 0.0, -1.0
            elif direction == "down":
                ux, uy = 0.0, 1.0
            else:
                length = max(1e-5, math.hypot(dx, dy))
                ux, uy = dx / length, dy / length

            amp = float(a.get("bounce_amp", 5.0)) * ui_scale
            speed = float(a.get("bounce_speed", 7.5))
            bounce = math.sin(t * speed) * amp
            bx = int(round(ux * bounce))
            by = int(round(uy * bounce))

            p_from_b = (p_from[0] + bx, p_from[1] + by)
            p_to_b = (p_to[0] + bx, p_to[1] + by)
            arrow_color = tuple(a.get("color", theme["arrow_color"]))
            shaft_w = max(2, int(round(a.get("width", 6) * ui_scale)))
            head_len = max(10, int(round(22 * ui_scale)))
            head_half_w = max(6, int(round(14 * ui_scale)))

            # Trim shaft slightly before tip so round/square cap never sticks past triangle tip
            shaft_end = (int(round(p_to_b[0] - ux * (head_len * 0.65))), int(round(p_to_b[1] - uy * (head_len * 0.65))))
            draw.line([p_from_b, shaft_end], fill=arrow_color, width=shaft_w)

            perp_x, perp_y = -uy, ux
            base_x = p_to_b[0] - ux * head_len
            base_y = p_to_b[1] - uy * head_len
            head = [
                p_to_b,
                (int(round(base_x + perp_x * head_half_w)), int(round(base_y + perp_y * head_half_w))),
                (int(round(base_x - perp_x * head_half_w)), int(round(base_y - perp_y * head_half_w))),
            ]
            draw.polygon(head, fill=arrow_color)

            tag_text = a.get("tag", "")
            if tag_text:
                tw_txt, th_txt = _text_size(fonts["tag"], tag_text)
                tw = tw_txt + int(round(24 * ui_scale))
                th = max(int(round(32 * ui_scale)), th_txt + int(round(14 * ui_scale)))
                tp_raw = a.get("tag_pos")
                if not tp_raw or tp_raw == "auto":
                    tp = [
                        int(round(p_from[0] - ux * (tw * 0.5 + 10 * ui_scale))),
                        int(round(p_from[1] - uy * (th * 0.5 + 10 * ui_scale))),
                    ]
                else:
                    tp_sc = _scale_coord_pair(tp_raw, src_w, src_h, recipe)
                    if zoom_rect is not None:
                        tp_sc = _transform_point_for_zoom(tp_sc, zoom_rect, src_w, src_h)
                    tp = [tp_sc[0] + stage_x, tp_sc[1] + stage_y]

                tp_b = (tp[0] + bx, tp[1] + by)
                tx1 = max(4, min(tp_b[0] - tw // 2, canvas_w - tw - 4))
                ty1 = max(4, min(tp_b[1] - th // 2, canvas_h - th - 4))
                draw.rounded_rectangle(
                    [tx1, ty1, tx1 + tw, ty1 + th],
                    radius=max(5, int(round(8 * ui_scale))),
                    fill=tuple(a.get("tag_bg", theme["arrow_tag_bg"])),
                    outline=tuple(theme["arrow_tag_border"]),
                    width=1,
                )
                _draw_text_in_box(
                    draw, tx1, ty1, tw, th, tag_text, fonts["tag"],
                    tuple(a.get("tag_color", theme["arrow_tag_text"])), align="center"
                )

    # Branding Pill render
    if branding_rect:
        bx1, by1, bx2, by2 = branding_rect
        draw.rounded_rectangle(
            branding_rect,
            radius=max(5, int(round(8 * ui_scale))),
            fill=tuple(theme["branding_bg"]),
            outline=tuple(theme["branding_border"]),
            width=1,
        )
        text_x = bx1 + int(round(16 * ui_scale))
        if logo_img is not None:
            lh_target = max(16, (by2 - by1) - int(round(10 * ui_scale)))
            lw_target = max(16, int(round(logo_img.width * (lh_target / float(max(1, logo_img.height))))))
            resized_logo = logo_img.resize((lw_target, lh_target), Image.Resampling.LANCZOS)
            ly_off = by1 + ((by2 - by1) - lh_target) // 2
            overlay.paste(resized_logo, (text_x, ly_off), resized_logo)
            text_x += lw_target + int(round(10 * ui_scale))
        if branding_text:
            _draw_text_in_box(
                draw, text_x, by1, max(1, bx2 - text_x), by2 - by1,
                branding_text, fonts["tag"], tuple(theme["branding_text"]), align="left"
            )

    # Adaptive Collision-Aware HUD Dock
    dock_rect, dock_layout, _ = _resolve_dock_placement(
        spec,
        canvas_w,
        canvas_h,
        stage_x,
        stage_y,
        src_w,
        src_h,
        pad_bottom,
        fonts,
        ui_scale,
        branding_rect,
        recipe,
        zoom_rect=zoom_rect,
    )
    if dock_rect and dock_layout:
        dx1, dy1, dx2, dy2 = dock_rect
        draw.rounded_rectangle(
            dock_rect,
            radius=max(8, int(round(14 * ui_scale))),
            fill=tuple(theme["dock_bg"]),
            outline=tuple(theme["dock_border"]),
            width=max(1, int(round(2 * ui_scale))),
        )
        px = dx1 + dock_layout["pad_x"]
        py = dy1 + dock_layout["pad_y"]

        step_text = spec.get("step_num", "")
        if step_text:
            bw = dock_layout["badge_w"]
            bh = dock_layout["badge_h"]
            complete_kws = [k.upper() for k in theme.get("complete_keywords", ["COMPLETE", "SUCCESS"])]
            is_done = step_text.strip().upper() in complete_kws
            badge_color = tuple(theme["badge_complete_bg"] if is_done else theme["badge_bg"])
            draw.rounded_rectangle([px, py, px + bw, py + bh], radius=max(4, int(round(6 * ui_scale))), fill=badge_color)
            _draw_text_in_box(draw, px, py, bw, bh, step_text, fonts["step"], tuple(theme["badge_text"]), align="center")
            title_x = px + bw + dock_layout["gap_x"]
        else:
            title_x = px

        title_text = spec.get("step_title", "")
        if title_text:
            _draw_text_in_box(
                draw, title_x, py, max(1, dx2 - title_x - dock_layout["pad_x"]), dock_layout["row1_h"],
                title_text, dock_layout["title_font"], tuple(theme["title_text"]), align="left"
            )

        sub_y = py + dock_layout["row1_h"] + (dock_layout["gap_y"] if dock_layout["row1_h"] else 0)
        for line in dock_layout["sub_lines"]:
            if line:
                draw.text((px, sub_y), line, font=dock_layout["sub_font"], fill=tuple(theme["sub_text"]))
                sub_y += dock_layout["line_h"]

    return np.array(Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB"))


def get_natural_sorted_files(folder):
    files = glob.glob(os.path.join(folder, "*.*"))
    exts = (".jpg", ".jpeg", ".png", ".webp")
    image_files = [f for f in files if f.lower().endswith(exts)]

    def natural_key(text):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]

    return sorted(image_files, key=natural_key)


def extract_frames_from_video(video_path, frames_dir, fps_extracted=3.0, pattern="%04d_frame.png", force=False):
    """Extract frames at fps_extracted using bundled FFmpeg (skips if frames exist unless force=True)."""
    if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError(f"Cannot extract frames; source video not found: {video_path}")

    os.makedirs(frames_dir, exist_ok=True)
    existing = get_natural_sorted_files(frames_dir)
    if existing and not force:
        print(f"[FRAMES] Reusing {len(existing)} existing extracted frames in: {frames_dir}")
        return existing

    if force and existing:
        for f in existing:
            try:
                os.remove(f)
            except OSError:
                pass

    out_pattern = os.path.join(frames_dir, pattern)
    fps_str = f"{fps_extracted:g}"
    print(f"[FRAMES] Extracting {fps_str} FPS frames via FFmpeg -> {frames_dir}")
    cmd = [
        FFMPEG_EXE, "-y",
        "-i", video_path,
        "-vf", f"fps={fps_str}",
        out_pattern,
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg frame extraction failed (exit {res.returncode}):\n{res.stderr}")

    extracted = get_natural_sorted_files(frames_dir)
    if not extracted:
        raise RuntimeError(f"FFmpeg ran without error but extracted 0 frames into: {frames_dir}")
    print(f"  • Extracted {len(extracted)} frames ({len(extracted) / float(fps_extracted):.2f}s @ {fps_str} fps).")
    return extracted


def analyze_frames_folder(frames_dir, video_path=None, fps_extracted=3.0, quiet=False):
    """Fast analysis of a 3 FPS extracted frames folder."""
    frame_files = get_natural_sorted_files(frames_dir)
    if not frame_files:
        raise FileNotFoundError(f"No image frames found in {frames_dir}")

    count = len(frame_files)
    duration_sec = count / float(fps_extracted)
    first_img = cv2.imread(frame_files[0])
    h, w, _ = first_img.shape

    if not quiet:
        print(f"\n==========================================")
        print(f"  {fps_extracted:g} FPS FRAMES DIRECTORY ANALYSIS")
        print(f"==========================================")
        print(f"Frames Folder    : {frames_dir}")
        print(f"Extracted Rate   : {fps_extracted:.2f} fps (1 frame = {1.0 / fps_extracted:.3f}s)")
        print(f"Total Frames     : {count}")
        print(f"Estimated Length : {duration_sec:.2f} seconds ({duration_sec / 60.0:.2f} mins)")
        print(f"Resolution       : {w} x {h}")
        if video_path and os.path.exists(video_path):
            print(f"Source Video     : {video_path}")
        print(f"==========================================\n")

    return {
        "count": count,
        "duration": duration_sec,
        "width": w,
        "height": h,
        "fps_extracted": fps_extracted,
        "frame_files": frame_files,
    }


def scaffold_recipe_from_frames(frames_dir, out_recipe_path, video_path=None, fps_extracted=3.0, diff_threshold=0.06):
    """Auto-detect page/UI transitions across frames and emit a starter recipe.json."""
    info = analyze_frames_folder(frames_dir, video_path=video_path, fps_extracted=fps_extracted, quiet=True)
    files = info["frame_files"]
    prev_small = None
    transitions = [0]

    for idx, fpath in enumerate(files):
        img = cv2.imread(fpath)
        if img is None:
            continue
        gray = cv2.cvtColor(cv2.resize(img, (160, 90)), cv2.COLOR_BGR2GRAY)
        if prev_small is not None:
            diff_ratio = float(np.mean(np.abs(gray.astype(np.float32) - prev_small.astype(np.float32)))) / 255.0
            if diff_ratio >= diff_threshold and (idx - transitions[-1]) >= max(2, int(round(fps_extracted * 1.5))):
                transitions.append(idx)
        prev_small = gray

    if transitions[-1] < len(files) - 1:
        transitions.append(len(files) - 1)

    # Cap scaffold steps cleanly if a video has lots of scrolling
    if len(transitions) > 20:
        step_stride = max(1, len(transitions) // 16)
        transitions = transitions[::step_stride]
        if transitions[-1] != len(files) - 1:
            transitions.append(len(files) - 1)

    timeline_mapping = []
    steps = []
    cur_out = 0.0
    for i in range(max(1, len(transitions) - 1)):
        f_s = transitions[i]
        f_e = transitions[i + 1] if i + 1 < len(transitions) else f_s
        seg_dur = max(3.5, round((f_e - f_s) / float(fps_extracted), 2))
        timeline_mapping.append({
            "start_sec": round(cur_out, 2),
            "end_sec": round(cur_out + seg_dur, 2),
            "source_frame_start_3fps": f_s,
            "source_frame_end_3fps": f_e,
        })
        step_id = "intro" if i == 0 else f"step{i}"
        step_num = "INTRO" if i == 0 else ("COMPLETE" if i == len(transitions) - 2 else f"STEP {i}")
        steps.append({
            "id": step_id,
            "start_time": round(cur_out + 0.3, 2),
            "active_start": round(cur_out, 2),
            "active_end": round(cur_out + seg_dur, 2),
            "step_num": step_num,
            "step_title": f"Action {i + 1} (Edit Title)",
            "narration": f"Describe action {i + 1} shown on screen.",
            "sub": f"Edit caption for frame {f_s + 1} to {f_e + 1}.",
            "boxes": [],
            "arrows": [],
        })
        cur_out += seg_dur

    recipe = {
        "source_video": video_path,
        "frames_dir": frames_dir,
        "fps_extracted": fps_extracted,
        "branding_text": "User Guide",
        "preset": "tech_hud",
        "tone": "professional",
        "default_voice": "en-IN-PrabhatNeural",
        "dock_mode": "auto",
        "dock_width_mode": "auto",
        "total_duration": "auto",
        "fps": 30,
        "background_music": True,
        "timeline_mapping": timeline_mapping,
        "steps": steps,
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_recipe_path)), exist_ok=True)
    with open(out_recipe_path, "w", encoding="utf-8") as f:
        json.dump(recipe, f, indent=2)
    print(f"[INIT] Scaffolded starter recipe ({len(steps)} steps) -> {out_recipe_path}")
    return out_recipe_path


def convert_3fps_steps_to_seconds(recipe, fps_extracted=3.0, reader_fps=None, reader_total_frames=None):
    """Resolve 3-FPS timing markers and source-frame indices to active reader framerate."""
    for step in recipe.get("steps", []):
        if "start_frame_3fps" in step and "start_time" not in step:
            step["start_time"] = step["start_frame_3fps"] / float(fps_extracted)
        if "active_start_frame_3fps" in step and "active_start" not in step:
            step["active_start"] = step["active_start_frame_3fps"] / float(fps_extracted)
        if "active_end_frame_3fps" in step and "active_end" not in step:
            step["active_end"] = step["active_end_frame_3fps"] / float(fps_extracted)

    timeline = recipe.get("timeline_mapping", [])
    explicit_src_fps = recipe.get("source_frame_fps")
    max_raw_frame = max(
        (max(seg.get("source_frame_start", 0), seg.get("source_frame_end", 0)) for seg in timeline),
        default=0,
    )

    for seg in timeline:
        if "start_frame_3fps" in seg and "start_sec" not in seg:
            seg["start_sec"] = seg["start_frame_3fps"] / float(fps_extracted)
        if "end_frame_3fps" in seg and "end_sec" not in seg:
            seg["end_sec"] = seg["end_frame_3fps"] / float(fps_extracted)

        if "source_frame_start_3fps" in seg and "source_frame_start" not in seg:
            ratio = (reader_fps / float(fps_extracted)) if reader_fps else 1.0
            seg["source_frame_start"] = int(round(seg["source_frame_start_3fps"] * ratio))
        if "source_frame_end_3fps" in seg and "source_frame_end" not in seg:
            ratio = (reader_fps / float(fps_extracted)) if reader_fps else 1.0
            seg["source_frame_end"] = int(round(seg["source_frame_end_3fps"] * ratio))

        # Auto-translate raw source_frame_start/end when recipe targets 30fps video vs 3fps folder (or vice versa)
        if reader_fps and "source_frame_start_3fps" not in seg:
            if explicit_src_fps:
                scale = reader_fps / float(explicit_src_fps)
            elif (
                reader_total_frames
                and abs(reader_fps - fps_extracted) < 0.25
                and recipe.get("source_video")
                and max_raw_frame > reader_total_frames
            ):
                # Recipe authored in ~30fps frame indices, now rendering from extracted 3fps folder
                assumed_video_fps = float(recipe.get("fps", 30.0))
                scale = reader_fps / assumed_video_fps
            else:
                scale = 1.0

            if abs(scale - 1.0) > 1e-3:
                seg["source_frame_start"] = int(round(seg["source_frame_start"] * scale))
                seg["source_frame_end"] = int(round(seg["source_frame_end"] * scale))

    return recipe


async def generate_step_audio(text, voice, rate, out_wav, pitch="+0Hz", use_cache=True):
    """Generate 44.1kHz mono WAV via Edge-TTS with optional metadata hash caching."""
    meta_path = out_wav + ".meta.json"
    sig = hashlib.sha256(f"{text}|{voice}|{rate}|{pitch}".encode("utf-8")).hexdigest()
    if use_cache and os.path.exists(out_wav) and os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as mf:
                if json.load(mf).get("sig") == sig:
                    with wave.open(out_wav, "r") as wf:
                        return wf.getnframes() / float(wf.getframerate()), True
        except Exception:
            pass

    import edge_tts

    tmp_mp3 = out_wav.replace(".wav", "_tmp.mp3")
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await comm.save(tmp_mp3)

    cmd = [FFMPEG_EXE, "-y", "-i", tmp_mp3, "-ar", "44100", "-ac", "1", out_wav]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(tmp_mp3):
        os.remove(tmp_mp3)

    with open(meta_path, "w", encoding="utf-8") as mf:
        json.dump({"sig": sig, "voice": voice, "rate": rate, "pitch": pitch}, mf)

    with wave.open(out_wav, "r") as wf:
        return wf.getnframes() / float(wf.getframerate()), False


def _prepare_external_audio(src_audio, out_wav, sample_rate=44100):
    """Convert any local audio/video audio track into 44.1kHz mono WAV."""
    cmd = [FFMPEG_EXE, "-y", "-i", src_audio, "-ar", str(sample_rate), "-ac", "1", out_wav]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0 or not os.path.exists(out_wav):
        return 0.0
    with wave.open(out_wav, "r") as wf:
        return wf.getnframes() / float(wf.getframerate())


def _read_wav_float(path, sample_rate=44100):
    with wave.open(path, "r") as wf:
        frames = wf.getnframes()
        data = wf.readframes(frames)
        return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def build_soundtrack(recipe, audio_dir, out_wav, total_duration, source_video=None):
    """Mix speech clips, optional source audio, and sidechain-ducked background music."""
    sample_rate = int(recipe.get("audio_sample_rate", 44100))
    total_samples = max(1, int(round(total_duration * sample_rate)))
    voice_buffer = np.zeros(total_samples, dtype=np.float32)

    for step in recipe.get("steps", []):
        clip_path = os.path.join(audio_dir, f"{step['id']}.wav")
        if not os.path.exists(clip_path):
            continue
        samples = _read_wav_float(clip_path, sample_rate) * float(step.get("volume", 1.0))
        start_idx = max(0, int(round(step["start_time"] * sample_rate)))
        end_idx = min(total_samples, start_idx + len(samples))
        copied = end_idx - start_idx
        if copied > 0:
            voice_buffer[start_idx:end_idx] += samples[:copied]

    # Optional original recording audio mix
    if recipe.get("source_audio", False) and source_video and os.path.exists(source_video):
        src_wav = os.path.join(audio_dir, "_source_audio.wav")
        if _prepare_external_audio(source_video, src_wav, sample_rate) > 0:
            src_samples = _read_wav_float(src_wav, sample_rate) * float(recipe.get("source_audio_volume", 0.25))
            n = min(total_samples, len(src_samples))
            voice_buffer[:n] += src_samples[:n]

    # Music configuration (supports both legacy background_music bool and full music dict)
    music_cfg = dict(recipe.get("music", {}))
    tone_cfg = TONE_PRESETS.get(recipe.get("tone", ""), {})
    music_enabled = music_cfg.get("enabled", recipe.get("background_music", True))

    if music_enabled:
        bg_buffer = np.zeros(total_samples, dtype=np.float32)
        music_src = music_cfg.get("source", "synth")
        if music_src != "synth" and os.path.exists(music_src):
            bg_wav = os.path.join(audio_dir, "_custom_music.wav")
            if _prepare_external_audio(music_src, bg_wav, sample_rate) > 0:
                raw_bg = _read_wav_float(bg_wav, sample_rate)
                if len(raw_bg) > 0:
                    reps = int(math.ceil(total_samples / float(len(raw_bg))))
                    bg_buffer = np.tile(raw_bg, reps)[:total_samples]
        else:
            chords = music_cfg.get(
                "chords",
                [
                    [261.63, 329.63, 392.00, 523.25],  # C
                    [196.00, 246.94, 293.66, 392.00],  # G
                    [220.00, 261.63, 329.63, 440.00],  # Am
                    [174.61, 220.00, 261.63, 349.23],  # F
                ],
            )
            chord_len = float(music_cfg.get("chord_len", 4.0))
            t = np.arange(total_samples) / float(sample_rate)
            for i in range(int(total_duration / max(0.5, chord_len)) + 2):
                c = chords[i % len(chords)]
                t_start = i * chord_len
                idx_start = int(t_start * sample_rate)
                idx_end = min(total_samples, int((t_start + chord_len) * sample_rate))
                if idx_start >= total_samples:
                    break
                t_seg = t[idx_start:idx_end] - t_start
                env = np.sin(np.pi * np.clip(t_seg / chord_len, 0, 1)) ** 0.6
                seg = np.zeros_like(t_seg)
                for freq in c:
                    seg += np.sin(2 * np.pi * freq * t_seg) * 0.25
                    seg += np.sin(2 * np.pi * freq * 2 * t_seg) * 0.05
                bg_buffer[idx_start:idx_end] += seg * env

        bg_peak = np.max(np.abs(bg_buffer))
        if bg_peak > 1e-6:
            bg_buffer = bg_buffer / bg_peak

        # Speech-activity sidechain ducking envelope (~250ms smooth window)
        base_gain = float(music_cfg.get("base_gain", tone_cfg.get("music_base_gain", 0.065)))
        duck_gain = float(music_cfg.get("duck_gain", tone_cfg.get("music_duck_gain", 0.025)))
        win = max(1, int(0.25 * sample_rate))
        speech_abs = np.abs(voice_buffer)
        kernel = np.ones(win, dtype=np.float32) / float(win)
        speech_env = np.convolve(speech_abs, kernel, mode="same")
        duck_factor = np.clip(speech_env * 12.0, 0.0, 1.0)
        gain_curve = base_gain * (1.0 - duck_factor) + duck_gain * duck_factor
        bg_buffer *= gain_curve

        # Apply fade-in and fade-out ONLY to background music (never cut speech tails)
        fade_in_samples = min(total_samples, int(round(float(music_cfg.get("fade_in_sec", 0.8)) * sample_rate)))
        if fade_in_samples > 1:
            bg_buffer[:fade_in_samples] *= np.linspace(0.0, 1.0, fade_in_samples, dtype=np.float32)

        fade_out_samples = min(total_samples, int(round(float(music_cfg.get("fade_out_sec", 1.5)) * sample_rate)))
        if fade_out_samples > 1:
            bg_buffer[-fade_out_samples:] *= np.linspace(1.0, 0.0, fade_out_samples, dtype=np.float32)

        mixed = voice_buffer * float(recipe.get("voice_volume", 0.95)) + bg_buffer
    else:
        mixed = voice_buffer * float(recipe.get("voice_volume", 0.98))

    max_val = np.max(np.abs(mixed))
    if max_val > 0.98:
        mixed = mixed / max_val * 0.98

    with wave.open(out_wav, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((mixed * 32767).astype(np.int16).tobytes())


def export_subtitles(recipe, out_path, fmt="srt"):
    """Export synchronized step subtitles to .srt or .vtt alongside the rendered video."""
    def fmt_ts(sec, vtt=False):
        ms = int(round(max(0.0, sec) * 1000))
        hrs = ms // 3600000
        mins = (ms % 3600000) // 60000
        secs = (ms % 60000) // 1000
        rem = ms % 1000
        sep = "." if vtt else ","
        return f"{hrs:02d}:{mins:02d}:{secs:02d}{sep}{rem:03d}"

    is_vtt = fmt.lower() == "vtt"
    lines = ["WEBVTT\n"] if is_vtt else []
    for idx, step in enumerate(recipe.get("steps", []), start=1):
        txt = step.get("sub") or step.get("narration") or step.get("step_title")
        if not txt:
            continue
        t0 = float(step.get("active_start", step.get("start_time", 0.0)))
        t1 = float(step.get("active_end", t0 + 3.0))
        if not is_vtt:
            lines.append(str(idx))
        lines.append(f"{fmt_ts(t0, is_vtt)} --> {fmt_ts(t1, is_vtt)}")
        lines.append(txt)
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[SUBTITLES] Exported {fmt.upper()} captions -> {out_path}")


class VideoFrameReader:
    """Memory-safe sequential + LRU-cached reader for full-framerate videos."""

    def __init__(self, video_path, max_cache=32):
        self.cap = cv2.VideoCapture(video_path)
        self.total_frames = max(1, int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        raw_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.fps = raw_fps if raw_fps > 1.0 else 30.0
        self.next_pos = 0
        self.max_cache = max_cache
        self.cache = OrderedDict()
        self.last_valid = None

    def get_frame(self, idx):
        idx = max(0, min(self.total_frames - 1, int(idx)))
        if idx in self.cache:
            self.cache.move_to_end(idx)
            return self.cache[idx]

        if idx != self.next_pos:
            if self.next_pos < idx <= self.next_pos + 12:
                while self.next_pos < idx:
                    ret, f = self.cap.read()
                    if not ret:
                        break
                    self.last_valid = f
                    self.next_pos += 1
            else:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                self.next_pos = idx

        ret, frame = self.cap.read()
        if not ret or frame is None:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = self.cap.read()
        if not ret or frame is None:
            if self.last_valid is not None:
                return self.last_valid
            return np.zeros((max(2, self.height), max(2, self.width), 3), dtype=np.uint8)

        self.next_pos = idx + 1
        self.last_valid = frame
        self.cache[idx] = frame
        if len(self.cache) > self.max_cache:
            self.cache.popitem(last=False)
        return frame

    def close(self):
        self.cap.release()


class ImageFolderReader:
    """Lazy LRU-cached reader for extracted frame folders."""

    def __init__(self, frame_files, fps_extracted=3.0, max_cache=64):
        self.frame_files = frame_files
        self.total_frames = len(frame_files)
        self.fps = float(fps_extracted)
        first = cv2.imread(frame_files[0])
        if first is None:
            raise ValueError(f"Could not decode first frame image: {frame_files[0]}")
        self.height, self.width = first.shape[:2]
        self.max_cache = max_cache
        self.cache = OrderedDict([(0, first)])
        self.last_valid = first

    def get_frame(self, idx):
        idx = max(0, min(self.total_frames - 1, int(idx)))
        if idx in self.cache:
            self.cache.move_to_end(idx)
            return self.cache[idx]
        frame = cv2.imread(self.frame_files[idx])
        if frame is None:
            return self.last_valid
        self.last_valid = frame
        self.cache[idx] = frame
        if len(self.cache) > self.max_cache:
            self.cache.popitem(last=False)
        return frame

    def close(self):
        pass


def _apply_voice_and_tone_selection(recipe, args, interactive_tty):
    """Apply CLI overrides or interactive Voice & Tone picker before rendering."""
    if args.voice:
        recipe["default_voice"] = args.voice
    if args.tone:
        recipe["tone"] = args.tone

    should_prompt = (args.interactive or interactive_tty) and not args.auto_proceed and not args.plan_only
    if should_prompt:
        cur_voice = recipe.get("default_voice", "en-IN-PrabhatNeural")
        cur_tone = recipe.get("tone", "professional")
        print("\n==========================================")
        print("  VOICE & TONE SELECTION")
        print("==========================================")
        print(f"Current Voice : {cur_voice}")
        for idx, (v_id, desc) in enumerate(VOICE_CATALOG, start=1):
            print(f"  [{idx}] {v_id:<22} - {desc}")
        v_choice = input(f"Select voice [1-{len(VOICE_CATALOG)}, custom ID, or Enter to keep '{cur_voice}']: ").strip()
        if v_choice.isdigit() and 1 <= int(v_choice) <= len(VOICE_CATALOG):
            recipe["default_voice"] = VOICE_CATALOG[int(v_choice) - 1][0]
        elif v_choice:
            recipe["default_voice"] = v_choice

        print(f"\nCurrent Tone  : {cur_tone}")
        tone_keys = list(TONE_PRESETS.keys())
        for idx, t_key in enumerate(tone_keys, start=1):
            print(f"  [{idx}] {t_key:<13} - {TONE_PRESETS[t_key]['description']}")
        t_choice = input(f"Select tone [1-{len(tone_keys)} or Enter to keep '{cur_tone}']: ").strip()
        if t_choice.isdigit() and 1 <= int(t_choice) <= len(tone_keys):
            recipe["tone"] = tone_keys[int(t_choice) - 1]
        elif t_choice in TONE_PRESETS:
            recipe["tone"] = t_choice

    # Apply tone rate/pitch defaults if not explicitly locked in recipe
    tone_name = recipe.get("tone")
    if tone_name in TONE_PRESETS:
        tp = TONE_PRESETS[tone_name]
        if "default_rate" not in recipe or args.tone:
            recipe["default_rate"] = tp["rate"]
        if "default_pitch" not in recipe or args.tone:
            recipe["default_pitch"] = tp["pitch"]

    return recipe


def _print_render_plan(recipe, input_desc, geometry, fonts, ui_scale, total_duration, clip_durations, branding_rect, src_w, src_h):
    """Display clear Pre-Render Editing Plan summary including per-step dock zones."""
    print("\n==========================================")
    print("  PRE-RENDER EDITING PLAN")
    print("==========================================")
    print(f"Input Source   : {input_desc} ({src_w}x{src_h})")
    print(f"Output Canvas  : {geometry['canvas_w']}x{geometry['canvas_h']} (pad_bottom={geometry['pad_bottom']}px, ui_scale={ui_scale:.2f})")
    print(f"Theme / Tone   : preset={recipe.get('preset', 'tech_hud')} | tone={recipe.get('tone', 'custom')}")
    print(f"Voice / Rate   : {recipe.get('default_voice', 'en-IN-PrabhatNeural')} @ {recipe.get('default_rate', '+8%')} ({recipe.get('default_pitch', '+0Hz')})")
    print(f"Total Duration : {total_duration:.2f}s @ {recipe.get('fps', 30)} fps")
    print("\nPlanned Steps & Dynamic Dock Placement:")
    for s in recipe.get("steps", []):
        sid = s["id"]
        dur = clip_durations.get(sid, 0.0)
        zoom_rect = _compute_active_zoom_rect(s, s.get("active_start", 0.0), src_w, src_h, recipe)
        rect, _, zone = _resolve_dock_placement(
            s,
            geometry["canvas_w"],
            geometry["canvas_h"],
            geometry["stage_x"],
            geometry["stage_y"],
            src_w,
            src_h,
            geometry["pad_bottom"],
            fonts,
            ui_scale,
            branding_rect,
            recipe,
            zoom_rect=zoom_rect,
        )
        rect_str = f"{rect}" if rect else "hidden"
        print(f"  • [{sid:<6}] {s.get('active_start', 0):5.1f}s..{s.get('active_end', 0):5.1f}s | tts={dur:4.2f}s | dock={zone:<13} {rect_str}")
    print("==========================================\n")


def render_video(recipe_path, output_video, args):
    with open(recipe_path, "r", encoding="utf-8") as f:
        recipe = json.load(f)

    interactive_tty = sys.stdin.isatty() and sys.stdout.isatty()
    recipe = _apply_voice_and_tone_selection(recipe, args, interactive_tty)

    fps_extracted = float(args.fps_extracted if args.fps_extracted is not None else recipe.get("fps_extracted", 3.0))
    source_video = args.video or recipe.get("source_video")
    frames_folder = args.frames_dir or recipe.get("frames_dir")
    input_source = args.input_source if args.input_source != "auto" else recipe.get("input_source", "auto")

    # Auto-extract 3 FPS frames when source_video exists and frames_dir is configured or requested
    should_extract = args.extract_frames or args.force_extract or (
        bool(source_video and os.path.exists(source_video) and frames_folder and recipe.get("auto_extract_frames", True))
        and (not os.path.exists(frames_folder) or not get_natural_sorted_files(frames_folder))
    )
    if should_extract and source_video and os.path.exists(source_video):
        if not frames_folder:
            stem = os.path.splitext(os.path.basename(source_video))[0]
            frames_folder = os.path.join(os.path.dirname(os.path.abspath(source_video)), f"{stem} frames")
        extract_frames_from_video(source_video, frames_folder, fps_extracted=fps_extracted, force=args.force_extract)

    # Select frame reader cleanly
    has_video = bool(source_video and os.path.exists(source_video))
    has_frames = bool(frames_folder and os.path.exists(frames_folder) and get_natural_sorted_files(frames_folder))

    if input_source == "frames":
        use_video = False
    elif input_source == "video":
        use_video = True
    elif args.frames_dir and has_frames and not args.video:
        use_video = False
    else:
        use_video = has_video

    if use_video:
        if not has_video:
            raise FileNotFoundError(f"Source video not found: {source_video}")
        print(f"[1/4] Opening streaming source video: {source_video}")
        reader = VideoFrameReader(source_video)
        input_desc = f"Video ({reader.fps:g} fps)"
    else:
        if not has_frames:
            raise FileNotFoundError("Neither source_video nor a populated frames_dir was found!")
        print(f"[1/4] Opening extracted frames directory: {frames_folder}")
        frame_files = get_natural_sorted_files(frames_folder)
        reader = ImageFolderReader(frame_files, fps_extracted=fps_extracted)
        input_desc = f"Frames folder ({fps_extracted:g} fps)"

    # Convert 3-FPS markers & cross-FPS timeline indices cleanly
    recipe = convert_3fps_steps_to_seconds(
        recipe,
        fps_extracted=fps_extracted,
        reader_fps=reader.fps,
        reader_total_frames=reader.total_frames,
    )

    work_dir = os.path.dirname(os.path.abspath(recipe_path))
    audio_dir = os.path.join(work_dir, "audio_tracks")
    os.makedirs(audio_dir, exist_ok=True)
    soundtrack_wav = os.path.join(work_dir, "final_soundtrack.wav")

    # 2. Generate / Prepare Speech
    print("[2/4] Preparing neural speech clips...")
    default_voice = recipe.get("default_voice", "en-IN-PrabhatNeural")
    default_rate = recipe.get("default_rate", "+8%")
    default_pitch = recipe.get("default_pitch", "+0Hz")
    use_tts_cache = not args.no_tts_cache
    clip_durations = {}

    async def generate_all():
        for step in recipe.get("steps", []):
            out_wav = os.path.join(audio_dir, f"{step['id']}.wav")
            custom_audio = step.get("audio_file")
            if custom_audio and os.path.exists(custom_audio):
                dur = _prepare_external_audio(custom_audio, out_wav)
                cached_tag = "custom audio"
            else:
                text = step.get("narration", "")
                if not text:
                    clip_durations[step["id"]] = 0.0
                    continue
                voice = step.get("voice", default_voice)
                rate = step.get("rate", default_rate)
                pitch = step.get("pitch", default_pitch)
                dur, from_cache = await generate_step_audio(text, voice, rate, out_wav, pitch=pitch, use_cache=use_tts_cache)
                cached_tag = "cached" if from_cache else "synthesized"
            clip_durations[step["id"]] = dur
            print(f"  • [{step['id']}] {dur:.2f}s ({cached_tag})")

    asyncio.run(generate_all())

    # Optional automatic overlap shifting
    steps_sorted = sorted(recipe.get("steps", []), key=lambda s: s.get("start_time", 0.0))
    if recipe.get("audio_timing_mode", "warn") == "auto_shift":
        min_gap = float(recipe.get("audio_min_gap", 0.2))
        cursor_end = 0.0
        for st in steps_sorted:
            if st["start_time"] < cursor_end:
                shift = cursor_end - st["start_time"]
                st["start_time"] = round(cursor_end, 3)
                if "active_end" in st and st["active_end"] < st["start_time"] + clip_durations.get(st["id"], 0.0):
                    st["active_end"] = round(st["start_time"] + clip_durations.get(st["id"], 0.0), 3)
                print(f"  [AUTO-SHIFT] Shifted '{st['id']}' +{shift:.2f}s to t={st['start_time']:.2f}s")
            cursor_end = st["start_time"] + clip_durations.get(st["id"], 0.0) + min_gap

    # Dynamic total_duration resolution
    raw_total = recipe.get("total_duration", "auto")
    timeline_map = recipe.get("timeline_mapping", [])
    if raw_total == "auto" or raw_total is None:
        max_tl = max((seg.get("end_sec", 0.0) for seg in timeline_map), default=0.0)
        max_act = max((s.get("active_end", 0.0) for s in steps_sorted), default=0.0)
        max_aud = max((s.get("start_time", 0.0) + clip_durations.get(s["id"], 0.0) + 1.0 for s in steps_sorted), default=0.0)
        total_duration = round(max(max_tl, max_act, max_aud, 1.0), 2)
    else:
        total_duration = float(raw_total)

    for idx_s, st in enumerate(steps_sorted):
        end_t = st.get("start_time", 0.0) + clip_durations.get(st["id"], 0.0)
        next_t = steps_sorted[idx_s + 1].get("start_time", total_duration) if idx_s + 1 < len(steps_sorted) else total_duration
        if end_t > next_t + 0.05:
            print(f"  [OVERLAP WARNING] '{st['id']}' ends at {end_t:.2f}s > next boundary {next_t:.2f}s")

    # Prepare visual sizing & theme before plan preview
    theme = resolve_theme(recipe)
    source_w, source_h = reader.width, reader.height
    prelim_ui_scale = compute_ui_scale(source_w, source_h, recipe)
    prelim_fonts = load_fonts(prelim_ui_scale, recipe)
    prelim_wide_cap = min(int(round(1320 * max(prelim_ui_scale, source_w / 1920.0))), max(320, source_w - 48))
    max_dock_h = max(
        (
            _layout_dock_content(s, prelim_fonts, prelim_wide_cap, prelim_ui_scale)["dock_h"]
            for s in recipe.get("steps", [])
            if (s.get("step_num") or s.get("step_title") or s.get("sub")) and not s.get("hide_dock")
        ),
        default=int(round(92 * prelim_ui_scale)),
    )
    geometry = compute_canvas_geometry(source_w, source_h, recipe, max_dock_h=max_dock_h)
    ui_scale = compute_ui_scale(geometry["canvas_w"], geometry["canvas_h"], recipe)
    fonts = load_fonts(ui_scale, recipe)

    branding_text = recipe.get("branding_text", "")
    logo_path = recipe.get("branding_logo")
    logo_img = Image.open(logo_path).convert("RGBA") if logo_path and os.path.exists(logo_path) else None
    branding_rect = _resolve_branding_rect(
        branding_text, fonts, geometry["canvas_w"], geometry["canvas_h"], source_h, ui_scale, recipe, has_logo=(logo_img is not None)
    )

    _print_render_plan(
        recipe, input_desc, geometry, fonts, ui_scale, total_duration, clip_durations, branding_rect, source_w, source_h
    )

    if args.plan_only:
        reader.close()
        print("[PLAN ONLY] Exiting before rendering.")
        return

    if (args.interactive or interactive_tty) and not args.auto_proceed:
        ans = input("Proceed with audio mixing & video rendering? [Y/n]: ").strip().lower()
        if ans in ("n", "no"):
            reader.close()
            print("[CANCELLED] Render aborted by user.")
            return

    # 3. Build Audio Track
    print(f"[3/4] Mixing master soundtrack ({total_duration:.2f}s)...")
    build_soundtrack(recipe, audio_dir, soundtrack_wav, total_duration, source_video=source_video)

    # 4. Render Video
    target_fps = float(recipe.get("fps", 30))
    num_frames = max(1, int(round(total_duration * target_fps)))
    target_w, target_h = geometry["canvas_w"], geometry["canvas_h"]

    os.makedirs(os.path.dirname(os.path.abspath(output_video)), exist_ok=True)
    enc = recipe.get("encoding", {})
    print(f"[4/4] Rendering video ({target_w}x{target_h} @ {target_fps:g}fps, pad_bottom={geometry['pad_bottom']}) -> {output_video}")

    ffmpeg_cmd = [
        FFMPEG_EXE, "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{target_w}x{target_h}",
        "-pix_fmt", "rgb24",
        "-r", str(target_fps),
        "-i", "-",
        "-i", soundtrack_wav,
        "-c:v", enc.get("codec", "libx264"),
        "-preset", enc.get("preset", "medium"),
        "-crf", str(enc.get("crf", 18)),
        "-pix_fmt", enc.get("pix_fmt", "yuv420p"),
        "-c:a", "aac",
        "-b:a", enc.get("audio_bitrate", "192k"),
        "-movflags", "+faststart",
        "-shortest",
        output_video,
    ]

    stderr_tmp = tempfile.NamedTemporaryFile(mode="w+", suffix=".log", delete=False, encoding="utf-8")
    stderr_path = stderr_tmp.name
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stderr_tmp)

    overlay_specs = recipe.get("steps", [])
    gap_behavior = recipe.get("gap_behavior", "hold_previous")

    def resolve_frame_idx(t):
        if not timeline_map:
            return 0
        if t < timeline_map[0]["start_sec"]:
            return timeline_map[0]["source_frame_start"]
        last_frame = timeline_map[0]["source_frame_start"]
        for seg in timeline_map:
            if seg["start_sec"] <= t < seg["end_sec"]:
                progress = (t - seg["start_sec"]) / max(1e-4, (seg["end_sec"] - seg["start_sec"]))
                f_start = seg["source_frame_start"]
                f_end = seg["source_frame_end"]
                return int(f_start + progress * (f_end - f_start))
            if t >= seg["end_sec"]:
                last_frame = seg["source_frame_end"]
        return last_frame

    def resolve_spec(t):
        if not overlay_specs:
            return None
        prev_spec = None
        for s in overlay_specs:
            if s["active_start"] <= t < s["active_end"]:
                return s
            if t >= s["active_end"]:
                prev_spec = s
        if gap_behavior == "hide":
            return None
        return prev_spec

    try:
        for f_idx in range(num_frames):
            t = f_idx / float(target_fps)
            src_idx = min(reader.total_frames - 1, max(0, resolve_frame_idx(t)))
            src_bgr = reader.get_frame(src_idx)
            src_rgb = cv2.cvtColor(src_bgr, cv2.COLOR_BGR2RGB)

            spec = resolve_spec(t)
            annotated_rgb = draw_hud_overlay(
                src_rgb,
                spec,
                t,
                fonts,
                branding_text,
                geometry,
                theme,
                recipe,
                ui_scale,
                logo_img=logo_img,
            )
            proc.stdin.write(annotated_rgb.tobytes())

            if f_idx % 300 == 0 or f_idx == num_frames - 1:
                print(f"  • Progress: {f_idx}/{num_frames} frames ({t:.1f}s / {total_duration:.1f}s)")
    finally:
        reader.close()
        if proc.stdin:
            proc.stdin.close()
        proc.wait()
        stderr_tmp.close()

    if proc.returncode == 0:
        if os.path.exists(stderr_path):
            os.remove(stderr_path)
        size_mb = os.path.getsize(output_video) / (1024 * 1024)
        print(f"\n[DONE] Successfully created guide video: {output_video} ({size_mb:.2f} MB)")
        if args.export_srt or recipe.get("export_subtitles"):
            srt_path = os.path.splitext(output_video)[0] + ".srt"
            export_subtitles(recipe, srt_path, fmt="srt")
    else:
        err_msg = ""
        if os.path.exists(stderr_path):
            with open(stderr_path, "r", encoding="utf-8", errors="ignore") as ef:
                err_msg = ef.read()
            os.remove(stderr_path)
        print(f"\n[ERROR] FFmpeg failed with exit code {proc.returncode}:\n{err_msg[-2000:]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Dynamic Video Guide Maker Engine")
    parser.add_argument("--recipe", help="Path to recipe.json")
    parser.add_argument("--output", help="Path to output .mp4")
    parser.add_argument("--frames_dir", help="Path to extracted frames directory")
    parser.add_argument("--video", help="Path to full source video")
    parser.add_argument("--analyze", action="store_true", help="Analyze frames directory without rendering")
    parser.add_argument("--extract_frames", action="store_true", help="Extract frames from --video using FFmpeg")
    parser.add_argument("--force_extract", action="store_true", help="Re-extract frames even if frames_dir is non-empty")
    parser.add_argument("--fps_extracted", type=float, default=None, help="Extraction framerate (default 3.0 = 3 images/sec)")
    parser.add_argument("--input_source", choices=["auto", "video", "frames"], default="auto", help="Force video or frames_dir input")
    parser.add_argument("--init_recipe", help="Scaffold a starter recipe.json from extracted frames")
    parser.add_argument("--voice", help="Override default Edge-TTS voice ID")
    parser.add_argument("--tone", choices=list(TONE_PRESETS.keys()), help="Override narration tone & styling preset")
    parser.add_argument("--interactive", action="store_true", help="Prompt interactively for Voice, Tone, and Plan confirmation")
    parser.add_argument("--auto_proceed", "-y", action="store_true", help="Skip Voice/Tone and Pre-Render Plan confirmation prompts")
    parser.add_argument("--plan_only", action="store_true", help="Print Pre-Render Editing Plan without rendering")
    parser.add_argument("--no_tts_cache", action="store_true", help="Force re-synthesis of TTS audio clips")
    parser.add_argument("--export_srt", action="store_true", help="Export synchronized .srt subtitle file alongside MP4")

    args = parser.parse_args()
    eff_fps = args.fps_extracted if args.fps_extracted is not None else 3.0

    if args.extract_frames and not args.recipe:
        if not args.video:
            print("Error: --video is required with --extract_frames (unless --recipe specifies source_video)")
        else:
            target_dir = args.frames_dir
            if not target_dir:
                stem = os.path.splitext(os.path.basename(args.video))[0]
                target_dir = os.path.join(os.path.dirname(os.path.abspath(args.video)), f"{stem} frames")
            extract_frames_from_video(args.video, target_dir, fps_extracted=eff_fps, force=args.force_extract)
            if args.analyze:
                analyze_frames_folder(target_dir, args.video, eff_fps)
            if args.init_recipe:
                scaffold_recipe_from_frames(target_dir, args.init_recipe, video_path=args.video, fps_extracted=eff_fps)
    elif args.init_recipe:
        if not args.frames_dir:
            print("Error: --frames_dir is required for --init_recipe (or pair with --extract_frames --video)")
        else:
            scaffold_recipe_from_frames(args.frames_dir, args.init_recipe, video_path=args.video, fps_extracted=eff_fps)
    elif args.analyze:
        if not args.frames_dir:
            print("Error: --frames_dir is required for --analyze")
        else:
            analyze_frames_folder(args.frames_dir, args.video, eff_fps)
    elif args.recipe and args.output:
        render_video(args.recipe, args.output, args)
    elif args.recipe and args.plan_only:
        render_video(args.recipe, args.output or "preview.mp4", args)
    else:
        parser.print_help()
