from __future__ import annotations

from pathlib import Path
from random import Random
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.dungeon import GENERATION_PROFILES, DungeonDefinition, floor_spec_matches
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


def test_generation_profiles_are_available_and_change_floor_shape():
    assert {"default", "compact", "many_small_rooms", "sprawling", "sparse_large_rooms", "tight_labyrinth", "open_hall"}.issubset(GENERATION_PROFILES)

    dungeon = DungeonDefinition.from_dict({
        "id": "profile_test",
        "name": "Profile Test",
        "floors": 8,
        "generation": {
            "type": "rooms_and_corridors",
            "width": 38,
            "height": 28,
            "room_count_min": 6,
            "room_count_max": 9,
            "room_w_min": 4,
            "room_w_max": 9,
            "room_h_min": 4,
            "room_h_max": 8,
        },
        "generation_profile_rules": [
            {"profile": "many_small_rooms", "floors": "1-4", "weight": 1},
            {"profile": "sprawling", "floors": "5-8", "weight": 1},
        ],
    })

    small = dungeon.generate_layout(2, Random(7))
    large = dungeon.generate_layout(6, Random(7))

    assert small.generation_profile == "many_small_rooms"
    assert (small.width, small.height) == (38, 28)
    assert all(3 <= room[2] <= 5 and 3 <= room[3] <= 5 for room in small.rooms)

    assert large.generation_profile == "sprawling"
    assert (large.width, large.height) == (52, 38)


def test_generation_profile_floor_ranges_and_weighted_pool():
    dungeon = DungeonDefinition.from_dict({
        "id": "profile_pool",
        "name": "Profile Pool",
        "floors": 12,
        "generation_profile_rules": [
            {"profile": "default", "floors": "1-6", "weight": 3},
            {"profile": "compact", "floors": "1-6", "weight": 1},
            {"profile": "sparse_large_rooms", "floors": "7+", "weight": 1},
            {"profile": "not_a_profile", "floors": "all", "weight": 100},
            {"profile": "sprawling", "floors": "all", "weight": 0},
        ],
    })

    early = dungeon.active_generation_profiles(3)
    late = dungeon.active_generation_profiles(9)
    assert [r["profile"] for r in early] == ["default", "compact"]
    assert [r["profile"] for r in late] == ["sparse_large_rooms"]
    assert dungeon.choose_generation_profile(9, Random(1)) == "sparse_large_rooms"


def test_generation_profile_rules_round_trip():
    dungeon = DungeonDefinition.from_dict({
        "id": "profile_round_trip",
        "name": "Profile Round Trip",
        "floors": 5,
        "generation_profile_rules": [
            {"profile": "default", "floors": "all", "weight": 4},
            {"profile": "open_hall", "floors": "3", "weight": 1},
        ],
    })
    payload = dungeon.to_dict()
    loaded = DungeonDefinition.from_dict(payload)
    assert loaded.generation_profile_rules == dungeon.generation_profile_rules


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
