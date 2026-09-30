from __future__ import annotations

from types import SimpleNamespace

import pygame

from mystery_engine.core.autotile import autotile_asset
from mystery_engine.editor.app import ExplorationSceneEditor
from mystery_engine.editor.dungeon_builder import DungeonBuilderEditor
from mystery_engine.editor.story_graph import StoryGraphEditor


def test_scene_editor_autotile_falls_back_to_runtime_asset(monkeypatch):
    editor = ExplorationSceneEditor.__new__(ExplorationSceneEditor)
    editor.project_registry = SimpleNamespace(
        terrain={
            "path": SimpleNamespace(mode="autotile", sprite_keys=()),
            "water": SimpleNamespace(mode="autotile", sprite_keys=()),
        }
    )

    calls: list[str] = []

    def fake_scaled(relative: str, _size):
        calls.append(relative)
        if relative == autotile_asset("path", 17):
            return "path-runtime-tile"
        if relative == autotile_asset("water", 17):
            return "water-runtime-tile"
        return None

    editor._scaled_surface = fake_scaled
    monkeypatch.setattr("mystery_engine.editor.app.oriented_neighbor_mask", lambda *_args: 17)

    assert editor._editor_terrain_surface("path", 2, 3, 64, object()) == "path-runtime-tile"
    assert editor._editor_terrain_surface("water", 2, 3, 64, object()) == "water-runtime-tile"
    assert "terrain/path/auto_017.png" in calls
    assert autotile_asset("path", 17) in calls
    assert "terrain/water/auto_017.png" in calls
    assert autotile_asset("water", 17) in calls


def test_scene_editor_window_close_requests_application_exit():
    editor = ExplorationSceneEditor.__new__(ExplorationSceneEditor)
    editor._close_application_requested = False
    editor._return_to_project_requested = False

    assert editor.handle_event(pygame.event.Event(pygame.QUIT)) is False
    assert editor._close_application_requested is True


def test_dungeon_editor_window_close_requests_application_exit():
    editor = DungeonBuilderEditor.__new__(DungeonBuilderEditor)
    editor._close_application_requested = False
    editor._return_to_project_requested = False

    assert editor.handle_event(pygame.event.Event(pygame.QUIT)) is False
    assert editor._close_application_requested is True


def test_story_editor_window_close_requests_application_exit():
    editor = StoryGraphEditor.__new__(StoryGraphEditor)
    editor._close_application_requested = False
    editor._return_to_project_requested = False

    assert editor.handle_event(pygame.event.Event(pygame.QUIT)) is False
    assert editor._close_application_requested is True


def test_storage_sprite_import_is_exposed_in_scene_editor():
    source = (__import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "mystery_engine" / "editor" / "app.py").read_text(encoding="utf-8")
    assert "__storage_sprite" in source
    assert "Import storage sprite" in source
    assert "Change storage sprite" in source
    assert "_change_selected_storage_sprite" in source


def test_story_editor_structured_action_registry_covers_common_choreography():
    actions = StoryGraphEditor.STRUCTURED_ACTIONS
    expected = {
        "move_actor", "face_actor", "teleport_actor", "set_actor_state", "set_object_state",
        "camera_pan", "camera_follow", "camera_reset", "camera_shake",
        "screen_fade", "screen_flash", "banner", "play_music", "stop_music",
        "play_sfx", "play_ambience", "stop_ambience", "change_scene",
        "enter_dungeon", "message",
    }
    assert expected <= set(actions)


def test_story_editor_structured_value_coercion():
    coerce = StoryGraphEditor._coerce_structured_value
    assert coerce("2.5", "float") == 2.5
    assert coerce("3", "int") == 3
    assert coerce("", "optional_float") is None
    assert coerce("true", "bool") is True
    assert coerce("false", "value") is False
    assert coerce('{"a": 1}', "value") == {"a": 1}
    assert coerce("plain text", "value") == "plain text"


def test_story_editor_keeps_json_escape_hatch_for_structured_nodes():
    source = (__import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "mystery_engine" / "editor" / "story_graph.py").read_text(encoding="utf-8")
    assert "Edit Action" in source
    assert "Edit Effects" in source
    assert "Advanced JSON…" in source


def test_story_editor_exposes_gameplay_actions_and_conditions():
    actions = StoryGraphEditor.STRUCTURED_ACTIONS
    for action in (
        "give_item", "remove_item", "give_money", "remove_money",
        "heal_party", "restore_skill_charges", "restore_party",
    ):
        assert action in actions

    conditions = StoryGraphEditor.CONDITION_KINDS
    for condition in (
        "has_item", "item_count", "has_money",
        "party_contains", "party_hp", "skill_charges",
    ):
        assert condition in conditions


def test_story_editor_exposes_structured_actor_animation_actions():
    assert "play_animation" in StoryGraphEditor.STRUCTURED_ACTIONS
    assert "reset_animation" in StoryGraphEditor.STRUCTURED_ACTIONS
    assert StoryGraphEditor.ACTION_TEMPLATES["Animation"][1]["action"] == "play_animation"


def test_pawn_editor_contains_animation_set_authoring():
    source = (__import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "mystery_engine" / "editor" / "project_editor.py").read_text(encoding="utf-8")
    assert "Pawn Animation Sets" in source
    assert "Import animation sheet" in source
    assert "Animation sets" in source
