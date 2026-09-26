from __future__ import annotations

import unittest

from mystery_engine.core import Vec2
from mystery_engine.story import (
    ExplorationActor,
    ExplorationMap,
    ExplorationScenery,
    ExplorationInteractable,
    PolygonObstacle,
    RectObstacle,
    TerrainTileMap,
)


class ExplorationCollisionTests(unittest.TestCase):
    def test_water_blocks_actor_movement(self):
        terrain = TerrainTileMap(
            tile_size=64,
            width_tiles=3,
            height_tiles=3,
            tiles=[
                ["grass", "grass", "grass"],
                ["grass", "water", "grass"],
                ["grass", "grass", "grass"],
            ],
        )
        fox = ExplorationActor("fox", "Fox", Vec2(42, 96), radius=12)
        world = ExplorationMap(
            "test", 192, 192,
            actors=[fox],
            terrain=terrain,
            blocked_terrain=frozenset({"water"}),
        )

        world.try_move(fox, Vec2(20, 0))
        self.assertEqual(fox.position.x, 42)

    def test_elevation_change_blocks_actor_without_traversal(self):
        terrain = TerrainTileMap(
            tile_size=64,
            width_tiles=3,
            height_tiles=2,
            tiles=[
                ["upper_grass", "upper_grass", "upper_grass"],
                ["grass", "grass", "grass"],
            ],
            elevations=[
                [1, 1, 1],
                [0, 0, 0],
            ],
        )
        fox = ExplorationActor("fox", "Fox", Vec2(96, 96), radius=12)
        world = ExplorationMap("test", 192, 128, actors=[fox], terrain=terrain)

        world.try_move(fox, Vec2(0, -40))
        self.assertEqual(fox.position.y, 96)

    def test_cliff_face_collision_matches_visible_wall_depth(self):
        terrain = TerrainTileMap(
            tile_size=64,
            width_tiles=3,
            height_tiles=3,
            tiles=[["upper_grass"] * 3, ["grass"] * 3, ["grass"] * 3],
            elevations=[[1, 1, 1], [0, 0, 0], [0, 0, 0]],
            elevation_face_depth=44,
        )
        fox = ExplorationActor("fox", "Fox", Vec2(96, 122), radius=8)
        world = ExplorationMap("test", 192, 192, actors=[fox], terrain=terrain)

        # Candidate center y=102 is still in the lower cell, but visually inside
        # the hanging cliff face (64..108), so movement must be rejected.
        world.try_move(fox, Vec2(0, -20))
        self.assertEqual(fox.position.y, 122)

    def test_scenery_local_collider_blocks_only_its_footprint(self):
        fox = ExplorationActor("fox", "Fox", Vec2(128, 160), radius=10)
        tree = ExplorationScenery(
            "tree", "tree", Vec2(128, 128), (196, 230),
            collision=RectObstacle(-24, -46, 48, 46),
        )
        world = ExplorationMap("test", 256, 256, actors=[fox], scenery=[tree])

        world.try_move(fox, Vec2(0, -25))
        self.assertEqual(fox.position.y, 160)

        fox.position.x = 70
        world.try_move(fox, Vec2(0, -25))
        self.assertEqual(fox.position.y, 135)

    def test_polygon_collider_blocks_irregular_footprint(self):
        fox = ExplorationActor("fox", "Fox", Vec2(128, 178), radius=10)
        stump = ExplorationScenery(
            "stump", "tree", Vec2(128, 128), (80, 80),
            collision=PolygonObstacle(((-26, -8), (-10, -36), (12, -34), (28, -10), (22, 20), (-24, 22))),
        )
        world = ExplorationMap("test", 256, 256, actors=[fox], scenery=[stump])

        world.try_move(fox, Vec2(0, -30))
        self.assertEqual(fox.position.y, 178)

        fox.position.x = 72
        world.try_move(fox, Vec2(0, -30))
        self.assertEqual(fox.position.y, 148)

    def test_other_actor_blocks_exploration_movement(self):
        fox = ExplorationActor("fox", "Fox", Vec2(80, 80), radius=20)
        mara = ExplorationActor("mara", "Mara", Vec2(125, 80), radius=20)
        world = ExplorationMap("test", 256, 256, actors=[fox, mara])

        world.try_move(fox, Vec2(10, 0))
        self.assertEqual(fox.position.x, 80)

    def test_interactable_rect_collider_blocks_only_base(self):
        fox = ExplorationActor("fox", "Fox", Vec2(128, 170), radius=10)
        stone = ExplorationInteractable(
            "stone", Vec2(128, 128), lambda: None,
            collision=RectObstacle(-30, -20, 60, 20),
        )
        world = ExplorationMap("test", 256, 256, actors=[fox], interactables=[stone])

        world.try_move(fox, Vec2(0, -35))
        self.assertEqual(fox.position.y, 170)

        fox.position.x = 70
        world.try_move(fox, Vec2(0, -35))
        self.assertEqual(fox.position.y, 135)

    def test_disabled_actor_does_not_block(self):
        fox = ExplorationActor("fox", "Fox", Vec2(80, 80), radius=20)
        mara = ExplorationActor("mara", "Mara", Vec2(125, 80), radius=20, enabled=False)
        world = ExplorationMap("test", 256, 256, actors=[fox, mara])

        world.try_move(fox, Vec2(10, 0))
        self.assertEqual(fox.position.x, 90)


if __name__ == "__main__":
    unittest.main()
