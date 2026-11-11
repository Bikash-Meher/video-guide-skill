"""
mcp_server.py — MCP (Model Context Protocol) server for the Video Guide Skill.

Exposes three tools over stdio MCP transport:
  • validate_recipe   — plan-only check
  • render_guide      — full MP4 render
  • extract_frames    — FFmpeg frame extraction

Compatible with:
  • Claude Code / Claude Desktop   (stdio MCP)
  • Cursor                         (.cursor/mcp.json)
  • Any MCP-aware client

Run directly:
    uv run --with mcp python mcp_server.py

Or via uvx after install:
    uvx video-guide-skill

Configure in Claude Desktop (~/.config/claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "video-guide": {
          "command": "uv",
          "args": ["run", "--with", "mcp,opencv-python,pillow,imageio-ffmpeg,edge-tts,numpy",
                   "python", "/path/to/mcp_server.py"]
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

# MCP SDK — installed via: uv add mcp / pip install mcp
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolRequest,
        CallToolResult,
        ListToolsRequest,
        ListToolsResult,
        TextContent,
        Tool,
    )
    import mcp.types as types
except ImportError as e:
    raise SystemExit(
        "MCP SDK not found. Install with: pip install mcp  or  uv add mcp\n" + str(e)
    )

from tool_executor import validate_recipe, render_guide, extract_frames, scaffold_recipe, create_guide

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("video-guide-mcp")

server = Server("video-guide-skill")

# ── Tool definitions ───────────────────────────────────────────────────────────

TOOL_DEFS: list[Tool] = [
    Tool(
        name="create_guide",
        description=(
            "MASTER TOOL — Agent needs only a video_path and output_path. "
            "Automatically extracts frames at 3 fps, detects UI scene transitions, "
            "and returns a draft recipe with scene thumbnails for the agent to inspect. "
            "The agent then fills narrations via vision and calls validate_recipe + render_guide. "
            "Use this as the starting point for ANY new user-guide video."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "video_path": {
                    "type": "string",
                    "description": "Absolute path to the screen recording (.mp4, .mov, .mkv).",
                },
                "output_path": {
                    "type": "string",
                    "description": "Absolute path for the final output .mp4.",
                },
                "fps": {
                    "type": "number",
                    "description": "Frame extraction rate. Default 3 (recommended for UI).",
                    "default": 3.0,
                },
                "voice": {
                    "type": "string",
                    "description": "Edge TTS voice. Default en-IN-NeerjaNeural.",
                    "default": "en-IN-NeerjaNeural",
                },
                "tone": {
                    "type": "string",
                    "enum": ["professional", "energetic", "calm", "corporate", "friendly"],
                    "default": "friendly",
                },
                "app_name": {
                    "type": "string",
                    "description": "Name of the app/website being recorded (used in title/narration context).",
                },
                "sensitivity": {
                    "type": "number",
                    "description": "Scene-cut sensitivity 0-1. Lower = more cuts. Default 0.18.",
                    "default": 0.18,
                },
            },
            "required": ["video_path", "output_path"],
        },
    ),
    Tool(
        name="scaffold_recipe",
        description=(
            "Auto-detect scene transitions in extracted frames and produce a draft recipe JSON. "
            "Returns scene_frames paths and base64 thumbnails so the agent can inspect "
            "each scene visually and fill in narration text. "
            "Call extract_frames first if frames_dir doesn't exist yet."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "frames_dir": {
                    "type": "string",
                    "description": "Directory containing *_frame.png files.",
                },
                "video_path": {
                    "type": "string",
                    "description": "Original video path (stored in recipe metadata).",
                },
                "fps": {"type": "number", "default": 3.0},
                "sensitivity": {
                    "type": "number",
                    "description": "Scene-cut sensitivity. Lower = more steps detected.",
                    "default": 0.18,
                },
                "voice": {"type": "string", "default": "en-IN-NeerjaNeural"},
                "tone": {
                    "type": "string",
                    "enum": ["professional", "energetic", "calm", "corporate", "friendly"],
                    "default": "friendly",
                },
                "app_name": {"type": "string", "default": "Application"},
            },
            "required": ["frames_dir"],
        },
    ),
    Tool(
        name="validate_recipe",
        description=(
            "Validate a Video Guide recipe JSON without rendering. "
            "Runs TTS synthesis and timing checks. Returns warnings and plan text. "
            "Always call this before render_guide to catch overlap issues."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "recipe_json": {
                    "type": "string",
                    "description": "Full recipe JSON string (or stringified dict).",
                },
            },
            "required": ["recipe_json"],
        },
    ),
    Tool(
        name="render_guide",
        description=(
            "Render a complete user-guide MP4 (with narration, HUD overlays, "
            "zoom annotations, background music) from a recipe JSON. "
            "Also produces an .srt caption file. Requires screen recording frames "
            "referenced in the recipe to exist on disk."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "recipe_json": {
                    "type": "string",
                    "description": "Full recipe JSON string.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Absolute path for the output .mp4 file.",
                },
                "export_srt": {
                    "type": "boolean",
                    "description": "Whether to export a .srt subtitle file alongside the mp4.",
                    "default": True,
                },
            },
            "required": ["recipe_json", "output_path"],
        },
    ),
    Tool(
        name="extract_frames",
        description=(
            "Extract frames from a screen recording video at a given FPS "
            "(default 3 fps). Frames are saved as 0001_frame.png, 0002_frame.png … "
            "Use frame paths in your recipe's timeline_mapping steps."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "video_path": {
                    "type": "string",
                    "description": "Absolute path to the input screen recording (.mp4, .mov, .mkv).",
                },
                "fps": {
                    "type": "number",
                    "description": "Frames per second to extract. 3 is recommended for UI walkthroughs.",
                    "default": 3.0,
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory to write frames into. Defaults to <video_dir>/<video_stem>_frames/.",
                },
            },
            "required": ["video_path"],
        },
    ),
]


@server.list_tools()
async def list_tools(req: ListToolsRequest) -> ListToolsResult:
    return ListToolsResult(tools=TOOL_DEFS)


@server.call_tool()
async def call_tool(req: CallToolRequest) -> CallToolResult:
    name = req.params.name
    args = req.params.arguments or {}
    log.info("Tool call: %s  args=%s", name, list(args.keys()))

    try:
        if name == "create_guide":
            result = create_guide(**args)
        elif name == "scaffold_recipe":
            result = scaffold_recipe(**args)
        elif name == "validate_recipe":
            result = validate_recipe(**args)
        elif name == "render_guide":
            result = render_guide(**args)
        elif name == "extract_frames":
            result = extract_frames(**args)
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        log.exception("Tool %s failed", name)
        result = {"error": str(exc)}

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result, indent=2))]
    )


async def _main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
