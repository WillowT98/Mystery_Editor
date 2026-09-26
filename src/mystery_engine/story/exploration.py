from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable, Iterable

from mystery_engine.core import Direction, Vec2


@dataclass(frozen=True)
class RectObstacle:
    x: float
    y: float
    w: float
    h: float

    def contains_circle(self, x: float, y: float, radius: float) -> bool:
        closest_x = max(self.x, min(x, self.x + self.w))
        closest_y = max(self.y, min(y, self.y + self.h))
        return (x - closest_x) ** 2 + (y - closest_y) ** 2 < radius ** 2

    def contains_point(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h

    def translated(self, dx: float, dy: float) -> "RectObstacle":
        return RectObstacle(self.x + dx, self.y + dy, self.w, self.h)

    def bounds(self) -> "RectObstacle":
        return self

    def polygon_points(self) -> tuple[tuple[float, float], ...]:
        return (
            (self.x, self.y),
            (self.x + self.w, self.y),
            (self.x + self.w, self.y + self.h),
            (self.x, self.y + self.h),
        )


@dataclass(frozen=True)
class PolygonObstacle:
    points: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        pts = tuple((float(x), float(y)) for x, y in self.points)
        if len(pts) < 3:
            raise ValueError("PolygonObstacle requires at least three points")
        object.__setattr__(self, "points", pts)

    def translated(self, dx: float, dy: float) -> "PolygonObstacle":
        return PolygonObstacle(tuple((px + dx, py + dy) for px, py in self.points))

    def contains_point(self, x: float, y: float) -> bool:
        inside = False
        n = len(self.points)
        for i in range(n):
            ax, ay = self.points[i]
            bx, by = self.points[(i + 1) % n]
            if _distance_sq_point_to_segment(x, y, ax, ay, bx, by) <= 1e-6:
                return True
            intersects = ((ay > y) != (by > y)) and (x < (bx - ax) * (y - ay) / ((by - ay) or 1e-9) + ax)
            if intersects:
                inside = not inside
        return inside

    def contains_circle(self, x: float, y: float, radius: float) -> bool:
        if self.contains_point(x, y):
            return True
        radius_sq = radius * radius
        n = len(self.points)
        for i in range(n):
            ax, ay = self.points[i]
            bx, by = self.points[(i + 1) % n]
            if _distance_sq_point_to_segment(x, y, ax, ay, bx, by) < radius_sq:
                return True
        return False

    def bounds(self) -> RectObstacle:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
        return RectObstacle(left, top, right - left, bottom - top)


ObstacleShape = RectObstacle | PolygonObstacle


def _distance_sq_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx = bx - ax
    aby = by - ay
    denom = abx * abx + aby * aby
    if denom <= 1e-9:
        dx = px - ax
        dy = py - ay
        return dx * dx + dy * dy
    t = ((px - ax) * abx + (py - ay) * aby) / denom
    t = max(0.0, min(1.0, t))
    qx = ax + t * abx
    qy = ay + t * aby
    dx = px - qx
    dy = py - qy
    return dx * dx + dy * dy


@dataclass(frozen=True)
class TerrainTileMap:
    tile_size: int
    width_tiles: int
    height_tiles: int
    default_terrain: str = "grass"
    tiles: list[list[str]] = field(default_factory=list)
    # Elevation is deliberately separate from terrain type. That lets an upper
    # plateau use the same grass/path terrain vocabulary as the lower meadow,
    # while cliff faces are derived from the height difference between cells.
    default_elevation: int = 0
    elevations: list[list[int]] = field(default_factory=list)
    # Projected screen-space depth of a one-level vertical cliff face. Collision
    # uses this so actors stop at the visible foot of the wall, not halfway
    # through its sprite.
    elevation_face_depth: int = 0

    def terrain_at(self, tx: int, ty: int) -> str:
        if 0 <= ty < self.height_tiles and 0 <= tx < self.width_tiles and self.tiles:
            return self.tiles[ty][tx]
        return self.default_terrain

    def elevation_at(self, tx: int, ty: int) -> int:
        if 0 <= ty < self.height_tiles and 0 <= tx < self.width_tiles and self.elevations:
            return self.elevations[ty][tx]
        return self.default_elevation


@dataclass(frozen=True)
class ExplorationScenery:
    id: str
    sprite_key: str
    position: Vec2
    size: tuple[int, int]
    anchor: str = "bottom_center"
    draw_behind_actors: bool = False
    # Collision shapes are local to scenery.position. For bottom-centered
    # scenery, (0, 0) is the bottom-center anchor used by the renderer.
    collision: ObstacleShape | None = None

    def world_collision(self) -> ObstacleShape | None:
        if self.collision is None:
            return None
        return self.collision.translated(self.position.x, self.position.y)


@dataclass
class ExplorationActor:
    id: str
    name: str
    position: Vec2
    radius: float = 28.0
    facing: Direction = Direction.S
    color_key: str = "neutral"
    sprite_key: str | None = None
    interaction: Callable[[], None] | None = None
    enabled: bool = True


@dataclass
class ExplorationInteractable:
    id: str
    position: Vec2
    interaction: Callable[[], None]
    label: str = "Interact"
    icon_key: str | None = None
    enabled: bool = True
    collision_radius: float = 0.0
    collision: ObstacleShape | None = None
    anchor: str = "bottom_center"
    # Some interactables (scene portals, invisible triggers, etc.) should exist
    # physically/interactively without drawing a runtime sprite.
    visible: bool = True
    # Optional editor/runtime metadata for scene-transition portals.
    portal_facing: str | None = None

    def world_collision(self) -> ObstacleShape | None:
        if self.collision is None:
            return None
        return self.collision.translated(self.position.x, self.position.y)


@dataclass
class ExplorationMap:
    id: str
    width: float
    height: float
    obstacles: list[ObstacleShape] = field(default_factory=list)
    actors: list[ExplorationActor] = field(default_factory=list)
    interactables: list[ExplorationInteractable] = field(default_factory=list)
    terrain: TerrainTileMap | None = None
    scenery: list[ExplorationScenery] = field(default_factory=list)
    blocked_terrain: frozenset[str] = field(default_factory=frozenset)
    music: str | None = None
    music_volume: float = 1.0

    def actor(self, actor_id: str) -> ExplorationActor:
        actor = next((a for a in self.actors if a.id == actor_id), None)
        if actor is None:
            raise KeyError(actor_id)
        return actor

    def try_move(self, actor: ExplorationActor, delta: Vec2) -> None:
        # Resolve each axis independently so characters slide naturally along
        # fences, trunks, shorelines, and other obstacles.
        source_elevation = self._elevation_at_world(actor.position.x, actor.position.y)
        nx = max(actor.radius, min(self.width - actor.radius, actor.position.x + delta.x))
        if not self._collides(actor, nx, actor.position.y, actor.radius, source_elevation):
            actor.position.x = nx
        ny = max(actor.radius, min(self.height - actor.radius, actor.position.y + delta.y))
        if not self._collides(actor, actor.position.x, ny, actor.radius, source_elevation):
            actor.position.y = ny

    def _collides(self, actor: ExplorationActor, x: float, y: float, radius: float, source_elevation: int | None = None) -> bool:
        if any(ob.contains_circle(x, y, radius) for ob in self.obstacles):
            return True

        if self._terrain_collides(x, y, radius, source_elevation):
            return True

        for scenery in self.scenery:
            obstacle = scenery.world_collision()
            if obstacle is not None and obstacle.contains_circle(x, y, radius):
                return True

        for other in self.actors:
            if other is actor or not other.enabled:
                continue
            min_distance = radius + other.radius
            if (x - other.position.x) ** 2 + (y - other.position.y) ** 2 < min_distance ** 2:
                return True

        for item in self.interactables:
            if not item.enabled:
                continue
            obstacle = item.world_collision()
            if obstacle is not None and obstacle.contains_circle(x, y, radius):
                return True
            if item.collision_radius > 0:
                min_distance = radius + item.collision_radius
                if (x - item.position.x) ** 2 + (y - item.position.y) ** 2 < min_distance ** 2:
                    return True

        return False

    def _elevation_at_world(self, x: float, y: float) -> int:
        if self.terrain is None:
            return 0
        tile = self.terrain.tile_size
        tx = max(0, min(self.terrain.width_tiles - 1, int(x // tile)))
        ty = max(0, min(self.terrain.height_tiles - 1, int(y // tile)))
        return self.terrain.elevation_at(tx, ty)

    def _terrain_collides(self, x: float, y: float, radius: float, source_elevation: int | None = None) -> bool:
        if self.terrain is None:
            return False
        tile = self.terrain.tile_size
        min_tx = max(0, int((x - radius) // tile))
        max_tx = min(self.terrain.width_tiles - 1, int((x + radius) // tile))
        min_ty = max(0, int((y - radius) // tile))
        max_ty = min(self.terrain.height_tiles - 1, int((y + radius) // tile))
        if source_elevation is None:
            source_elevation = self._elevation_at_world(x, y)

        for ty in range(min_ty, max_ty + 1):
            for tx in range(min_tx, max_tx + 1):
                obstacle = RectObstacle(tx * tile, ty * tile, tile, tile)
                if not obstacle.contains_circle(x, y, radius):
                    continue
                if self.terrain.terrain_at(tx, ty) in self.blocked_terrain:
                    return True
                if self.terrain.elevation_at(tx, ty) != source_elevation:
                    return True

                # A cliff face is drawn on the lower cell and hangs inward from
                # the higher neighbor. Match collision to that visible wall foot.
                depth = self.terrain.elevation_face_depth
                if depth > 0:
                    cell_elevation = self.terrain.elevation_at(tx, ty)
                    x0, y0 = tx * tile, ty * tile
                    if self.terrain.elevation_at(tx, ty - 1) > cell_elevation:
                        if RectObstacle(x0, y0, tile, depth).contains_circle(x, y, radius):
                            return True
                    if self.terrain.elevation_at(tx, ty + 1) > cell_elevation:
                        if RectObstacle(x0, y0 + tile - depth, tile, depth).contains_circle(x, y, radius):
                            return True
                    if self.terrain.elevation_at(tx - 1, ty) > cell_elevation:
                        if RectObstacle(x0, y0, depth, tile).contains_circle(x, y, radius):
                            return True
                    if self.terrain.elevation_at(tx + 1, ty) > cell_elevation:
                        if RectObstacle(x0 + tile - depth, y0, depth, tile).contains_circle(x, y, radius):
                            return True
        return False

    def nearest_interaction(self, actor: ExplorationActor, max_distance: float):
        candidates: list[tuple[float, Callable[[], None], str]] = []
        for other in self.actors:
            if other is actor or not other.enabled or other.interaction is None:
                continue
            distance = math.hypot(other.position.x - actor.position.x, other.position.y - actor.position.y)
            if distance <= max_distance:
                candidates.append((distance, other.interaction, other.name))
        for item in self.interactables:
            if not item.enabled:
                continue
            distance = math.hypot(item.position.x - actor.position.x, item.position.y - actor.position.y)
            if distance <= max_distance:
                candidates.append((distance, item.interaction, item.label))
        if not candidates:
            return None
        return min(candidates, key=lambda c: c[0])
