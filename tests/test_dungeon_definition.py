from __future__ import annotations

from pathlib import Path
from random import Random
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.dungeon import DungeonDefinition, floor_spec_matches
from test_game.game_definition import TestGameDefinition


def test_floor_specs_cover_ranges_lists_and_open_ended_ranges():
    assert floor_spec_matches("all", 7, 20)
    assert floor_spec_matches("1-3,8,12+", 2, 20)
    assert floor_spec_matches("1-3,8,12+", 8, 20)
    assert floor_spec_matches("1-3,8,12+", 16, 20)
    assert not floor_spec_matches("1-3,8,12+", 6, 20)


def test_test_dungeon_loads_from_json_and_has_music():
    definition = TestGameDefinition()
    dungeon = definition.dungeon_definition
    assert dungeon.id == "test_dungeon"
    assert dungeon.floor_count == 3
    settings = dungeon.settings_for_floor(1)
    assert settings["music"] == "music/02_Ancient_Ruins_B1.ogg"
    assert settings["music_volume"] == 0.8


def test_generator_type_and_floor_rules_are_data_driven():
    dungeon = DungeonDefinition.from_dict({
        "id": "builder_test",
        "name": "Builder Test",
        "floors": 6,
        "tileset": "ruins",
        "generation": {"type": "rooms_and_corridors", "width": 32, "height": 24},
        "music": {"track": "music/a.ogg", "volume": 0.7},
        "floor_rules": [
            {
                "floors": "5-6",
                "tileset": "deep_ruins",
                "generation": {"type": "open_room", "width": 20, "height": 18, "margin": 2},
                "music": {"track": "music/deep.ogg", "volume": 0.5}
            }
        ]
    })
    early = dungeon.generate_layout(2, Random(1))
    deep = dungeon.generate_layout(5, Random(1))
    assert (early.width, early.height, early.tileset, early.music) == (32, 24, "ruins", "music/a.ogg")
    assert (deep.width, deep.height, deep.tileset, deep.music) == (20, 18, "deep_ruins", "music/deep.ogg")
    assert deep.music_volume == 0.5
    assert len(deep.rooms) == 1


def test_enemy_floor_ranges_filter_spawn_pool():
    dungeon = DungeonDefinition.from_dict({
        "id": "spawns",
        "name": "Spawns",
        "floors": 10,
        "enemies": [
            {"enemy": "early", "floors": "1-4", "weight": 1},
            {"enemy": "late", "floors": "5+", "weight": 1}
        ]
    })
    assert [r.content_id for r in dungeon.active_enemies(3)] == ["early"]
    assert [r.content_id for r in dungeon.active_enemies(7)] == ["late"]


def test_dungeon_definition_round_trips(tmp_path):
    dungeon = DungeonDefinition.from_dict({
        "id": "round_trip",
        "name": "Round Trip",
        "floors": 12,
        "tileset": "cave",
        "generation": {"type": "open_room", "width": 22, "height": 18, "margin": 2},
        "music": {"track": "music/test.ogg", "volume": 0.6},
        "enemies": [{"enemy": "mossling", "floors": "1-6", "weight": 3}]
    })
    path = tmp_path / "round_trip.json"
    dungeon.save(path)
    loaded = DungeonDefinition.load(path)
    assert loaded.to_dict() == dungeon.to_dict()
