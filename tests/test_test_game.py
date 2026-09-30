from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mystery_engine.core import RangePattern
from mystery_engine.project import ProjectRegistry
from mystery_engine.project_runtime import ProjectGameDefinition


ROOT = Path(__file__).resolve().parents[1]
GAME_ROOT = ROOT / "src" / "test_game"


def _definition() -> ProjectGameDefinition:
    return ProjectGameDefinition(GAME_ROOT)


def test_example_project_builds_party_from_data():
    definition = _definition()
    state = definition.create_state()
    assert [c.name for c in state.party] == ["Fox", "Mara"]
    assert state.party[0].leader
    assert not state.party[1].leader
    assert state.wallet.carried == 100


def test_example_items_and_attacks_are_data_defined():
    registry = ProjectRegistry.load(GAME_ROOT)

    shard = registry.item("waystone_shard")
    assert shard.key_item
    assert not shard.droppable

    lunge = registry.attack_skill("fox_lunge")
    spark = registry.attack_skill("mara_spark")
    mend = registry.attack_skill("mara_mend")
    bolt = registry.attack_skill("wisp_bolt")

    assert lunge.range_pattern is RangePattern.TWO_TILES
    assert spark.range_pattern is RangePattern.LINE
    assert spark.range == 10
    assert mend.range_pattern is RangePattern.ROOM
    assert bolt.range_pattern is RangePattern.LINE
    assert bolt.range == 10

    assert lunge.sfx_cue == "combat.light_hit"
    assert spark.sfx_cue == "magic.bolt_launch"
    assert spark.impact_sfx_cue == "magic.bolt_impact"
    assert mend.sfx_cue == "magic.heal"


def test_example_projectile_assets_and_item_metadata_are_data_driven():
    registry = ProjectRegistry.load(GAME_ROOT)
    stone = registry.item("throwing_stone")
    assert stone.projectile_key == "stone"
    assert stone.projectile_arc_px > 0

    for index, item_id in enumerate(("field_salve", "throwing_stone", "waystone_shard")):
        item = registry.item(item_id)
        assert item.sprite_sheet_key == "item_sheet"
        assert item.sprite_sheet_index == index
        assert item.sprite_sheet_columns == 3
    assert (registry.asset_root / "items" / "item_sheet.png").exists()

    for key in ("spark", "needle", "stone"):
        assert (registry.asset_root / "projectiles" / f"{key}.png").exists()


def test_example_enemy_roster_is_registered_from_json():
    registry = ProjectRegistry.load(GAME_ROOT)
    expected = {
        "lost_lantern",
        "mirror_shade",
        "weaving_wisp",
        "clockwork_sentinel",
        "forgotten_hound",
        "veil_bloom",
    }
    assert expected.issubset(registry.enemies)

    for enemy_id in expected:
        enemy = registry.make_enemy(enemy_id, f"test_{enemy_id}")
        assert enemy.hostile
        assert enemy.skills
        assert (registry.asset_root / "characters" / f"{enemy_id}.png").exists()


def test_example_enemy_attacks_use_supported_targeting_patterns():
    registry = ProjectRegistry.load(GAME_ROOT)
    assert registry.attack_skill("lost_lantern_glow_shot").range_pattern is RangePattern.LINE
    assert registry.attack_skill("mirror_shade_shard_volley").range_pattern is RangePattern.LINE
    assert registry.attack_skill("weaving_wisp_wave_burst").range_pattern is RangePattern.LINE
    assert registry.attack_skill("clockwork_sentinel_time_pulse").range_pattern is RangePattern.ROOM
    assert registry.attack_skill("forgotten_hound_pounce").range_pattern is RangePattern.TWO_TILES
    assert registry.attack_skill("veil_bloom_spore_burst").range_pattern is RangePattern.ROOM


def test_example_sfx_catalog_is_shipped():
    definition = _definition()
    assert definition.sfx_catalog_path.exists()
    assert definition.sfx_event_cues["cursor_move"] == "ui.cursor_move"
    assert definition.sfx_event_cues["basic_hit"] == "combat.light_hit"


def test_example_exploration_loads_through_generic_runtime():
    definition = _definition()
    state = definition.create_state()
    fake_game = SimpleNamespace(
        state=state,
        add_message=lambda *_: None,
        change_exploration_scene=lambda *_: None,
        run_story=lambda *_: None,
        enter_dungeon=lambda *_: None,
    )
    world = definition.create_exploration(fake_game)

    assert world.terrain is not None
    assert world.scenery
    assert world.terrain.terrain_at(12, 11) == "path"
    assert world.terrain.terrain_at(0, 0) == "void"
    assert world.terrain.terrain_at(1, 1) == "upper_grass"
    assert world.terrain.elevation_at(1, 1) == 1
    assert world.terrain.elevation_at(2, 2) == 0

    waystone = next(i for i in world.interactables if i.id == "waystone")
    assert waystone.collision is not None
    assert waystone.collision_radius == 0.0

    dungeon_gate = next(i for i in world.interactables if i.id == "dungeon_gate")
    assert dungeon_gate.collision is not None
    assert (
        dungeon_gate.collision.x,
        dungeon_gate.collision.y,
        dungeon_gate.collision.w,
        dungeon_gate.collision.h,
    ) == (-88, -136, 176, 58)

    fences = [s for s in world.scenery if s.sprite_key == "fence"]
    assert fences
    assert all(not fence.draw_behind_actors for fence in fences)
