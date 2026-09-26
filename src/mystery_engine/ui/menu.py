from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


ChildrenFactory = Callable[[], list["MenuEntry"]]


@dataclass
class MenuEntry:
    label: str
    action: Callable[[], None] | None = None
    children: list["MenuEntry"] | ChildrenFactory | None = None
    enabled: bool = True
    detail: str = ""

    def resolve_children(self) -> list["MenuEntry"]:
        if callable(self.children):
            return self.children()
        return list(self.children or [])


@dataclass
class MenuLevel:
    title: str
    entries: list[MenuEntry]
    selected: int = 0

    def normalize(self) -> None:
        if not self.entries:
            self.selected = 0
            return
        self.selected %= len(self.entries)


class MenuController:
    def __init__(self) -> None:
        self.stack: list[MenuLevel] = []

    @property
    def active(self) -> bool:
        return bool(self.stack)

    @property
    def current(self) -> MenuLevel | None:
        return self.stack[-1] if self.stack else None

    def open(self, title: str, entries: list[MenuEntry]) -> None:
        self.stack = [MenuLevel(title, entries)]
        self._select_enabled(1)

    def close(self) -> None:
        self.stack.clear()

    def move(self, delta: int) -> None:
        level = self.current
        if level is None or not level.entries:
            return
        original = level.selected
        for _ in range(len(level.entries)):
            level.selected = (level.selected + delta) % len(level.entries)
            if level.entries[level.selected].enabled:
                return
        level.selected = original

    def confirm(self) -> None:
        level = self.current
        if level is None or not level.entries:
            return
        entry = level.entries[level.selected]
        if not entry.enabled:
            return
        children = entry.resolve_children()
        if children:
            self.stack.append(MenuLevel(entry.label, children))
            self._select_enabled(1)
            return
        if entry.action:
            entry.action()

    def back(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()
        else:
            self.close()

    def _select_enabled(self, delta: int) -> None:
        level = self.current
        if level is None or not level.entries:
            return
        if level.entries[level.selected].enabled:
            return
        self.move(delta)
