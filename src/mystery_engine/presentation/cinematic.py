from __future__ import annotations

from dataclasses import dataclass, field
import math

import pygame


@dataclass
class CinematicOverlay:
    fade_color: pygame.Color = field(default_factory=lambda: pygame.Color("black"))
    fade_alpha: float = 0.0
    fade_start_alpha: float = 0.0
    fade_target_alpha: float = 0.0
    fade_duration: float = 0.0
    fade_elapsed: float = 0.0
    fade_hold: bool = False
    banner_text: str | None = None
    banner_time: float = 0.0

    def start_fade(self, color: str = "black", duration: float = 0.4, to_alpha: float = 1.0, hold: bool = True) -> None:
        try:
            self.fade_color = pygame.Color(color)
        except ValueError:
            self.fade_color = pygame.Color("black")
        self.fade_start_alpha = self.fade_alpha
        self.fade_target_alpha = max(0.0, min(1.0, float(to_alpha)))
        self.fade_duration = max(0.0, float(duration))
        self.fade_elapsed = 0.0
        self.fade_hold = bool(hold)
        if self.fade_duration <= 0:
            self.fade_alpha = self.fade_target_alpha

    def show_banner(self, text: str, duration: float = 2.0) -> None:
        self.banner_text = text
        self.banner_time = max(0.0, float(duration))

    def update(self, dt: float) -> None:
        dt = max(0.0, dt)
        if self.fade_elapsed < self.fade_duration:
            self.fade_elapsed += dt
            t = 1.0 if self.fade_duration <= 0 else min(1.0, self.fade_elapsed / self.fade_duration)
            # Smoothstep avoids a harsh linear-looking fade.
            t = t * t * (3.0 - 2.0 * t)
            self.fade_alpha = self.fade_start_alpha + (self.fade_target_alpha - self.fade_start_alpha) * t
        elif not self.fade_hold and self.fade_alpha > 0:
            self.fade_alpha = max(0.0, self.fade_alpha - dt * 3.0)

        if self.banner_time > 0:
            self.banner_time = max(0.0, self.banner_time - dt)
            if self.banner_time <= 0:
                self.banner_text = None
