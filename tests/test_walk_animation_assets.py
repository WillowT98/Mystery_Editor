from __future__ import annotations

import struct
from pathlib import Path


ASSET_DIR = Path(__file__).parents[1] / "src" / "test_game" / "assets" / "characters"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_main_character_walk_atlases_are_directional_8_by_4_sheets() -> None:
    expected_size = (48 * 8, 48 * 4)
    assert _png_size(ASSET_DIR / "fox_walk.png") == expected_size
    assert _png_size(ASSET_DIR / "mara_walk.png") == expected_size
