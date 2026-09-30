from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Callable

from mystery_engine.core.types import Direction, Vec2
from .graph import ImmediateAction, StoryActionHandle, TimedAction


@dataclass
class MoveActorAction:
    game: Any
    actor_id: str
    target_id: str | None = None
    x: float | None = None
    y: float | None = None
    speed: float = 180.0
    tolerance: float = 5.0
    timeout: float = 8.0
    teleport_on_fail: bool = True
    face_movement: bool = True
    elapsed: float = 0.0
    _stuck_time: float = 0.0
    _last_pos: tuple[float, float] | None = None

    def _target(self) -> Vec2:
        world = self.game.exploration
        if world is None:
            raise RuntimeError("Actor movement requires an exploration scene")
        if self.target_id:
            pos = world.target_position(self.target_id)
            return Vec2(pos.x, pos.y)
        if self.x is None or self.y is None:
            raise ValueError("move_actor requires target or x/y")
        return Vec2(float(self.x), float(self.y))

    def update(self, dt: float) -> bool:
        world = self.game.exploration
        if world is None:
            return True
        try:
            actor = world.actor(self.actor_id)
            target = self._target()
        except (KeyError, ValueError, RuntimeError):
            return True

        dx, dy = target.x - actor.position.x, target.y - actor.position.y
        distance = math.hypot(dx, dy)
        if distance <= self.tolerance:
            actor.position.x, actor.position.y = target.x, target.y
            return True

        self.elapsed += max(0.0, dt)
        if self.elapsed >= self.timeout:
            if self.teleport_on_fail:
                actor.position.x, actor.position.y = target.x, target.y
            return True

        if distance > 1e-6:
            if self.face_movement:
                direction = Direction.from_axes(round(dx), round(dy))
                if direction is not None:
                    actor.facing = direction
            step = min(distance, max(1.0, self.speed) * max(0.0, dt))
            before = (actor.position.x, actor.position.y)
            world.try_move(actor, Vec2(dx / distance * step, dy / distance * step))
            after = (actor.position.x, actor.position.y)
            if math.hypot(after[0] - before[0], after[1] - before[1]) < 0.1:
                self._stuck_time += dt
            else:
                self._stuck_time = 0.0
            self._last_pos = after
            if self.teleport_on_fail and self._stuck_time >= min(1.5, self.timeout):
                actor.position.x, actor.position.y = target.x, target.y
                return True
        return False

    def cancel(self) -> None:
        pass


@dataclass
class CameraMoveAction:
    game: Any
    target_id: str | None
    x: float | None
    y: float | None
    duration: float
    elapsed: float = 0.0
    _start: tuple[float, float] | None = None

    def update(self, dt: float) -> bool:
        world = self.game.exploration
        if world is None:
            return True
        if self._start is None:
            current = getattr(world, "camera_override", None)
            if current is None:
                leader = world.actor(self.game.state.leader.id)
                self._start = (leader.position.x, leader.position.y)
            else:
                self._start = (current.x, current.y)

        try:
            if self.target_id:
                target = world.target_position(self.target_id)
                tx, ty = target.x, target.y
            else:
                tx = float(self.x if self.x is not None else self._start[0])
                ty = float(self.y if self.y is not None else self._start[1])
        except KeyError:
            return True

        self.elapsed += max(0.0, dt)
        progress = 1.0 if self.duration <= 0 else min(1.0, self.elapsed / self.duration)
        sx, sy = self._start
        world.camera_override = Vec2(sx + (tx - sx) * progress, sy + (ty - sy) * progress)
        return progress >= 1.0

    def cancel(self) -> None:
        pass


