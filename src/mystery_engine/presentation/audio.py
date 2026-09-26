from __future__ import annotations

import json
from pathlib import Path
from random import Random

import pygame

from .sfx import SoundCueCatalog


class MusicController:
    """Music + semantic SFX controller.

    BGM continues to use SDL_mixer's dedicated music stream. Short effects and
    ambience use mixer Sound channels, allowing them to overlap music and each
    other. Game/editor data refers to semantic cue IDs rather than filenames.
    """

    def __init__(
        self,
        asset_root: Path | None,
        game_id: str,
        *,
        default_volume: float = 0.70,
        default_sfx_volume: float = 0.80,
        settings_path: Path | None = None,
        cue_catalog_path: Path | None = None,
    ) -> None:
        self.asset_root = Path(asset_root) if asset_root else None
        self.game_id = game_id
        self.master_volume = self._clamp(default_volume)
        self.sfx_volume = self._clamp(default_sfx_volume)
        self.scene_gain = 1.0
        self.current_track: str | None = None
        self.current_ambience: str | None = None
        self.ambience_gain = 1.0
        self.available = False
        self.last_error: str | None = None
        self.settings_path = settings_path or (Path.home() / ".mystery_engine" / game_id / "settings.json")
        if cue_catalog_path is None and self.asset_root is not None:
            cue_catalog_path = self.asset_root / "sfx_cues.json"
        self.cues = SoundCueCatalog.load(cue_catalog_path)
        self._sound_cache: dict[str, pygame.mixer.Sound] = {}
        self._last_played_ms: dict[str, int] = {}
        self._ambience_channel: pygame.mixer.Channel | None = None
        self._rng = Random()
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
            pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))
            self._ambience_channel = pygame.mixer.Channel(0)
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

    def _load_sound(self, relative: str) -> pygame.mixer.Sound | None:
        normalized = relative.replace("\\", "/")
        if normalized in self._sound_cache:
            return self._sound_cache[normalized]
        path = self._resolve(normalized)
        if path is None or not path.exists():
            self.last_error = f"Sound file not found: {normalized}"
            return None
        try:
            sound = pygame.mixer.Sound(str(path))
        except pygame.error as exc:
            self.last_error = f"Could not load {path.name}: {exc}"
            return None
        self._sound_cache[normalized] = sound
        return sound

    def play_sfx(self, cue_id: str | None, *, gain: float = 1.0) -> bool:
        """Play one random variant of a semantic cue."""
        if not self.available or not cue_id:
            return False
        cue = self.cues.get(cue_id)
        if cue is None:
            return False
        now = pygame.time.get_ticks()
        last = self._last_played_ms.get(cue.id)
        if last is not None and now - last < round(cue.cooldown * 1000):
            return False
        variant = self._rng.choice(cue.variants)
        sound = self._load_sound(variant)
        if sound is None:
            return False
        channel = pygame.mixer.find_channel(True)
        if channel is None:
            return False
        channel.set_volume(self._clamp(self.sfx_volume * cue.volume * gain))
        channel.play(sound)
        self._last_played_ms[cue.id] = now
        return True

    def play_ambience(self, cue_id: str | None, gain: float = 1.0) -> bool:
        """Loop a semantic ambience cue on its own channel."""
        self.ambience_gain = self._clamp(gain)
        if not self.available:
            self.current_ambience = None
            return False
        if not cue_id:
            self.stop_ambience()
            return True
        cue = self.cues.get(cue_id)
        if cue is None:
            self.stop_ambience()
            return False
        if self.current_ambience == cue_id and self._ambience_channel and self._ambience_channel.get_busy():
            self._ambience_channel.set_volume(self._clamp(self.sfx_volume * cue.volume * self.ambience_gain))
            return True
        variant = self._rng.choice(cue.variants)
        sound = self._load_sound(variant)
        if sound is None:
            return False
        channel = self._ambience_channel or pygame.mixer.Channel(0)
        channel.stop()
        channel.set_volume(self._clamp(self.sfx_volume * cue.volume * self.ambience_gain))
        channel.play(sound, loops=-1)
        self._ambience_channel = channel
        self.current_ambience = cue_id
        return True

    def stop_ambience(self) -> None:
        if self._ambience_channel is not None:
            try:
                self._ambience_channel.stop()
            except pygame.error:
                pass
        self.current_ambience = None

    def set_master_volume(self, value: float, *, persist: bool = True) -> None:
        self.master_volume = self._clamp(value)
        if self.available:
            try:
                pygame.mixer.music.set_volume(self.effective_volume)
            except pygame.error:
                pass
        if persist:
            self._save_settings()

    def set_sfx_volume(self, value: float, *, persist: bool = True) -> None:
        self.sfx_volume = self._clamp(value)
        if self.current_ambience:
            cue = self.cues.get(self.current_ambience)
            if cue is not None and self._ambience_channel is not None:
                self._ambience_channel.set_volume(self._clamp(self.sfx_volume * cue.volume * self.ambience_gain))
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
                self.sfx_volume = self._clamp(float(payload.get("sfx_volume", self.sfx_volume)))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def _save_settings(self) -> None:
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "music_volume": round(self.master_volume, 3),
                "sfx_volume": round(self.sfx_volume, 3),
            }
            self.settings_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
