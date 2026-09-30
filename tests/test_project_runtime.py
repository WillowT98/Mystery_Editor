from __future__ import annotations

from types import SimpleNamespace

from mystery_engine.project import (
    GameSettingsData,
    PawnDefinitionData,
    PlayableCharacterDefinitionData,
    ProjectRegistry,
    TerrainDefinitionData,
)
from mystery_engine.core import DungeonResult
from mystery_engine.project_runtime import ProjectGameDefinition, SYSTEM_WORLD_ASSETS
from mystery_engine.story import ExplorationSceneData, save_exploration_scene


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



def test_generic_dungeon_result_fallback_uses_enum_name(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Standalone Game")
    definition = ProjectGameDefinition(registry.game_root)
    messages: list[str] = []
    game = SimpleNamespace(
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
        add_message=messages.append,
        run_story=stories.append,
    )

    definition.on_dungeon_result(game, DungeonResult.SUCCESS)

    assert stories == ["victory_scene"]
    assert messages == []
