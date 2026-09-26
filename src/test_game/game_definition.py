from __future__ import annotations

from pathlib import Path
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mystery_engine.core.game import MysteryGame
from mystery_engine.core import DungeonResult, PersistentGameState, StoryState, Wallet
from mystery_engine.core.inventory import Inventory
from mystery_engine.dungeon import DungeonDefinition
from mystery_engine.story import (
    build_exploration_map,
    load_exploration_scene,
    DialogueLine,
    ExplorationMap,
)

from .world_assets import WORLD_ASSETS

from .content import (
    ENEMY_FACTORIES,
    ITEM_CATALOG,
    make_fox,
    make_mara,
    make_starting_bag,
)


class TestGameDefinition:
    game_id = "fox_and_mara_test"
    asset_root = Path(__file__).resolve().parent / "assets"
    sfx_catalog_path = asset_root / "sfx_cues.json"
    # Engine events resolve to semantic cues. The files behind these cues can be
    # swapped or expanded without touching gameplay code or scene JSON.
    sfx_event_cues = {
        "menu_open": "ui.menu_open",
        "menu_close": "ui.menu_close",
        "cursor_move": "ui.cursor_move",
        "confirm": "ui.confirm",
        "cancel": "ui.cancel",
        "error": "ui.error",
        "text_advance": "ui.text_advance",
        "item_get": "ui.item_get",
        "save": "ui.save",
        "basic_hit": "combat.light_hit",
        "defeat": "combat.defeat",
    }
    game_version = "0.1.0"
    title = "Fox & Mara — Mystery Engine Test"
    defeat_money_loss_fraction = 0.50
    defeat_item_loss_chance = 0.30

    exploration_tile_size = 64
    dungeon_path = Path(__file__).resolve().parent / "dungeons" / "test_dungeon.json"

    def __init__(self) -> None:
        override = os.environ.get("MYSTERY_DUNGEON_PATH")
        self.dungeon_definition = DungeonDefinition.load(Path(override) if override else self.dungeon_path)
        self.dungeon_floor_count = self.dungeon_definition.floor_count

    def create_state(self) -> PersistentGameState:
        fox = make_fox()
        mara = make_mara()
        return PersistentGameState(
            game_id=self.game_id,
            game_version=self.game_version,
            party=[fox, mara],
            bag=make_starting_bag(),
            storage=Inventory(capacity=40),
            wallet=Wallet(carried=100, stored=0),
            story=StoryState(flags={
                "completed_test_dungeon": False,
                "failed_test_dungeon": False,
                "entered_test_dungeon": False,
            }),
        )

    def create_exploration(self, game: "MysteryGame") -> ExplorationMap:
        """Load the default exploration scene produced by the visual editor."""
        override = os.environ.get("MYSTERY_SCENE_PATH")
        scene_path = Path(override) if override else Path(__file__).resolve().parent / "scenes" / "test_clearing.json"
        return self.create_exploration_scene(game, scene_path)

    def create_exploration_scene(self, game: "MysteryGame", scene_path: Path) -> ExplorationMap:
        """Load any exploration scene, including editor-created linked rooms."""

        def talk_to_mara() -> None:
            if game.state.story.flag("completed_test_dungeon"):
                lines = [
                    DialogueLine("Mara", "There you are. The path through the dungeon is stable now."),
                    DialogueLine("Fox", "So the engine survived us."),
                    DialogueLine("Mara", "For a first expedition? I'll accept that."),
                ]
            elif game.state.story.flag("failed_test_dungeon"):
                lines = [
                    DialogueLine("Mara", "That hurt. We can go back whenever you're ready."),
                    DialogueLine("Fox", "And perhaps lose slightly fewer of our things this time."),
                ]
            else:
                lines = [
                    DialogueLine("Mara", "The test dungeon is just east of here."),
                    DialogueLine("Mara", "Three floors. Enough to see whether all of this actually works."),
                    DialogueLine("Fox", "That's reassuringly scientific."),
                ]
            game.say(lines)

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

        return build_exploration_map(scene, WORLD_ASSETS, interactions, portal_transition_factory=portal_transition)

    def create_dungeon_floor(self, game: "MysteryGame", floor_number: int):
        def enemy_factory(enemy_id: str, identifier: str):
            try:
                return ENEMY_FACTORIES[enemy_id](identifier)
            except KeyError as exc:
                raise KeyError(f"Unknown dungeon enemy: {enemy_id}") from exc

        def item_lookup(item_id: str):
            try:
                return ITEM_CATALOG[item_id]
            except KeyError as exc:
                raise KeyError(f"Unknown dungeon item: {item_id}") from exc

        return self.dungeon_definition.build_floor(
            floor_number,
            game.rng,
            enemy_factory,
            item_lookup,
        )

    def on_dungeon_result(self, game: "MysteryGame", result: DungeonResult, *, lost_money: int = 0, lost_items: list[str] | None = None) -> None:
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
