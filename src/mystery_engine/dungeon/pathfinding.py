from __future__ import annotations

from collections import deque

from mystery_engine.core import Direction, GridPos
from .floor import DungeonFloor


DIRECTIONS = list(Direction)


def next_step_toward(floor: DungeonFloor, start: GridPos, goal: GridPos, ignore_entities: bool = False) -> GridPos | None:
    if start == goal:
        return start
    frontier = deque([start])
    came_from: dict[GridPos, GridPos | None] = {start: None}

    while frontier:
        current = frontier.popleft()
        if current == goal:
            break
        for direction in DIRECTIONS:
            nxt = current.moved(direction)
            if nxt in came_from or not floor.in_bounds(nxt):
                continue
            if not floor.tile(nxt).walkable:
                continue
            if abs(direction.dx) == 1 and abs(direction.dy) == 1:
                if not floor.tile(GridPos(current.x + direction.dx, current.y)).walkable:
                    continue
                if not floor.tile(GridPos(current.x, current.y + direction.dy)).walkable:
                    continue
            occupant = floor.entity_at(nxt)
            if occupant is not None and nxt != goal and not ignore_entities:
                continue
            came_from[nxt] = current
            frontier.append(nxt)

    if goal not in came_from:
        return None
    current = goal
    while came_from[current] is not None and came_from[current] != start:
        current = came_from[current]
    return current if came_from[current] == start else None
