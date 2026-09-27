from __future__ import annotations

from dataclasses import dataclass, field

from mystery_engine.core import GridPos
from .floor import DungeonFloor


@dataclass
class ExplorationMemory:
    discovered: set[GridPos] = field(default_factory=set)
    visible: set[GridPos] = field(default_factory=set)

    def update(self, floor: DungeonFloor, origin: GridPos, radius: int = 7) -> None:
        self.visible = compute_fov(floor, origin, radius)
        self.discovered.update(self.visible)

    def mapped_tiles(self, floor: DungeonFloor) -> set[GridPos]:
        """Traversable discovered cells suitable for minimap geometry.

        FOV discovery intentionally includes blocking wall cells at the edge of
        sight. Those are useful for visibility, but the dungeon presentation
        treats wall cells as void and draws boundaries on adjacent walkable
        autotiles. The minimap should therefore map only discovered walkable
        terrain.
        """
        return {pos for pos in self.discovered if floor.tile(pos).walkable}


def compute_fov(floor: DungeonFloor, origin: GridPos, radius: int) -> set[GridPos]:
    visible: set[GridPos] = {origin}
    for y in range(max(0, origin.y - radius), min(floor.height, origin.y + radius + 1)):
        for x in range(max(0, origin.x - radius), min(floor.width, origin.x + radius + 1)):
            target = GridPos(x, y)
            if origin.euclidean(target) > radius + 0.25:
                continue
            if has_line_of_sight(floor, origin, target):
                visible.add(target)
    return visible


def has_line_of_sight(floor: DungeonFloor, start: GridPos, end: GridPos) -> bool:
    points = list(_bresenham(start, end))
    for pos in points[1:-1]:
        if floor.tile(pos).blocks_sight:
            return False
    return True


def _bresenham(start: GridPos, end: GridPos):
    x0, y0 = start.x, start.y
    x1, y1 = end.x, end.y
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        yield GridPos(x0, y0)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
