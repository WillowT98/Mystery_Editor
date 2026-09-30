from __future__ import annotations

import json
from pathlib import Path

from mystery_engine.dungeon import DungeonDefinition, SpawnRule
from mystery_engine.project import AttackDefinitionData, EnemyDefinitionData, PawnDefinitionData, ProjectRegistry
from mystery_engine.story import SceneObjectData, WorldAssetCatalog


def _registry(tmp_path: Path) -> ProjectRegistry:
    game_root = tmp_path / "game"
    (game_root / "content" / "attacks").mkdir(parents=True)
    (game_root / "content" / "enemies").mkdir(parents=True)
    (game_root / "content" / "pawns").mkdir(parents=True)
    (game_root / "dungeons").mkdir()
    (game_root / "scenes").mkdir()
    (game_root / "stories").mkdir()
    (game_root / "assets").mkdir()
    (game_root / "project.json").write_text(json.dumps({
        "format": 1,
        "id": "test_project",
        "name": "Test Project",
        "default_dungeon": "first",
        "content": {
            "attacks": "content/attacks",
            "enemies": "content/enemies",
            "pawns": "content/pawns",
            "dungeons": "dungeons",
            "scenes": "scenes",
            "stories": "stories",
            "assets": "assets",
        },
        "damage_types": ["physical", "lightning", "arcane"],
    }), encoding="utf-8")
    DungeonDefinition.blank("first", "First Dungeon").save(game_root / "dungeons" / "first.json")
    return ProjectRegistry.load(game_root)


def test_project_registry_saves_and_builds_data_defined_enemy(tmp_path):
    registry = _registry(tmp_path)
    registry.save_attack(AttackDefinitionData(
        id="zap",
        name="Zap",
        target="enemy",
        range=6,
        power=4,
        damage_type="lightning",
        max_charges=5,
        range_pattern="line",
    ))
    registry.save_enemy(EnemyDefinitionData(
        id="beetle",
        name="Glass Beetle",
        max_hp=20,
        attack=4,
        defense=3,
        sprite_key="beetle",
        attacks=("zap",),
        resistances={"physical": 0.8},
    ))

    enemy = registry.make_enemy("beetle", "beetle_1")
    assert enemy.name == "Glass Beetle"
    assert enemy.stats.max_hp == 20
    assert enemy.resistances["physical"] == 0.8
    assert [skill.definition.id for skill in enemy.skills] == ["zap"]
    assert registry.enemy_labels["beetle"] == "Glass Beetle"


def test_spawn_modifiers_apply_without_mutating_base_enemy(tmp_path):
    registry = _registry(tmp_path)
    registry.save_attack(AttackDefinitionData(
        id="burst", name="Burst", target="enemy", range=1, power=3,
        damage_type="arcane", range_pattern="adjacent",
    ))
    registry.save_enemy(EnemyDefinitionData(
        id="shade", name="Shade", max_hp=20, attack=6, defense=4,
        sprite_key="shade", resistances={"physical": 0.8},
    ))

    rule = SpawnRule(
        content_id="shade",
        hp_percent=150,
        attack_percent=80,
        defense_percent=125,
        name_override="Deep Shade",
        sprite_override="deep_shade",
        resistances={"lightning": 1.5},
        extra_attacks=["burst"],
    )
    base = registry.make_enemy("shade", "shade_1")
    modified = registry.apply_spawn_modifiers(base, rule)

    assert modified.name == "Deep Shade"
    assert modified.stats.max_hp == 30
    assert modified.stats.attack == 5
    assert modified.stats.defense == 5
    assert modified.metadata["sprite_key"] == "deep_shade"
    assert modified.resistances == {"physical": 0.8, "lightning": 1.5}
    assert [skill.definition.id for skill in modified.skills] == ["burst"]

    fresh = registry.make_enemy("shade", "shade_2")
    assert fresh.name == "Shade"
    assert fresh.stats.max_hp == 20
    assert fresh.metadata["sprite_key"] == "shade"


