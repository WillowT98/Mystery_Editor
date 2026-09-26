from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from .types import Direction, GridPos


class TargetKind(Enum):
    ENEMY = auto()
    ALLY = auto()
    SELF = auto()


class AITactic(Enum):
    FOLLOW = "Follow closely"
    ATTACK = "Attack nearby"
    PROTECT = "Protect leader"
    CONSERVE = "Conserve skills"


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    target: TargetKind
    range: int
    power: int = 0
    heal: int = 0
    damage_type: str | None = None
    costs: dict[str, int] = field(default_factory=dict)
    max_charges: int | None = None
    accuracy: float = 1.0
    sfx_cue: str | None = None
    impact_sfx_cue: str | None = None


@dataclass
class SkillRuntime:
    definition: SkillDefinition
    charges: int | None = None

    @classmethod
    def from_definition(cls, definition: SkillDefinition) -> "SkillRuntime":
        return cls(definition=definition, charges=definition.max_charges)

    def available(self, resources: dict[str, int]) -> bool:
        if self.charges is not None and self.charges <= 0:
            return False
        return all(resources.get(name, 0) >= amount for name, amount in self.definition.costs.items())

    def spend(self, resources: dict[str, int]) -> None:
        if self.charges is not None:
            self.charges -= 1
        for name, amount in self.definition.costs.items():
            resources[name] = resources.get(name, 0) - amount


@dataclass
class Stats:
    max_hp: int
    attack: int
    defense: int
    current_hp: int | None = None

    def __post_init__(self) -> None:
        if self.current_hp is None:
            self.current_hp = self.max_hp
        self.current_hp = max(0, min(self.max_hp, int(self.current_hp)))

    @property
    def alive(self) -> bool:
        return self.current_hp > 0

    @property
    def hp_ratio(self) -> float:
        return self.current_hp / self.max_hp if self.max_hp else 0.0

    def heal(self, amount: int) -> int:
        before = self.current_hp
        self.current_hp = min(self.max_hp, self.current_hp + max(0, amount))
        return self.current_hp - before

    def damage(self, amount: int) -> int:
        amount = max(0, amount)
        before = self.current_hp
        self.current_hp = max(0, self.current_hp - amount)
        return before - self.current_hp


@dataclass
class Character:
    id: str
    name: str
    stats: Stats
    skills: list[SkillRuntime] = field(default_factory=list)
    resources: dict[str, int] = field(default_factory=dict)
    resistances: dict[str, float] = field(default_factory=dict)
    party_member: bool = False
    hostile: bool = False
    leader: bool = False
    ai_tactic: AITactic = AITactic.FOLLOW
    grid_pos: GridPos | None = None
    facing: Direction = Direction.S
    incapacitated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.stats.alive and not self.incapacitated

    def resistance_to(self, damage_type: str | None) -> float:
        if not damage_type:
            return 1.0
        return self.resistances.get(damage_type, 1.0)

    def skill(self, skill_id: str) -> SkillRuntime | None:
        return next((skill for skill in self.skills if skill.definition.id == skill_id), None)

    def restore_for_expedition(self) -> None:
        self.stats.current_hp = self.stats.max_hp
        self.incapacitated = False
        for skill in self.skills:
            skill.charges = skill.definition.max_charges
