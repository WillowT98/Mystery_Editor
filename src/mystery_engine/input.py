from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pygame

from .config import EngineConfig
from .core import Direction, Vec2


_MOVE_KEYS = {
    pygame.K_w: (0, -1),
    pygame.K_s: (0, 1),
    pygame.K_a: (-1, 0),
    pygame.K_d: (1, 0),
}


@dataclass
class FrameInput:
    move: Vec2
    sprint: bool
    interact: bool = False
    menu: bool = False
    cancel: bool = False
    fullscreen: bool = False


class DungeonDirectionalInput:
    """Turns WASD key chords into one of eight discrete directions."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.held: set[int] = set()
        self.pending_keys: set[int] = set()
        self.pending_since: float | None = None
        self.force_emit = False
        self.last_emit: float | None = None
        self.repeat_started = False
        self.dash_stopped = False
        self.blocked_until_release: set[int] = set()

    def reset(self) -> None:
        self.held.clear()
        self.pending_keys.clear()
        self.pending_since = None
        self.force_emit = False
        self.last_emit = None
        self.repeat_started = False
        self.dash_stopped = False
        self.blocked_until_release.clear()

    def suspend_until_release(self) -> None:
        """Discard movement during a temporary gameplay lock.

        Keys that were held when the lock began, or pressed while locked, must
        be released before they can produce movement again. This prevents a
        projectile/cutscene pause from turning held-key repeat into buffered
        dungeon steps when control returns.
        """
        self.blocked_until_release.update(self.held)
        self.held.clear()
        self.pending_keys.clear()
        self.pending_since = None
        self.force_emit = False
        self.last_emit = None
        self.repeat_started = False
        self.dash_stopped = False

    def feed_locked(self, event: pygame.event.Event) -> None:
        """Track releases while ignoring movement presses during a lock."""
        if getattr(event, "key", None) not in _MOVE_KEYS:
            return
        if event.type == pygame.KEYDOWN:
            self.blocked_until_release.add(event.key)
        elif event.type == pygame.KEYUP:
            self.held.discard(event.key)
            self.blocked_until_release.discard(event.key)

    def stop_dash(self) -> None:
        self.dash_stopped = True

    def feed(self, event: pygame.event.Event, now: float) -> None:
        if event.type == pygame.KEYDOWN and event.key in _MOVE_KEYS:
            if event.key in self.blocked_until_release:
                return
            if event.key not in self.held:
                self.held.add(event.key)
                if self.pending_since is None:
                    self.pending_since = now
                    self.pending_keys = set(self.held)
                    self.force_emit = False
                    self.dash_stopped = False
                else:
                    self.pending_keys.add(event.key)
                    if now - self.pending_since <= self.config.dungeon_diagonal_grace:
                        self.force_emit = True
        elif event.type == pygame.KEYUP and event.key in _MOVE_KEYS:
            self.held.discard(event.key)
            self.blocked_until_release.discard(event.key)

    def poll(self, now: float, sprint: bool) -> Direction | None:
        if self.pending_since is not None:
            if self.force_emit or now - self.pending_since >= self.config.dungeon_diagonal_grace:
                direction = self._direction_from_keys(self.pending_keys)
                self.pending_keys.clear()
                self.pending_since = None
                self.force_emit = False
                self.last_emit = now
                self.repeat_started = False
                return direction
            return None

        if not sprint:
            self.dash_stopped = False
        if sprint and self.dash_stopped:
            return None

        direction = self._direction_from_keys(self.held)
        if direction is None:
            self.last_emit = None
            self.repeat_started = False
            return None
        if self.last_emit is None:
            # This can occur if focus was regained while a key is already held.
            self.last_emit = now
            return direction

        if sprint:
            interval = self.config.dungeon_dash_interval
            if now - self.last_emit >= interval:
                self.last_emit = now
                self.repeat_started = True
                return direction
            return None

        wait = self.config.dungeon_repeat_interval if self.repeat_started else self.config.dungeon_repeat_delay
        if now - self.last_emit >= wait:
            self.last_emit = now
            self.repeat_started = True
            return direction
        return None

    @staticmethod
    def _direction_from_keys(keys: set[int]) -> Direction | None:
        x = int(pygame.K_d in keys) - int(pygame.K_a in keys)
        y = int(pygame.K_s in keys) - int(pygame.K_w in keys)
        return Direction.from_axes(x, y)


class InputManager:
    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.dungeon = DungeonDirectionalInput(config)

    def frame_input(self, events: Iterable[pygame.event.Event]) -> FrameInput:
        interact = menu = cancel = fullscreen = False
        for event in events:
            if event.type != pygame.KEYDOWN or getattr(event, "repeat", False):
                continue
            if event.key == pygame.K_SPACE:
                interact = True
            elif event.key == pygame.K_e:
                menu = True
            elif event.key == pygame.K_ESCAPE:
                cancel = True
            elif event.key == pygame.K_F11:
                fullscreen = True

        keys = pygame.key.get_pressed()
        x = int(keys[pygame.K_d]) - int(keys[pygame.K_a])
        y = int(keys[pygame.K_s]) - int(keys[pygame.K_w])
        move = Vec2(float(x), float(y))
        if move.length() > 0:
            move = move.normalized()
        return FrameInput(
            move=move,
            sprint=bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]),
            interact=interact,
            menu=menu,
            cancel=cancel,
            fullscreen=fullscreen,
        )