class StoryActionDispatcher:
    """Maps generic story action IDs onto engine behavior.

    The graph/editor only know semantic action IDs. Game-specific actions can be
    supplied by the game definition through `story_actions` or
    `run_story_action(game, action, params)`.
    """

    def __init__(self, game: Any) -> None:
        self.game = game

    def __call__(self, action: str, params: dict[str, Any]) -> StoryActionHandle | None:
        action = action.strip().lower()
        world = self.game.exploration

        if action == "move_actor":
            return MoveActorAction(
                self.game,
                actor_id=str(params.get("actor", "")),
                target_id=(str(params["target"]) if params.get("target") else None),
                x=(float(params["x"]) if params.get("x") is not None else None),
                y=(float(params["y"]) if params.get("y") is not None else None),
                speed=float(params.get("speed", 180.0)),
                tolerance=float(params.get("tolerance", 5.0)),
                timeout=float(params.get("timeout", 8.0)),
                teleport_on_fail=bool(params.get("teleport_on_fail", True)),
                face_movement=bool(params.get("face_movement", True)),
            )

        if action in {"teleport_actor", "place_actor"}:
            if world is not None:
                try:
                    actor = world.actor(str(params.get("actor", "")))
                    if params.get("target"):
                        target = world.target_position(str(params["target"]))
                        actor.position.x, actor.position.y = target.x, target.y
                    else:
                        actor.position.x = float(params.get("x", actor.position.x))
                        actor.position.y = float(params.get("y", actor.position.y))
                except (KeyError, ValueError, TypeError):
                    pass
            return ImmediateAction()

        if action in {"face_actor", "turn_actor"}:
            if world is not None:
                try:
                    actor = world.actor(str(params.get("actor", "")))
                    if params.get("target"):
                        target = world.target_position(str(params["target"]))
                        direction = Direction.from_axes(round(target.x - actor.position.x), round(target.y - actor.position.y))
                    else:
                        direction = getattr(Direction, str(params.get("direction", "S")).upper(), None)
                    if direction is not None:
                        actor.facing = direction
                except KeyError:
                    pass
            return ImmediateAction()

        if action == "set_actor_state":
            if world is not None:
                try:
                    actor = world.actor(str(params.get("actor", "")))
                    if "visible" in params:
                        actor.enabled = bool(params["visible"])
                    if "enabled" in params:
                        actor.enabled = bool(params["enabled"])
                    if params.get("sprite_key"):
                        actor.sprite_key = str(params["sprite_key"])
                except KeyError:
                    pass
            return ImmediateAction()

        if action == "set_object_state":
            if world is not None:
                target_id = str(params.get("object", params.get("target", "")))
                item = next((i for i in world.interactables if i.id == target_id), None)
                if item is not None and "enabled" in params:
                    item.enabled = bool(params["enabled"])
            return ImmediateAction()

        if action in {"camera_to", "camera_pan"}:
            return CameraMoveAction(
                self.game,
                (str(params["target"]) if params.get("target") else None),
                (float(params["x"]) if params.get("x") is not None else None),
                (float(params["y"]) if params.get("y") is not None else None),
                float(params.get("duration", 0.5)),
            )

        if action == "camera_follow":
            if world is not None:
                world.camera_follow = str(params.get("target", "")) or None
                world.camera_override = None
            return ImmediateAction()

        if action == "camera_reset":
            if world is not None:
                world.camera_override = None
                world.camera_follow = None
            return ImmediateAction()

        if action == "camera_shake":
            if world is not None:
                world.camera_shake_strength = max(0.0, float(params.get("strength", 10.0)))
                world.camera_shake_time = max(0.0, float(params.get("duration", 0.5)))
            return TimedAction(max(0.0, float(params.get("duration", 0.5))))

        if action == "play_music":
            self.game.audio.play_scene(
                str(params.get("track")) if params.get("track") else None,
                float(params.get("volume", 1.0)),
                fade_ms=int(params.get("fade_ms", 350)),
            )
            return ImmediateAction()

        if action == "stop_music":
            self.game.audio.stop(fade_ms=int(params.get("fade_ms", 350)))
            return ImmediateAction()

        if action == "play_sfx":
            self.game.audio.play_sfx(str(params.get("cue", "")), gain=float(params.get("gain", 1.0)))
            return ImmediateAction()

        if action == "play_ambience":
            self.game.audio.play_ambience(str(params.get("cue", "")), gain=float(params.get("gain", 1.0)))
            return ImmediateAction()

        if action == "stop_ambience":
            self.game.audio.stop_ambience()
            return ImmediateAction()

        if action in {"screen_fade", "screen_flash"}:
            overlay = getattr(self.game, "cinematic_overlay", None)
            if overlay is not None:
                overlay.start_fade(
                    color=str(params.get("color", "black")),
                    duration=float(params.get("duration", 0.4)),
                    to_alpha=float(params.get("alpha", 1.0)),
                    hold=bool(params.get("hold", action == "screen_fade")),
                )
            return TimedAction(max(0.0, float(params.get("duration", 0.4))))

        if action in {"banner", "title_card"}:
            overlay = getattr(self.game, "cinematic_overlay", None)
            duration = max(0.0, float(params.get("duration", 2.0)))
            if overlay is not None:
                overlay.show_banner(str(params.get("text", "")), duration)
            return TimedAction(duration)

        if action == "change_scene":
            scene = params.get("scene")
            if scene:
                base = Path(getattr(self.game.definition, "scene_root", Path(".")))
                path = Path(str(scene))
                if not path.is_absolute():
                    path = base / path
                self.game.change_exploration_scene(path, str(params.get("marker")) if params.get("marker") else None)
            return ImmediateAction()

        if action == "enter_dungeon":
            self.game.enter_dungeon(start_floor=max(1, int(params.get("floor", 1))))
            return ImmediateAction()

        if action == "message":
            self.game.add_message(str(params.get("text", "")))
            return ImmediateAction()

        if action in {"give_item", "remove_item"}:
            item_id = str(params.get("item", ""))
            quantity = max(1, int(params.get("quantity", 1)))
            location = str(params.get("location", "bag")).lower()
            inventory = self.game.state.storage if location == "storage" else self.game.state.bag
            registry = getattr(self.game.definition, "project_registry", None)
            if action == "give_item":
                if registry is None or item_id not in getattr(registry, "items", {}):
                    self.game.add_message(f"Unknown item: {item_id}")
                    return ImmediateAction()
                if inventory.add(registry.item(item_id), quantity):
                    self.game.add_message(f"Received {registry.item(item_id).name} ×{quantity}.")
                else:
                    self.game.add_message("There is no room for that item.")
            else:
                if inventory.remove(item_id, quantity):
                    self.game.add_message(f"Removed {item_id} ×{quantity}.")
                else:
                    self.game.add_message(f"Not enough {item_id}.")
            return ImmediateAction()

        if action in {"give_money", "remove_money"}:
            amount = max(0, int(params.get("amount", 0)))
            location = str(params.get("location", "carried")).lower()
            if location == "stored":
                current = self.game.state.wallet.stored
                if action == "give_money":
                    self.game.state.wallet.stored += amount
                else:
                    self.game.state.wallet.stored = max(0, current - amount)
            else:
                current = self.game.state.wallet.carried
                if action == "give_money":
                    self.game.state.wallet.carried += amount
                else:
                    self.game.state.wallet.carried = max(0, current - amount)
            self.game.add_message(f"{'Received' if action == 'give_money' else 'Removed'} {amount} money.")
            return ImmediateAction()

        if action in {"heal_party", "restore_skill_charges", "restore_party"}:
            character_id = str(params.get("character", "")).strip()
            members = (
                [member for member in self.game.state.party if member.id == character_id]
                if character_id else list(self.game.state.party)
            )
            if action in {"heal_party", "restore_party"}:
                amount = params.get("amount")
                for member in members:
                    if amount is None or str(amount).lower() == "full":
                        member.stats.current_hp = member.stats.max_hp
                    else:
                        member.stats.current_hp = min(
                            member.stats.max_hp,
                            member.stats.current_hp + max(0, int(amount)),
                        )
                    member.incapacitated = False
            if action in {"restore_skill_charges", "restore_party"}:
                skill_id = str(params.get("skill", "")).strip()
                amount = params.get("amount")
                for member in members:
                    skills = [skill for skill in member.skills if not skill_id or skill.definition.id == skill_id]
                    for skill in skills:
                        if skill.definition.max_charges is None:
                            skill.charges = None
                        elif amount is None or str(amount).lower() == "full":
                            skill.charges = skill.definition.max_charges
                        else:
                            skill.charges = min(
                                skill.definition.max_charges,
                                (skill.charges or 0) + max(0, int(amount)),
                            )
            self.game.add_message(
                "Party restored." if action == "restore_party"
                else ("Party healed." if action == "heal_party" else "Skill charges restored.")
            )
            return ImmediateAction()

        # Game-specific semantic actions stay out of engine code.
        registry = dict(getattr(self.game.definition, "story_actions", {}))
        callback = registry.get(action)
        if callback is not None:
            result = callback(self.game, params)
            return result if hasattr(result, "update") else ImmediateAction()

        hook = getattr(self.game.definition, "run_story_action", None)
        if callable(hook):
            result = hook(self.game, action, params)
            return result if hasattr(result, "update") else ImmediateAction()

        self.game.add_message(f"Unknown story action: {action}")
        return ImmediateAction()
