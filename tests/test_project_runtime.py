from __future__ import annotations

from types import SimpleNamespace

from mystery_engine.project import (
    GameSettingsData,
    PawnDefinitionData,
    PlayableCharacterDefinitionData,
    ProjectRegistry,
    TerrainDefinitionData,
)
from mystery_engine.core import Direction, DungeonResult, SaveManager, StoryState
from mystery_engine.project_runtime import ProjectGameDefinition, SYSTEM_WORLD_ASSETS, build_project_game
from mystery_engine.story import ExplorationSceneData, SceneObjectData, SceneTriggerData, save_exploration_scene


def test_generic_project_runtime_builds_state_and_scene(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Standalone Game")
    registry.save_pawn(PawnDefinitionData(
        id="hero_pawn",
        name="Hero",
        sprite_key="hero",
        portrait_key=None,
    ))
    registry.save_character(PlayableCharacterDefinitionData(
        id="hero",
        pawn_id="hero_pawn",
        max_hp=30,
        attack=5,
        defense=3,
    ))
    registry.save_terrain(TerrainDefinitionData(
        id="lava",
        name="Lava",
        mode="single",
        blocked=True,
        fallback_color="#ff5500",
    ))

    scene = ExplorationSceneData.blank("start", 6, 5)
    scene.terrain[1][1] = "lava"
    scene.background_key = "backdrop"
    path = registry.scene_dir / "start.json"
    save_exploration_scene(scene, path)

    registry.save_game_settings(GameSettingsData(
        title="Standalone Game",
        starting_scene="start",
        starting_party=("hero",),
        leader="hero",
    ))

    definition = ProjectGameDefinition(registry.game_root)
    state = definition.create_state()
    fake_game = SimpleNamespace(
        state=state,
        add_message=lambda *_: None,
        change_exploration_scene=lambda *_: None,
        run_story=lambda *_: None,
        enter_dungeon=lambda *_: None,
        open_item_storage=lambda: None,
        open_money_storage=lambda: None,
    )
    world = definition.create_exploration(fake_game)

    assert state.leader.name == "Hero"
    assert world.actor("hero").name == "Hero"
    assert "lava" in world.blocked_terrain
    assert world.background_key == "backdrop"
    assert world.terrain_styles["lava"]["fallback_color"] == "#ff5500"


def test_system_assets_include_editor_primitives():
    assert SYSTEM_WORLD_ASSETS.get("scene_door").category == "portal"
    assert SYSTEM_WORLD_ASSETS.get("dungeon_entrance").category == "dungeon"
    assert SYSTEM_WORLD_ASSETS.get("story_marker").category == "marker"
    assert SYSTEM_WORLD_ASSETS.get("item_storage").action_id == "storage.items"
    assert SYSTEM_WORLD_ASSETS.get("money_storage").action_id == "storage.money"



def test_generic_dungeon_result_fallback_uses_enum_name(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Standalone Game")
    definition = ProjectGameDefinition(registry.game_root)
    messages: list[str] = []
    game = SimpleNamespace(
        state=SimpleNamespace(story=StoryState()),
        add_message=messages.append,
        run_story=lambda *_: None,
    )

    definition.on_dungeon_result(game, DungeonResult.SUCCESS)
    definition.on_dungeon_result(game, DungeonResult.DEFEAT)
    definition.on_dungeon_result(game, DungeonResult.ABANDONED)

    assert messages == ["Success", "Defeat", "Abandoned"]


def test_generic_dungeon_result_prefers_configured_story(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Standalone Game")
    registry.save_game_settings(GameSettingsData(
        title="Standalone Game",
        dungeon_result_stories={"success": "victory_scene"},
    ))
    definition = ProjectGameDefinition(registry.game_root)
    stories: list[str] = []
    messages: list[str] = []
    game = SimpleNamespace(
        state=SimpleNamespace(story=StoryState()),
        add_message=messages.append,
        run_story=stories.append,
    )

    definition.on_dungeon_result(
        game,
        DungeonResult.SUCCESS,
        lost_money=17,
        lost_items=["Field Salve", "Throwing Stone"],
    )

    assert stories == ["victory_scene"]
    assert messages == []
    assert game.state.story.variables["dungeon_result"] == "success"
    assert game.state.story.variables["dungeon_lost_money"] == 17
    assert game.state.story.variables["dungeon_lost_items"] == "Field Salve, Throwing Stone"



def test_example_project_configures_data_driven_dungeon_result_stories():
    registry = ProjectRegistry.load(
        __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    )
    configured = registry.game_settings.dungeon_result_stories
    assert configured == {
        "success": "test_dungeon_success",
        "defeat": "test_dungeon_defeat",
        "abandoned": "test_dungeon_abandoned",
    }

    success = registry.load_story("test_dungeon_success")
    mark_complete = success.nodes["mark_complete"]
    assert mark_complete["type"] == "effect"
    assert {
        (effect["name"], effect["value"])
        for effect in mark_complete["effects"]
        if effect["type"] == "set_flag"
    } == {
        ("completed_test_dungeon", True),
        ("failed_test_dungeon", False),
    }

    defeat = registry.load_story("test_dungeon_defeat")
    line = defeat.nodes["dialogue"]["lines"][1]["text"]
    assert "{dungeon_lost_money}" in line
    assert "{dungeon_lost_items}" in line


def test_item_storage_transfers_single_items_and_whole_stacks():
    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    salve = game.definition.project_registry.item("field_salve")
    game.state.bag.stacks.clear()
    game.state.storage.stacks.clear()
    game.state.bag.add(salve, 3)

    game._transfer_storage_item("bag", "field_salve", 1)
    assert game.state.bag.stacks[0].quantity == 2
    assert game.state.storage.stacks[0].quantity == 1

    game._transfer_storage_item("bag", "field_salve", None)
    assert not game.state.bag.stacks
    assert game.state.storage.stacks[0].quantity == 3

    game._transfer_storage_item("storage", "field_salve", None)
    assert game.state.bag.stacks[0].quantity == 3
    assert not game.state.storage.stacks


def test_item_storage_does_not_remove_item_when_destination_is_full():
    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    salve = game.definition.project_registry.item("field_salve")
    stone = game.definition.project_registry.item("throwing_stone")
    game.state.bag.stacks.clear()
    game.state.storage.stacks.clear()
    game.state.storage.capacity = 1
    game.state.bag.add(salve, 2)
    game.state.storage.add(stone, 1)

    game._transfer_storage_item("bag", "field_salve", 1)

    assert game.state.bag.stacks[0].quantity == 2
    assert game.state.storage.stacks[0].item.id == "throwing_stone"


def test_money_storage_moves_between_carried_and_stored_balances():
    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    game.state.wallet.carried = 275
    game.state.wallet.stored = 40

    game._transfer_storage_money(True, 100)
    assert game.state.wallet.carried == 175
    assert game.state.wallet.stored == 140

    game._transfer_storage_money(False, 90)
    assert game.state.wallet.carried == 265
    assert game.state.wallet.stored == 50


def test_save_roundtrip_restores_world_location_and_scene_state(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Persistent Game")
    registry.save_pawn(PawnDefinitionData(
        id="hero_pawn",
        name="Hero",
        sprite_key="hero",
        portrait_key=None,
    ))
    registry.save_pawn(PawnDefinitionData(
        id="npc",
        name="NPC",
        sprite_key="npc",
        portrait_key=None,
    ))
    registry.save_character(PlayableCharacterDefinitionData(
        id="hero",
        pawn_id="hero_pawn",
        max_hp=30,
        attack=5,
        defense=3,
    ))

    scene = ExplorationSceneData.blank("start", 8, 8)
    scene.objects.extend([
        SceneObjectData("npc_instance", "npc", 160, 180),
        SceneObjectData("storage_box", "item_storage", 260, 180),
    ])
    save_exploration_scene(scene, registry.scene_dir / "start.json")
    registry.save_game_settings(GameSettingsData(
        title="Persistent Game",
        starting_scene="start",
        starting_party=("hero",),
        leader="hero",
        bag_capacity=7,
        storage_capacity=13,
    ))

    game = build_project_game(registry.game_root)
    game.exploration = game.definition.create_exploration(game)
    hero = game.exploration.actor("hero")
    hero.position.x = 333.5
    hero.position.y = 444.25
    hero.facing = Direction.E

    npc = game.exploration.actor("npc_instance")
    npc.position.x = 512
    npc.position.y = 288
    npc.facing = Direction.W
    npc.enabled = False
    npc.sprite_key = "npc_changed"

    storage = next(item for item in game.exploration.interactables if item.id == "storage_box")
    storage.enabled = False
    game._capture_exploration_state()

    save_path = tmp_path / "save.json"
    SaveManager().dump(game.state, save_path)
    loaded_state = game.definition.load_state(SaveManager().load_raw(save_path))

    assert loaded_state.world.current_scene == "start"
    assert loaded_state.bag.capacity == 7
    assert loaded_state.storage.capacity == 13
    assert loaded_state.world.party_positions["hero"].x == 333.5
    assert loaded_state.world.party_positions["hero"].facing == "E"

    fake_game = SimpleNamespace(
        state=loaded_state,
        add_message=lambda *_: None,
        change_exploration_scene=lambda *_: None,
        run_story=lambda *_: None,
        enter_dungeon=lambda *_: None,
        open_item_storage=lambda: None,
        open_money_storage=lambda: None,
    )
    restored = game.definition.create_exploration(fake_game)
    restored_hero = restored.actor("hero")
    restored_npc = restored.actor("npc_instance")
    restored_storage = next(item for item in restored.interactables if item.id == "storage_box")

    assert (restored_hero.position.x, restored_hero.position.y) == (333.5, 444.25)
    assert restored_hero.facing is Direction.E
    assert (restored_npc.position.x, restored_npc.position.y) == (512, 288)
    assert restored_npc.facing is Direction.W
    assert restored_npc.enabled is False
    assert restored_npc.sprite_key == "npc_changed"
    assert restored_storage.enabled is False


def test_scene_transition_captures_scene_state_before_leaving(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Transition Game")
    registry.save_pawn(PawnDefinitionData(
        id="hero_pawn",
        name="Hero",
        sprite_key="hero",
        portrait_key=None,
    ))
    registry.save_character(PlayableCharacterDefinitionData(
        id="hero",
        pawn_id="hero_pawn",
        max_hp=30,
        attack=5,
        defense=3,
    ))
    first = ExplorationSceneData.blank("first", 6, 5)
    first.objects.append(SceneObjectData("storage_box", "item_storage", 160, 160))
    second = ExplorationSceneData.blank("second", 6, 5)
    save_exploration_scene(first, registry.scene_dir / "first.json")
    save_exploration_scene(second, registry.scene_dir / "second.json")
    registry.save_game_settings(GameSettingsData(
        title="Transition Game",
        starting_scene="first",
        starting_party=("hero",),
        leader="hero",
    ))

    game = build_project_game(registry.game_root)
    game.exploration = game.definition.create_exploration(game)
    item = next(entry for entry in game.exploration.interactables if entry.id == "storage_box")
    item.enabled = False

    game.change_exploration_scene(registry.scene_dir / "second.json")

    assert game.state.world.current_scene == "second"
    assert game.state.world.scenes["first"].objects["storage_box"].enabled is False


def test_legacy_save_without_world_data_still_loads(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Legacy Game")
    registry.save_pawn(PawnDefinitionData(
        id="hero_pawn",
        name="Hero",
        sprite_key="hero",
        portrait_key=None,
    ))
    registry.save_character(PlayableCharacterDefinitionData(
        id="hero",
        pawn_id="hero_pawn",
        max_hp=30,
        attack=5,
        defense=3,
    ))
    registry.save_game_settings(GameSettingsData(
        title="Legacy Game",
        starting_party=("hero",),
        leader="hero",
    ))
    definition = ProjectGameDefinition(registry.game_root)
    payload = {
        "game_id": registry.project_id,
        "game_version": "0.1.0",
        "characters": [{"id": "hero", "hp": 19, "resources": {}, "skill_charges": {}}],
        "wallet": {"carried": 12, "stored": 34},
        "bag": [],
        "storage": [],
        "story": {"flags": {"legacy": True}, "variables": {}},
    }

    state = definition.load_state(payload)

    assert state.leader.stats.current_hp == 19
    assert state.wallet.carried == 12
    assert state.story.flag("legacy")
    assert state.world.current_scene is None


def test_game_load_snapshot_replaces_runtime_state_and_restores_location(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Load Game")
    registry.save_pawn(PawnDefinitionData(
        id="hero_pawn",
        name="Hero",
        sprite_key="hero",
        portrait_key=None,
    ))
    registry.save_character(PlayableCharacterDefinitionData(
        id="hero",
        pawn_id="hero_pawn",
        max_hp=30,
        attack=5,
        defense=3,
    ))
    scene = ExplorationSceneData.blank("start", 8, 8)
    save_exploration_scene(scene, registry.scene_dir / "start.json")
    registry.save_game_settings(GameSettingsData(
        title="Load Game",
        starting_scene="start",
        starting_party=("hero",),
        leader="hero",
    ))

    game = build_project_game(registry.game_root)
    game.exploration = game.definition.create_exploration(game)
    game._play_event_sfx = lambda *_args, **_kwargs: None
    game._sync_exploration_music = lambda: None
    hero = game.exploration.actor("hero")
    hero.position.x = 222
    hero.position.y = 333
    hero.facing = Direction.N
    game.state.wallet.carried = 77

    save_path = tmp_path / "save.json"
    assert game.save_snapshot(save_path) == save_path

    hero.position.x = 10
    hero.position.y = 20
    game.state.wallet.carried = 0

    assert game.load_snapshot(save_path) is True
    restored = game.exploration.actor("hero")
    assert (restored.position.x, restored.position.y) == (222, 333)
    assert restored.facing is Direction.N
    assert game.state.wallet.carried == 77


def _dungeon_signature(game):
    floor = game.dungeon.floor
    return {
        "floor_number": game.dungeon.floor_number,
        "tiles": [[(tile.kind.name, tile.walkable, tile.blocks_sight, tile.terrain) for tile in row] for row in floor.tiles],
        "stairs": (floor.stairs_pos.x, floor.stairs_pos.y) if floor.stairs_pos else None,
        "spawn": (floor.player_spawn.x, floor.player_spawn.y) if floor.player_spawn else None,
        "actors": sorted(
            (
                actor.id,
                actor.metadata.get("definition_id"),
                actor.name,
                actor.hostile,
                (actor.grid_pos.x, actor.grid_pos.y) if actor.grid_pos else None,
                actor.facing.name,
                actor.incapacitated,
                actor.stats.max_hp,
                actor.stats.current_hp,
                actor.stats.attack,
                actor.stats.defense,
                tuple(sorted(actor.resources.items())),
                tuple(sorted(actor.resistances.items())),
                tuple((skill.definition.id, skill.charges) for skill in actor.skills),
            )
            for actor in floor.entities
        ),
        "items": sorted((item.item.id, item.pos.x, item.pos.y) for item in floor.ground_items),
        "discovered": sorted((pos.x, pos.y) for pos in game.dungeon.turns.memory.discovered),
        "visible": sorted((pos.x, pos.y) for pos in game.dungeon.turns.memory.visible),
        "turn_count": game.dungeon.turns.turn_count,
    }


def test_dungeon_save_load_restores_exact_generated_session(tmp_path):
    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    game.exploration = game.definition.create_exploration(game)
    game._play_event_sfx = lambda *_args, **_kwargs: None
    game.audio.play_scene = lambda *_args, **_kwargs: None
    game._start_floor(1)
    game.mode = __import__("mystery_engine.core", fromlist=["GameMode"]).GameMode.DUNGEON

    game.dungeon.turns.turn_count = 17
    enemy = next(actor for actor in game.dungeon.floor.entities if actor.hostile)
    enemy.stats.current_hp = max(0, enemy.stats.current_hp - 3)
    enemy.facing = Direction.W
    if game.dungeon.floor.ground_items:
        game.dungeon.floor.ground_items.pop()
    game.dungeon.turns.memory.discovered.add(
        __import__("mystery_engine.core", fromlist=["GridPos"]).GridPos(0, 0)
    )

    expected = _dungeon_signature(game)
    save_path = tmp_path / "dungeon-save.json"
    assert game.save_snapshot(save_path) == save_path

    # Mutate the live session heavily after saving.
    game.dungeon.floor.tiles[0][0] = __import__("mystery_engine.dungeon.tiles", fromlist=["FLOOR"]).FLOOR
    game.dungeon.turns.turn_count = 999
    enemy.stats.current_hp = 1
    game.dungeon.floor.ground_items.clear()

    assert game.load_snapshot(save_path) is True
    assert game.mode.name == "DUNGEON"
    assert _dungeon_signature(game) == expected


def test_dungeon_load_does_not_regenerate_floor(tmp_path):
    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    game.exploration = game.definition.create_exploration(game)
    game._play_event_sfx = lambda *_args, **_kwargs: None
    game.audio.play_scene = lambda *_args, **_kwargs: None
    game._start_floor(1)
    game.mode = __import__("mystery_engine.core", fromlist=["GameMode"]).GameMode.DUNGEON

    save_path = tmp_path / "dungeon-save.json"
    assert game.save_snapshot(save_path) == save_path
    original_generator = game.definition.create_dungeon_floor
    game.definition.create_dungeon_floor = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("dungeon generation must not run while loading")
    )
    try:
        assert game.load_snapshot(save_path) is True
    finally:
        game.definition.create_dungeon_floor = original_generator


def test_dungeon_save_restores_rng_checkpoint(tmp_path):
    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    game.exploration = game.definition.create_exploration(game)
    game._play_event_sfx = lambda *_args, **_kwargs: None
    game.audio.play_scene = lambda *_args, **_kwargs: None
    game._start_floor(1)
    game.mode = __import__("mystery_engine.core", fromlist=["GameMode"]).GameMode.DUNGEON

    save_path = tmp_path / "dungeon-save.json"
    assert game.save_snapshot(save_path) == save_path
    expected_next = [game.rng.random() for _ in range(5)]

    assert game.load_snapshot(save_path) is True
    actual_next = [game.rng.random() for _ in range(5)]
    assert actual_next == expected_next


def _build_trigger_test_game(tmp_path, triggers):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Trigger Game")
    registry.save_pawn(PawnDefinitionData(
        id="hero_pawn",
        name="Hero",
        sprite_key="hero",
        portrait_key=None,
    ))
    registry.save_character(PlayableCharacterDefinitionData(
        id="hero",
        pawn_id="hero_pawn",
        max_hp=30,
        attack=5,
        defense=3,
    ))
    scene = ExplorationSceneData.blank("start", 10, 8)
    scene.triggers.extend(triggers)
    save_exploration_scene(scene, registry.scene_dir / "start.json")
    registry.save_game_settings(GameSettingsData(
        title="Trigger Game",
        starting_scene="start",
        starting_party=("hero",),
        leader="hero",
    ))
    game = build_project_game(registry.game_root)
    game.exploration = game.definition.create_exploration(game)
    return game


def test_scene_enter_trigger_fires_once_and_persists_via_story_flag(tmp_path):
    game = _build_trigger_test_game(tmp_path, [
        SceneTriggerData("arrival", "on_scene_enter", "intro", once=True),
    ])
    fired = []
    game.run_story = lambda story, entry="default": fired.append((story, entry))

    game._process_scene_enter_triggers()
    game._process_scene_enter_triggers()

    assert fired == [("intro", "default")]
    assert game.state.story.flag("__trigger_once__:start:arrival") is True

    # A new visit should still not replay a persistent once trigger.
    game._scene_entry_fired.clear()
    game._process_scene_enter_triggers()
    assert fired == [("intro", "default")]


def test_repeatable_scene_enter_trigger_fires_once_per_visit(tmp_path):
    game = _build_trigger_test_game(tmp_path, [
        SceneTriggerData("arrival", "on_scene_enter", "intro", once=False),
    ])
    fired = []
    game.run_story = lambda story, entry="default": fired.append((story, entry))

    game._process_scene_enter_triggers()
    game._process_scene_enter_triggers()
    assert fired == [("intro", "default")]

    game._scene_entry_fired.clear()
    game._process_scene_enter_triggers()
    assert fired == [("intro", "default"), ("intro", "default")]


def test_scene_trigger_condition_is_checked_on_entry(tmp_path):
    game = _build_trigger_test_game(tmp_path, [
        SceneTriggerData(
            "conditional",
            "on_scene_enter",
            "intro",
            once=False,
            condition={"kind": "flag", "name": "ready", "op": "==", "value": True},
        ),
    ])
    fired = []
    game.run_story = lambda story, entry="default": fired.append((story, entry))

    game._process_scene_enter_triggers()
    game.state.story.set_flag("ready", True)
    game._process_scene_enter_triggers()
    assert fired == []

    game._scene_entry_fired.clear()
    game._process_scene_enter_triggers()
    assert fired == [("intro", "default")]


def test_region_trigger_fires_on_outside_to_inside_edge(tmp_path):
    game = _build_trigger_test_game(tmp_path, [
        SceneTriggerData(
            "threshold",
            "on_region_enter",
            "threshold_story",
            once=False,
            x=200,
            y=200,
            w=100,
            h=100,
        ),
    ])
    fired = []
    game.run_story = lambda story, entry="default": fired.append((story, entry))
    leader = game.exploration.actor("hero")

    leader.position.x, leader.position.y = 100, 100
    game._process_region_triggers()
    leader.position.x, leader.position.y = 225, 225
    game._process_region_triggers()
    game._process_region_triggers()
    assert fired == [("threshold_story", "default")]

    leader.position.x, leader.position.y = 100, 100
    game._process_region_triggers()
    leader.position.x, leader.position.y = 250, 250
    game._process_region_triggers()
    assert fired == [("threshold_story", "default"), ("threshold_story", "default")]


def test_once_region_trigger_does_not_refire_after_reentry(tmp_path):
    game = _build_trigger_test_game(tmp_path, [
        SceneTriggerData(
            "threshold",
            "on_region_enter",
            "threshold_story",
            once=True,
            x=200,
            y=200,
            w=100,
            h=100,
        ),
    ])
    fired = []
    game.run_story = lambda story, entry="default": fired.append((story, entry))
    leader = game.exploration.actor("hero")

    for pos in ((100, 100), (225, 225), (100, 100), (225, 225)):
        leader.position.x, leader.position.y = pos
        game._process_region_triggers()

    assert fired == [("threshold_story", "default")]
    assert game.state.story.flag("__trigger_once__:start:threshold") is True


def test_generic_gameplay_story_actions_modify_inventory_money_and_party():
    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    action = game.story_actions

    game.state.bag.stacks.clear()
    game.state.storage.stacks.clear()
    game.state.wallet.carried = 25
    game.state.wallet.stored = 10

    action("give_item", {"item": "field_salve", "quantity": 2, "location": "bag"})
    assert next(stack for stack in game.state.bag.stacks if stack.item.id == "field_salve").quantity == 2

    action("give_item", {"item": "throwing_stone", "quantity": 3, "location": "storage"})
    assert next(stack for stack in game.state.storage.stacks if stack.item.id == "throwing_stone").quantity == 3

    action("remove_item", {"item": "field_salve", "quantity": 1, "location": "bag"})
    assert next(stack for stack in game.state.bag.stacks if stack.item.id == "field_salve").quantity == 1

    action("give_money", {"amount": 75, "location": "carried"})
    action("give_money", {"amount": 40, "location": "stored"})
    assert game.state.wallet.carried == 100
    assert game.state.wallet.stored == 50

    action("remove_money", {"amount": 30, "location": "carried"})
    action("remove_money", {"amount": 20, "location": "stored"})
    assert game.state.wallet.carried == 70
    assert game.state.wallet.stored == 30

    member = game.state.party[0]
    member.stats.current_hp = 1
    for skill in member.skills:
        if skill.charges is not None:
            skill.charges = 0

    action("heal_party", {"character": member.id, "amount": 5})
    assert member.stats.current_hp == min(member.stats.max_hp, 6)

    action("restore_skill_charges", {"character": member.id, "amount": "full"})
    for skill in member.skills:
        if skill.definition.max_charges is not None:
            assert skill.charges == skill.definition.max_charges

    member.stats.current_hp = 1
    action("restore_party", {"character": member.id})
    assert member.stats.current_hp == member.stats.max_hp


def test_gameplay_story_conditions_query_inventory_money_party_and_hp():
    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    game.state.bag.stacks.clear()
    game.state.storage.stacks.clear()
    game.state.wallet.carried = 125
    game.state.wallet.stored = 400

    game.story_actions("give_item", {"item": "field_salve", "quantity": 2, "location": "bag"})
    game.story_actions("give_item", {"item": "field_salve", "quantity": 3, "location": "storage"})
    member = game.state.party[0]
    member.stats.current_hp = max(1, member.stats.max_hp // 2)

    assert game.evaluate_gameplay_condition({
        "kind": "has_item", "item": "field_salve", "location": "bag", "value": 2
    }) is True
    assert game.evaluate_gameplay_condition({
        "kind": "item_count", "item": "field_salve", "location": "either", "op": "==", "value": 5
    }) is True
    assert game.evaluate_gameplay_condition({
        "kind": "has_money", "location": "total", "value": 500
    }) is True
    assert game.evaluate_gameplay_condition({
        "kind": "party_contains", "character": member.id
    }) is True
    assert game.evaluate_gameplay_condition({
        "kind": "party_hp", "character": member.id, "mode": "missing", "op": ">", "value": 0
    }) is True


def test_gameplay_conditions_work_inside_boolean_story_conditions():
    from mystery_engine.story import evaluate_condition

    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    game.state.bag.stacks.clear()
    game.story_actions("give_item", {"item": "field_salve", "quantity": 1})

    condition = {
        "all": [
            {"kind": "has_item", "item": "field_salve", "value": 1},
            {"not": {"kind": "has_money", "location": "carried", "value": 999999}},
        ]
    }
    assert evaluate_condition(condition, game.state.story, game.evaluate_gameplay_condition) is True


def test_pawn_animation_sets_roundtrip_and_reach_runtime_actor(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Animation Game")
    animations = {
        "idle": {
            "path": "characters/hero_idle.png",
            "columns": 2,
            "rows": 4,
            "directions": ["n", "e", "s", "w"],
            "frames": [0, 1],
            "fps": 4.0,
            "loop": True,
        },
        "wave": {
            "path": "characters/hero_wave.png",
            "columns": 3,
            "rows": 1,
            "directions": ["s"],
            "frames": [0, 1, 2],
            "fps": 6.0,
            "loop": False,
        },
    }
    registry.save_pawn(PawnDefinitionData(
        id="hero_pawn",
        name="Hero",
        sprite_key="hero",
        animations=animations,
    ))
    registry.save_character(PlayableCharacterDefinitionData(
        id="hero",
        pawn_id="hero_pawn",
        max_hp=20,
        attack=4,
        defense=3,
    ))
    scene = ExplorationSceneData.blank("start", 6, 6)
    save_exploration_scene(scene, registry.scene_dir / "start.json")
    registry.save_game_settings(GameSettingsData(
        title="Animation Game",
        starting_scene="start",
        starting_party=("hero",),
        leader="hero",
    ))

    reloaded = ProjectRegistry.load(registry.game_root)
    assert reloaded.pawn("hero_pawn").animations["wave"]["frames"] == [0, 1, 2]

    game = build_project_game(registry.game_root)
    world = game.definition.create_exploration(game)
    actor = world.actor("hero")
    assert set(actor.animations) == {"idle", "wave"}


def test_actor_animation_auto_walk_and_one_shot_completion():
    from mystery_engine.core import Vec2
    from mystery_engine.story import ExplorationActor

    actor = ExplorationActor(
        "actor", "Actor", Vec2(10, 10),
        animations={
            "idle": {"columns": 1, "frames": [0], "fps": 4.0, "loop": True},
            "walk": {"columns": 2, "frames": [0, 1], "fps": 8.0, "loop": True},
            "wave": {"columns": 2, "frames": [0, 1], "fps": 4.0, "loop": False},
        },
    )
    actor.update_animation(0.016)
    actor.position.x += 4
    actor.update_animation(0.016)
    assert actor.animation_name == "walk"

    assert actor.play_animation("wave", loop=False, return_to_idle=True)
    before = actor.animation_completion_count
    actor.update_animation(0.6)
    assert actor.animation_completion_count == before + 1
    assert actor.animation_name == "idle"
    assert actor.animation_override is False


def test_story_play_animation_waits_for_one_shot_completion(tmp_path):
    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    game.exploration = game.definition.create_exploration(game)
    actor = game.exploration.actor(game.state.leader.id)
    actor.animations = {
        "cast": {"columns": 2, "frames": [0, 1], "fps": 4.0, "loop": False},
        "idle": {"columns": 1, "frames": [0], "fps": 4.0, "loop": True},
    }

    handle = game.story_actions("play_animation", {
        "actor": actor.id,
        "animation": "cast",
        "loop": False,
        "return_to_idle": True,
    })
    assert handle.update(0.0) is False
    actor.update_animation(0.6)
    assert handle.update(0.0) is True
    assert actor.animation_name == "idle"


def test_gameplay_story_conditions_survive_save_load_runtime_rebuild(tmp_path):
    from mystery_engine.story import evaluate_condition

    game_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "test_game"
    game = build_project_game(game_root)
    game.exploration = game.definition.create_exploration(game)
    game._play_event_sfx = lambda *_args, **_kwargs: None
    game._sync_exploration_music = lambda: None
    game.story_actions("give_item", {"item": "field_salve", "quantity": 1, "location": "bag"})

    save_path = tmp_path / "condition-save.json"
    assert game.save_snapshot(save_path) == save_path
    assert game.load_snapshot(save_path) is True

    resolver = game.story_runner.context.evaluate_gameplay_condition
    assert callable(resolver)
    assert evaluate_condition(
        {"kind": "has_item", "item": "field_salve", "location": "bag", "value": 1},
        game.state.story,
        resolver,
    ) is True
