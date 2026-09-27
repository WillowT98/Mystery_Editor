from __future__ import annotations

from dataclasses import dataclass
from random import Random

from .models import Character, SkillRuntime, TargetKind
from .types import GridPos


@dataclass(frozen=True)
class ProjectileEvent:
    source_id: str
    target_id: str
    source_pos: GridPos
    target_pos: GridPos
    projectile_key: str
    hit: bool = True
    launch_sfx_cue: str | None = None
    impact_sfx_cue: str | None = None
    arc_px: float = 0.0


@dataclass(frozen=True)
class CombatEvent:
    text: str
    amount: int = 0
    kind: str = "info"


class CombatResolver:
    def __init__(self, rng: Random | None = None) -> None:
        self.rng = rng or Random()

    def basic_attack(self, attacker: Character, defender: Character) -> CombatEvent:
        raw = max(1, 4 + attacker.stats.attack - defender.stats.defense + self.rng.randint(-1, 1))
        dealt = defender.stats.damage(raw)
        return CombatEvent(f"{attacker.name} attacks {defender.name} for {dealt} damage.", dealt, "damage")

    def use_skill(self, user: Character, skill: SkillRuntime, target: Character) -> CombatEvent:
        definition = skill.definition
        if not skill.available(user.resources):
            return CombatEvent(f"{definition.name} is unavailable.")
        if self.rng.random() > definition.accuracy:
            skill.spend(user.resources)
            return CombatEvent(f"{user.name}'s {definition.name} misses.", 0, "miss")

        if definition.target in (TargetKind.ALLY, TargetKind.SELF) and definition.heal > 0:
            healed = target.stats.heal(definition.heal)
            skill.spend(user.resources)
            return CombatEvent(f"{user.name} uses {definition.name}; {target.name} recovers {healed} HP.", healed, "heal")

        raw = max(1, definition.power + user.stats.attack - target.stats.defense + self.rng.randint(-1, 1))
        multiplier = target.resistance_to(definition.damage_type)
        dealt = target.stats.damage(max(1, round(raw * multiplier)))
        skill.spend(user.resources)
        type_note = f" {definition.damage_type}" if definition.damage_type else ""
        return CombatEvent(f"{user.name} uses {definition.name} for {dealt}{type_note} damage.", dealt, "damage")
