from __future__ import annotations

from dataclasses import dataclass

from mystery_engine.core import ProjectileEvent


@dataclass
class ProjectileAnimation:
    event: ProjectileEvent
    travel_duration: float
    impact_duration: float = 0.16
    elapsed: float = 0.0
    impact_sound_played: bool = False

    @classmethod
    def from_event(cls, event: ProjectileEvent) -> "ProjectileAnimation":
        distance = max(1, event.source_pos.chebyshev(event.target_pos))
        # Long shots remain readable without making a full enemy turn feel slow.
        travel = min(0.55, max(0.20, 0.10 + distance * 0.075))
        return cls(event=event, travel_duration=travel)

    @property
    def in_impact(self) -> bool:
        return self.event.hit and self.elapsed >= self.travel_duration

    @property
    def finished(self) -> bool:
        total = self.travel_duration + (self.impact_duration if self.event.hit else 0.0)
        return self.elapsed >= total

    @property
    def progress(self) -> float:
        if self.travel_duration <= 0:
            return 1.0
        return min(1.0, self.elapsed / self.travel_duration)

    @property
    def frame_index(self) -> int:
        if self.in_impact:
            t = min(0.999, (self.elapsed - self.travel_duration) / max(0.001, self.impact_duration))
            return 4 + min(1, int(t * 2))
        return min(3, int(self.progress * 4))

    def update(self, dt: float) -> None:
        self.elapsed += max(0.0, dt)
