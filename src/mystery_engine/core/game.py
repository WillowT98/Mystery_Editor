from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from random import Random
from typing import Protocol, TYPE_CHECKING

import pygame

from mystery_engine.config import EngineConfig
from mystery_engine.core.combat import CombatResolver, ProjectileEvent
from mystery_engine.core.game_state import PersistentGameState, SaveManager
from mystery_engine.core.inventory import ItemDefinition
from mystery_engine.core.models import AITactic, Character, TargetKind
from mystery_engine.core.types import Direction, DungeonResult, GameMode, GridPos, Vec2
from mystery_engine.dungeon.actions import BasicAttackAction, MoveAction, SkillAction, WaitAction
from mystery_engine.dungeon.floor import DungeonFloor
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
        self.story_runner = StoryGraphRunner(StoryRuntimeContext(
            story=self.state.story,
            dialogue=self.dialogue,
            choose=self._open_story_choice,
            run_action=self.story_actions,
            load_graph=self._load_story_graph,
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
        return StoryGraph.load(path)

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
        self.mode = GameMode.EXPLORATION
        self.menu.close()
        self._sync_exploration_music()
        self.add_message(f"Entered {new_world.id}.")

    def enter_dungeon(self, start_floor: int = 1) -> None:
        if self.dialogue.active:
            return
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
        self.mode = GameMode.EXPLORATION
        self.menu.close()
        self._sync_exploration_music()
        assert self.input is not None
        self.input.dungeon.reset()
        for member in self.state.party:
            member.restore_for_expedition()
            member.grid_pos = None
        self.definition.on_dungeon_result(self, result, lost_money=lost_money, lost_items=lost_items)

    def save_snapshot(self, path: Path | None = None) -> Path:
        path = path or Path("saves") / "test-save.json"
        self.save_manager.dump(self.state, path)
        self._play_event_sfx("save")
        self.add_message(f"Saved snapshot to {path}.")
        return path

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

        # Stairs are intentionally automatic in the test vertical slice.
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
            MenuEntry("Controls", action=self._show_controls),
            MenuEntry("Save snapshot", action=lambda: self._save_from_menu()),
            MenuEntry("Quit", action=self._quit_from_menu),
        ]
        self.menu.open("System", entries)

    def _exploration_menu_entries(self) -> list[MenuEntry]:
        return [
            MenuEntry("Party", children=self._party_entries),
            MenuEntry("Bag", children=self._bag_entries),
            MenuEntry("Journal", action=self._show_journal),
            MenuEntry("System", children=lambda: [
                MenuEntry("Audio", children=self._audio_menu_entries, detail=f"Music {round(self.audio.master_volume * 100)}%"),
                MenuEntry("Save snapshot", action=lambda: self._save_from_menu()),
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
        self.add_message(f"Fox throws {item.name}; {target.name} takes {dealt} damage.")
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
        if definition.target is TargetKind.SELF:
            target = leader
        elif definition.target is TargetKind.ALLY:
            candidates = [c for c in self.state.party if c.active and c.grid_pos and leader.grid_pos and leader.grid_pos.chebyshev(c.grid_pos) <= definition.range]
            target = min(candidates, key=lambda c: c.stats.hp_ratio) if candidates else None
        else:
            target = self._first_hostile_in_facing(definition.range)
        if target is None:
            self.add_message("No valid target in that direction.")
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
        complete = self.state.story.flag("completed_test_dungeon")
        text = "The test expedition is complete." if complete else "Mara is waiting near the dungeon entrance."
        self.say([DialogueLine("Journal", text)])

    def _show_controls(self) -> None:
        self.menu.close()
        self.say([DialogueLine("Controls", "WASD moves. Hold two directions for diagonals. Shift sprints or dashes. Space interacts/confirms. E opens the command menu. Esc goes back or opens System.")])

    def _show_item_info_short(self, item: ItemDefinition) -> None:
        self.add_message(f"{item.name}: {item.description}")

    def _save_from_menu(self) -> None:
        self.save_snapshot()
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
