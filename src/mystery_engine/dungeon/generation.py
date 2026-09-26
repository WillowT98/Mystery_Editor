from __future__ import annotations

from dataclasses import dataclass
from random import Random

from mystery_engine.core import GridPos
from .floor import DungeonFloor


@dataclass(frozen=True)
class GeneratorConfig:
    width: int = 38
    height: int = 28
    room_count_min: int = 6
    room_count_max: int = 9
    room_w_min: int = 4
    room_w_max: int = 9
    room_h_min: int = 4
    room_h_max: int = 8
    attempts: int = 140


class RoomsAndCorridorsGenerator:
    def __init__(self, config: GeneratorConfig | None = None, rng: Random | None = None) -> None:
        self.config = config or GeneratorConfig()
        self.rng = rng or Random()

    def generate(self) -> DungeonFloor:
        c = self.config
        floor = DungeonFloor.empty(c.width, c.height)
        target_count = self.rng.randint(c.room_count_min, c.room_count_max)
        rooms: list[tuple[int, int, int, int]] = []

        for _ in range(c.attempts):
            if len(rooms) >= target_count:
                break
            w = self.rng.randint(c.room_w_min, c.room_w_max)
            h = self.rng.randint(c.room_h_min, c.room_h_max)
            x = self.rng.randint(2, c.width - w - 3)
            y = self.rng.randint(2, c.height - h - 3)
            candidate = (x, y, w, h)
            if any(self._overlaps(candidate, other, pad=1) for other in rooms):
                continue
            rooms.append(candidate)
            self._carve_room(floor, candidate)

        if len(rooms) < 2:
            # Deterministic safety fallback.
            rooms = [(3, 3, 7, 6), (c.width - 11, c.height - 9, 7, 6)]
            floor = DungeonFloor.empty(c.width, c.height)
            for room in rooms:
                self._carve_room(floor, room)

        # Connect all rooms in shuffled order, with occasional extra loop edges.
        self.rng.shuffle(rooms)
        for a, b in zip(rooms, rooms[1:]):
            self._carve_corridor(floor, self._center(a), self._center(b))
        if len(rooms) >= 4:
            for _ in range(max(1, len(rooms) // 3)):
                a, b = self.rng.sample(rooms, 2)
                self._carve_corridor(floor, self._center(a), self._center(b))

        floor.rooms = rooms
        spawn_room = rooms[0]
        stair_room = max(rooms[1:], key=lambda r: self._center(r).euclidean(self._center(spawn_room)))
        floor.player_spawn = self._center(spawn_room)
        floor.set_stairs(self._center(stair_room))
        return floor

    @staticmethod
    def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int], pad: int = 0) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (
            ax + aw + pad <= bx or bx + bw + pad <= ax or
            ay + ah + pad <= by or by + bh + pad <= ay
        )

    @staticmethod
    def _center(room: tuple[int, int, int, int]) -> GridPos:
        x, y, w, h = room
        return GridPos(x + w // 2, y + h // 2)

    @staticmethod
    def _carve_room(floor: DungeonFloor, room: tuple[int, int, int, int]) -> None:
        x, y, w, h = room
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                floor.set_floor(GridPos(xx, yy))

    def _carve_corridor(self, floor: DungeonFloor, a: GridPos, b: GridPos) -> None:
        if self.rng.random() < 0.5:
            self._carve_h(floor, a.x, b.x, a.y)
            self._carve_v(floor, a.y, b.y, b.x)
        else:
            self._carve_v(floor, a.y, b.y, a.x)
            self._carve_h(floor, a.x, b.x, b.y)

    @staticmethod
    def _carve_h(floor: DungeonFloor, x1: int, x2: int, y: int) -> None:
        for x in range(min(x1, x2), max(x1, x2) + 1):
            floor.set_floor(GridPos(x, y))

    @staticmethod
    def _carve_v(floor: DungeonFloor, y1: int, y2: int, x: int) -> None:
        for y in range(min(y1, y2), max(y1, y2) + 1):
            floor.set_floor(GridPos(x, y))
