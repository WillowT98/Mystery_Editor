from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from test_game.game_definition import build_game


def main() -> None:
    game = build_game()
    game.run()


if __name__ == "__main__":
    main()
