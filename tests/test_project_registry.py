from __future__ import annotations

import json
from pathlib import Path

from mystery_engine.dungeon import DungeonDefinition, SpawnRule
from mystery_engine.project import (
    AttackDefinitionData,
    EnemyDefinitionData,
    GameSettingsData,
    ItemDefinitionData,
    PawnDefinitionData,
    PlayableCharacterDefinitionData,
    ProjectRegistry,
    TerrainDefinitionData,
    WorldObjectDefinitionData,
)
from mystery_engine.story import RectObstacle, SceneObjectData, WorldAssetCatalog


def _registry(tmp_path: Path) -> ProjectRegistry:
    game_root = tmp_path / "game"
    (game_root / "content" / "attacks").mkdir(parents=True)
    (game_root / "content" / "enemies").mkdir(parents=True)
    (game_root / "content" / "items").mkdir(parents=True)
    (game_root / "content" / "characters").mkdir(parents=True)
    (game_root / "content" / "objects").mkdir(parents=True)
    (game_root / "content" / "terrain").mkdir(parents=True)
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
            "items": "content/items",
            "characters": "content/characters",
            "objects": "content/objects",
            "terrain": "content/terrain",
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


def test_project_registry_saves_items_and_sprite_keys(tmp_path):
    registry = _registry(tmp_path)
    registry.save_item(ItemDefinitionData(
        id="herb",
        name="Healing Herb",
        description="Restores HP.",
        heal=12,
        droppable=True,
        sprite_key="green_herb",
    ))
    item = registry.item("herb")
    assert item.name == "Healing Herb"
    assert item.heal == 12
    assert item.sprite_key == "green_herb"
    assert registry.item_labels == {"herb": "Healing Herb"}


def test_project_registry_builds_playable_character_from_pawn(tmp_path):
    registry = _registry(tmp_path)
    registry.save_pawn(PawnDefinitionData(
        id="hero_pawn", name="Hero", sprite_key="hero", portrait_key="hero_face",
    ))
    registry.save_attack(AttackDefinitionData(
        id="jab", name="Jab", target="enemy", range=1, power=4,
        damage_type="physical", range_pattern="adjacent",
    ))
    registry.save_character(PlayableCharacterDefinitionData(
        id="hero",
        pawn_id="hero_pawn",
        max_hp=42,
        attack=7,
        defense=5,
        attacks=("jab",),
        resistances={"lightning": 0.75},
        ai_tactic="protect",
    ))
    hero = registry.make_character("hero", leader=True)
    assert hero.name == "Hero"
    assert hero.leader
    assert hero.party_member
    assert hero.stats.max_hp == 42
    assert hero.metadata["sprite_key"] == "hero"
    assert hero.metadata["portrait_key"] == "hero_face"
    assert [skill.definition.id for skill in hero.skills] == ["jab"]
    assert hero.resistances["lightning"] == 0.75
    assert registry.character_labels == {"hero": "Hero"}


def test_game_settings_round_trip_in_manifest(tmp_path):
    registry = _registry(tmp_path)
    settings = GameSettingsData(
        title="A New Adventure",
        version="2.1",
        starting_scene="meadow",
        starting_marker="arrival",
        default_dungeon="first",
        bag_capacity=16,
        storage_capacity=60,
        starting_carried_money=75,
        starting_stored_money=25,
        defeat_money_loss_fraction=0.25,
        defeat_item_loss_chance=0.10,
        starting_party=("hero", "friend"),
        leader="hero",
        starting_items={"herb": 3},
        starting_storage={"stone": 2},
        starting_flags={"intro_seen": False},
        starting_variables={"trust": 2},
        dungeon_result_stories={"success": "victory_scene"},
        sfx_event_cues={"confirm": "ui.confirm"},
    )
    registry.save_game_settings(settings)
    loaded = ProjectRegistry.load(registry.game_root).game_settings
    assert loaded == settings


