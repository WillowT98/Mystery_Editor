from __future__ import annotations

from pathlib import Path
import os
from typing import TYPE_CHECKING

from mystery_engine.core import DungeonResult, PersistentGameState, StoryState, Wallet
from mystery_engine.core.inventory import Inventory
from mystery_engine.project import ProjectRegistry
from mystery_engine.core import Vec2
from mystery_engine.story import (
    ExplorationActor,
    ExplorationMap,
    RectObstacle,
    WorldAssetCatalog,
    WorldAssetDefinition,
    build_exploration_map,
    load_exploration_scene,
)

if TYPE_CHECKING:
    from mystery_engine.core.game import MysteryGame


SYSTEM_WORLD_ASSETS = WorldAssetCatalog(assets={
    "dungeon_entrance": WorldAssetDefinition(
        id="dungeon_entrance",
        category="dungeon",
        sprite_key=None,
        display_name="Dungeon entrance",
        size=(192, 150),
        collision=RectObstacle(-88, -136, 176, 58),
        label="Dungeon entrance",
    ),
    "scene_door": WorldAssetDefinition(
        id="scene_door",
        category="portal",
        sprite_key=None,
        display_name="Scene door",
        size=(72, 56),
        collision=None,
        label="Door",
        runtime_visible=False,
    ),
    "story_marker": WorldAssetDefinition(
        id="story_marker",
        category="marker",
        sprite_key=None,
        display_name="Story marker",
        size=(48, 48),
        collision=None,
        runtime_visible=False,
    ),
    "item_storage": WorldAssetDefinition(
        id="item_storage",
        category="interactable",
        sprite_key="item_storage",
        display_name="Item storage",
        size=(72, 64),
        collision=RectObstacle(-30, -38, 60, 38),
        label="Item storage",
        action_id="storage.items",
    ),
    "money_storage": WorldAssetDefinition(
        id="money_storage",
        category="interactable",
        sprite_key="money_storage",
        display_name="Money storage",
        size=(72, 64),
        collision=RectObstacle(-30, -38, 60, 38),
        label="Money storage",
        action_id="storage.money",
    ),
})


