from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from mystery_engine.story import (
    ExplorationSceneData,
    PolygonObstacle,
    RectObstacle,
    SceneObjectData,
    build_exploration_map,
    load_exploration_scene,
    save_exploration_scene,
)
from test_game.world_assets import WORLD_ASSETS


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


    def test_collision_override_roundtrip_and_runtime(self):
        scene = ExplorationSceneData.blank("collision_override", 6, 5)
        scene.objects.append(
            SceneObjectData(
                "gate", "dungeon_gate", 192, 192,
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

    def test_every_scene_asset_exists_in_catalog(self):
        path = Path(__file__).resolve().parents[1] / "src" / "test_game" / "scenes" / "test_clearing.json"
        scene = load_exploration_scene(path)
        for obj in scene.objects:
            WORLD_ASSETS.get(obj.asset)


if __name__ == "__main__":
    unittest.main()
