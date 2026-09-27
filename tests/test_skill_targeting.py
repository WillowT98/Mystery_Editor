from __future__ import annotations

from pathlib import Path
from random import Random
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.core import (
    Character,
    GridPos,
    Inventory,
    RangePattern,
    SkillDefinition,
    SkillRuntime,
    Stats,
    TargetKind,
)
from mystery_engine.dungeon import DungeonFloor, target_is_valid, targets_for_skill
from mystery_engine.dungeon.actions import SkillAction
from mystery_engine.dungeon.turns import TurnManager


def _character(identifier: str, pos: GridPos, *, hostile: bool = False) -> Character:
    return Character(identifier, identifier.title(), Stats(30, 5, 2), hostile=hostile, grid_pos=pos)


def _room_floor() -> DungeonFloor:
    floor = DungeonFloor.empty(12, 8)
    room = (2, 2, 6, 4)
    for y in range(room[1], room[1] + room[3]):
        for x in range(room[0], room[0] + room[2]):
            floor.set_floor(GridPos(x, y))
    # A corridor outside the room is walkable but should not count as room range.
    for x in range(8, 11):
        floor.set_floor(GridPos(x, 3))
    floor.rooms = [room]
    return floor


def test_adjacent_pattern_only_hits_neighboring_aligned_target():
    floor = _room_floor()
    actor = _character("actor", GridPos(3, 3))
    adjacent = _character("adjacent", GridPos(4, 3), hostile=True)
    distant = _character("distant", GridPos(5, 3), hostile=True)
    floor.entities.extend([actor, adjacent, distant])
    skill = SkillDefinition(
        "adj", "Adjacent", "", TargetKind.ENEMY, 1,
        power=1, range_pattern=RangePattern.ADJACENT,
    )
    assert target_is_valid(floor, actor, adjacent, skill)
    assert not target_is_valid(floor, actor, distant, skill)


def test_two_tile_pattern_is_blocked_by_first_entity():
    floor = _room_floor()
    actor = _character("actor", GridPos(3, 3))
    blocker = _character("blocker", GridPos(4, 3), hostile=False)
    enemy = _character("enemy", GridPos(5, 3), hostile=True)
    floor.entities.extend([actor, blocker, enemy])
    skill = SkillDefinition(
        "quick", "Quick", "", TargetKind.ENEMY, 2,
        power=1, range_pattern=RangePattern.TWO_TILES,
    )
    assert not target_is_valid(floor, actor, enemy, skill)
    assert targets_for_skill(floor, actor, skill) == []


def test_two_tile_pattern_can_hit_first_enemy_one_or_two_tiles_away():
    floor = _room_floor()
    actor = _character("actor", GridPos(3, 3))
    enemy = _character("enemy", GridPos(5, 3), hostile=True)
    floor.entities.extend([actor, enemy])
    skill = SkillDefinition(
        "quick", "Quick", "", TargetKind.ENEMY, 2,
        power=1, range_pattern=RangePattern.TWO_TILES,
    )
    assert target_is_valid(floor, actor, enemy, skill)
    assert targets_for_skill(floor, actor, skill, facing=actor.facing.__class__.E) == [enemy]


def test_line_pattern_hits_first_entity_only_and_respects_max_range():
    floor = _room_floor()
    actor = _character("actor", GridPos(3, 3))
    first = _character("first", GridPos(6, 3), hostile=True)
    behind = _character("behind", GridPos(7, 3), hostile=True)
    floor.entities.extend([actor, first, behind])
    skill = SkillDefinition(
        "beam", "Beam", "", TargetKind.ENEMY, 4,
        power=1, range_pattern=RangePattern.LINE,
    )
    assert target_is_valid(floor, actor, first, skill)
    assert not target_is_valid(floor, actor, behind, skill)

    first.grid_pos = GridPos(9, 3)
    behind.grid_pos = GridPos(10, 3)
    assert not target_is_valid(floor, actor, first, skill)


def test_room_pattern_targets_only_matching_entities_in_same_room():
    floor = _room_floor()
    actor = _character("actor", GridPos(3, 3))
    in_room_a = _character("a", GridPos(4, 3), hostile=True)
    in_room_b = _character("b", GridPos(7, 4), hostile=True)
    corridor = _character("corridor", GridPos(9, 3), hostile=True)
    ally = _character("ally", GridPos(5, 4), hostile=False)
    floor.entities.extend([actor, in_room_a, in_room_b, corridor, ally])
    skill = SkillDefinition(
        "room", "Room", "", TargetKind.ENEMY, 99,
        power=1, range_pattern=RangePattern.ROOM,
    )
    assert {target.id for target in targets_for_skill(floor, actor, skill)} == {"a", "b"}


def test_self_pattern_targets_only_user():
    floor = _room_floor()
    actor = _character("actor", GridPos(3, 3))
    ally = _character("ally", GridPos(4, 3))
    floor.entities.extend([actor, ally])
    skill = SkillDefinition(
        "focus", "Focus", "", TargetKind.SELF, 0,
        heal=5, range_pattern=RangePattern.SELF,
    )
    assert targets_for_skill(floor, actor, skill) == [actor]
    assert target_is_valid(floor, actor, actor, skill)
    assert not target_is_valid(floor, actor, ally, skill)


def test_room_skill_affects_all_targets_but_spends_one_charge():
    floor = _room_floor()
    actor = _character("actor", GridPos(3, 3))
    actor.party_member = True
    enemy_a = _character("a", GridPos(4, 3), hostile=True)
    enemy_b = _character("b", GridPos(6, 4), hostile=True)
    floor.entities.extend([actor, enemy_a, enemy_b])

    definition = SkillDefinition(
        "burst", "Burst", "", TargetKind.ENEMY, 99,
        power=3, max_charges=2, range_pattern=RangePattern.ROOM,
    )
    runtime = SkillRuntime.from_definition(definition)
    actor.skills = [runtime]

    turns = TurnManager(floor, [actor], Inventory(4), actor, Random(1))
    before_a = enemy_a.stats.current_hp
    before_b = enemy_b.stats.current_hp
    messages: list[str] = []

    consumed = turns._resolve_action(SkillAction(actor, runtime, None), messages)

    assert consumed
    assert enemy_a.stats.current_hp < before_a
    assert enemy_b.stats.current_hp < before_b
    assert runtime.charges == 1
