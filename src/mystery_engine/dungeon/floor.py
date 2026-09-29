from __future__ import annotations

from dataclasses import dataclass, field

from mystery_engine.core import Character, GridPos, ItemDefinition
from .tiles import FLOOR, STAIRS, WALL, Tile


@dataclass
class GroundItem:
    item: ItemDefinition
    pos: GridPos


@dataclass
class DungeonFloor:
    width: int
    height: int
    tiles: list[list[Tile]]
    rooms: list[tuple[int, int, int, int]] = field(default_factory=list)
    entities: list[Character] = field(default_factory=list)
    ground_items: list[GroundItem] = field(default_factory=list)
    player_spawn: GridPos | None = None
    stairs_pos: GridPos | None = None
    tileset: str = "dungeon"
    music: str | None = None
    music_volume: float = 1.0
    dungeon_name: str = "Dungeon"
    generation_profile: str = "default"

    @classmethod
    def empty(cls, width: int, height: int) -> "DungeonFloor":
        return cls(width, height, [[WALL for _ in range(width)] for _ in range(height)])

    def in_bounds(self, pos: GridPos) -> bool:
        return 0 <= pos.x < self.width and 0 <= pos.y < self.height

    def tile(self, pos: GridPos) -> Tile:
        if not self.in_bounds(pos):
            return WALL
        return self.tiles[pos.y][pos.x]

    def set_floor(self, pos: GridPos) -> None:
        self.tiles[pos.y][pos.x] = FLOOR

    def set_stairs(self, pos: GridPos) -> None:
        self.tiles[pos.y][pos.x] = STAIRS
        self.stairs_pos = pos

    def entity_at(self, pos: GridPos, include_inactive: bool = False) -> Character | None:
        for entity in self.entities:
            if entity.grid_pos == pos and (include_inactive or entity.active):
                return entity
        return None

    def item_at(self, pos: GridPos) -> GroundItem | None:
        return next((item for item in self.ground_items if item.pos == pos), None)

    def is_walkable(self, pos: GridPos, ignore_entity: Character | None = None) -> bool:
        if not self.tile(pos).walkable:
            return False
        occupant = self.entity_at(pos)
        return occupant is None or occupant is ignore_entity

    def terrain_allows_step(self, start: GridPos, end: GridPos) -> bool:
        if not self.tile(end).walkable:
            return False
        dx = end.x - start.x
        dy = end.y - start.y
        if abs(dx) > 1 or abs(dy) > 1 or (dx == 0 and dy == 0):
            return False
        if abs(dx) == 1 and abs(dy) == 1:
            side_a = GridPos(start.x + dx, start.y)
            side_b = GridPos(start.x, start.y + dy)
            if not self.tile(side_a).walkable or not self.tile(side_b).walkable:
                return False
        return True

    def can_step(self, start: GridPos, end: GridPos, ignore_entity: Character | None = None) -> bool:
        if not self.terrain_allows_step(start, end):
            return False
        return self.is_walkable(end, ignore_entity)