class ProjectGameDefinition:
    """Generic runtime adapter for any editor-authored project."""

    exploration_tile_size = 64

    def __init__(self, project_root: Path) -> None:
        self.project_registry = ProjectRegistry.load(project_root)
        requested_locale = os.environ.get("MYSTERY_LOCALE") or self.project_registry.localization.default_locale
        self.project_registry.set_active_locale(requested_locale)
        settings = self.project_registry.game_settings
        self.game_id = self.project_registry.project_id
        self.game_version = settings.version
        self.title = self.project_registry.text("game.title", settings.title)
        self.asset_root = self.project_registry.asset_root
        self.sfx_catalog_path = self.asset_root / "sfx_cues.json"
        self.story_root = self.project_registry.story_dir
        self.scene_root = self.project_registry.scene_dir
        self.defeat_money_loss_fraction = settings.defeat_money_loss_fraction
        self.defeat_item_loss_chance = settings.defeat_item_loss_chance
        self.sfx_event_cues = dict(settings.sfx_event_cues)

        override = os.environ.get("MYSTERY_DUNGEON_PATH")
        if override:
            from mystery_engine.dungeon import DungeonDefinition
            self.active_dungeon_id = Path(override).stem
            self.dungeon_definition = DungeonDefinition.load(Path(override))
        elif settings.default_dungeon:
            self.active_dungeon_id = settings.default_dungeon
            self.dungeon_definition = self.project_registry.load_dungeon(settings.default_dungeon)
        else:
            self.active_dungeon_id = ""
            self.dungeon_definition = None
        self.dungeon_floor_count = self.dungeon_definition.floor_count if self.dungeon_definition else 0

    def select_dungeon(self, dungeon_id: str) -> None:
        self.dungeon_definition = self.project_registry.load_dungeon(dungeon_id)
        self.active_dungeon_id = dungeon_id
        self.dungeon_floor_count = self.dungeon_definition.floor_count

    def resolve_story_pawn(self, pawn_id: str) -> tuple[str, str | None]:
        return self.project_registry.resolve_story_pawn(pawn_id)

    def localize_story(self, graph):
        return self.project_registry.localize_story(graph)

    def available_locales(self) -> list[tuple[str, str]]:
        loc = self.project_registry.localization
        return [(code, loc.locale_label(code)) for code in loc.supported_locales]

    def active_locale(self) -> str:
        return self.project_registry.localization.active_locale

    def active_locale_label(self) -> str:
        loc = self.project_registry.localization
        return loc.locale_label(loc.active_locale)

    def set_locale(self, game: "MysteryGame", locale: str) -> None:
        self.project_registry.set_active_locale(locale)
        settings = self.project_registry.game_settings
        self.title = self.project_registry.text("game.title", settings.title)

        # Refresh already-created runtime content so switching language does not
        # require restarting the game.
        for member in game.state.party:
            definition = self.project_registry.characters.get(member.id)
            if definition is not None:
                pawn = self.project_registry.pawns.get(definition.pawn_id)
                if pawn is not None:
                    member.name = self.project_registry.text(f"pawn.{pawn.id}.name", pawn.name)
            for skill in member.skills:
                attack = self.project_registry.attacks.get(skill.definition.id)
                if attack is not None:
                    skill.definition = attack

        for inventory in (game.state.bag, game.state.storage):
            for stack in inventory.stacks:
                if stack.item.id in self.project_registry.items:
                    stack.item = self.project_registry.items[stack.item.id]

        if self.dungeon_definition is not None and self.active_dungeon_id:
            self.dungeon_definition = self.project_registry.load_dungeon(self.active_dungeon_id)
            self.dungeon_floor_count = self.dungeon_definition.floor_count

        if game.exploration is not None:
            for actor in game.exploration.actors:
                pawn = self.project_registry.pawns.get(actor.id)
                if pawn is not None:
                    actor.name = self.project_registry.text(f"pawn.{pawn.id}.name", pawn.name)
            for interactable in game.exploration.interactables:
                # Instance-specific labels are translated when scenes load; use
                # reusable object labels as a live-refresh fallback.
                object_data = self.project_registry.objects.get(interactable.id)
                if object_data is not None and object_data.label:
                    interactable.label = self.project_registry.text(
                        f"object.{object_data.id}.label", object_data.label
                    )

    def create_state(self) -> PersistentGameState:
        settings = self.project_registry.game_settings
        if not settings.starting_party:
            raise RuntimeError("Set at least one starting party member in Game Settings before running.")
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
            wallet=Wallet(carried=settings.starting_carried_money, stored=settings.starting_stored_money),
            story=StoryState(flags=dict(settings.starting_flags), variables=dict(settings.starting_variables)),
        )

    def create_exploration(self, game: "MysteryGame") -> ExplorationMap:
        override = os.environ.get("MYSTERY_SCENE_PATH")
        settings = self.project_registry.game_settings
        if override:
            path = Path(override)
        elif settings.starting_scene:
            try:
                path = self.project_registry.scene_paths()[settings.starting_scene]
            except KeyError as exc:
                raise RuntimeError(f"Unknown starting scene: {settings.starting_scene}") from exc
        else:
            scenes = self.project_registry.scene_paths()
            if not scenes:
                raise RuntimeError("Create a scene and choose it as the starting scene before running.")
            path = next(iter(scenes.values()))
        world = self.create_exploration_scene(game, path)
        if settings.starting_marker:
            try:
                target = world.target_position(settings.starting_marker)
                actor = world.actor(game.state.leader.id)
                actor.position.x, actor.position.y = target.x, target.y
            except KeyError:
                pass
        return world

    def create_exploration_scene(self, game: "MysteryGame", scene_path: Path) -> ExplorationMap:
        scene_path = Path(scene_path).resolve()
        scene = self.project_registry.localize_scene(load_exploration_scene(scene_path))

        def portal_transition(placed):
            def transition() -> None:
                if not placed.target_scene:
                    game.add_message("This scene door is not linked yet.")
                    return
                target = Path(placed.target_scene)
                if not target.is_absolute():
                    target = scene_path.parent / target
                if not target.exists():
                    game.add_message(f"Linked scene does not exist: {target.name}")
                    return
                game.change_exploration_scene(target, placed.target_door)
            return transition

        def dungeon_transition(placed):
            def transition() -> None:
                if not placed.target_dungeon:
                    game.add_message("This dungeon entrance is not linked yet.")
                    return
                self.select_dungeon(placed.target_dungeon)
                game.enter_dungeon()
            return transition

        def story_transition(placed):
            def transition() -> None:
                if placed.target_story:
                    game.run_story(placed.target_story)
            return transition

        system_interactions = {
            "storage.items": game.open_item_storage,
            "storage.money": game.open_money_storage,
        }
        world = build_exploration_map(
            scene,
            self.project_registry.world_asset_catalog(SYSTEM_WORLD_ASSETS),
            system_interactions,
            portal_transition_factory=portal_transition,
            dungeon_transition_factory=dungeon_transition,
            story_transition_factory=story_transition,
            terrain_styles=self.project_registry.terrain_runtime(),
        )
        for member in game.state.party:
            if any(actor.id == member.id for actor in world.actors):
                continue
            world.actors.append(ExplorationActor(
                id=member.id,
                name=member.name,
                position=Vec2(world.width / 2, world.height / 2),
                radius=28.0,
                sprite_key=member.metadata.get("sprite_key", member.id),
            ))
        return world

    def create_dungeon_floor(self, game: "MysteryGame", floor_number: int):
        if self.dungeon_definition is None:
            raise RuntimeError("No dungeon is selected.")
        return self.dungeon_definition.build_floor(
            floor_number,
            game.rng,
            lambda enemy_id, identifier: self.project_registry.make_enemy(enemy_id, identifier),
            self.project_registry.item,
            enemy_modifier=self.project_registry.apply_spawn_modifiers,
        )

    def on_dungeon_result(
        self,
        game: "MysteryGame",
        result: DungeonResult,
        *,
        lost_money: int = 0,
        lost_items: list[str] | None = None,
    ) -> None:
        # Dungeon-result stories can reference these values through normal story
        # variable substitution, keeping result handling data-driven.
        game.state.story.variables["dungeon_result"] = result.name.lower()
        game.state.story.variables["dungeon_lost_money"] = lost_money
        game.state.story.variables["dungeon_lost_items"] = (
            ", ".join(lost_items or []) if lost_items else "nothing from the bag"
        )

        story_id = self.project_registry.game_settings.dungeon_result_stories.get(result.name.lower())
        if story_id:
            game.run_story(story_id)
        else:
            game.add_message(result.name.replace("_", " ").title())


def build_project_game(project_root: Path):
    from mystery_engine.core.game import MysteryGame
    return MysteryGame(ProjectGameDefinition(project_root))
