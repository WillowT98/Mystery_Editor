from __future__ import annotations

from pathlib import Path
import sys
from random import Random
from types import SimpleNamespace

import pygame

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.config import EngineConfig
from mystery_engine.core import GameMode, GridPos, ProjectileEvent
from mystery_engine.core.game import MysteryGame
from mystery_engine.input import DungeonDirectionalInput
from mystery_engine.dungeon import DungeonFloor
from mystery_engine.dungeon.actions import SkillAction
from mystery_engine.dungeon.turns import TurnManager
from mystery_engine.presentation import ProjectileAnimation
from test_game.content import make_fox, make_mara, make_mossling, make_starting_bag


def _open_floor(width=8, height=8):
    floor = DungeonFloor.empty(width, height)
    for y in range(height):
        for x in range(width):
            floor.set_floor(GridPos(x, y))
    return floor


def test_projectile_animation_advances_travel_then_impact_frames():
    event = ProjectileEvent(
        source_id="mara",
        target_id="enemy",
        source_pos=GridPos(1, 1),
        target_pos=GridPos(5, 1),
        projectile_key="spark",
        hit=True,
    )
    animation = ProjectileAnimation.from_event(event)
    assert animation.frame_index == 0
    animation.update(animation.travel_duration * 0.55)
    assert animation.frame_index in {2, 3}
    animation.update(animation.travel_duration)
    assert animation.in_impact
    assert animation.frame_index in {4, 5}
    animation.update(animation.impact_duration)
    assert animation.finished


def test_missed_projectile_has_no_impact_phase():
    event = ProjectileEvent(
        source_id="wisp",
        target_id="fox",
        source_pos=GridPos(1, 1),
        target_pos=GridPos(4, 1),
        projectile_key="needle",
        hit=False,
    )
    animation = ProjectileAnimation.from_event(event)
    animation.update(animation.travel_duration + 0.01)
    assert animation.finished
    assert not animation.in_impact


def test_ranged_skill_emits_projectile_event_instead_of_immediate_projectile_sfx():
    floor = _open_floor()
    fox = make_fox()
    mara = make_mara()
    enemy = make_mossling("mossling_test")
    fox.grid_pos = GridPos(1, 2)
    mara.grid_pos = GridPos(1, 1)
    enemy.grid_pos = GridPos(4, 1)
    floor.entities.extend([fox, mara, enemy])

    turns = TurnManager(floor, [fox, mara], make_starting_bag(), fox, Random(1))
    messages: list[str] = []
    sounds: list[str] = []
    projectiles = []
    spark = mara.skill("mara_spark")
    assert spark is not None

    consumed = turns._resolve_action(
        SkillAction(mara, spark, enemy),
        messages,
        sounds,
        projectiles,
    )

    assert consumed
    assert len(projectiles) == 1
    event = projectiles[0]
    assert event.projectile_key == "spark"
    assert event.source_pos == GridPos(1, 1)
    assert event.target_pos == GridPos(4, 1)
    assert event.launch_sfx_cue == "magic.bolt_launch"
    assert "magic.bolt_launch" not in sounds
    assert "magic.bolt_impact" not in sounds


def test_locked_dungeon_input_discards_held_and_buffered_movement():
    directional = DungeonDirectionalInput(EngineConfig())
    now = 1.0
    directional.feed(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d), now)
    assert pygame.K_d in directional.held

    directional.suspend_until_release()
    assert directional.poll(now + 1.0, sprint=False) is None

    # Repeat/down events while locked do not become queued movement.
    directional.feed_locked(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d))
    assert directional.poll(now + 2.0, sprint=False) is None

    # Releasing clears the lock; a fresh press can move normally.
    directional.feed_locked(pygame.event.Event(pygame.KEYUP, key=pygame.K_d))
    directional.feed(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d), now + 3.0)
    direction = directional.poll(now + 3.0 + directional.config.dungeon_diagonal_grace, sprint=False)
    assert direction is not None
    assert direction.dx == 1 and direction.dy == 0


def test_projectile_animation_requires_visible_on_screen_attacker():
    game = MysteryGame.__new__(MysteryGame)
    game.mode = GameMode.DUNGEON
    game.config = EngineConfig()
    leader = SimpleNamespace(grid_pos=GridPos(10, 10))
    game.state = SimpleNamespace(leader=leader)

    visible_source = GridPos(12, 10)
    far_source = GridPos(40, 10)
    game.dungeon = SimpleNamespace(
        turns=SimpleNamespace(
            memory=SimpleNamespace(visible={visible_source, far_source})
        )
    )

    visible_event = ProjectileEvent(
        source_id="mara",
        target_id="enemy",
        source_pos=visible_source,
        target_pos=GridPos(14, 10),
        projectile_key="spark",
    )
    far_event = ProjectileEvent(
        source_id="wisp",
        target_id="fox",
        source_pos=far_source,
        target_pos=GridPos(10, 10),
        projectile_key="needle",
    )
    hidden_event = ProjectileEvent(
        source_id="hidden",
        target_id="fox",
        source_pos=GridPos(11, 11),
        target_pos=GridPos(10, 10),
        projectile_key="needle",
    )

    assert game._projectile_source_is_visible(visible_event)
    assert not game._projectile_source_is_visible(far_event)
    assert not game._projectile_source_is_visible(hidden_event)
