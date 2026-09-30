from __future__ import annotations

from pathlib import Path
import os
from typing import TYPE_CHECKING

from mystery_engine.core import (
    AITactic,
    Direction,
    DungeonActorState,
    DungeonGroundItemState,
    DungeonResult,
    DungeonState,
    PersistentGameState,
    PersistentWorldState,
    SceneActorState,
    SceneObjectState,
    SceneState,
    StoryState,
    Wallet,
)
from mystery_engine.core.inventory import Inventory
from mystery_engine.dungeon.floor import DungeonFloor, GroundItem
from mystery_engine.dungeon.tiles import Tile, TileKind
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

    def load_state(self, payload: dict) -> PersistentGameState:
        """Reconstruct project-backed runtime objects from stable IDs in a save."""
        if str(payload.get("game_id", "")) != self.game_id:
            raise ValueError(f"Save belongs to {payload.get('game_id')!r}, not {self.game_id!r}.")

        settings = self.project_registry.game_settings
        character_rows = list(payload.get("characters") or [])
        if not character_rows:
            # Legacy/incomplete saves fall back to the configured starting party.
            state = self.create_state()
        else:
            party = []
            for index, row in enumerate(character_rows):
                character_id = str(row.get("id", ""))
                if character_id not in self.project_registry.characters:
                    raise ValueError(f"Save references unknown character: {character_id}")
                leader = bool(row.get("leader", False))
                character = self.project_registry.make_character(character_id, leader=leader)
                character.stats.current_hp = max(0, min(character.stats.max_hp, int(row.get("hp", character.stats.max_hp))))
                character.resources = {
                    str(k): int(v) for k, v in dict(row.get("resources") or character.resources).items()
                }
                tactic = row.get("ai_tactic")
                if tactic:
                    try:
                        character.ai_tactic = AITactic(str(tactic))
                    except ValueError:
                        pass
                saved_charges = dict(row.get("skill_charges") or {})
                for skill in character.skills:
                    if skill.definition.id in saved_charges:
                        value = saved_charges[skill.definition.id]
                        skill.charges = None if value is None else max(0, int(value))
                party.append(character)

            if not any(member.leader for member in party):
                leader_id = settings.leader or (party[0].id if party else "")
                for member in party:
                    member.leader = member.id == leader_id
                if party and not any(member.leader for member in party):
                    party[0].leader = True

            capacities = dict(payload.get("inventory_capacities") or {})
            bag = Inventory(capacity=max(1, int(capacities.get("bag", settings.bag_capacity))))
            for row in payload.get("bag", []):
                item_id = str(row.get("item_id", ""))
                if item_id in self.project_registry.items:
                    bag.add(self.project_registry.item(item_id), max(0, int(row.get("quantity", 0))))

            storage = Inventory(capacity=max(1, int(capacities.get("storage", settings.storage_capacity))))
            for row in payload.get("storage", []):
                item_id = str(row.get("item_id", ""))
                if item_id in self.project_registry.items:
                    storage.add(self.project_registry.item(item_id), max(0, int(row.get("quantity", 0))))

            wallet_data = dict(payload.get("wallet") or {})
            story_data = dict(payload.get("story") or {})
            state = PersistentGameState(
                game_id=self.game_id,
                game_version=str(payload.get("game_version") or self.game_version),
                party=party,
                bag=bag,
                storage=storage,
                wallet=Wallet(
                    carried=max(0, int(wallet_data.get("carried", 0))),
                    stored=max(0, int(wallet_data.get("stored", 0))),
                ),
                story=StoryState(
                    flags={str(k): bool(v) for k, v in dict(story_data.get("flags") or {}).items()},
                    variables=dict(story_data.get("variables") or {}),
                ),
            )

        world_data = dict(payload.get("world") or {})
        state.world = PersistentWorldState(
            current_scene=(str(world_data["current_scene"]) if world_data.get("current_scene") else None),
            party_positions={
                str(actor_id): self._load_scene_actor_state(actor_data)
                for actor_id, actor_data in dict(world_data.get("party_positions") or {}).items()
            },
            scenes={
                str(scene_id): SceneState(
                    actors={
                        str(actor_id): self._load_scene_actor_state(actor_data)
                        for actor_id, actor_data in dict(scene_data.get("actors") or {}).items()
                    },
                    objects={
                        str(object_id): SceneObjectState(enabled=bool(object_data.get("enabled", True)))
                        for object_id, object_data in dict(scene_data.get("objects") or {}).items()
                    },
                )
                for scene_id, scene_data in dict(world_data.get("scenes") or {}).items()
            },
        )

        dungeon_data = payload.get("dungeon")
        state.dungeon = self._load_dungeon_state(dungeon_data) if isinstance(dungeon_data, dict) else None
        return state

    @staticmethod
    def _load_dungeon_actor_state(data: dict) -> DungeonActorState:
        position = data.get("position")
        stats = dict(data.get("stats") or {})
        return DungeonActorState(
            id=str(data.get("id", "")),
            definition_id=(str(data["definition_id"]) if data.get("definition_id") else None),
            name=str(data.get("name", data.get("id", ""))),
            hostile=bool(data.get("hostile", False)),
            x=(int(position[0]) if isinstance(position, list) and len(position) >= 2 else None),
            y=(int(position[1]) if isinstance(position, list) and len(position) >= 2 else None),
            facing=str(data.get("facing", "S")).upper(),
            incapacitated=bool(data.get("incapacitated", False)),
            max_hp=max(1, int(stats.get("max_hp", 1))),
            current_hp=max(0, int(stats.get("current_hp", stats.get("max_hp", 1)))),
            attack=max(0, int(stats.get("attack", 0))),
            defense=max(0, int(stats.get("defense", 0))),
            resources={str(k): int(v) for k, v in dict(data.get("resources") or {}).items()},
            resistances={str(k): float(v) for k, v in dict(data.get("resistances") or {}).items()},
            skill_charges={
                str(k): (None if v is None else max(0, int(v)))
                for k, v in dict(data.get("skill_charges") or {}).items()
            },
            skill_ids=[str(v) for v in data.get("skill_ids", [])],
            metadata=dict(data.get("metadata") or {}),
        )

    @classmethod
    def _load_dungeon_state(cls, data: dict) -> DungeonState:
        memory = dict(data.get("memory") or {})
        player_spawn = data.get("player_spawn")
        stairs_pos = data.get("stairs_pos")
        return DungeonState(
            dungeon_id=str(data.get("dungeon_id", "")),
            floor_number=max(1, int(data.get("floor_number", 1))),
            width=max(1, int(data.get("width", 1))),
            height=max(1, int(data.get("height", 1))),
            tiles=[
                [dict(tile) for tile in row]
                for row in data.get("tiles", [])
            ],
            rooms=[[int(v) for v in room] for room in data.get("rooms", [])],
            player_spawn=(
                (int(player_spawn[0]), int(player_spawn[1]))
                if isinstance(player_spawn, list) and len(player_spawn) >= 2 else None
            ),
            stairs_pos=(
                (int(stairs_pos[0]), int(stairs_pos[1]))
                if isinstance(stairs_pos, list) and len(stairs_pos) >= 2 else None
            ),
            tileset=str(data.get("tileset", "dungeon")),
            music=(str(data["music"]) if data.get("music") else None),
            music_volume=float(data.get("music_volume", 1.0)),
            dungeon_name=str(data.get("dungeon_name", "Dungeon")),
            generation_profile=str(data.get("generation_profile", "default")),
            actors=[cls._load_dungeon_actor_state(row) for row in data.get("actors", [])],
            ground_items=[
                DungeonGroundItemState(
                    item_id=str(row.get("item_id", "")),
                    x=int(row.get("x", 0)),
                    y=int(row.get("y", 0)),
                )
                for row in data.get("ground_items", [])
            ],
            discovered=[
                (int(pos[0]), int(pos[1]))
                for pos in memory.get("discovered", [])
                if isinstance(pos, list) and len(pos) >= 2
            ],
            visible=[
                (int(pos[0]), int(pos[1]))
                for pos in memory.get("visible", [])
                if isinstance(pos, list) and len(pos) >= 2
            ],
            turn_count=max(0, int(data.get("turn_count", 0))),
            rng_state=data.get("rng_state"),
        )

    def restore_dungeon_floor(self, saved: DungeonState, party: list) -> DungeonFloor:
        """Rebuild an exact saved floor without consulting the dungeon RNG."""
        if saved.dungeon_id not in self.project_registry.dungeon_paths():
            raise ValueError(f"Save references unknown dungeon: {saved.dungeon_id}")
        self.select_dungeon(saved.dungeon_id)

        rows: list[list[Tile]] = []
        for y in range(saved.height):
            source_row = saved.tiles[y] if y < len(saved.tiles) else []
            row: list[Tile] = []
            for x in range(saved.width):
                raw = source_row[x] if x < len(source_row) else {}
                kind_name = str(raw.get("kind", "WALL")).upper()
                kind = TileKind.__members__.get(kind_name, TileKind.WALL)
                row.append(Tile(
                    kind=kind,
                    walkable=bool(raw.get("walkable", kind is not TileKind.WALL)),
                    blocks_sight=bool(raw.get("blocks_sight", kind is TileKind.WALL)),
                    terrain=str(raw.get("terrain", "normal")),
                ))
            rows.append(row)

        floor = DungeonFloor(
            width=saved.width,
            height=saved.height,
            tiles=rows,
            rooms=[tuple(room) for room in saved.rooms],
            player_spawn=(GridPos(*saved.player_spawn) if saved.player_spawn else None),
            stairs_pos=(GridPos(*saved.stairs_pos) if saved.stairs_pos else None),
            tileset=saved.tileset,
            music=saved.music,
            music_volume=saved.music_volume,
            dungeon_name=saved.dungeon_name,
            generation_profile=saved.generation_profile,
        )

        party_by_id = {member.id: member for member in party}
        for actor_state in saved.actors:
            if actor_state.id in party_by_id:
                actor = party_by_id[actor_state.id]
            else:
                if not actor_state.definition_id:
                    raise ValueError(f"Saved enemy {actor_state.id} has no definition ID.")
                actor = self.project_registry.make_enemy(actor_state.definition_id, actor_state.id)
                existing = {skill.definition.id for skill in actor.skills}
                for skill_id in actor_state.skill_ids:
                    if skill_id not in existing and skill_id in self.project_registry.attacks:
                        from mystery_engine.core import SkillRuntime
                        actor.skills.append(SkillRuntime.from_definition(self.project_registry.attack_skill(skill_id)))
                        existing.add(skill_id)

            actor.name = actor_state.name
            actor.hostile = actor_state.hostile
            actor.grid_pos = (
                GridPos(actor_state.x, actor_state.y)
                if actor_state.x is not None and actor_state.y is not None else None
            )
            actor.facing = getattr(Direction, actor_state.facing, Direction.S)
            actor.incapacitated = actor_state.incapacitated
            actor.stats.max_hp = actor_state.max_hp
            actor.stats.current_hp = min(actor_state.max_hp, actor_state.current_hp)
            actor.stats.attack = actor_state.attack
            actor.stats.defense = actor_state.defense
            actor.resources = dict(actor_state.resources)
            actor.resistances = dict(actor_state.resistances)
            actor.metadata = dict(actor_state.metadata)
            for skill in actor.skills:
                if skill.definition.id in actor_state.skill_charges:
                    skill.charges = actor_state.skill_charges[skill.definition.id]
            floor.entities.append(actor)

        for item in saved.ground_items:
            if item.item_id in self.project_registry.items:
                floor.ground_items.append(
                    GroundItem(self.project_registry.item(item.item_id), GridPos(item.x, item.y))
                )
        return floor

    @staticmethod
    def _load_scene_actor_state(data: dict) -> SceneActorState:
        return SceneActorState(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            facing=str(data.get("facing", "S")).upper(),
            enabled=bool(data.get("enabled", True)),
            sprite_key=(str(data["sprite_key"]) if data.get("sprite_key") is not None else None),
        )

    def create_exploration(self, game: "MysteryGame") -> ExplorationMap:
        override = os.environ.get("MYSTERY_SCENE_PATH")
        settings = self.project_registry.game_settings
        scenes = self.project_registry.scene_paths()
        saved_scene = game.state.world.current_scene
        if override:
            path = Path(override)
        elif saved_scene and saved_scene in scenes:
            path = scenes[saved_scene]
        elif settings.starting_scene:
            try:
                path = scenes[settings.starting_scene]
            except KeyError as exc:
                raise RuntimeError(f"Unknown starting scene: {settings.starting_scene}") from exc
        else:
            if not scenes:
                raise RuntimeError("Create a scene and choose it as the starting scene before running.")
            path = next(iter(scenes.values()))

        world = self.create_exploration_scene(game, path)
        restored_party = False
        if saved_scene == world.id and game.state.world.party_positions:
            for actor_id, saved in game.state.world.party_positions.items():
                actor = next((candidate for candidate in world.actors if candidate.id == actor_id), None)
                if actor is None:
                    continue
                actor.position.x, actor.position.y = saved.x, saved.y
                actor.facing = getattr(Direction, saved.facing, Direction.S)
                actor.enabled = saved.enabled
                if saved.sprite_key is not None:
                    actor.sprite_key = saved.sprite_key
                restored_party = True

        if not restored_party and settings.starting_marker:
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

        def unavailable_storage(kind: str):
            return lambda: game.add_message(f"{kind} storage is unavailable in this runtime.")

        system_interactions = {
            "storage.items": getattr(game, "open_item_storage", unavailable_storage("Item")),
            "storage.money": getattr(game, "open_money_storage", unavailable_storage("Money")),
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

        saved_scene_state = game.state.world.scenes.get(world.id)
        if saved_scene_state is not None:
            party_ids = {member.id for member in game.state.party}
            for actor_id, saved in saved_scene_state.actors.items():
                if actor_id in party_ids:
                    continue
                actor = next((candidate for candidate in world.actors if candidate.id == actor_id), None)
                if actor is None:
                    continue
                actor.position.x, actor.position.y = saved.x, saved.y
                actor.facing = getattr(Direction, saved.facing, Direction.S)
                actor.enabled = saved.enabled
                if saved.sprite_key is not None:
                    actor.sprite_key = saved.sprite_key
            for object_id, saved in saved_scene_state.objects.items():
                item = next((candidate for candidate in world.interactables if candidate.id == object_id), None)
                if item is not None:
                    item.enabled = saved.enabled
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
