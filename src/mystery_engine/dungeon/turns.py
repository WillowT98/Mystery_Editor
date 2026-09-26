from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Callable

from mystery_engine.core import Character, CombatResolver, Direction, DungeonResult, GridPos, Inventory, TargetKind
from .actions import Action, BasicAttackAction, MoveAction, PickupAction, SkillAction, WaitAction
from .floor import DungeonFloor
from .pathfinding import next_step_toward
from .visibility import ExplorationMemory, has_line_of_sight


@dataclass
class TurnOutcome:
    messages: list[str] = field(default_factory=list)
    consumed_turn: bool = True
    dungeon_result: DungeonResult | None = None


class TurnManager:
    def __init__(
        self,
        floor: DungeonFloor,
        party: list[Character],
        bag: Inventory,
        leader: Character,
        rng: Random | None = None,
    ) -> None:
        self.floor = floor
        self.party = party
        self.bag = bag
        self.leader = leader
        self.rng = rng or Random()
        self.combat = CombatResolver(self.rng)
        self.memory = ExplorationMemory()
        self.turn_count = 0
        self._companions_moved_by_player: set[str] = set()
        self.refresh_visibility()

    @property
    def enemies(self) -> list[Character]:
        return [e for e in self.floor.entities if e.hostile and e.active]

    @property
    def allies(self) -> list[Character]:
        return [e for e in self.party if e.active]

    def refresh_visibility(self) -> None:
        if self.leader.grid_pos:
            self.memory.update(self.floor, self.leader.grid_pos)

    def execute_player_action(self, action: Action) -> TurnOutcome:
        outcome = TurnOutcome()
        if not self.leader.active:
            outcome.dungeon_result = DungeonResult.DEFEAT
            return outcome

        self._companions_moved_by_player.clear()
        consumed = self._resolve_action(action, outcome.messages)
        outcome.consumed_turn = consumed
        if not consumed:
            return outcome

        self.turn_count += 1
        self._pickup_underfoot(self.leader, outcome.messages)
        if self._check_stairs(outcome):
            return outcome

        for ally in [c for c in self.party if c is not self.leader and c.active]:
            if ally.id in self._companions_moved_by_player:
                continue
            ai_action = self._choose_companion_action(ally)
            if ai_action:
                self._resolve_action(ai_action, outcome.messages)
                self._pickup_underfoot(ally, outcome.messages, allow_pickup=False)

        for enemy in list(self.enemies):
            if not enemy.active:
                continue
            ai_action = self._choose_enemy_action(enemy)
            if ai_action:
                self._resolve_action(ai_action, outcome.messages)
            if not self.leader.active:
                outcome.dungeon_result = DungeonResult.DEFEAT
                break

        self._apply_incapacitation(outcome.messages)
        self.refresh_visibility()
        return outcome

    def _resolve_action(self, action: Action, messages: list[str]) -> bool:
        actor = action.actor
        if not actor.active:
            return False
        if isinstance(action, WaitAction):
            messages.append(f"{actor.name} waits.")
            return True
        if isinstance(action, BasicAttackAction):
            event = self.combat.basic_attack(actor, action.target)
            messages.append(event.text)
            return True
        if isinstance(action, SkillAction):
            if actor.grid_pos is None or action.target.grid_pos is None:
                return False
            if actor.grid_pos.chebyshev(action.target.grid_pos) > action.skill.definition.range:
                messages.append(f"{action.skill.definition.name} has no target in range.")
                return False
            event = self.combat.use_skill(actor, action.skill, action.target)
            messages.append(event.text)
            return not event.text.endswith("unavailable.")
        if isinstance(action, PickupAction):
            return self._pickup_at(action.position, messages)
        if isinstance(action, MoveAction):
            if actor.grid_pos is None:
                return False
            actor.facing = action.direction
            destination = actor.grid_pos.moved(action.direction)
            occupant = self.floor.entity_at(destination)
            if occupant is not None:
                if occupant.hostile != actor.hostile:
                    event = self.combat.basic_attack(actor, occupant)
                    messages.append(event.text)
                    return True

                # The player-controlled leader may move through a companion by
                # swapping cells with them. The swap is the companion's movement
                # for this turn, so they do not then receive a second AI action.
                if actor is self.leader and occupant in self.party and occupant is not self.leader:
                    if not self.floor.terrain_allows_step(actor.grid_pos, destination):
                        return False
                    origin = actor.grid_pos
                    actor.grid_pos = destination
                    occupant.grid_pos = origin
                    occupant.facing = action.direction.opposite
                    self._companions_moved_by_player.add(occupant.id)
                    return True
                return False
            if not self.floor.can_step(actor.grid_pos, destination, ignore_entity=actor):
                return False
            actor.grid_pos = destination
            return True
        return False

    def _pickup_at(self, pos: GridPos, messages: list[str]) -> bool:
        ground = self.floor.item_at(pos)
        if ground is None:
            return False
        if not self.bag.add(ground.item):
            messages.append("The bag is full.")
            return False
        self.floor.ground_items.remove(ground)
        messages.append(f"Picked up {ground.item.name}.")
        return True

    def _pickup_underfoot(self, actor: Character, messages: list[str], allow_pickup: bool = True) -> None:
        if allow_pickup and actor.grid_pos:
            self._pickup_at(actor.grid_pos, messages)

    def _check_stairs(self, outcome: TurnOutcome) -> bool:
        if self.leader.grid_pos == self.floor.stairs_pos:
            outcome.messages.append("Fox reaches the stairs.")
            return True
        return False

    def _apply_incapacitation(self, messages: list[str]) -> None:
        for member in self.party:
            if member is self.leader:
                continue
            if member.stats.current_hp <= 0 and not member.incapacitated:
                member.incapacitated = True
                messages.append(f"{member.name} is incapacitated for the expedition.")

    def _choose_companion_action(self, ally: Character) -> Action | None:
        if ally.grid_pos is None or self.leader.grid_pos is None:
            return None

        # "Follow closely" should actually keep the companion near the leader.
        leash = 1 if ally.ai_tactic.name == "FOLLOW" else (2 if ally.ai_tactic.name == "PROTECT" else 99)

        # Heal a seriously injured active ally first, as long as doing so does not break the leash.
        heal_skill = next((s for s in ally.skills if s.definition.heal > 0 and s.available(ally.resources)), None)
        if heal_skill and ally.ai_tactic.name != "CONSERVE":
            candidates = [a for a in self.allies if a.stats.hp_ratio <= 0.60 and a.grid_pos is not None]
            candidates = [a for a in candidates if ally.grid_pos.chebyshev(a.grid_pos) <= heal_skill.definition.range]
            if ally.ai_tactic.name == "FOLLOW":
                candidates = [a for a in candidates if a.grid_pos.chebyshev(self.leader.grid_pos) <= leash]
            if candidates:
                target = min(candidates, key=lambda c: c.stats.hp_ratio)
                return SkillAction(ally, heal_skill, target)

        enemy = self._nearest(ally, self.enemies)
        if enemy is not None and enemy.grid_pos is not None:
            dist_enemy = ally.grid_pos.chebyshev(enemy.grid_pos)
            dist_leader = ally.grid_pos.chebyshev(self.leader.grid_pos)
            offensive = [s for s in ally.skills if s.definition.target is TargetKind.ENEMY and s.definition.power > 0 and s.available(ally.resources)]

            # If already in position, FOLLOW may attack, but it should not wander off to chase.
            for skill in sorted(offensive, key=lambda s: s.definition.range, reverse=True):
                if dist_enemy <= skill.definition.range and has_line_of_sight(self.floor, ally.grid_pos, enemy.grid_pos):
                    if ally.ai_tactic.name != "CONSERVE" or dist_enemy > 1:
                        if ally.ai_tactic.name != "FOLLOW" or dist_leader <= leash:
                            return SkillAction(ally, skill, enemy)
            if dist_enemy <= 1 and (ally.ai_tactic.name != "FOLLOW" or dist_leader <= leash):
                return BasicAttackAction(ally, enemy)

            if ally.ai_tactic.name == "ATTACK":
                step = next_step_toward(self.floor, ally.grid_pos, enemy.grid_pos)
                if step:
                    return MoveAction(ally, Direction.from_axes(step.x - ally.grid_pos.x, step.y - ally.grid_pos.y))
            elif ally.ai_tactic.name == "PROTECT":
                # Engage nearby threats, but only within a short leash of the leader.
                if enemy.grid_pos.chebyshev(self.leader.grid_pos) <= 3 and dist_leader <= leash + 1:
                    step = next_step_toward(self.floor, ally.grid_pos, enemy.grid_pos)
                    if step and step.chebyshev(self.leader.grid_pos) <= leash + 1:
                        return MoveAction(ally, Direction.from_axes(step.x - ally.grid_pos.x, step.y - ally.grid_pos.y))

        # Default behavior is to maintain formation around the leader.
        if ally.grid_pos.chebyshev(self.leader.grid_pos) > leash:
            step = next_step_toward(self.floor, ally.grid_pos, self.leader.grid_pos)
            if step:
                direction = Direction.from_axes(step.x - ally.grid_pos.x, step.y - ally.grid_pos.y)
                if direction:
                    return MoveAction(ally, direction)
        return WaitAction(ally)

    def _choose_enemy_action(self, enemy: Character) -> Action | None:
        if enemy.grid_pos is None:
            return None
        target = self._nearest(enemy, self.allies)
        if target is None or target.grid_pos is None:
            return WaitAction(enemy)
        offensive = [s for s in enemy.skills if s.definition.target is TargetKind.ENEMY and s.definition.power > 0 and s.available(enemy.resources)]
        for skill in sorted(offensive, key=lambda s: s.definition.range, reverse=True):
            if enemy.grid_pos.chebyshev(target.grid_pos) <= skill.definition.range and has_line_of_sight(self.floor, enemy.grid_pos, target.grid_pos):
                return SkillAction(enemy, skill, target)
        if enemy.grid_pos.chebyshev(target.grid_pos) <= 1:
            return BasicAttackAction(enemy, target)
        step = next_step_toward(self.floor, enemy.grid_pos, target.grid_pos)
        if step:
            direction = Direction.from_axes(step.x - enemy.grid_pos.x, step.y - enemy.grid_pos.y)
            if direction:
                return MoveAction(enemy, direction)
        return WaitAction(enemy)

    @staticmethod
    def _nearest(origin: Character, candidates: list[Character]) -> Character | None:
        if origin.grid_pos is None:
            return None
        valid = [c for c in candidates if c.active and c.grid_pos is not None]
        return min(valid, key=lambda c: origin.grid_pos.chebyshev(c.grid_pos)) if valid else None
