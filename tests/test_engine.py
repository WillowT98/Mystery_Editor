from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
from random import Random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.core import Character, GridPos, Inventory, ItemDefinition, Stats
from mystery_engine.core.combat import CombatResolver
from mystery_engine.dungeon import RoomsAndCorridorsGenerator
from mystery_engine.dungeon.floor import DungeonFloor
from mystery_engine.dungeon.visibility import ExplorationMemory


class GenerationTests(unittest.TestCase):
    def test_generated_spawn_reaches_stairs(self):
        for seed in range(50):
            floor = RoomsAndCorridorsGenerator(rng=Random(seed)).generate()
            self.assertIsNotNone(floor.player_spawn)
            self.assertIsNotNone(floor.stairs_pos)
            start = floor.player_spawn
            goal = floor.stairs_pos
            frontier = deque([start])
            seen = {start}
            while frontier:
                current = frontier.popleft()
                if current == goal:
                    break
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if not (dx or dy):
                            continue
                        nxt = GridPos(current.x + dx, current.y + dy)
                        if nxt in seen or not floor.in_bounds(nxt) or not floor.tile(nxt).walkable:
                            continue
                        if dx and dy:
                            if not floor.tile(GridPos(current.x + dx, current.y)).walkable:
                                continue
                            if not floor.tile(GridPos(current.x, current.y + dy)).walkable:
                                continue
                        seen.add(nxt)
                        frontier.append(nxt)
            self.assertIn(goal, seen, f"seed {seed} produced unreachable stairs")

    def test_diagonal_corner_cutting_is_blocked(self):
        floor = DungeonFloor.empty(5, 5)
        floor.set_floor(GridPos(1, 1))
        floor.set_floor(GridPos(2, 2))
        # Cardinal side cells stay walls, so diagonal is illegal.
        self.assertFalse(floor.can_step(GridPos(1, 1), GridPos(2, 2)))
        floor.set_floor(GridPos(2, 1))
        floor.set_floor(GridPos(1, 2))
        self.assertTrue(floor.can_step(GridPos(1, 1), GridPos(2, 2)))


class VisibilityTests(unittest.TestCase):
    def test_discovery_persists_after_visibility_changes(self):
        floor = DungeonFloor.empty(9, 5)
        for x in range(1, 8):
            floor.set_floor(GridPos(x, 2))
        memory = ExplorationMemory()
        memory.update(floor, GridPos(2, 2), radius=2)
        first = set(memory.discovered)
        memory.update(floor, GridPos(6, 2), radius=2)
        self.assertTrue(first <= memory.discovered)
        self.assertNotEqual(first, memory.visible)


class CombatTests(unittest.TestCase):
    def test_typed_resistance_reduces_damage(self):
        rng_a = Random(7)
        rng_b = Random(7)
        attacker = Character("a", "A", Stats(30, 8, 2))
        normal = Character("n", "N", Stats(30, 3, 3))
        resistant = Character("r", "R", Stats(30, 3, 3), resistances={"lightning": 0.5})
        resolver_a = CombatResolver(rng_a)
        resolver_b = CombatResolver(rng_b)
        # Mirror the skill formula directly through basic stats by comparing a typed helper-like calculation.
        from mystery_engine.core.models import SkillDefinition, SkillRuntime, TargetKind
        skill = SkillRuntime.from_definition(SkillDefinition("s", "Spark", "", TargetKind.ENEMY, 5, power=6, damage_type="lightning"))
        event_normal = resolver_a.use_skill(attacker, skill, normal)
        skill2 = SkillRuntime.from_definition(skill.definition)
        event_resistant = resolver_b.use_skill(attacker, skill2, resistant)
        self.assertLess(event_resistant.amount, event_normal.amount)


class InventoryTests(unittest.TestCase):
    def test_protected_item_survives_total_loss_chance(self):
        bag = Inventory(10)
        ordinary = ItemDefinition("ordinary", "Ordinary", "", droppable=True)
        key = ItemDefinition("key", "Key", "", droppable=False, key_item=True)
        bag.add(ordinary, 3)
        bag.add(key, 1)
        lost = bag.apply_loss(Random(1), 1.0)
        self.assertEqual(lost.count("Ordinary"), 3)
        self.assertIsNotNone(next((s for s in bag.stacks if s.item.id == "key"), None))


