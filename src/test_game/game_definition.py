from __future__ import annotations

from pathlib import Path
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mystery_engine.core.game import MysteryGame
from mystery_engine.core import DungeonResult, PersistentGameState, StoryState, Wallet
from mystery_engine.core.inventory import Inventory
from mystery_engine.dungeon import DungeonDefinition
from mystery_engine.project import ProjectRegistry
from mystery_engine.story import (
    build_exploration_map,
    load_exploration_scene,
    DialogueLine,
    ExplorationMap,
)

from .world_assets import WORLD_ASSETS

class TestGameDefinition:
    asset_root = Path(__file__).resolve().parent / "assets"
    sfx_catalog_path = asset_root / "sfx_cues.json"
    exploration_tile_size = 64
    story_root = Path(__file__).resolve().parent / "stories"
    scene_root = Path(__file__).resolve().parent / "scenes"

    def __init__(self) -> None:
        self.project_registry = ProjectRegistry.load(Path(__file__).resolve().parent)
        settings = self.project_registry.game_settings
        self.game_id = self.project_registry.project_id
        self.game_version = settings.version
        self.title = settings.title
        self.defeat_money_loss_fraction = settings.defeat_money_loss_fraction
        self.defeat_item_loss_chance = settings.defeat_item_loss_chance
        self.sfx_event_cues = dict(settings.sfx_event_cues)
        override = os.environ.get("MYSTERY_DUNGEON_PATH")
        if override:
            self.active_dungeon_id = Path(override).stem
            self.dungeon_definition = DungeonDefinition.load(Path(override))
        else:
            self.active_dungeon_id = self.project_registry.default_dungeon_id or "test_dungeon"
            self.dungeon_definition = self.project_registry.load_dungeon(self.active_dungeon_id)
        self.dungeon_floor_count = self.dungeon_definition.floor_count

    def select_dungeon(self, dungeon_id: str) -> None:
        self.dungeon_definition = self.project_registry.load_dungeon(dungeon_id)
        self.active_dungeon_id = dungeon_id
        self.dungeon_floor_count = self.dungeon_definition.floor_count

    def resolve_story_pawn(self, pawn_id: str) -> tuple[str, str | None]:
        return self.project_registry.resolve_story_pawn(pawn_id)

    def create_state(self) -> PersistentGameState:
        settings = self.project_registry.game_settings
        if not settings.starting_party:
            raise RuntimeError("Game settings require at least one starting party member")
        leader_id = settings.leader or settings.starting_party[0]
        party = [
            self.project_registry.make_character(character_id, leader=(character_id == leader_id))
            for character_id in settings.starting_party
        ]

        bag = Inventory(capacity=settings.bag_capacity)
        for item_id, quantity in settings.starting_items.items():
            if quantity > 0:
                bag.add(self.project_registry.item(item_id), quantity)

        storage = Inventory(capacity=settings.storage_capacity)
        for item_id, quantity in settings.starting_storage.items():
            if quantity > 0:
                storage.add(self.project_registry.item(item_id), quantity)

        return PersistentGameState(
            game_id=self.game_id,
            game_version=self.game_version,
            party=party,
            bag=bag,
            storage=storage,
            wallet=Wallet(
                carried=settings.starting_carried_money,
                stored=settings.starting_stored_money,
            ),
            story=StoryState(
                flags=dict(settings.starting_flags),
                variables=dict(settings.starting_variables),
            ),
        )

    def create_exploration(self, game: "MysteryGame") -> ExplorationMap:
        """Load the project-configured starting scene."""
        override = os.environ.get("MYSTERY_SCENE_PATH")
        settings = self.project_registry.game_settings
        if override:
            scene_path = Path(override)
        elif settings.starting_scene:
            try:
                scene_path = self.project_registry.scene_paths()[settings.starting_scene]
            except KeyError as exc:
                raise RuntimeError(f"Unknown starting scene: {settings.starting_scene}") from exc
        else:
            paths = self.project_registry.scene_paths()
            if not paths:
                raise RuntimeError("Project has no exploration scenes")
            scene_path = next(iter(paths.values()))

        world = self.create_exploration_scene(game, scene_path)
        if settings.starting_marker:
            try:
                target = world.target_position(settings.starting_marker)
                leader = world.actor(game.state.leader.id)
                leader.position.x, leader.position.y = target.x, target.y
            except KeyError:
                pass
        return world

    def create_exploration_scene(self, game: "MysteryGame", scene_path: Path) -> ExplorationMap:
        """Load any exploration scene, including editor-created linked rooms."""

        def talk_to_mara() -> None:
            game.run_story("mara_meadow")

        def enter_dungeon() -> None:
            if not game.state.story.flag("entered_test_dungeon"):
                game.state.story.set_flag("entered_test_dungeon")
                game.say(
                    [
                        DialogueLine("Fox", "This is the entrance?"),
                        DialogueLine("Mara", "Unless the prototype has put another one somewhere."),
                    ],
                    on_complete=game.enter_dungeon,
                )
            else:
                game.enter_dungeon()

        def inspect_waystone() -> None:
            game.say([DialogueLine("Waystone", "A plain marker has been driven into the clearing. Someone has written: TEST AREA.")])

        scene_path = Path(scene_path).resolve()
        scene = load_exploration_scene(scene_path)
        interactions = {
            "talk_mara": talk_to_mara,
            "enter_test_dungeon": enter_dungeon,
            "inspect_waystone": inspect_waystone,
        }

        def portal_transition(placed):
            def transition() -> None:
                if not placed.target_scene:
                    game.add_message("This scene door is not linked yet.")
                    return
                target_path = Path(placed.target_scene)
                if not target_path.is_absolute():
                    target_path = scene_path.parent / target_path
                if not target_path.exists():
                    game.add_message(f"Linked scene does not exist: {target_path.name}")
                    return
                game.change_exploration_scene(target_path, placed.target_door)
            return transition

        def dungeon_transition(placed):
            def transition() -> None:
                if not placed.target_dungeon:
                    game.add_message("This dungeon entrance is not linked yet.")
                    return
                try:
                    self.select_dungeon(placed.target_dungeon)
                except KeyError:
                    game.add_message(f"Unknown dungeon: {placed.target_dungeon}")
                    return
                game.enter_dungeon()
            return transition

        def story_transition(placed):
            def transition() -> None:
                if not placed.target_story:
                    return
                try:
                    game.run_story(placed.target_story)
                except (KeyError, FileNotFoundError):
                    game.add_message(f"Unknown story: {placed.target_story}")
            return transition

        return build_exploration_map(
            scene,
            self.project_registry.world_asset_catalog(WORLD_ASSETS),
            interactions,
            portal_transition_factory=portal_transition,
            dungeon_transition_factory=dungeon_transition,
            story_transition_factory=story_transition,
            terrain_styles=self.project_registry.terrain_runtime(),
        )

    def create_dungeon_floor(self, game: "MysteryGame", floor_number: int):
        def enemy_factory(enemy_id: str, identifier: str):
            return self.project_registry.make_enemy(enemy_id, identifier)

        def item_lookup(item_id: str):
            return self.project_registry.item(item_id)

        return self.dungeon_definition.build_floor(
            floor_number,
            game.rng,
            enemy_factory,
            item_lookup,
            enemy_modifier=self.project_registry.apply_spawn_modifiers,
        )

    def on_dungeon_result(self, game: "MysteryGame", result: DungeonResult, *, lost_money: int = 0, lost_items: list[str] | None = None) -> None:
        result_story = self.project_registry.game_settings.dungeon_result_stories.get(result.name.lower())
        if result_story:
            game.run_story(result_story)
            return

        # Compatibility fallback for the existing test vertical slice. New games
        # can author these outcomes as ordinary project stories in Game Settings.
        lost_items = lost_items or []
        if result is DungeonResult.SUCCESS:
            game.state.story.set_flag("completed_test_dungeon")
            game.state.story.set_flag("failed_test_dungeon", False)
            game.say([
                DialogueLine("Fox", "Back in one piece."),
                DialogueLine("Mara", "And with a functioning dungeon engine, apparently."),
            ])
        elif result is DungeonResult.DEFEAT:
            game.state.story.set_flag("failed_test_dungeon")
            item_text = ", ".join(lost_items) if lost_items else "nothing from the bag"
            game.say([
                DialogueLine("Fox", "Ow."),
                DialogueLine("Mara", f"We lost {lost_money} coins and {item_text}. At least the waystone shard is protected."),
            ])
        else:
            game.say([DialogueLine("Mara", "We'll call that one a tactical retreat.")])


def build_game():
    from mystery_engine.core.game import MysteryGame
    return MysteryGame(TestGameDefinition())
