from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.editor import run_story_editor
from mystery_engine.project import ProjectRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Edit Mystery Engine story/dialogue graphs")
    parser.add_argument(
        "--story",
        type=Path,
        default=ROOT / "src" / "test_game" / "stories" / "mara_meadow.json",
    )
    args = parser.parse_args()
    registry = ProjectRegistry.load(ROOT / "src" / "test_game")
    run_story_editor(args.story, project_root=ROOT, project_registry=registry)


if __name__ == "__main__":
    main()
