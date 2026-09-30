from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.editor import run_dungeon_builder
from mystery_engine.project import ProjectRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Edit Mystery Engine dungeon definitions")
    parser.add_argument(
        "--dungeon",
        type=Path,
        default=ROOT / "src" / "test_game" / "dungeons" / "test_dungeon.json",
    )
    args = parser.parse_args()
    registry = ProjectRegistry.load(ROOT / "src" / "test_game")
    run_dungeon_builder(
        args.dungeon,
        registry.asset_root,
        registry.enemy_labels,
        registry.item_labels,
        project_root=ROOT,
        project_registry=registry,
    )


if __name__ == "__main__":
    main()
