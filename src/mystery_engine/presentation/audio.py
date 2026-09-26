from __future__ import annotations

import json
from pathlib import Path

import pygame


class MusicController:
    """Small looping-BGM controller for scene music.

    Scene volume and player volume are independent: the final SDL_mixer volume is
    `scene_gain * master_volume`. The latter is persisted per game so editor
    playtests do not reset it every launch.
    """

    def __init__(
        self,
        asset_root: Path | None,
        game_id: str,
        *,
        default_volume: float = 0.70,
        settings_path: Path | None = None,
    ) -> None:
        self.asset_root = Path(asset_root) if asset_root else None
        self.game_id = game_id
        self.master_volume = self._clamp(default_volume)
        self.scene_gain = 1.0
        self.current_track: str | None = None
        self.available = False
        self.last_error: str | None = None
        self.settings_path = settings_path or (Path.home() / ".mystery_engine" / game_id / "settings.json")
        self._load_settings()

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @property
    def effective_volume(self) -> float:
        return self._clamp(self.master_volume * self.scene_gain)

    def initialize(self) -> None:
        self.last_error = None
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            self.available = True
            pygame.mixer.music.set_volume(self.effective_volume)
        except pygame.error as exc:
            self.available = False
            self.last_error = f"Audio unavailable: {exc}"

    def play_scene(self, track: str | None, scene_gain: float = 1.0, *, fade_ms: int = 350) -> str | None:
        """Start or update scene music. Returns an error string on failure."""
        self.scene_gain = self._clamp(scene_gain)
        if not self.available:
            return self.last_error
        if not track:
            self.stop(fade_ms=fade_ms)
            return None

        normalized = str(track).replace("\\", "/")
        path = self._resolve(normalized)
        if path is None or not path.exists():
            self.stop(fade_ms=fade_ms)
            self.last_error = f"Music file not found: {normalized}"
            return self.last_error

        # Do not restart a track simply because a linked scene uses it too.
        if self.current_track == normalized and pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(self.effective_volume)
            return None

        try:
            pygame.mixer.music.fadeout(max(0, fade_ms))
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(self.effective_volume)
            pygame.mixer.music.play(loops=-1, fade_ms=max(0, fade_ms))
            self.current_track = normalized
            self.last_error = None
            return None
        except pygame.error as exc:
            self.current_track = None
            self.last_error = f"Could not play {path.name}: {exc}"
            return self.last_error

    def stop(self, *, fade_ms: int = 250) -> None:
        if not self.available:
            self.current_track = None
            return
        try:
            if fade_ms > 0:
                pygame.mixer.music.fadeout(fade_ms)
            else:
                pygame.mixer.music.stop()
        except pygame.error:
            pass
        self.current_track = None

    def set_master_volume(self, value: float, *, persist: bool = True) -> None:
        self.master_volume = self._clamp(value)
        if self.available:
            try:
                pygame.mixer.music.set_volume(self.effective_volume)
            except pygame.error:
                pass
        if persist:
            self._save_settings()

    def _resolve(self, track: str) -> Path | None:
        path = Path(track)
        if path.is_absolute():
            return path
        if self.asset_root is None:
            return None
        return self.asset_root / path

    def _load_settings(self) -> None:
        try:
            if self.settings_path.exists():
                payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
                self.master_volume = self._clamp(float(payload.get("music_volume", self.master_volume)))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def _save_settings(self) -> None:
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"music_volume": round(self.master_volume, 3)}
            self.settings_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError:
            # Volume still changes for this run even if settings cannot be written.
            pass