def test_project_registry_saves_custom_world_objects(tmp_path):
    registry = _registry(tmp_path)
    registry.save_object(WorldObjectDefinitionData(
        id="mushroom_lamp",
        name="Mushroom Lamp",
        category="interactable",
        sprite_key="mushroom_lamp",
        width=72,
        height=96,
        collider_enabled=True,
        collision=RectObstacle(-20, -24, 40, 24),
        draw_behind_actors=False,
        label="Mushroom lamp",
        sound_cues={"interact": "magic.arcane_cast"},
    ))

    loaded = registry.objects["mushroom_lamp"]
    assert loaded.name == "Mushroom Lamp"
    assert loaded.collider_enabled
    assert loaded.collision == RectObstacle(-20, -24, 40, 24)

    catalog = registry.world_asset_catalog(WorldAssetCatalog(assets={}))
    definition = catalog.get("mushroom_lamp")
    assert definition.category == "interactable"
    assert definition.sprite_key == "mushroom_lamp"
    assert definition.collision == RectObstacle(-20, -24, 40, 24)
    assert definition.label == "Mushroom lamp"
    assert definition.sound_cues["interact"] == "magic.arcane_cast"


def test_custom_world_object_can_default_to_no_collider(tmp_path):
    registry = _registry(tmp_path)
    registry.save_object(WorldObjectDefinitionData(
        id="rug",
        name="Rug",
        category="scenery",
        sprite_key="rug",
        width=120,
        height=80,
        collider_enabled=False,
        collision=RectObstacle(-60, -20, 120, 20),
    ))
    definition = registry.world_asset_catalog(WorldAssetCatalog(assets={})).get("rug")
    assert definition.collision is None
    assert definition.collision_radius == 0.0


def test_blank_project_creation_is_self_contained(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "fresh_game", "Fresh Game")
    assert registry.manifest_path.exists()
    assert registry.project_name == "Fresh Game"
    assert {"grass", "void"}.issubset(registry.terrain)
    assert registry.terrain["grass"].blocked is False
    assert registry.terrain["void"].blocked is True
    assert registry.scene_dir.exists()
    assert registry.asset_root.exists()


def test_project_registry_saves_custom_terrain(tmp_path):
    registry = _registry(tmp_path)
    registry.save_terrain(TerrainDefinitionData(
        id="snow",
        name="Snow",
        mode="variants",
        sprite_keys=("snow_0", "snow_1"),
        blocked=False,
        fallback_color="#ddeeff",
    ))
    loaded = registry.terrain["snow"]
    assert loaded.name == "Snow"
    assert loaded.mode == "variants"
    assert loaded.sprite_keys == ("snow_0", "snow_1")
    assert registry.terrain_runtime()["snow"]["fallback_color"] == "#ddeeff"


def test_scene_background_round_trip():
    from mystery_engine.story import ExplorationSceneData
    source = ExplorationSceneData.blank("painted_room", 8, 6)
    source.background_key = "painted_room_bg"
    source.background_mode = "tile"
    loaded = ExplorationSceneData.from_dict(source.to_dict())
    assert loaded.background_key == "painted_room_bg"
    assert loaded.background_mode == "tile"



def test_item_sprite_sheet_metadata_round_trip(tmp_path):
    registry = _registry(tmp_path)
    registry.save_item(ItemDefinitionData(
        id="potion",
        name="Potion",
        sprite_key="potion_labelled",
        sprite_sheet_key="clean_items",
        sprite_sheet_index=2,
        sprite_sheet_columns=4,
    ))
    loaded = registry.items_data["potion"]
    runtime = registry.item("potion")
    assert loaded.sprite_sheet_key == "clean_items"
    assert loaded.sprite_sheet_index == 2
    assert loaded.sprite_sheet_columns == 4
    assert runtime.sprite_sheet_key == "clean_items"
    assert runtime.sprite_sheet_index == 2
    assert runtime.sprite_sheet_columns == 4
