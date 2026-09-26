from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.editor import run_editor
from test_game.world_assets import WORLD_ASSETS


def main() -> None:
    parser = argparse.ArgumentParser(description="Edit Mystery Engine exploration scenes")
    parser.add_argument("--scene", type=Path, default=ROOT / "src" / "test_game" / "scenes" / "test_clearing.json")
    parser.add_argument("--width", type=int, default=40, help="Width in tiles when creating a new scene")
    parser.add_argument("--height", type=int, default=24, help="Height in tiles when creating a new scene")
    parser.add_argument("--screenshot", type=Path, help="Render one editor frame to PNG and exit")
    args = parser.parse_args()
    run_editor(
        args.scene,
        WORLD_ASSETS,
        ROOT / "src" / "test_game" / "assets",
        project_root=ROOT,
        new_width=max(4, args.width),
        new_height=max(4, args.height),
        screenshot=args.screenshot,
    )


if __name__ == "__main__":
    main()
