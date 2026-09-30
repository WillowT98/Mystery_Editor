from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.editor import run_project_editor
from mystery_engine.project_runtime import SYSTEM_WORLD_ASSETS


def main() -> None:
    parser = argparse.ArgumentParser(description="Open the Mystery Engine game maker")
    parser.add_argument(
        "--project",
        type=Path,
        default=ROOT / "src" / "test_game",
        help="Project folder containing project.json",
    )
    args = parser.parse_args()
    run_project_editor(args.project, SYSTEM_WORLD_ASSETS, ROOT)


if __name__ == "__main__":
    main()