class TurnTests(unittest.TestCase):
    def test_player_move_advances_ai_turn(self):
        from mystery_engine.core import Direction, Inventory
        from mystery_engine.dungeon import MoveAction, TurnManager
        floor = DungeonFloor.empty(9, 5)
        for y in range(1, 4):
            for x in range(1, 8):
                floor.set_floor(GridPos(x, y))
        fox = Character("fox", "Fox", Stats(30, 7, 4), party_member=True, leader=True, grid_pos=GridPos(2, 2))
        mara = Character("mara", "Mara", Stats(25, 5, 3), party_member=True, grid_pos=GridPos(1, 2))
        enemy = Character("e", "Enemy", Stats(20, 5, 2), hostile=True, grid_pos=GridPos(6, 2))
        floor.entities.extend([fox, mara, enemy])
        turns = TurnManager(floor, [fox, mara], Inventory(8), fox, Random(3))
        before = enemy.grid_pos
        outcome = turns.execute_player_action(MoveAction(fox, Direction.E))
        self.assertTrue(outcome.consumed_turn)
        self.assertEqual(turns.turn_count, 1)
        self.assertNotEqual(enemy.grid_pos, before)



    def test_leader_swaps_with_ally_and_updates_both_facings(self):
        from mystery_engine.core import Direction, Inventory
        from mystery_engine.dungeon import MoveAction, TurnManager
        floor = DungeonFloor.empty(7, 5)
        for y in range(1, 4):
            for x in range(1, 6):
                floor.set_floor(GridPos(x, y))
        fox = Character("fox", "Fox", Stats(30, 7, 4), party_member=True, leader=True, grid_pos=GridPos(2, 2), facing=Direction.N)
        mara = Character("mara", "Mara", Stats(25, 5, 3), party_member=True, grid_pos=GridPos(3, 2), facing=Direction.N)
        floor.entities.extend([fox, mara])
        turns = TurnManager(floor, [fox, mara], Inventory(8), fox, Random(3))

        outcome = turns.execute_player_action(MoveAction(fox, Direction.E))

        self.assertTrue(outcome.consumed_turn)
        self.assertEqual(fox.grid_pos, GridPos(3, 2))
        self.assertEqual(mara.grid_pos, GridPos(2, 2))
        self.assertEqual(fox.facing, Direction.E)
        self.assertEqual(mara.facing, Direction.W)

    def test_swapped_ally_does_not_take_second_ai_move(self):
        from mystery_engine.core import Direction, Inventory
        from mystery_engine.dungeon import MoveAction, TurnManager
        floor = DungeonFloor.empty(7, 5)
        for y in range(1, 4):
            for x in range(1, 6):
                floor.set_floor(GridPos(x, y))
        fox = Character("fox", "Fox", Stats(30, 7, 4), party_member=True, leader=True, grid_pos=GridPos(2, 2))
        mara = Character("mara", "Mara", Stats(25, 5, 3), party_member=True, grid_pos=GridPos(3, 2))
        floor.entities.extend([fox, mara])
        turns = TurnManager(floor, [fox, mara], Inventory(8), fox, Random(3))

        turns.execute_player_action(MoveAction(fox, Direction.E))

        self.assertEqual(mara.grid_pos, GridPos(2, 2))
        self.assertEqual(mara.facing, Direction.W)


class SaveTests(unittest.TestCase):
    def test_save_manager_uses_stable_ids(self):
        import json
        import tempfile
        from mystery_engine.core import PersistentGameState, SaveManager, StoryState, Wallet
        fox = Character("fox", "Fox", Stats(30, 5, 4), party_member=True, leader=True)
        bag = Inventory(5)
        item = ItemDefinition("salve", "Salve", "")
        bag.add(item)
        state = PersistentGameState("test", "0.1", [fox], bag, Inventory(10), Wallet(7, 11), StoryState({"x": True}, {}))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "save.json"
            SaveManager().dump(state, path)
            payload = json.loads(path.read_text())
        self.assertEqual(payload["game_id"], "test")
        self.assertEqual(payload["characters"][0]["id"], "fox")
        self.assertEqual(payload["bag"][0]["item_id"], "salve")


class ArchitectureTests(unittest.TestCase):
    def test_engine_never_imports_test_game(self):
        engine_root = SRC / "mystery_engine"
        offenders = []
        for path in engine_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("test_game"):
                            offenders.append(path)
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "").startswith("test_game"):
                        offenders.append(path)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
