from __future__ import annotations

from dataclasses import dataclass

from mystery_engine.core import Character, Direction, GridPos, SkillRuntime


@dataclass(frozen=True)
class Action:
    actor: Character


@dataclass(frozen=True)
class MoveAction(Action):
    direction: Direction


@dataclass(frozen=True)
class WaitAction(Action):
    pass


@dataclass(frozen=True)
class BasicAttackAction(Action):
    target: Character


@dataclass(frozen=True)
class SkillAction(Action):
    skill: SkillRuntime
    target: Character


@dataclass(frozen=True)
class PickupAction(Action):
    position: GridPos