def test_spawn_rule_modifier_json_round_trip():
    source = SpawnRule(
        content_id="mossling",
        floors="4-8",
        weight=7,
        min_per_floor=1,
        max_per_floor=3,
        hp_percent=125,
        attack_percent=110,
        defense_percent=90,
        name_override="Old Mossling",
        sprite_override="old_mossling",
        resistances={"fire": 1.5},
        extra_attacks=["bite"],
    )
    payload = source.to_dict("enemy")
    loaded = SpawnRule.from_dict(payload, "enemy")
    assert loaded == source


def test_asset_import_copies_instead_of_moving(tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "outside.png"
    source.write_bytes(b"fake png bytes")

    key, destination = registry.import_asset(source, "characters", preferred_id="new_enemy", allowed_suffixes={".png"})

    assert key == "new_enemy"
    assert source.exists()
    assert source.read_bytes() == b"fake png bytes"
    assert destination.exists()
    assert destination.read_bytes() == source.read_bytes()
    assert destination.parent == registry.asset_root / "characters"


def test_registry_creates_and_discovers_dungeons(tmp_path):
    registry = _registry(tmp_path)
    dungeon, path = registry.create_dungeon("Glass Vault", floors=7)
    assert path.exists()
    assert registry.dungeon_labels()[dungeon.id] == "Glass Vault"
    loaded = registry.load_dungeon(dungeon.id)
    assert loaded.floor_count == 7


def test_scene_dungeon_entrance_metadata_round_trip():
    placed = SceneObjectData(
        "ruins_gate", "dungeon_entrance", 128, 256,
        label="Ancient Ruins",
        target_dungeon="ancient_ruins",
        sprite_override="ruins_arch",
    )
    loaded = SceneObjectData.from_dict(placed.to_dict())
    assert loaded.target_dungeon == "ancient_ruins"
    assert loaded.sprite_override == "ruins_arch"
    assert loaded.label == "Ancient Ruins"


def test_project_registry_saves_pawns_and_merges_world_asset_catalog(tmp_path):
    registry = _registry(tmp_path)
    registry.save_pawn(PawnDefinitionData(
        id="willow",
        name="Willow",
        sprite_key="willow_sprite",
        portrait_key="willow_portrait",
        radius=30,
        color_key="willow",
    ))

    assert registry.pawn_labels["willow"] == "Willow"
    assert registry.resolve_story_pawn("willow") == ("Willow", "willow_portrait")

    merged = registry.world_asset_catalog(WorldAssetCatalog(assets={}))
    pawn_asset = merged.get("willow")
    assert pawn_asset.category == "actor"
    assert pawn_asset.sprite_key == "willow_sprite"
    assert pawn_asset.actor_name == "Willow"


def test_registry_creates_scene_bound_story(tmp_path):
    registry = _registry(tmp_path)
    scene_path = registry.scene_dir / "meadow.json"
    scene_path.write_text(
        json.dumps({
            "format": 1,
            "id": "meadow",
            "tile_size": 64,
            "width_tiles": 4,
            "height_tiles": 4,
            "terrain": [["grass"] * 4 for _ in range(4)],
            "elevations": [[0] * 4 for _ in range(4)],
            "objects": [],
        }),
        encoding="utf-8",
    )

    graph, path = registry.create_story("Meadow Talk", "meadow")
    assert path.exists()
    assert graph.scene_id == "meadow"
    assert graph.name == "Meadow Talk"
    assert registry.stories_for_scene("meadow") == {graph.id: path}


def test_scene_story_link_metadata_round_trip():
    placed = SceneObjectData(
        "mara", "mara", 128, 256,
        target_story="mara_meadow",
    )
    loaded = SceneObjectData.from_dict(placed.to_dict())
    assert loaded.target_story == "mara_meadow"
