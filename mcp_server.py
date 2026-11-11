"""
mcp_server.py — Cross-version (MCP SDK 1.x + 2.x) stdio server for the Video Guide Skill.

Exposes all 7 zero-user-recipe tools over MCP stdio transport:
  • create_guide         — Start here: video_path -> 3fps frames -> ALL frames analyzed -> storyboards + draft recipe
  • extract_frames       — FFmpeg N-FPS frame extraction (--fps_extracted, default 3.0)
  • analyze_frames       — Analyze ALL extracted frames -> segments + changed bboxes + storyboards
  • inspect_frame_slice  — Render dense contact sheet for narrow frame range [start..end]
  • scaffold_recipe      — Generate engine.py-compatible starter recipe.json
  • validate_recipe      — Reject unresolved placeholders + run engine.py --plan_only
  • render_guide         — Render narrated, HUD-annotated MP4 + SRT captions

Compatible with Claude Code, Claude Desktop, Cursor, Antigravity MCP, and any MCP client.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Literal

HERE = Path(__file__).parent.resolve()
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError as exc:
        raise SystemExit(
            "MCP SDK not found. Run `python bootstrap.py` or `pip install mcp`.\n" + str(exc)
        )

from tool_executor import (
    analyze_frames as _analyze_frames,
    create_guide as _create_guide,
    extract_frames as _extract_frames,
    inspect_frame_slice as _inspect_frame_slice,
    render_guide as _render_guide,
    scaffold_recipe as _scaffold_recipe,
    validate_recipe as _validate_recipe,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
log = logging.getLogger("video-guide-mcp")

mcp = MCPServer("video-guide-skill")


def _dump(res: dict) -> str:
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool(
    name="create_guide",
    description=(
        "MASTER START TOOL — End user ONLY provides `video_path` (plus optional `user_flow_notes`; NO recipe JSON "
        "from user). Extracts 3 FPS frames via FFmpeg (e.g., ~630 frames for 210s), analyzes ALL extracted frames, "
        "creates labeled Storyboard Contact Sheets + analysis_3fps.json + starter engine.py recipe_draft.json. "
        "Agent MUST inspect all returned storyboard images & key frames BEFORE editing recipe, validating, and rendering."
    ),
)
def create_guide(
    video_path: str,
    output_path: str | None = None,
    user_flow_notes: str = "",
    fps: float = 3.0,
    voice: str = "en-IN-NeerjaNeural",
    tone: Literal["friendly", "professional", "energetic", "calm", "corporate"] = "friendly",
    app_name: str | None = None,
) -> str:
    return _dump(
        _create_guide(
            video_path=video_path,
            output_path=output_path,
            user_flow_notes=user_flow_notes,
            fps=fps,
            voice=voice,
            tone=tone,
            app_name=app_name,
        )
    )


@mcp.tool(
    name="extract_frames",
    description="Extract N-FPS PNG frames from a video via bundled FFmpeg (`--fps_extracted`, default 3.0 = 3 images/sec).",
)
def extract_frames(
    video_path: str,
    fps: float = 3.0,
    output_dir: str | None = None,
    force: bool = False,
) -> str:
    return _dump(_extract_frames(video_path=video_path, fps=fps, output_dir=output_dir, force=force))


@mcp.tool(
    name="analyze_frames",
    description=(
        "Scan ALL extracted 3-FPS frames (`0 .. N-1`), classify PAGE_TRANSITION / UI_ACTION / IDLE_HOLD segments, "
        "detect changed pixel regions [x1,y1,x2,y2], and render labeled Storyboard Contact Sheets."
    ),
)
def analyze_frames(
    frames_dir: str,
    video_path: str | None = None,
    fps: float = 3.0,
    page_threshold: float = 0.055,
    ui_threshold: float = 0.095,
) -> str:
    return _dump(
        _analyze_frames(
            frames_dir=frames_dir,
            video_path=video_path,
            fps=fps,
            page_threshold=page_threshold,
            ui_threshold=ui_threshold,
        )
    )


@mcp.tool(
    name="inspect_frame_slice",
    description="Render a dense storyboard sheet containing every frame in [start_frame .. end_frame] (0-based 3-FPS indices).",
)
def inspect_frame_slice(
    frames_dir: str,
    start_frame: int,
    end_frame: int,
    fps: float = 3.0,
    stride: int = 1,
) -> str:
    return _dump(_inspect_frame_slice(frames_dir=frames_dir, start_frame=start_frame, end_frame=end_frame, fps=fps, stride=stride))


@mcp.tool(
    name="scaffold_recipe",
    description="Analyze ALL frames in `frames_dir` and generate an engine.py-compatible starter recipe.json + storyboards.",
)
def scaffold_recipe(
    frames_dir: str,
    video_path: str | None = None,
    fps: float = 3.0,
    voice: str = "en-IN-NeerjaNeural",
    tone: Literal["friendly", "professional", "energetic", "calm", "corporate"] = "friendly",
    app_name: str = "Application",
    user_flow_notes: str = "",
) -> str:
    return _dump(
        _scaffold_recipe(
            frames_dir=frames_dir,
            video_path=video_path,
            fps=fps,
            voice=voice,
            tone=tone,
            app_name=app_name,
            user_flow_notes=user_flow_notes,
        )
    )


@mcp.tool(
    name="validate_recipe",
    description=(
        "Validate completed recipe (by `recipe_path` or `recipe_json`), ensure zero [AGENT:] placeholders remain, "
        "synthesize Edge-TTS audio clips, check timings/overlaps, and return Pre-Render Editing Plan (`--plan_only`)."
    ),
)
def validate_recipe(
    recipe_path: str | None = None,
    recipe_json: str | None = None,
) -> str:
    return _dump(_validate_recipe(recipe_json=recipe_json, recipe_path=recipe_path))


@mcp.tool(
    name="render_guide",
    description="Render the final narrated, HUD-annotated MP4 user guide video and synchronized .srt captions via engine.py.",
)
def render_guide(
    output_path: str,
    recipe_path: str | None = None,
    recipe_json: str | None = None,
    export_srt: bool = True,
    voice: str | None = None,
    tone: Literal["friendly", "professional", "energetic", "calm", "corporate"] | None = None,
) -> str:
    return _dump(
        _render_guide(
            output_path=output_path,
            recipe_json=recipe_json,
            recipe_path=recipe_path,
            export_srt=export_srt,
            voice=voice,
            tone=tone,
        )
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
