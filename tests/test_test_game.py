from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from test_game.content import FOX_LUNGE, MARA_MEND, MARA_SPARK, WAYSTONE_SHARD, WISP_BOLT
from test_game.game_definition import TestGameDefinition


class TestGameContentTests(unittest.TestCase):
    def test_party_is_fox_then_mara_and_fox_leads(self):
        state = TestGameDefinition().create_state()
        self.assertEqual([c.name for c in state.party], ["Fox", "Mara"])
        self.assertTrue(state.party[0].leader)
        self.assertFalse(state.party[1].leader)

    def test_waystone_shard_is_protected(self):
        self.assertTrue(WAYSTONE_SHARD.key_item)
        self.assertFalse(WAYSTONE_SHARD.droppable)

    def test_starting_money(self):
        state = TestGameDefinition().create_state()
        self.assertEqual(state.wallet.carried, 100)

    def test_sfx_defaults_match_current_content(self):
        game_def = TestGameDefinition()
        self.assertEqual(game_def.sfx_event_cues["cursor_move"], "ui.cursor_move")
        self.assertEqual(game_def.sfx_event_cues["basic_hit"], "combat.light_hit")
        self.assertEqual(FOX_LUNGE.sfx_cue, "combat.light_hit")
        self.assertEqual(MARA_SPARK.sfx_cue, "magic.bolt_launch")
        self.assertEqual(MARA_SPARK.impact_sfx_cue, "magic.bolt_impact")
        self.assertEqual(MARA_MEND.sfx_cue, "magic.heal")
        self.assertEqual(WISP_BOLT.sfx_cue, "magic.bolt_launch")

    def test_sfx_catalog_is_shipped_with_test_game(self):
        self.assertTrue(TestGameDefinition.sfx_catalog_path.exists())

    def test_exploration_uses_semantic_terrain_and_scenery(self):
        game_def = TestGameDefinition()
        class _Dummy:  # minimal stand-in for callbacks captured during map creation
            state = type("S", (), {"story": type("Story", (), {"flag": staticmethod(lambda *_: False), "set_flag": staticmethod(lambda *_, **__: None)})()})()
            say = staticmethod(lambda *_, **__: None)
            enter_dungeon = staticmethod(lambda: None)
        world = game_def.create_exploration(_Dummy())
        self.assertIsNotNone(world.terrain)
        self.assertGreater(len(world.scenery), 0)
        self.assertEqual(world.terrain.terrain_at(12, 11), "path")
        self.assertEqual(world.terrain.terrain_at(0, 0), "void")
        self.assertEqual(world.terrain.terrain_at(1, 1), "upper_grass")
        self.assertEqual(world.terrain.elevation_at(1, 1), 1)
        self.assertEqual(world.terrain.elevation_at(2, 2), 0)


    def test_world_props_use_depth_sortable_collision_model(self):
        game_def = TestGameDefinition()
        class _Dummy:
            state = type("S", (), {"story": type("Story", (), {"flag": staticmethod(lambda *_: False), "set_flag": staticmethod(lambda *_, **__: None)})()})()
            say = staticmethod(lambda *_, **__: None)
            enter_dungeon = staticmethod(lambda: None)
        world = game_def.create_exploration(_Dummy())

        waystone = next(i for i in world.interactables if i.id == "waystone")
        self.assertIsNotNone(waystone.collision)
        self.assertEqual(waystone.collision_radius, 0.0)

        dungeon_gate = next(i for i in world.interactables if i.id == "dungeon_gate")
        self.assertIsNotNone(dungeon_gate.collision)
        self.assertEqual(
            (dungeon_gate.collision.x, dungeon_gate.collision.y, dungeon_gate.collision.w, dungeon_gate.collision.h),
            (-88, -136, 176, 58),
        )
        # The rear wall is solid, but the foreground doorway remains open so
        # the player can still approach the entrance from below.
        self.assertLess(dungeon_gate.collision.y + dungeon_gate.collision.h, -50)

        fences = [s for s in world.scenery if s.sprite_key == "fence"]
        self.assertTrue(fences)
        self.assertTrue(all(not f.draw_behind_actors for f in fences))


if __name__ == "__main__":
    unittest.main()
