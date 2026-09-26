"""Reusable Mystery Dungeon-style story RPG engine.

The top-level package stays lightweight so simulation modules can be imported by
headless tools without initializing Pygame. ``MysteryGame`` is loaded lazily.
"""

from .config import EngineConfig

__all__ = ["EngineConfig", "MysteryGame"]


def __getattr__(name: str):
    if name == "MysteryGame":
        from .core.game import MysteryGame
        return MysteryGame
    raise AttributeError(name)
