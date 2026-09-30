from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Mystery Engine project")
    parser.add_argument(
        "--project",
        type=Path,
        help="Project folder containing project.json. Omit for the legacy test game.",
    )
    parser.add_argument(
        "--locale",
        help="Game locale to use, e.g. en-US, fr-FR, or ja-JP.",
    )
    args = parser.parse_args()
    if args.locale:
        import os
        os.environ["MYSTERY_LOCALE"] = args.locale

    if args.project is not None:
        from mystery_engine.project_runtime import build_project_game
        game = build_project_game(args.project)
    else:
        from test_game.game_definition import build_game
        game = build_game()
    game.run()


if __name__ == "__main__":
    main()
