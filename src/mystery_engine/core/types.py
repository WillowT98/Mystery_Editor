from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
import math


class GameMode(Enum):
    EXPLORATION = auto()
    DUNGEON = auto()


class DungeonResult(Enum):
    SUCCESS = auto()
    DEFEAT = auto()
    ABANDONED = auto()


class Direction(Enum):
    N = (0, -1)
    NE = (1, -1)
    E = (1, 0)
    SE = (1, 1)
    S = (0, 1)
    SW = (-1, 1)
    W = (-1, 0)
    NW = (-1, -1)

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]

    @property
    def opposite(self) -> "Direction":
        return Direction.from_axes(-self.dx, -self.dy)  # type: ignore[return-value]

    @classmethod
    def from_axes(cls, x: int, y: int) -> "Direction | None":
        sx = 0 if x == 0 else (1 if x > 0 else -1)
        sy = 0 if y == 0 else (1 if y > 0 else -1)
        if sx == 0 and sy == 0:
            return None
        for direction in cls:
            if direction.value == (sx, sy):
                return direction
        return None


@dataclass(frozen=True, order=True)
class GridPos:
    x: int
    y: int

    def moved(self, direction: Direction) -> "GridPos":
        return GridPos(self.x + direction.dx, self.y + direction.dy)

    def chebyshev(self, other: "GridPos") -> int:
        return max(abs(self.x - other.x), abs(self.y - other.y))

    def euclidean(self, other: "GridPos") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass
class Vec2:
    x: float
    y: float

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vec2":
        length = self.length()
        if length <= 1e-9:
            return Vec2(0.0, 0.0)
        return Vec2(self.x / length, self.y / length)
