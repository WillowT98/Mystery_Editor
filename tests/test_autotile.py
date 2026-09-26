from __future__ import annotations

import unittest
from pathlib import Path

from mystery_engine.core.autotile import E, N, NE, NW, S, SE, SW, W, autotile_asset, dungeon_walkable_mask, elevation_cliff_assets, elevation_higher_mask, oriented_neighbor_mask
from mystery_engine.story import TerrainTileMap
from mystery_engine.dungeon.floor import DungeonFloor
from mystery_engine.core.types import GridPos


class AutotileOrientationTests(unittest.TestCase):
    def terrain(self, rows: list[str]) -> TerrainTileMap:
        return TerrainTileMap(
            tile_size=64,
            width_tiles=len(rows[0]),
            height_tiles=len(rows),
            default_terrain="grass",
            tiles=[["path" if c == "P" else "grass" for c in row] for row in rows],
        )

    def test_horizontal_middle_tracks_east_west_orientation(self):
        t = self.terrain(["GGG", "PPP", "GGG"])
        self.assertEqual(oriented_neighbor_mask(t, 1, 1, "path"), E | W)

    def test_vertical_middle_tracks_north_south_orientation(self):
        t = self.terrain(["GPG", "GPG", "GPG"])
        self.assertEqual(oriented_neighbor_mask(t, 1, 1, "path"), N | S)

    def test_outer_corner_tracks_its_exact_orientation(self):
        t = self.terrain(["GGG", "GPP", "GPP"])
        self.assertEqual(oriented_neighbor_mask(t, 1, 1, "path"), E | S | SE)

    def test_inner_corner_keeps_missing_diagonal_distinct(self):
        t = self.terrain(["GPP", "PPP", "PPP"])
        mask = oriented_neighbor_mask(t, 1, 1, "path")
        self.assertEqual(mask & (N | E | S | W), N | E | S | W)
        self.assertFalse(mask & NW)
        self.assertTrue(mask & NE)
        self.assertTrue(mask & SE)
        self.assertTrue(mask & SW)

    def test_asset_name_is_mask_specific(self):
        self.assertEqual(autotile_asset("water", N | E), "tiles/water_auto_003.png")
        self.assertEqual(autotile_asset("path", E | W), "tiles/path_auto_010.png")

    def test_dungeon_walkable_mask_tracks_corridor_orientation(self):
        floor = DungeonFloor.empty(3, 3)
        for y in range(3):
            floor.set_floor(GridPos(1, y))
        self.assertEqual(dungeon_walkable_mask(floor, 1, 1), N | S)


    def test_renderer_imports_dungeon_and_elevation_helpers(self):
        renderer_source = (Path(__file__).resolve().parents[1] / "src" / "mystery_engine" / "presentation" / "renderer.py").read_text()
        self.assertIn("elevation_cliff_assets", renderer_source)
        self.assertIn("dungeon_walkable_mask", renderer_source)

    def test_elevation_cliff_corner_tracks_two_higher_neighbors(self):
        t = TerrainTileMap(
            tile_size=64,
            width_tiles=3,
            height_tiles=3,
            tiles=[["grass"] * 3 for _ in range(3)],
            elevations=[
                [1, 1, 0],
                [1, 0, 0],
                [0, 0, 0],
            ],
        )
        self.assertEqual(elevation_higher_mask(t, 1, 1), N | W | NW)
        self.assertEqual(elevation_cliff_assets(t, 1, 1), ("tiles/elevation_cliff_auto_025.png",))

    def test_elevation_cliff_straight_tracks_single_higher_neighbor(self):
        t = TerrainTileMap(
            tile_size=64,
            width_tiles=3,
            height_tiles=3,
            tiles=[["grass"] * 3 for _ in range(3)],
            elevations=[
                [0, 1, 0],
                [0, 0, 0],
                [0, 0, 0],
            ],
        )
        self.assertEqual(elevation_higher_mask(t, 1, 1), N)
        self.assertEqual(elevation_cliff_assets(t, 1, 1), ("tiles/elevation_cliff_auto_001.png",))


    def test_elevation_mask_keeps_diagonal_corner_information(self):
        t = TerrainTileMap(
            tile_size=64,
            width_tiles=3,
            height_tiles=3,
            tiles=[["grass"] * 3 for _ in range(3)],
            elevations=[
                [1, 0, 0],
                [0, 0, 0],
                [0, 0, 0],
            ],
        )
        self.assertEqual(elevation_higher_mask(t, 1, 1), NW)
        self.assertEqual(elevation_cliff_assets(t, 1, 1), ("tiles/elevation_cliff_auto_016.png",))

    def test_dungeon_asset_name_is_mask_specific(self):
        self.assertEqual(autotile_asset("dungeon_floor", N | E | NE), "tiles/dungeon_auto_035.png")


if __name__ == "__main__":
    unittest.main()
