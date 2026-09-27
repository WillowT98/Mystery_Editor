from __future__ import annotations

from mystery_engine.core import Character, Direction, GridPos, RangePattern, TargetKind
from mystery_engine.core.models import SkillDefinition
from .floor import DungeonFloor


def effective_range_pattern(definition: SkillDefinition) -> RangePattern:
    raw = getattr(definition, "range_pattern", None)
    if isinstance(raw, RangePattern):
        return raw
    if isinstance(raw, str):
        try:
            return RangePattern(raw)
        except ValueError:
            pass
    if definition.target is TargetKind.SELF:
        return RangePattern.SELF
    if definition.range <= 1:
        return RangePattern.ADJACENT
    if definition.range == 2:
        return RangePattern.TWO_TILES
    return RangePattern.LINE


def _same_alignment(a: GridPos, b: GridPos) -> tuple[int, int, int] | None:
    dx = b.x - a.x
    dy = b.y - a.y
    if dx == 0 and dy == 0:
        return None
    if dx != 0 and dy != 0 and abs(dx) != abs(dy):
        return None
    sx = 0 if dx == 0 else (1 if dx > 0 else -1)
    sy = 0 if dy == 0 else (1 if dy > 0 else -1)
    return sx, sy, max(abs(dx), abs(dy))


def _entity_matches_target(actor: Character, candidate: Character, kind: TargetKind) -> bool:
    if not candidate.active:
        return False
    if kind is TargetKind.SELF:
        return candidate is actor
    if kind is TargetKind.ENEMY:
        return candidate.hostile != actor.hostile
    if kind is TargetKind.ALLY:
        return candidate.hostile == actor.hostile
    return False


def _first_entity_on_ray(
    floor: DungeonFloor,
    origin: GridPos,
    direction: Direction,
    max_distance: int,
) -> Character | None:
    pos = origin
    for _ in range(max_distance):
        pos = pos.moved(direction)
        if not floor.in_bounds(pos) or floor.tile(pos).blocks_sight:
            return None
        entity = floor.entity_at(pos)
        if entity is not None and entity.active:
            return entity
    return None


def room_containing(floor: DungeonFloor, pos: GridPos) -> tuple[int, int, int, int] | None:
    for room in floor.rooms:
        x, y, w, h = room
        if x <= pos.x < x + w and y <= pos.y < y + h:
            return room
    return None


def target_is_valid(
    floor: DungeonFloor,
    actor: Character,
    target: Character,
    definition: SkillDefinition,
) -> bool:
    if actor.grid_pos is None or target.grid_pos is None:
        return False
    if not _entity_matches_target(actor, target, definition.target):
        return False

    pattern = effective_range_pattern(definition)
    if pattern is RangePattern.SELF:
        return target is actor

    if pattern is RangePattern.ROOM:
        room = room_containing(floor, actor.grid_pos)
        if room is None:
            return False
        x, y, w, h = room
        return x <= target.grid_pos.x < x + w and y <= target.grid_pos.y < y + h

    aligned = _same_alignment(actor.grid_pos, target.grid_pos)
    if aligned is None:
        return False
    dx, dy, distance = aligned
    direction = Direction.from_axes(dx, dy)
    if direction is None:
        return False

    if pattern is RangePattern.ADJACENT:
        return distance == 1

    max_distance = 2 if pattern is RangePattern.TWO_TILES else max(1, definition.range)
    if distance > max_distance:
        return False

    # Directional PMD ranges stop at the first entity, regardless of allegiance.
    # This prevents shots and two-tile attacks from passing through party members
    # or enemies to reach something behind them.
    return _first_entity_on_ray(floor, actor.grid_pos, direction, max_distance) is target


def targets_for_skill(
    floor: DungeonFloor,
    actor: Character,
    definition: SkillDefinition,
    *,
    facing: Direction | None = None,
) -> list[Character]:
    if actor.grid_pos is None:
        return []
    pattern = effective_range_pattern(definition)

    if pattern is RangePattern.SELF:
        return [actor] if _entity_matches_target(actor, actor, definition.target) else []

    if pattern is RangePattern.ROOM:
        room = room_containing(floor, actor.grid_pos)
        if room is None:
            return []
        x, y, w, h = room
        return [
            entity
            for entity in floor.entities
            if entity.grid_pos is not None
            and x <= entity.grid_pos.x < x + w
            and y <= entity.grid_pos.y < y + h
            and _entity_matches_target(actor, entity, definition.target)
        ]

    if facing is not None:
        max_distance = 1 if pattern is RangePattern.ADJACENT else (2 if pattern is RangePattern.TWO_TILES else max(1, definition.range))
        first = _first_entity_on_ray(floor, actor.grid_pos, facing, max_distance)
        return [first] if first is not None and _entity_matches_target(actor, first, definition.target) else []

    # AI/non-facing queries may consider any of the eight PMD directions.
    candidates: list[Character] = []
    for direction in Direction:
        max_distance = 1 if pattern is RangePattern.ADJACENT else (2 if pattern is RangePattern.TWO_TILES else max(1, definition.range))
        first = _first_entity_on_ray(floor, actor.grid_pos, direction, max_distance)
        if first is not None and _entity_matches_target(actor, first, definition.target):
            candidates.append(first)
    return candidates
