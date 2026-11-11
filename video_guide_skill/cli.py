"""CLI entrypoint for `video-guide` console script."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    # If installed via wheel (flat site-packages), engine.py sits alongside video_guide_skill
    candidates = [root / "engine.py", Path(__file__).resolve().parent / "engine.py"]
    engine = next((c for c in candidates if c.exists()), None)
    if engine is None:
        raise SystemExit("Cannot locate engine.py. Run from cloned repository or check installation.")
    if str(engine.parent) not in sys.path:
        sys.path.insert(0, str(engine.parent))
    sys.argv[0] = str(engine)
    runpy.run_path(str(engine), run_name="__main__")


if __name__ == "__main__":
    main()
