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
from mystery_engine.story import ExplorationSceneData, SceneObjectData, save_exploration_scene


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

    assert game.state.world.current_scene == "first"
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
