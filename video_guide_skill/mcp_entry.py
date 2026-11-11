"""MCP entrypoint for `video-guide-mcp` console script."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    candidates = [root / "mcp_server.py", Path(__file__).resolve().parent / "mcp_server.py"]
    mcp_file = next((c for c in candidates if c.exists()), None)
    if mcp_file is None:
        raise SystemExit("Cannot locate mcp_server.py.")
    if str(mcp_file.parent) not in sys.path:
        sys.path.insert(0, str(mcp_file.parent))
    import mcp_server
    mcp_server.main()


if __name__ == "__main__":
    main()
