name: video-guide-skill
description: >
  Produce professional user-guide MP4 videos from screen recordings and a recipe JSON.
  Supports narration (Edge TTS), animated HUD overlays, zoom annotations,
  background music, and SRT captions.
  Works with any app, website, portal, or web application recording.

tools:
  - name: validate_recipe
    description: >
      Validate a Video Guide recipe JSON without rendering.
      Runs TTS synthesis + timing checks. Returns warnings and plan text.
      Always call this before render_guide.
    input_schema:
      type: object
      properties:
        recipe_json:
          type: string
          description: Full recipe JSON string.
      required: [recipe_json]

  - name: render_guide
    description: >
      Render a complete user-guide MP4 from a recipe JSON.
      Produces narration, HUD overlays, zoom annotations, music, and SRT.
    input_schema:
      type: object
      properties:
        recipe_json:
          type: string
        output_path:
          type: string
          description: Absolute path for the output .mp4
        export_srt:
          type: boolean
          default: true
      required: [recipe_json, output_path]

  - name: extract_frames
    description: >
      Extract frames from a screen recording at a given FPS (default 3).
      Returns the frames_dir and frame_count.
    input_schema:
      type: object
      properties:
        video_path:
          type: string
          description: Absolute path to the screen recording.
        fps:
          type: number
          default: 3.0
        output_dir:
          type: string
          description: Output directory for frames (optional).
      required: [video_path]

executor:
  runtime: python
  min_version: "3.11"
  script: tool_executor.py
  install: |
    uv pip install -e .
    # or: pip install video-guide-skill
  invocation: |
    python tool_executor.py --args '{"tool": "<tool_name>", ...}'

mcp_server:
  script: mcp_server.py
  transport: stdio
  config_snippets:
    claude_desktop: |
      {
        "mcpServers": {
          "video-guide": {
            "command": "uv",
            "args": ["run", "--with",
              "mcp,opencv-python,pillow,imageio-ffmpeg,edge-tts,numpy",
              "python", "/path/to/video-guide-skill/mcp_server.py"]
          }
        }
      }
    cursor: |
      // .cursor/mcp.json
      {
        "mcpServers": {
          "video-guide": {
            "command": "uv",
            "args": ["run", "--with",
              "mcp,opencv-python,pillow,imageio-ffmpeg,edge-tts,numpy",
              "python", "/path/to/video-guide-skill/mcp_server.py"],
            "transport": "stdio"
          }
        }
      }
