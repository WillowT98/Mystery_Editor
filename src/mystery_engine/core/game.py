from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from random import Random
from typing import Protocol, TYPE_CHECKING

import pygame

from mystery_engine.config import EngineConfig
from mystery_engine.core.combat import CombatResolver, ProjectileEvent
from mystery_engine.core.game_state import (
    DungeonActorState,
    DungeonGroundItemState,
    DungeonState,
    PersistentGameState,
    SaveManager,
    SceneActorState,
    SceneObjectState,
    SceneState,
)
from mystery_engine.core.inventory import ItemDefinition
from mystery_engine.core.models import AITactic, Character, RangePattern, TargetKind
from mystery_engine.core.types import Direction, DungeonResult, GameMode, GridPos, Vec2
from mystery_engine.dungeon.actions import BasicAttackAction, MoveAction, SkillAction, WaitAction
from mystery_engine.dungeon.floor import DungeonFloor
from mystery_engine.dungeon.targeting import effective_range_pattern, targets_for_skill
from mystery_engine.dungeon.turns import TurnManager
from mystery_engine.input import InputManager
from mystery_engine.presentation import CinematicOverlay, MusicController, ProjectileAnimation, Renderer
from mystery_engine.story import (
    ChoiceOption,
    DialogueController,
    DialogueLine,
    DialogueSequence,
    ExplorationActor,
    ExplorationMap,
    StoryActionDispatcher,
    StoryGraph,
    StoryGraphRunner,
    StoryRuntimeContext,
    evaluate_condition,
)
from mystery_engine.ui import MenuController, MenuEntry

if TYPE_CHECKING:
    from collections.abc import Sequence


class GameDefinition(Protocol):
    game_id: str
    game_version: str
    title: str
    dungeon_floor_count: int
    defeat_money_loss_fraction: float
    defeat_item_loss_chance: float

    def create_state(self) -> PersistentGameState: ...
    def load_state(self, payload: dict) -> PersistentGameState: ...
    def create_exploration(self, game: "MysteryGame") -> ExplorationMap: ...
    def create_exploration_scene(self, game: "MysteryGame", scene_path: Path) -> ExplorationMap: ...
    def create_dungeon_floor(self, game: "MysteryGame", floor_number: int) -> DungeonFloor: ...
    def on_dungeon_result(self, game: "MysteryGame", result: DungeonResult, *, lost_money: int = 0, lost_items: list[str] | None = None) -> None: ...


@dataclass
class DungeonSession:
    floor_number: int
    floor: DungeonFloor
    turns: TurnManager


