from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineConfig:
    logical_width: int = 1920
    logical_height: int = 1080
    dungeon_view_width: int = 1440
    sidebar_width: int = 480
    tile_px: int = 64
    map_panel_px: int = 432
    dialogue_height: int = 270
    portrait_px: int = 160
    dungeon_diagonal_grace: float = 0.05
    dungeon_repeat_delay: float = 0.18
    dungeon_repeat_interval: float = 0.105
    dungeon_dash_interval: float = 0.055
    exploration_walk_speed: float = 240.0
    exploration_sprint_speed: float = 390.0
    interaction_range: float = 110.0
    target_fps: int = 60

    @property
    def logical_size(self) -> tuple[int, int]:
        return (self.logical_width, self.logical_height)

    @property
    def dungeon_view_size(self) -> tuple[int, int]:
        return (self.dungeon_view_width, self.logical_height)
