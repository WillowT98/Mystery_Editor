from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from mystery_engine.project import ProjectRegistry
from mystery_engine.project_runtime import SYSTEM_WORLD_ASSETS
from mystery_engine.story import (
    ExplorationSceneData,
    PolygonObstacle,
    RectObstacle,
    SceneObjectData,
    SceneTriggerData,
    build_exploration_map,
    load_exploration_scene,
    save_exploration_scene,
)


GAME_ROOT = Path(__file__).resolve().parents[1] / "src" / "test_game"
REGISTRY = ProjectRegistry.load(GAME_ROOT)
WORLD_ASSETS = REGISTRY.world_asset_catalog(SYSTEM_WORLD_ASSETS)

class SceneDataTests(unittest.TestCase):
    def test_scene_roundtrip(self):
        scene = ExplorationSceneData.blank("roundtrip", 6, 5)
        scene.terrain[2][3] = "water"
        scene.elevations[1][2] = 1
        scene.objects.append(SceneObjectData("tree", "tree", 128, 192))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.json"
            save_exploration_scene(scene, path)
            loaded = load_exploration_scene(path)
        self.assertEqual(loaded.to_dict(), scene.to_dict())

    def test_test_clearing_is_data_driven(self):
        path = Path(__file__).resolve().parents[1] / "src" / "test_game" / "scenes" / "test_clearing.json"
        scene = load_exploration_scene(path)
        self.assertEqual((scene.width_tiles, scene.height_tiles), (40, 24))
        ids = {obj.id for obj in scene.objects}
        self.assertIn("fox", ids)
        self.assertIn("mara", ids)
        self.assertIn("dungeon_gate", ids)
        self.assertIn("waystone", ids)

    def test_catalog_builds_exploration_map(self):
        scene = ExplorationSceneData.blank("build", 8, 8)
        scene.objects.extend([
            SceneObjectData("fox", "fox", 100, 100),
            SceneObjectData("tree", "tree", 200, 200),
            SceneObjectData("stone", "waystone", 300, 300, action="inspect"),
        ])
        world = build_exploration_map(scene, WORLD_ASSETS, {"inspect": lambda: None})
        self.assertEqual(world.actor("fox").sprite_key, "fox")
        self.assertEqual(world.scenery[0].sprite_key, "tree")
        self.assertEqual(world.interactables[0].icon_key, "waystone")


    def test_storage_assets_bind_as_separate_interactables(self):
        scene = ExplorationSceneData.blank("storage", 8, 8)
        scene.objects.extend([
            SceneObjectData("items", "item_storage", 128, 128, action="storage.items"),
            SceneObjectData("money", "money_storage", 256, 128, action="storage.money"),
        ])
        called: list[str] = []
        world = build_exploration_map(
            scene,
            WORLD_ASSETS,
            {
                "storage.items": lambda: called.append("items"),
                "storage.money": lambda: called.append("money"),
            },
        )
        self.assertEqual([entry.label for entry in world.interactables], ["Item storage", "Money storage"])
        world.interactables[0].interaction()
        world.interactables[1].interaction()
        self.assertEqual(called, ["items", "money"])

    def test_collision_override_roundtrip_and_runtime(self):
        scene = ExplorationSceneData.blank("collision_override", 6, 5)
        scene.objects.append(
            SceneObjectData(
                "gate", "dungeon_entrance", 192, 192,
                collision=RectObstacle(-70, -120, 140, 46),
            )
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.json"
            save_exploration_scene(scene, path)
            loaded = load_exploration_scene(path)
        self.assertIsNotNone(loaded.objects[0].collision)
        self.assertEqual(loaded.objects[0].collision, RectObstacle(-70, -120, 140, 46))
        world = build_exploration_map(loaded, WORLD_ASSETS)
        self.assertEqual(world.interactables[0].collision, RectObstacle(-70, -120, 140, 46))

    def test_polygon_collision_roundtrip_and_runtime(self):
        scene = ExplorationSceneData.blank("polygon_override", 6, 5)
        scene.objects.append(
            SceneObjectData(
                "tree", "tree", 192, 192,
                collision=PolygonObstacle(((-22, -24), (0, -60), (22, -24), (18, 0), (-18, 0))),
            )
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.json"
            save_exploration_scene(scene, path)
            loaded = load_exploration_scene(path)
        self.assertIsInstance(loaded.objects[0].collision, PolygonObstacle)
        self.assertEqual(loaded.objects[0].collision.points[1], (0.0, -60.0))
        world = build_exploration_map(loaded, WORLD_ASSETS)
        self.assertIsInstance(world.scenery[0].collision, PolygonObstacle)
        self.assertEqual(len(world.scenery[0].collision.points), 5)

    def test_scene_door_is_invisible_portal(self):
        door = WORLD_ASSETS.get("scene_door")
        self.assertEqual(door.category, "portal")
        self.assertIsNone(door.sprite_key)
        self.assertFalse(door.runtime_visible)

    def test_scene_door_link_roundtrip_and_runtime(self):
        scene = ExplorationSceneData.blank("portal", 8, 8)
        scene.objects.append(SceneObjectData(
            "door_a", "scene_door", 192, 256,
            target_scene="inside.json", target_door="door_b", portal_facing="N",
        ))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.json"
            save_exploration_scene(scene, path)
            loaded = load_exploration_scene(path)
        door = loaded.objects[0]
        self.assertEqual(door.target_scene, "inside.json")
        self.assertEqual(door.target_door, "door_b")
        self.assertEqual(door.portal_facing, "N")
        called = []
        world = build_exploration_map(loaded, WORLD_ASSETS, portal_transition_factory=lambda placed: lambda: called.append(placed.id))
        self.assertFalse(world.interactables[0].visible)
        self.assertEqual(world.interactables[0].portal_facing, "N")
        world.interactables[0].interaction()
        self.assertEqual(called, ["door_a"])


    def test_scene_door_defaults_to_two_way_mode(self):
        door = SceneObjectData("door_a", "scene_door", 64, 64)
        self.assertEqual(door.portal_mode, "two_way")
        self.assertNotIn("portal_mode", door.to_dict())

    def test_one_way_scene_door_roundtrip(self):
        scene = ExplorationSceneData.blank("one_way", 8, 8)
        scene.objects.append(SceneObjectData(
            "drop", "scene_door", 192, 256,
            target_scene="below.json", target_door="drop_arrival",
            portal_facing="N", portal_mode="one_way",
        ))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.json"
            save_exploration_scene(scene, path)
            loaded = load_exploration_scene(path)
        door = loaded.objects[0]
        self.assertEqual(door.portal_mode, "one_way")
        self.assertEqual(door.to_dict()["portal_mode"], "one_way")

    def test_unknown_portal_mode_falls_back_to_two_way(self):
        data = {
            "id": "door",
            "asset": "scene_door",
            "x": 64,
            "y": 64,
            "portal_mode": "future_mode",
        }
        door = SceneObjectData.from_dict(data)
        self.assertEqual(door.portal_mode, "two_way")


    def test_scene_music_roundtrip_and_runtime_metadata(self):
        scene = ExplorationSceneData.blank("music_scene", 6, 5)
        scene.music = "music/meadow.ogg"
        scene.music_volume = 0.65
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.json"
            save_exploration_scene(scene, path)
            loaded = load_exploration_scene(path)
        self.assertEqual(loaded.music, "music/meadow.ogg")
        self.assertAlmostEqual(loaded.music_volume, 0.65)
        world = build_exploration_map(loaded, WORLD_ASSETS)
        self.assertEqual(world.music, "music/meadow.ogg")
        self.assertAlmostEqual(world.music_volume, 0.65)

    def test_scene_ambience_roundtrip_and_runtime_metadata(self):
        scene = ExplorationSceneData.blank("ambience_scene", 6, 5)
        scene.ambience_cue = "ambience.night_field"
        scene.ambience_volume = 0.55
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.json"
            save_exploration_scene(scene, path)
            loaded = load_exploration_scene(path)
        self.assertEqual(loaded.ambience_cue, "ambience.night_field")
        self.assertAlmostEqual(loaded.ambience_volume, 0.55)
        world = build_exploration_map(loaded, WORLD_ASSETS)
        self.assertEqual(world.ambience_cue, "ambience.night_field")
        self.assertAlmostEqual(world.ambience_volume, 0.55)

    def test_object_sound_override_roundtrip_and_runtime(self):
        scene = ExplorationSceneData.blank("sfx_scene", 6, 5)
        scene.objects.append(SceneObjectData(
            "stone", "waystone", 128, 128,
            sound_cues={"interact": "magic.arcane_cast"},
        ))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.json"
            save_exploration_scene(scene, path)
            loaded = load_exploration_scene(path)
        self.assertEqual(loaded.objects[0].sound_cues["interact"], "magic.arcane_cast")
        world = build_exploration_map(loaded, WORLD_ASSETS, {"inspect_waystone": lambda: None})
        self.assertEqual(world.interactables[0].interaction_sound, "magic.arcane_cast")

    def test_every_scene_asset_exists_in_catalog(self):
        path = Path(__file__).resolve().parents[1] / "src" / "test_game" / "scenes" / "test_clearing.json"
        scene = load_exploration_scene(path)
        for obj in scene.objects:
            WORLD_ASSETS.get(obj.asset)



    def test_collision_enabled_override_roundtrip_and_runtime(self):
        scene = ExplorationSceneData.blank("toggle_collision", 6, 5)
        scene.objects.append(SceneObjectData(
            "tree_no_collision", "tree", 192, 192,
            collision_enabled=False,
        ))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scene.json"
            save_exploration_scene(scene, path)
            loaded = load_exploration_scene(path)
        self.assertFalse(loaded.objects[0].collision_enabled)
        self.assertIn("collision_enabled", loaded.objects[0].to_dict())
        world = build_exploration_map(loaded, WORLD_ASSETS)
        self.assertIsNone(world.scenery[0].collision)

    def test_explicit_collision_enable_preserves_instance_shape(self):
        scene = ExplorationSceneData.blank("enable_collision", 6, 5)
        scene.objects.append(SceneObjectData(
            "custom_prop", "tree", 192, 192,
            collision_enabled=True,
            collision=RectObstacle(-10, -12, 20, 12),
        ))
        world = build_exploration_map(scene, WORLD_ASSETS)
        self.assertEqual(world.scenery[0].collision, RectObstacle(-10, -12, 20, 12))



    def test_scene_trigger_roundtrip(self):
        scene = ExplorationSceneData.blank("triggers", 8, 6)
        scene.triggers.extend([
            SceneTriggerData(
                id="arrival",
                kind="on_scene_enter",
                story="intro",
                entry="alternate",
                once=True,
                condition={"kind": "flag", "name": "ready", "op": "==", "value": True},
            ),
            SceneTriggerData(
                id="threshold",
                kind="on_region_enter",
                story="threshold_story",
                once=False,
                x=128,
                y=192,
                w=160,
                h=96,
            ),
        ])
        payload = scene.to_dict()
        restored = ExplorationSceneData.from_dict(payload)

        self.assertEqual(len(restored.triggers), 2)
        self.assertEqual(restored.triggers[0].kind, "on_scene_enter")
        self.assertEqual(restored.triggers[0].entry, "alternate")
        self.assertEqual(restored.triggers[0].condition["name"], "ready")
        self.assertEqual(restored.triggers[1].kind, "on_region_enter")
        self.assertFalse(restored.triggers[1].once)
        self.assertEqual(
            (restored.triggers[1].x, restored.triggers[1].y, restored.triggers[1].w, restored.triggers[1].h),
            (128.0, 192.0, 160.0, 96.0),
        )


if __name__ == "__main__":
    unittest.main()