class MysteryGame:
    """Runtime/composition layer. It depends on a game definition; engine code never imports one."""

    def __init__(
        self,
        definition: GameDefinition,
        config: EngineConfig | None = None,
        seed: int | None = None,
    ) -> None:
        self.definition = definition
        self.config = config or EngineConfig()
        self.rng = Random(seed)
        self.state = definition.create_state()
        self.mode = GameMode.EXPLORATION
        self.dialogue = DialogueController()
        self.menu = MenuController()
        self.messages: list[str] = []
        self.input: InputManager | None = None
        self.renderer: Renderer | None = None
        self.audio = MusicController(
            getattr(definition, "asset_root", None),
            definition.game_id,
            cue_catalog_path=getattr(definition, "sfx_catalog_path", None),
        )
        self.exploration: ExplorationMap | None = None
        self.dungeon: DungeonSession | None = None
        self.running = False
        self._display: pygame.Surface | None = None
        self._fullscreen = False
        self._system_menu = False
        self.save_manager = SaveManager()
        self.cinematic_overlay = CinematicOverlay()
        self.story_actions = StoryActionDispatcher(self)
        self.projectile_queue: list[ProjectileAnimation] = []
        self.active_projectile: ProjectileAnimation | None = None
        self._pending_dungeon_result: DungeonResult | None = None
        self._trigger_region_inside: dict[tuple[str, str], bool] = {}
        self._scene_entry_fired: set[tuple[str, str]] = set()
        self.story_runner = StoryGraphRunner(StoryRuntimeContext(
            story=self.state.story,
            dialogue=self.dialogue,
            choose=self._open_story_choice,
            run_action=self.story_actions,
            load_graph=self._load_story_graph,
            resolve_pawn=getattr(self.definition, "resolve_story_pawn", None),
            evaluate_gameplay_condition=self.evaluate_gameplay_condition,
            on_finish=self._story_finished,
            rng=self.rng,
        ))

    def run(self) -> None:
        pygame.init()
        self.audio.initialize()
        pygame.display.set_caption(self.definition.title)
        self._display = pygame.display.set_mode(self.config.logical_size, pygame.RESIZABLE)
        self.input = InputManager(self.config)
        self.renderer = Renderer(self.config, getattr(self.definition, "asset_root", None))
        self.exploration = self.definition.create_exploration(self)
        self._sync_exploration_music()
        self._process_scene_enter_triggers()
        self._process_region_triggers()
        if os.environ.get("MYSTERY_DUNGEON_PLAYTEST"):
            self.enter_dungeon(start_floor=max(1, int(os.environ.get("MYSTERY_DUNGEON_START_FLOOR", "1"))))
        elif os.environ.get("MYSTERY_STORY_PLAYTEST"):
            story_path = os.environ.get("MYSTERY_STORY_PATH")
            if story_path:
                self.run_story(StoryGraph.load(Path(story_path)))
        clock = pygame.time.Clock()
        self.running = True

        while self.running:
            dt = min(0.05, clock.tick(self.config.target_fps) / 1000.0)
            now = pygame.time.get_ticks() / 1000.0
            events = pygame.event.get()
            if any(event.type == pygame.QUIT for event in events):
                self.running = False
                break

            frame = self.input.frame_input(events)
            if frame.fullscreen:
                self._toggle_fullscreen()

            self.cinematic_overlay.update(dt)
            if self.exploration is not None and self.exploration.camera_shake_time > 0:
                self.exploration.camera_shake_time = max(0.0, self.exploration.camera_shake_time - dt)
            self.story_runner.update(dt)
            self._update_projectiles(dt)

            if self.dialogue.active:
                self._handle_dialogue(events)
            elif self.menu.active:
                self._handle_menu(events)
            elif self.story_runner.active:
                # Story graphs own player control while a cutscene/conversation
                # is running, even during non-dialogue choreography.
                pass
            elif self.active_projectile is not None or self.projectile_queue:
                # Projectiles temporarily own dungeon actions, but key releases
                # must still be observed or held movement can get "stuck" after
                # the animation ends. Movement presses during the lock are
                # deliberately discarded rather than buffered.
                if self.mode is GameMode.DUNGEON:
                    for event in events:
                        self.input.dungeon.feed_locked(event)
            else:
                if self.mode is GameMode.EXPLORATION:
                    self._process_scene_enter_triggers()
                    self._process_region_triggers()
                if frame.menu:
                    self._open_gameplay_menu()
                elif frame.cancel:
                    self._open_system_menu()
                elif self.mode is GameMode.EXPLORATION:
                    self._update_exploration(frame, dt)
                else:
                    self._update_dungeon(events, frame.sprint, frame.interact, now)

            self._render()

        pygame.quit()

    def evaluate_gameplay_condition(self, condition: dict) -> bool | None:
        """Resolve engine-owned gameplay condition kinds for story graphs."""
        kind = str(condition.get("kind", "")).lower()
        value = condition.get("value", 1)

        def quantity_in(inventory, item_id: str) -> int:
            stack = next((stack for stack in inventory.stacks if stack.item.id == item_id), None)
            return stack.quantity if stack is not None else 0

        if kind in {"has_item", "item_count"}:
            item_id = str(condition.get("item", condition.get("name", "")))
            location = str(condition.get("location", "bag")).lower()
            actual = 0
            if location in {"bag", "carried", "either", "any"}:
                actual += quantity_in(self.state.bag, item_id)
            if location in {"storage", "either", "any"}:
                actual += quantity_in(self.state.storage, item_id)
            expected = int(value if value is not None else 1)
            op = str(condition.get("op", ">=")).lower()
            return self._compare_story_value(actual, expected, op)

        if kind in {"has_money", "money"}:
            location = str(condition.get("location", "carried")).lower()
            if location == "stored":
                actual = self.state.wallet.stored
            elif location in {"total", "any"}:
                actual = self.state.wallet.carried + self.state.wallet.stored
            else:
                actual = self.state.wallet.carried
            expected = int(value if value is not None else 0)
            return self._compare_story_value(actual, expected, str(condition.get("op", ">=")).lower())

        if kind in {"party_contains", "has_party_member"}:
            character_id = str(condition.get("character", condition.get("name", "")))
            return any(member.id == character_id for member in self.state.party)

        if kind in {"party_hp", "hp"}:
            character_id = str(condition.get("character", condition.get("name", "")))
            member = next((member for member in self.state.party if member.id == character_id), None)
            if member is None:
                return False
            mode = str(condition.get("mode", "current")).lower()
            if mode == "percent":
                actual = (member.stats.current_hp / member.stats.max_hp * 100.0) if member.stats.max_hp else 0.0
            elif mode == "missing":
                actual = member.stats.max_hp - member.stats.current_hp
            else:
                actual = member.stats.current_hp
            return self._compare_story_value(actual, float(value), str(condition.get("op", ">=")).lower())

        if kind in {"skill_charges", "has_skill_charges"}:
            character_id = str(condition.get("character", condition.get("name", "")))
            skill_id = str(condition.get("skill", ""))
            member = next((member for member in self.state.party if member.id == character_id), None)
            skill = member.skill(skill_id) if member is not None else None
            if skill is None:
                return False
            actual = skill.charges if skill.charges is not None else 10**9
            return self._compare_story_value(actual, int(value), str(condition.get("op", ">=")).lower())

        return None

    @staticmethod
    def _compare_story_value(actual, expected, op: str) -> bool:
        try:
            if op in {"=", "==", "is"}: return actual == expected
            if op in {"!=", "is_not"}: return actual != expected
            if op == ">": return actual > expected
            if op == ">=": return actual >= expected
            if op == "<": return actual < expected
            if op == "<=": return actual <= expected
        except (TypeError, ValueError):
            return False
        return False

    # ---------- public hooks for game content ----------

    def _cue(self, event: str) -> str | None:
        return dict(getattr(self.definition, "sfx_event_cues", {})).get(event)

    def _play_event_sfx(self, event: str, *, gain: float = 1.0) -> None:
        self.audio.play_sfx(self._cue(event), gain=gain)

    def _projectile_source_is_visible(self, event: ProjectileEvent) -> bool:
        """Only animate attacks whose attacker is actually visible on screen."""
        if self.mode is not GameMode.DUNGEON or self.dungeon is None:
            return False
        leader = self.state.leader
        if leader.grid_pos is None:
            return False
        if event.source_pos not in self.dungeon.turns.memory.visible:
            return False

        tile = self.config.tile_px
        center_x = self.config.dungeon_view_width // 2
        center_y = self.config.logical_height // 2
        camera_world_x = leader.grid_pos.x * tile + tile // 2 - center_x
        camera_world_y = leader.grid_pos.y * tile + tile // 2 - center_y
        source_x = event.source_pos.x * tile + tile // 2 - camera_world_x
        source_y = event.source_pos.y * tile + tile // 2 - camera_world_y
        return 0 <= source_x < self.config.dungeon_view_width and 0 <= source_y < self.config.logical_height

    def _queue_projectiles(self, events) -> None:
        for event in events:
            if self._projectile_source_is_visible(event):
                self.projectile_queue.append(ProjectileAnimation.from_event(event))
        self._start_next_projectile()

    def _start_next_projectile(self) -> None:
        if self.active_projectile is not None or not self.projectile_queue:
            return
        self.active_projectile = self.projectile_queue.pop(0)
        if self.input is not None and self.mode is GameMode.DUNGEON:
            self.input.dungeon.suspend_until_release()
        self.audio.play_sfx(self.active_projectile.event.launch_sfx_cue)

    def _update_projectiles(self, dt: float) -> None:
        animation = self.active_projectile
        if animation is None:
            self._start_next_projectile()
            if self.active_projectile is None and self._pending_dungeon_result is not None:
                result, self._pending_dungeon_result = self._pending_dungeon_result, None
                self.return_to_exploration(result)
            return
        was_impact = animation.in_impact
        animation.update(dt)
        if animation.in_impact and not was_impact and not animation.impact_sound_played:
            self.audio.play_sfx(animation.event.impact_sfx_cue)
            animation.impact_sound_played = True
        if animation.finished:
            self.active_projectile = None
            self._start_next_projectile()
            if self.active_projectile is None and not self.projectile_queue and self._pending_dungeon_result is not None:
                result, self._pending_dungeon_result = self._pending_dungeon_result, None
                self.return_to_exploration(result)

    def _queue_turn_projectiles(self, outcome) -> None:
        self._queue_projectiles(getattr(outcome, "projectiles", []))

    def _finish_or_defer_dungeon_result(self, result: DungeonResult) -> None:
        if self.active_projectile is not None or self.projectile_queue:
            self._pending_dungeon_result = result
        else:
            self.return_to_exploration(result)

    def _play_dialogue_reaction(self) -> None:
        line = self.dialogue.current
        if line is None or not line.expression or line.expression == "neutral":
            return
        self.audio.play_sfx(f"reactions.{line.expression}")

    def say(self, lines: list[DialogueLine], on_complete=None) -> None:
        self.dialogue.start(DialogueSequence(lines, on_complete=on_complete))
        self._play_dialogue_reaction()

    def add_message(self, text: str) -> None:
        self.messages.append(text)
        self.messages[:] = self.messages[-8:]

    def _story_root(self) -> Path:
        root = getattr(self.definition, "story_root", None)
        if root is not None:
            return Path(root)
        module_path = Path(getattr(self.definition, "asset_root", Path("."))).parent
        return module_path / "stories"

    def _load_story_graph(self, graph_name: str) -> StoryGraph:
        path = Path(graph_name)
        if not path.suffix:
            path = path.with_suffix(".json")
        if not path.is_absolute():
            path = self._story_root() / path
        graph = StoryGraph.load(path)
        localizer = getattr(self.definition, "localize_story", None)
        return localizer(graph) if callable(localizer) else graph

    def run_story(self, graph: str | Path | StoryGraph, entry: str = "default") -> None:
        story = graph if isinstance(graph, StoryGraph) else self._load_story_graph(str(graph))
        self.menu.close()
        self.story_runner.start(story, entry)

    def _open_story_choice(self, title: str, options: list[ChoiceOption], choose) -> None:
        entries: list[MenuEntry] = []
        for option in options:
            def select(target=option.target):
                choose(target)
                self.menu.close()
            entries.append(MenuEntry(option.text, action=select, enabled=option.enabled, detail=option.detail))
        self._system_menu = False
        self.menu.open(title or "Choose", entries)

    def _story_finished(self, result: str | None) -> None:
        self.menu.close()
        hook = getattr(self.definition, "on_story_result", None)
        if callable(hook):
            hook(self, result)

    @staticmethod
    def _trigger_flag(scene_id: str, trigger_id: str) -> str:
        return f"__trigger_once__:{scene_id}:{trigger_id}"

    def _trigger_available(self, trigger) -> bool:
        world = self.exploration
        if world is None or not trigger.enabled or not trigger.story:
            return False
        if trigger.once and self.state.story.flag(self._trigger_flag(world.id, trigger.id)):
            return False
        return evaluate_condition(trigger.condition, self.state.story)

    def _fire_trigger(self, trigger) -> bool:
        world = self.exploration
        if world is None or self.story_runner.active or self.dialogue.active or self.menu.active:
            return False
        if not self._trigger_available(trigger):
            return False
        if trigger.once:
            self.state.story.set_flag(self._trigger_flag(world.id, trigger.id), True)
        self.run_story(trigger.story, trigger.entry)
        return True

    def _process_scene_enter_triggers(self) -> None:
        world = self.exploration
        if world is None or self.story_runner.active or self.dialogue.active or self.menu.active:
            return
        for trigger in world.triggers:
            key = (world.id, trigger.id)
            if trigger.kind != "on_scene_enter" or key in self._scene_entry_fired:
                continue
            # A scene-enter condition is evaluated for this visit. If false, the
            # trigger does not suddenly fire later merely because a flag changes
            # while the player remains in the room.
            self._scene_entry_fired.add(key)
            if self._fire_trigger(trigger):
                break

    def _process_region_triggers(self) -> None:
        world = self.exploration
        if world is None:
            return
        try:
            leader = world.actor(self.state.leader.id)
        except KeyError:
            return

        for trigger in world.triggers:
            if trigger.kind != "on_region_enter" or trigger.region is None:
                continue
            key = (world.id, trigger.id)
            inside = trigger.region.contains_point(leader.position.x, leader.position.y)
            was_inside = self._trigger_region_inside.get(key, False)
            if not inside:
                self._trigger_region_inside[key] = False
                continue
            if was_inside:
                continue
            if self.story_runner.active or self.dialogue.active or self.menu.active:
                # Preserve the edge until control returns, so a trigger entered
                # during another scene-enter cutscene is not lost.
                continue
            self._trigger_region_inside[key] = True
            if self._fire_trigger(trigger):
                break

    def change_exploration_scene(self, scene_path: Path, target_door_id: str | None = None) -> None:
        """Load another exploration scene while preserving the active party.

        Scene-door portals are intentionally generic engine features: the game
        definition is responsible for turning a scene file into an ExplorationMap,
        while the engine preserves party actors and places them beside the target
        door in the destination scene.
        """
        loader = getattr(self.definition, "create_exploration_scene", None)
        if loader is None:
            self.add_message("This game does not support exploration scene links.")
            return

        old_world = self.exploration
        if old_world is not None:
            self._capture_exploration_state()
        new_world = loader(self, Path(scene_path))

        old_party_actors = {}
        if old_world is not None:
            for member in self.state.party:
                actor = next((a for a in old_world.actors if a.id == member.id), None)
                if actor is not None:
                    old_party_actors[member.id] = actor

        # Ensure every active party member exists in the destination even when
        # the scene file contains only environment/NPC data.
        for member in self.state.party:
            existing = next((a for a in new_world.actors if a.id == member.id), None)
            if existing is None:
                actor = old_party_actors.get(member.id)
                if actor is None:
                    actor = ExplorationActor(member.id, getattr(member, "name", member.id.title()), Vec2(0, 0), sprite_key=member.id)
                new_world.actors.append(actor)

        target = None
        marker_target = None
        if target_door_id:
            target = next((i for i in new_world.interactables if i.id == target_door_id), None)
            if target is None:
                marker_target = next((m for m in new_world.markers if m.id == target_door_id), None)
        if target is None and marker_target is None:
            target = next((i for i in new_world.interactables if getattr(i, "portal_facing", None)), None)

        leader_actor = next(a for a in new_world.actors if a.id == self.state.leader.id)
        if marker_target is not None:
            leader_actor.position.x = max(leader_actor.radius, min(new_world.width - leader_actor.radius, marker_target.position.x))
            leader_actor.position.y = max(leader_actor.radius, min(new_world.height - leader_actor.radius, marker_target.position.y))
            facing = leader_actor.facing
        elif target is not None:
            facing_name = getattr(target, "portal_facing", None) or "S"
            facing = getattr(Direction, facing_name, Direction.S)
            distance = max(72.0, self.config.interaction_range * 0.9)
            leader_actor.position.x = max(leader_actor.radius, min(new_world.width - leader_actor.radius, target.position.x + facing.dx * distance))
            leader_actor.position.y = max(leader_actor.radius, min(new_world.height - leader_actor.radius, target.position.y + facing.dy * distance))
            leader_actor.facing = facing
        else:
            leader_actor.position.x = new_world.width / 2
            leader_actor.position.y = new_world.height / 2
            facing = leader_actor.facing

        # Keep companions nearby rather than stacking them on the same point.
        companions = [a for a in new_world.actors if a.id in {m.id for m in self.state.party} and a.id != leader_actor.id]
        for index, actor in enumerate(companions, start=1):
            actor.position.x = max(actor.radius, min(new_world.width - actor.radius, leader_actor.position.x - facing.dy * 52 * index))
            actor.position.y = max(actor.radius, min(new_world.height - actor.radius, leader_actor.position.y + facing.dx * 52 * index))
            actor.facing = facing

        self.exploration = new_world
        self._scene_entry_fired.clear()
        self._trigger_region_inside.clear()
        self.state.world.current_scene = new_world.id
        self.mode = GameMode.EXPLORATION
        self.menu.close()
        self._sync_exploration_music()
        self.add_message(f"Entered {new_world.id}.")
        self._process_scene_enter_triggers()
        self._process_region_triggers()

    def enter_dungeon(self, start_floor: int = 1) -> None:
        if self.dialogue.active:
            return
        if self.exploration is not None:
            self._capture_exploration_state()
        self.state.dungeon = None
        self.mode = GameMode.DUNGEON
        self.menu.close()
        self.audio.stop(fade_ms=350)
        self.audio.stop_ambience()
        assert self.input is not None
        self.input.dungeon.reset()
        for member in self.state.party:
            member.restore_for_expedition()
        self._start_floor(min(max(1, start_floor), self.definition.dungeon_floor_count))
        self.messages = ["The expedition begins."]

    def return_to_exploration(self, result: DungeonResult) -> None:
        lost_money = 0
        lost_items: list[str] = []
        if result is DungeonResult.DEFEAT:
            lost_money = self.state.wallet.lose_carried_fraction(self.definition.defeat_money_loss_fraction)
            lost_items = self.state.bag.apply_loss(self.rng, self.definition.defeat_item_loss_chance)

        self.dungeon = None
        self.state.dungeon = None
        self.mode = GameMode.EXPLORATION
        self.menu.close()
        self._sync_exploration_music()
        assert self.input is not None
        self.input.dungeon.reset()
        for member in self.state.party:
            member.restore_for_expedition()
            member.grid_pos = None
        self.definition.on_dungeon_result(self, result, lost_money=lost_money, lost_items=lost_items)

    @property
    def default_save_path(self) -> Path:
        return Path("saves") / f"{self.definition.game_id}-save.json"

    def _capture_exploration_state(self) -> None:
        """Copy mutable exploration state into the persistent state graph."""
        world = self.exploration
        if world is None:
            return
        party_ids = {member.id for member in self.state.party}
        self.state.world.current_scene = world.id
        self.state.world.party_positions = {
            actor.id: SceneActorState(
                x=actor.position.x,
                y=actor.position.y,
                facing=actor.facing.name,
                enabled=actor.enabled,
                sprite_key=actor.sprite_key,
            )
            for actor in world.actors
            if actor.id in party_ids
        }
        self.state.world.scenes[world.id] = SceneState(
            actors={
                actor.id: SceneActorState(
                    x=actor.position.x,
                    y=actor.position.y,
                    facing=actor.facing.name,
                    enabled=actor.enabled,
                    sprite_key=actor.sprite_key,
                )
                for actor in world.actors
                if actor.id not in party_ids
            },
            objects={
                item.id: SceneObjectState(enabled=item.enabled)
                for item in world.interactables
            },
        )

    def _capture_dungeon_state(self) -> None:
        session = self.dungeon
        if session is None:
            self.state.dungeon = None
            return
        floor = session.floor
        self.state.dungeon = DungeonState(
            dungeon_id=str(getattr(self.definition, "active_dungeon_id", "")),
            floor_number=session.floor_number,
            width=floor.width,
            height=floor.height,
            tiles=[
                [
                    {
                        "kind": tile.kind.name,
                        "walkable": tile.walkable,
                        "blocks_sight": tile.blocks_sight,
                        "terrain": tile.terrain,
                    }
                    for tile in row
                ]
                for row in floor.tiles
            ],
            rooms=[list(room) for room in floor.rooms],
            player_spawn=(
                (floor.player_spawn.x, floor.player_spawn.y)
                if floor.player_spawn is not None else None
            ),
            stairs_pos=(
                (floor.stairs_pos.x, floor.stairs_pos.y)
                if floor.stairs_pos is not None else None
            ),
            tileset=floor.tileset,
            music=floor.music,
            music_volume=floor.music_volume,
            dungeon_name=floor.dungeon_name,
            generation_profile=floor.generation_profile,
            actors=[
                DungeonActorState(
                    id=actor.id,
                    definition_id=(
                        str(actor.metadata.get("definition_id"))
                        if actor.metadata.get("definition_id") else None
                    ),
                    name=actor.name,
                    hostile=actor.hostile,
                    x=(actor.grid_pos.x if actor.grid_pos is not None else None),
                    y=(actor.grid_pos.y if actor.grid_pos is not None else None),
                    facing=actor.facing.name,
                    incapacitated=actor.incapacitated,
                    max_hp=actor.stats.max_hp,
                    current_hp=actor.stats.current_hp,
                    attack=actor.stats.attack,
                    defense=actor.stats.defense,
                    resources=dict(actor.resources),
                    resistances=dict(actor.resistances),
                    skill_charges={
                        skill.definition.id: skill.charges for skill in actor.skills
                    },
                    skill_ids=[skill.definition.id for skill in actor.skills],
                    metadata=dict(actor.metadata),
                )
                for actor in floor.entities
            ],
            ground_items=[
                DungeonGroundItemState(item.item.id, item.pos.x, item.pos.y)
                for item in floor.ground_items
            ],
            discovered=[(pos.x, pos.y) for pos in sorted(session.turns.memory.discovered, key=lambda p: (p.y, p.x))],
            visible=[(pos.x, pos.y) for pos in sorted(session.turns.memory.visible, key=lambda p: (p.y, p.x))],
            turn_count=session.turns.turn_count,
            rng_state=self.rng.getstate(),
        )

    @staticmethod
    def _tupleify_rng_state(value):
        if isinstance(value, list):
            return tuple(MysteryGame._tupleify_rng_state(item) for item in value)
        return value

    def _restore_dungeon_session(self, saved: DungeonState) -> None:
        restorer = getattr(self.definition, "restore_dungeon_floor", None)
        if not callable(restorer):
            raise ValueError("This project cannot restore dungeon saves.")
        floor = restorer(saved, self.state.party)
        leader = self.state.leader
        turns = TurnManager(
            floor,
            self.state.party,
            self.state.bag,
            leader,
            self.rng,
            event_sounds=getattr(self.definition, "sfx_event_cues", {}),
        )
        turns.turn_count = saved.turn_count
        turns.memory.discovered = {GridPos(x, y) for x, y in saved.discovered}
        turns.memory.visible = {GridPos(x, y) for x, y in saved.visible}
        self.dungeon = DungeonSession(saved.floor_number, floor, turns)
        if saved.rng_state is not None:
            self.rng.setstate(self._tupleify_rng_state(saved.rng_state))
        self.mode = GameMode.DUNGEON
        error = self.audio.play_scene(floor.music, floor.music_volume)
        if error:
            self.add_message(error)

    def save_snapshot(self, path: Path | None = None) -> Path | None:
        if self.mode is GameMode.DUNGEON:
            if self.dungeon is None:
                self.add_message("There is no active dungeon session to save.")
                return None
            self._capture_dungeon_state()
        else:
            if self.exploration is None:
                self.add_message("There is no active exploration state to save.")
                return None
            self.state.dungeon = None
            self._capture_exploration_state()

        path = path or self.default_save_path
        self.save_manager.dump(self.state, path)
        self._play_event_sfx("save")
        self.add_message(f"Game saved to {path}.")
        return path

    def load_snapshot(self, path: Path | None = None) -> bool:
        path = path or self.default_save_path
        if not path.exists():
            self.add_message("No save game was found.")
            return False
        loader = getattr(self.definition, "load_state", None)
        if not callable(loader):
            self.add_message("This project cannot reconstruct saved games.")
            return False
        try:
            payload = self.save_manager.load_raw(path)
            state = loader(payload)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.add_message(f"Could not load save: {exc}")
            return False

        self.state = state
        self.dungeon = None
        self._scene_entry_fired.clear()
        self._trigger_region_inside.clear()
        self.mode = GameMode.EXPLORATION
        self.dialogue = DialogueController()
        self.menu.close()
        self.projectile_queue.clear()
        self.active_projectile = None
        self._pending_dungeon_result = None
        self.story_runner = StoryGraphRunner(StoryRuntimeContext(
            story=self.state.story,
            dialogue=self.dialogue,
            choose=self._open_story_choice,
            run_action=self.story_actions,
            load_graph=self._load_story_graph,
            resolve_pawn=getattr(self.definition, "resolve_story_pawn", None),
            on_finish=self._story_finished,
            rng=self.rng,
        ))
        # Always rebuild exploration first because it is the dungeon return point.
        self.exploration = self.definition.create_exploration(self)
        if self.input is not None:
            self.input.dungeon.reset()
        if self.state.dungeon is not None:
            try:
                self._restore_dungeon_session(self.state.dungeon)
            except (ValueError, KeyError, TypeError) as exc:
                self.state.dungeon = None
                self.mode = GameMode.EXPLORATION
                self._sync_exploration_music()
                self.add_message(f"Dungeon save could not be restored: {exc}")
                return False
        else:
            self.mode = GameMode.EXPLORATION
            self._sync_exploration_music()
            self._process_scene_enter_triggers()
            self._process_region_triggers()
        self.add_message(f"Loaded save from {path}.")
        return True

    # ---------- update ----------

    def _update_exploration(self, frame, dt: float) -> None:
        assert self.exploration is not None
        player = self.exploration.actor(self.state.leader.id)
        if frame.move.length() > 0:
            speed = self.config.exploration_sprint_speed if frame.sprint else self.config.exploration_walk_speed
            delta = Vec2(frame.move.x * speed * dt, frame.move.y * speed * dt)
            self.exploration.try_move(player, delta)
            direction = Direction.from_axes(round(frame.move.x), round(frame.move.y))
            if direction:
                player.facing = direction
            self._process_region_triggers()
        if frame.interact:
            interaction = self.exploration.nearest_interaction_detail(player, self.config.interaction_range)
            if interaction:
                _, callback, _, sound_cue = interaction
                self.audio.play_sfx(sound_cue)
                callback()
            else:
                self.add_message("Nothing nearby to interact with.")

    def _update_dungeon(self, events: list[pygame.event.Event], sprint: bool, interact: bool, now: float) -> None:
        assert self.input is not None and self.dungeon is not None
        for event in events:
            self.input.dungeon.feed(event, now)

        direction = self.input.dungeon.poll(now, sprint)
        action = None
        if direction is not None:
            action = MoveAction(self.state.leader, direction)
        elif interact:
            action = self._basic_attack_or_wait()

        if action is None:
            return
        before_visible_enemies = self._visible_enemy_ids()
        outcome = self.dungeon.turns.execute_player_action(action)
        for cue in outcome.sound_cues:
            self.audio.play_sfx(cue)
        for message in outcome.messages:
            self.add_message(message)
        self._queue_turn_projectiles(outcome)

        if outcome.dungeon_result is DungeonResult.DEFEAT or not self.state.leader.active:
            self._finish_or_defer_dungeon_result(DungeonResult.DEFEAT)
            return

        # Reaching stairs advances automatically; dungeon definitions decide the floor count.
        if self.state.leader.grid_pos == self.dungeon.floor.stairs_pos:
            if self.dungeon.floor_number >= self.definition.dungeon_floor_count:
                self.return_to_exploration(DungeonResult.SUCCESS)
            else:
                self._start_floor(self.dungeon.floor_number + 1)
                self.add_message(f"Entered floor {self.dungeon.floor_number}.")
            return

        if sprint:
            after_visible_enemies = self._visible_enemy_ids()
            item_here = self.dungeon.floor.item_at(self.state.leader.grid_pos) is not None
            if after_visible_enemies - before_visible_enemies or item_here:
                self.input.dungeon.stop_dash()

    def _start_floor(self, floor_number: int) -> None:
        floor = self.definition.create_dungeon_floor(self, floor_number)
        leader = self.state.leader
        if floor.player_spawn is None:
            raise RuntimeError("Dungeon floor has no player spawn")
        leader.grid_pos = floor.player_spawn
        leader.incapacitated = False

        # Put active companions in nearby legal cells.
        occupied = {leader.grid_pos}
        for companion in [c for c in self.state.party if c is not leader and c.active]:
            companion.grid_pos = self._find_nearby_open(floor, leader.grid_pos, occupied)
            if companion.grid_pos:
                occupied.add(companion.grid_pos)
        for companion in [c for c in self.state.party if c is not leader and not c.active]:
            companion.grid_pos = None

        # Game content may already have populated enemies/items. Party is appended here.
        floor.entities.extend([c for c in self.state.party if c.grid_pos is not None])
        turns = TurnManager(
            floor, self.state.party, self.state.bag, leader, self.rng,
            event_sounds=getattr(self.definition, "sfx_event_cues", {}),
        )
        self.dungeon = DungeonSession(floor_number, floor, turns)
        error = self.audio.play_scene(floor.music, floor.music_volume)
        if error:
            self.add_message(error)

    @staticmethod
    def _find_nearby_open(floor: DungeonFloor, center: GridPos, occupied: set[GridPos]) -> GridPos | None:
        for radius in range(1, 5):
            for direction in Direction:
                pos = GridPos(center.x + direction.dx * radius, center.y + direction.dy * radius)
                if pos not in occupied and floor.tile(pos).walkable and floor.entity_at(pos) is None:
                    return pos
        return None

    # ---------- menus ----------

    def _open_gameplay_menu(self) -> None:
        assert self.input is not None
        self.input.dungeon.reset()
        self._play_event_sfx("menu_open")
        self._system_menu = False
        if self.mode is GameMode.DUNGEON:
            self.menu.open("Command", self._dungeon_menu_entries())
        else:
            self.menu.open("Command", self._exploration_menu_entries())

    def _open_system_menu(self) -> None:
        assert self.input is not None
        self.input.dungeon.reset()
        self._play_event_sfx("menu_open")
        self._system_menu = True
        entries = [
            MenuEntry("Resume", action=self.menu.close),
            MenuEntry("Audio", children=self._audio_menu_entries, detail=f"Music {round(self.audio.master_volume * 100)}%"),
        ]
        locales = getattr(self.definition, "available_locales", None)
        if callable(locales) and len(locales()) > 1:
            entries.append(MenuEntry(
                "Language",
                children=self._language_menu_entries,
                detail=str(getattr(self.definition, "active_locale_label", lambda: "")()),
            ))
        entries.extend([
            MenuEntry("Controls", action=self._show_controls),
            MenuEntry(
                "Save Game",
                action=lambda: self._save_from_menu(),
            ),
            MenuEntry(
                "Load Game",
                action=lambda: self._load_from_menu(),
                enabled=self.default_save_path.exists(),
            ),
            MenuEntry("Quit", action=self._quit_from_menu),
        ])
        self.menu.open("System", entries)

    def _exploration_menu_entries(self) -> list[MenuEntry]:
        return [
            MenuEntry("Party", children=self._party_entries),
            MenuEntry("Bag", children=self._bag_entries),
            MenuEntry("Journal", action=self._show_journal),
            MenuEntry("System", children=lambda: [
                MenuEntry("Audio", children=self._audio_menu_entries, detail=f"Music {round(self.audio.master_volume * 100)}%"),
                MenuEntry("Save Game", action=lambda: self._save_from_menu()),
                MenuEntry("Load Game", action=lambda: self._load_from_menu(), enabled=self.default_save_path.exists()),
                MenuEntry("Controls", action=self._show_controls),
            ]),
        ]

    def _dungeon_menu_entries(self) -> list[MenuEntry]:
        return [
            MenuEntry("Skills", children=self._skill_entries),
            MenuEntry("Items", children=self._bag_entries),
            MenuEntry("Party", children=self._party_entries),
            MenuEntry("Ground", children=self._ground_entries),
            MenuEntry("Others", children=lambda: [
                MenuEntry("Dungeon info", action=self._show_dungeon_info),
                MenuEntry("Wait", action=self._wait_from_menu),
                MenuEntry("Give up", action=lambda: self._give_up_from_menu()),
            ]),
        ]

    def _language_menu_entries(self) -> list[MenuEntry]:
        provider = getattr(self.definition, "available_locales", None)
        setter = getattr(self.definition, "set_locale", None)
        if not callable(provider) or not callable(setter):
            return []
        current = str(getattr(self.definition, "active_locale", lambda: "")())
        entries: list[MenuEntry] = []
        for locale, label in provider():
            def select(value=locale):
                setter(self, value)
                self.menu.close()
                self.add_message(f"Language: {getattr(self.definition, 'active_locale_label', lambda: value)()}")
            entries.append(MenuEntry(
                label,
                action=select,
                detail="Current" if locale == current else "",
            ))
        return entries

    def _audio_menu_entries(self) -> list[MenuEntry]:
        return [
            MenuEntry(
                "Music volume",
                children=self._music_volume_entries,
                detail=f"{round(self.audio.master_volume * 100)}%",
            ),
            MenuEntry(
                "SFX volume",
                children=self._sfx_volume_entries,
                detail=f"{round(self.audio.sfx_volume * 100)}%",
            ),
        ]

    def _music_volume_entries(self) -> list[MenuEntry]:
        current = round(self.audio.master_volume * 100)
        entries: list[MenuEntry] = []
        for percent in range(0, 101, 10):
            label = f"{percent}%" + ("  (current)" if percent == current else "")
            entries.append(MenuEntry(label, action=lambda p=percent: self._set_music_volume(p / 100.0)))
        return entries

    def _set_music_volume(self, value: float) -> None:
        self.audio.set_master_volume(value)
        self.add_message(f"Music volume: {round(self.audio.master_volume * 100)}%")
        # Rebuild the audio submenu so the checkmark/detail updates immediately.
        if self.menu.current is not None and self.menu.current.title == "Music volume":
            self.menu.current.entries = self._music_volume_entries()
            self.menu.current.selected = min(10, max(0, round(self.audio.master_volume * 10)))

    def _sfx_volume_entries(self) -> list[MenuEntry]:
        current = round(self.audio.sfx_volume * 100)
        entries: list[MenuEntry] = []
        for percent in range(0, 101, 10):
            label = f"{percent}%" + ("  (current)" if percent == current else "")
            entries.append(MenuEntry(label, action=lambda p=percent: self._set_sfx_volume(p / 100.0)))
        return entries

    def _set_sfx_volume(self, value: float) -> None:
        self.audio.set_sfx_volume(value)
        self.add_message(f"SFX volume: {round(self.audio.sfx_volume * 100)}%")
        if self.menu.current is not None and self.menu.current.title == "SFX volume":
            self.menu.current.entries = self._sfx_volume_entries()
            self.menu.current.selected = min(10, max(0, round(self.audio.sfx_volume * 10)))

    def _sync_exploration_music(self) -> None:
        if self.exploration is None:
            return
        error = self.audio.play_scene(self.exploration.music, self.exploration.music_volume)
        if error:
            self.add_message(error)
        self.audio.play_ambience(self.exploration.ambience_cue, self.exploration.ambience_volume)

    def _party_entries(self) -> list[MenuEntry]:
        entries: list[MenuEntry] = []
        for member in self.state.party:
            children = [MenuEntry("Status", action=lambda m=member: self._show_status(m))]
            if not member.leader:
                children.append(MenuEntry("Tactics", children=lambda m=member: self._tactic_entries(m), detail=member.ai_tactic.value))
            entries.append(MenuEntry(member.name, children=children))
        return entries

    def _skill_entries(self) -> list[MenuEntry]:
        leader = self.state.leader
        entries: list[MenuEntry] = []
        for runtime in leader.skills:
            charges = "∞" if runtime.charges is None else str(runtime.charges)
            label = f"{runtime.definition.name}  [{charges}]"
            entries.append(MenuEntry(label, action=lambda s=runtime: self._use_skill_from_menu(s), enabled=runtime.available(leader.resources)))
        if not entries:
            entries.append(MenuEntry("No skills", enabled=False))
        return entries

    def _bag_entries(self) -> list[MenuEntry]:
        entries: list[MenuEntry] = []
        for stack in self.state.bag.stacks:
            actions = []
            if stack.item.heal > 0:
                actions.append(MenuEntry("Use", action=lambda i=stack.item: self._use_item(i)))
            if self.mode is GameMode.DUNGEON and stack.item.throwable_damage > 0:
                actions.append(MenuEntry("Throw", action=lambda i=stack.item: self._throw_item(i)))
            actions.append(MenuEntry("Info", action=lambda i=stack.item: self._show_item_info(i)))
            entries.append(MenuEntry(f"{stack.item.name} ×{stack.quantity}", children=actions))
        if not entries:
            entries.append(MenuEntry("Bag is empty", enabled=False))
        return entries

    def open_item_storage(self) -> None:
        """Open the shared bag/storage transfer interface from an exploration object."""
        if self.mode is not GameMode.EXPLORATION:
            self.add_message("Item storage is only available while exploring.")
            return
        self._system_menu = False
        self.menu.open("Item Storage", [
            MenuEntry(
                "Deposit from bag",
                children=lambda: self._storage_item_entries("bag"),
                detail=f"{self.state.bag.occupied_slots}/{self.state.bag.capacity} bag slots",
            ),
            MenuEntry(
                "Withdraw from storage",
                children=lambda: self._storage_item_entries("storage"),
                detail=f"{self.state.storage.occupied_slots}/{self.state.storage.capacity} storage slots",
            ),
            MenuEntry("Close", action=self.menu.close),
        ])

    def _storage_item_entries(self, source_name: str) -> list[MenuEntry]:
        source = self.state.bag if source_name == "bag" else self.state.storage
        verb = "Deposit" if source_name == "bag" else "Withdraw"
        if not source.stacks:
            return [MenuEntry("Nothing here", enabled=False)]

        entries: list[MenuEntry] = []
        for stack in source.stacks:
            item_id = stack.item.id
            quantity = stack.quantity

            def actions(i=item_id, q=quantity, v=verb, src=source_name):
                return [
                    MenuEntry(f"{v} one", action=lambda: self._transfer_storage_item(src, i, 1)),
                    MenuEntry(
                        f"{v} stack",
                        action=lambda: self._transfer_storage_item(src, i, None),
                        detail=f"×{q}",
                    ),
                ]

            entries.append(MenuEntry(
                f"{stack.item.name} ×{quantity}",
                children=actions,
                detail=stack.item.description,
            ))
        return entries

    def _transfer_storage_item(self, source_name: str, item_id: str, quantity: int | None) -> None:
        source = self.state.bag if source_name == "bag" else self.state.storage
        destination = self.state.storage if source_name == "bag" else self.state.bag
        stack = next((entry for entry in source.stacks if entry.item.id == item_id), None)
        if stack is None:
            self.add_message("That item is no longer available.")
            self.open_item_storage()
            return

        amount = stack.quantity if quantity is None else min(stack.quantity, max(1, int(quantity)))
        item = stack.item
        if not destination.add(item, amount):
            target = "storage" if source_name == "bag" else "bag"
            self.add_message(f"The {target} is full.")
            self.open_item_storage()
            return

        source.remove(item_id, amount)
        direction = "Stored" if source_name == "bag" else "Withdrew"
        self.add_message(f"{direction} {item.name} ×{amount}.")
        self.open_item_storage()

    def open_money_storage(self) -> None:
        """Open the carried/stored money transfer interface from an exploration object."""
        if self.mode is not GameMode.EXPLORATION:
            self.add_message("Money storage is only available while exploring.")
            return
        self._system_menu = False
        self.menu.open("Money Storage", [
            MenuEntry(
                "Deposit",
                children=lambda: self._money_storage_entries(to_storage=True),
                detail=f"Carried: {self.state.wallet.carried}",
            ),
            MenuEntry(
                "Withdraw",
                children=lambda: self._money_storage_entries(to_storage=False),
                detail=f"Stored: {self.state.wallet.stored}",
            ),
            MenuEntry("Close", action=self.menu.close),
        ])

    def _money_storage_entries(self, *, to_storage: bool) -> list[MenuEntry]:
        available = self.state.wallet.carried if to_storage else self.state.wallet.stored
        verb = "Deposit" if to_storage else "Withdraw"
        if available <= 0:
            return [MenuEntry("No money available", enabled=False)]

        amounts = [value for value in (1, 10, 100, 1000) if value < available]
        entries = [
            MenuEntry(str(value), action=lambda amount=value: self._transfer_storage_money(to_storage, amount))
            for value in amounts
        ]
        entries.append(MenuEntry(
            f"All ({available})",
            action=lambda amount=available: self._transfer_storage_money(to_storage, amount),
        ))
        return entries

    def _transfer_storage_money(self, to_storage: bool, amount: int) -> None:
        amount = max(0, int(amount))
        if to_storage:
            moved = min(amount, self.state.wallet.carried)
            self.state.wallet.carried -= moved
            self.state.wallet.stored += moved
            verb = "Stored"
        else:
            moved = min(amount, self.state.wallet.stored)
            self.state.wallet.stored -= moved
            self.state.wallet.carried += moved
            verb = "Withdrew"

        if moved:
            self.add_message(f"{verb} {moved} money.")
        self.open_money_storage()

    def _ground_entries(self) -> list[MenuEntry]:
        if self.dungeon is None or self.state.leader.grid_pos is None:
            return [MenuEntry("Nothing here", enabled=False)]
        ground = self.dungeon.floor.item_at(self.state.leader.grid_pos)
        if ground is None:
            return [MenuEntry("Nothing here", enabled=False)]
        return [MenuEntry(ground.item.name, action=self._pickup_ground_from_menu)]

    def _handle_menu(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type != pygame.KEYDOWN or getattr(event, "repeat", False):
                continue
            if event.key == pygame.K_w:
                before = self.menu.current.selected if self.menu.current else None
                self.menu.move(-1)
                if self.menu.current and self.menu.current.selected != before:
                    self._play_event_sfx("cursor_move")
            elif event.key == pygame.K_s:
                before = self.menu.current.selected if self.menu.current else None
                self.menu.move(1)
                if self.menu.current and self.menu.current.selected != before:
                    self._play_event_sfx("cursor_move")
            elif event.key == pygame.K_SPACE:
                level = self.menu.current
                enabled = bool(level and level.entries and level.entries[level.selected].enabled)
                self._play_event_sfx("confirm" if enabled else "error")
                self.menu.confirm()
            elif event.key == pygame.K_ESCAPE:
                if self.story_runner.active:
                    self._play_event_sfx("error")
                    continue
                self._play_event_sfx("cancel")
                self.menu.back()
            elif event.key == pygame.K_e and not self._system_menu:
                self._play_event_sfx("menu_close")
                self.menu.close()

    def _handle_dialogue(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and not getattr(event, "repeat", False) and event.key == pygame.K_SPACE:
                self._play_event_sfx("text_advance")
                self.dialogue.advance()
                self._play_dialogue_reaction()

    # ---------- menu actions ----------

    def _show_status(self, member: Character) -> None:
        skills = ", ".join(s.definition.name for s in member.skills) or "none"
        self.menu.close()
        self.say([DialogueLine(member.name, f"HP {member.stats.current_hp}/{member.stats.max_hp}. Attack {member.stats.attack}; Defense {member.stats.defense}. Skills: {skills}.")])

    def _tactic_entries(self, member: Character) -> list[MenuEntry]:
        entries: list[MenuEntry] = []
        for tactic in AITactic:
            label = ("✓ " if member.ai_tactic is tactic else "  ") + tactic.value
            entries.append(MenuEntry(label, action=lambda m=member, t=tactic: self._set_tactic(m, t)))
        return entries

    def _set_tactic(self, member: Character, tactic: AITactic) -> None:
        member.ai_tactic = tactic
        self.add_message(f"{member.name}: {member.ai_tactic.value}.")
        self.menu.back()

    def _show_item_info(self, item: ItemDefinition) -> None:
        self.menu.close()
        self.say([DialogueLine("Bag", f"{item.name}: {item.description}")])

    def _use_item(self, item: ItemDefinition) -> None:
        if item.heal <= 0:
            return
        leader = self.state.leader
        healed = leader.stats.heal(item.heal)
        if healed <= 0:
            self.add_message(f"{leader.name} is already at full HP.")
            return
        self.state.bag.remove(item.id)
        self.audio.play_sfx(item.sfx_cue)
        self.add_message(f"{leader.name} uses {item.name} and recovers {healed} HP.")
        self.menu.close()
        if self.mode is GameMode.DUNGEON and self.dungeon:
            outcome = self.dungeon.turns.execute_player_action(WaitAction(leader))
            for cue in outcome.sound_cues:
                self.audio.play_sfx(cue)
            for msg in outcome.messages:
                if not msg.endswith("waits."):
                    self.add_message(msg)
            self._queue_turn_projectiles(outcome)
            if outcome.dungeon_result is DungeonResult.DEFEAT:
                self._finish_or_defer_dungeon_result(DungeonResult.DEFEAT)

    def _throw_item(self, item: ItemDefinition) -> None:
        if self.dungeon is None or self.state.leader.grid_pos is None:
            return
        target = self._first_hostile_in_facing(item_range=6)
        if target is None:
            self.add_message("No target in that direction.")
            return
        source_pos = self.state.leader.grid_pos
        target_pos = target.grid_pos
        self.state.bag.remove(item.id)
        raw = item.throwable_damage
        dealt = target.stats.damage(max(1, round(raw * target.resistance_to(item.damage_type))))
        self.add_message(f"{self.state.leader.name} throws {item.name}; {target.name} takes {dealt} damage.")
        self.menu.close()
        outcome = self.dungeon.turns.execute_player_action(WaitAction(self.state.leader))
        for cue in outcome.sound_cues:
            self.audio.play_sfx(cue)
        for msg in outcome.messages:
            if not msg.endswith("waits."):
                self.add_message(msg)
        thrown = []
        if item.projectile_key and source_pos is not None and target_pos is not None:
            thrown.append(ProjectileEvent(
                source_id=self.state.leader.id,
                target_id=target.id,
                source_pos=source_pos,
                target_pos=target_pos,
                projectile_key=item.projectile_key,
                hit=True,
                launch_sfx_cue=item.sfx_cue,
                impact_sfx_cue=item.impact_sfx_cue,
                arc_px=item.projectile_arc_px,
            ))
        self._queue_projectiles([*thrown, *outcome.projectiles])
        if outcome.dungeon_result is DungeonResult.DEFEAT:
            self._finish_or_defer_dungeon_result(DungeonResult.DEFEAT)

    def _use_skill_from_menu(self, skill) -> None:
        if self.dungeon is None:
            return
        leader = self.state.leader
        definition = skill.definition
        pattern = effective_range_pattern(definition)

        if pattern is RangePattern.ROOM:
            candidates = targets_for_skill(self.dungeon.floor, leader, definition)
            target = None
        elif pattern is RangePattern.SELF:
            candidates = targets_for_skill(self.dungeon.floor, leader, definition)
            target = leader if candidates else None
        else:
            candidates = targets_for_skill(
                self.dungeon.floor,
                leader,
                definition,
                facing=leader.facing,
            )
            target = candidates[0] if candidates else None

        if not candidates:
            where = "in this room" if pattern is RangePattern.ROOM else "in that direction"
            self.add_message(f"No valid target {where}.")
            return

        self.menu.close()
        outcome = self.dungeon.turns.execute_player_action(SkillAction(leader, skill, target))
        for cue in outcome.sound_cues:
            self.audio.play_sfx(cue)
        for msg in outcome.messages:
            self.add_message(msg)
        self._queue_turn_projectiles(outcome)
        if outcome.dungeon_result is DungeonResult.DEFEAT:
            self._finish_or_defer_dungeon_result(DungeonResult.DEFEAT)

    def _pickup_ground_from_menu(self) -> None:
        if self.dungeon is None or self.state.leader.grid_pos is None:
            return
        ground = self.dungeon.floor.item_at(self.state.leader.grid_pos)
        if ground and self.state.bag.add(ground.item):
            self.dungeon.floor.ground_items.remove(ground)
            self._play_event_sfx("item_get")
            self.add_message(f"Picked up {ground.item.name}.")
            self.menu.close()
        else:
            self.add_message("The bag is full.")

    def _wait_from_menu(self) -> None:
        if self.dungeon is None:
            return
        self.menu.close()
        outcome = self.dungeon.turns.execute_player_action(WaitAction(self.state.leader))
        for cue in outcome.sound_cues:
            self.audio.play_sfx(cue)
        for msg in outcome.messages:
            self.add_message(msg)
        self._queue_turn_projectiles(outcome)
        if outcome.dungeon_result is DungeonResult.DEFEAT:
            self._finish_or_defer_dungeon_result(DungeonResult.DEFEAT)

    def _give_up_from_menu(self) -> None:
        self.menu.close()
        self.return_to_exploration(DungeonResult.ABANDONED)

    def _show_dungeon_info(self) -> None:
        if self.dungeon is None:
            return
        self.menu.close()
        self.say([DialogueLine("Dungeon", f"Floor {self.dungeon.floor_number} of {self.definition.dungeon_floor_count}. Turn {self.dungeon.turns.turn_count}. Reach the stairs to descend.")])

    def _show_journal(self) -> None:
        self.menu.close()
        provider = getattr(self.definition, "journal_text", None)
        text = str(provider(self) if callable(provider) else "No journal entries.")
        self.say([DialogueLine("Journal", text)])

    def _show_controls(self) -> None:
        self.menu.close()
        self.say([DialogueLine("Controls", "WASD moves. Hold two directions for diagonals. Shift sprints or dashes. Space interacts/confirms. E opens the command menu. Esc goes back or opens System.")])

    def _show_item_info_short(self, item: ItemDefinition) -> None:
        self.add_message(f"{item.name}: {item.description}")

    def _save_from_menu(self) -> None:
        self.save_snapshot()
        self.menu.close()

    def _load_from_menu(self) -> None:
        self.load_snapshot()
        self.menu.close()

    def _quit_from_menu(self) -> None:
        self.menu.close()
        self.running = False

    # ---------- dungeon helpers ----------

    def _basic_attack_or_wait(self):
        assert self.dungeon is not None
        leader = self.state.leader
        if leader.grid_pos is None:
            return WaitAction(leader)
        pos = leader.grid_pos.moved(leader.facing)
        target = self.dungeon.floor.entity_at(pos)
        if target and target.hostile:
            return BasicAttackAction(leader, target)
        return WaitAction(leader)

    def _first_hostile_in_facing(self, item_range: int) -> Character | None:
        if self.dungeon is None:
            return None
        leader = self.state.leader
        if leader.grid_pos is None:
            return None
        pos = leader.grid_pos
        for _ in range(item_range):
            pos = pos.moved(leader.facing)
            if not self.dungeon.floor.in_bounds(pos) or self.dungeon.floor.tile(pos).blocks_sight:
                break
            target = self.dungeon.floor.entity_at(pos)
            if target is not None:
                return target if target.hostile else None
        return None

    def _visible_enemy_ids(self) -> set[str]:
        if not self.dungeon:
            return set()
        return {
            e.id for e in self.dungeon.turns.enemies
            if e.grid_pos is not None and e.grid_pos in self.dungeon.turns.memory.visible
        }

    # ---------- rendering/window ----------

    def _render(self) -> None:
        assert self.renderer is not None and self._display is not None
        self.renderer.begin()
        if self.mode is GameMode.EXPLORATION:
            assert self.exploration is not None
            self.renderer.draw_exploration(self.exploration, self.state.leader.id)
        else:
            assert self.dungeon is not None
            preserve = {self.active_projectile.event.target_id} if self.active_projectile is not None else set()
            self.renderer.draw_dungeon(
                self.dungeon.floor,
                self.dungeon.turns.memory,
                self.state.party,
                self.dungeon.floor_number,
                self.definition.dungeon_floor_count,
                preserve_entity_ids=preserve,
            )
            if self.active_projectile is not None:
                self.renderer.draw_projectile(self.active_projectile, self.dungeon.floor, self.state.party)
        self.renderer.draw_message_log(self.messages, self.mode is GameMode.DUNGEON)
        if self.menu.active:
            self.renderer.draw_menu(self.menu)
        if self.dialogue.active:
            width = self.config.dungeon_view_width if self.mode is GameMode.DUNGEON else self.config.logical_width
            self.renderer.draw_dialogue(self.dialogue, max_width=width)
        self.renderer.draw_cinematic_overlay(self.cinematic_overlay)
        self.renderer.present(self._display)

    def _toggle_fullscreen(self) -> None:
        self._fullscreen = not self._fullscreen
        flags = pygame.FULLSCREEN if self._fullscreen else pygame.RESIZABLE
        size = (0, 0) if self._fullscreen else (1280, 720)
        self._display = pygame.display.set_mode(size, flags)
