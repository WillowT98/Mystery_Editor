from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TileKind(Enum):
    WALL = auto()
    FLOOR = auto()
    STAIRS = auto()


@dataclass(frozen=True)
class Tile:
    kind: TileKind
    walkable: bool
    blocks_sight: bool
    terrain: str = "normal"


WALL = Tile(TileKind.WALL, False, True)
FLOOR = Tile(TileKind.FLOOR, True, False)
STAIRS = Tile(TileKind.STAIRS, True, False)
