from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.project_runtime import build_project_game


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Mystery Engine project")
    parser.add_argument(
        "--project",
        type=Path,
        default=ROOT / "src" / "test_game",
        help="Project folder containing project.json.",
    )
    parser.add_argument(
        "--locale",
        help="Game locale to use, e.g. en-US, fr-FR, or ja-JP.",
    )
    args = parser.parse_args()
    if args.locale:
        os.environ["MYSTERY_LOCALE"] = args.locale

    build_project_game(args.project).run()


if __name__ == "__main__":
    main()
