from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.editor import run_dungeon_builder
from test_game.content import ENEMY_LABELS, ITEM_LABELS


def main() -> None:
    parser = argparse.ArgumentParser(description="Edit Mystery Engine dungeon definitions")
    parser.add_argument(
        "--dungeon",
        type=Path,
        default=ROOT / "src" / "test_game" / "dungeons" / "test_dungeon.json",
    )
    args = parser.parse_args()
    run_dungeon_builder(
        args.dungeon,
        ROOT / "src" / "test_game" / "assets",
        ENEMY_LABELS,
        ITEM_LABELS,
        project_root=ROOT,
    )


if __name__ == "__main__":
    main()
