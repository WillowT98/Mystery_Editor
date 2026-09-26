from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SoundCue:
    """One semantic sound cue backed by one or more interchangeable files."""

    id: str
    label: str
    category: str
    variants: tuple[str, ...]
    volume: float = 1.0
    cooldown: float = 0.0
    loop: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "SoundCue":
        variants = tuple(str(v).replace("\\", "/") for v in data.get("variants", []))
        if not variants:
            raise ValueError(f"Sound cue {data.get('id', '<unknown>')} has no variants")
        return cls(
            id=str(data["id"]),
            label=str(data.get("label") or data["id"]),
            category=str(data.get("category") or "Other"),
            variants=variants,
            volume=max(0.0, min(1.0, float(data.get("volume", 1.0)))),
            cooldown=max(0.0, float(data.get("cooldown", 0.0))),
            loop=bool(data.get("loop", False)),
        )


class SoundCueCatalog:
    """Data-only cue catalog shared by runtime and editor."""

    def __init__(self, cues: Iterable[SoundCue] = ()) -> None:
        self.cues = {cue.id: cue for cue in cues}

    @classmethod
    def load(cls, path: Path | None) -> "SoundCueCatalog":
        if path is None or not Path(path).exists():
            return cls()
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            rows = payload.get("cues", []) if isinstance(payload, dict) else payload
            return cls(SoundCue.from_dict(row) for row in rows)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return cls()

    def get(self, cue_id: str | None) -> SoundCue | None:
        if not cue_id:
            return None
        return self.cues.get(cue_id)

    def all(self) -> list[SoundCue]:
        return sorted(self.cues.values(), key=lambda cue: (cue.category.lower(), cue.label.lower()))

    def by_category(self, category: str) -> list[SoundCue]:
        return sorted(
            (cue for cue in self.cues.values() if cue.category.lower() == category.lower()),
            key=lambda cue: cue.label.lower(),
        )

    def categories(self) -> list[str]:
        return sorted({cue.category for cue in self.cues.values()}, key=str.lower)
