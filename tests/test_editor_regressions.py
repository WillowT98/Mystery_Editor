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
