from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.editor import run_project_editor
from test_game.world_assets import WORLD_ASSETS
from test_game.content import ITEM_LABELS


def main() -> None:
    run_project_editor(ROOT / "src" / "test_game", WORLD_ASSETS, ROOT, ITEM_LABELS)


if __name__ == "__main__":
    main()
