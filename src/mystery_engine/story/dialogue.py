from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class DialogueLine:
    speaker: str
    text: str
    portrait_key: str | None = None
    expression: str = "neutral"
    voice_cue: str | None = None


@dataclass
class DialogueSequence:
    lines: list[DialogueLine]
    on_complete: Callable[[], None] | None = None


class DialogueController:
    def __init__(self, *, chars_per_second: float = 42.0) -> None:
        self.sequence: DialogueSequence | None = None
        self.index: int = 0
        self.chars_per_second = max(1.0, float(chars_per_second))
        self.reveal_count: int = 0
        self._reveal_progress: float = 0.0

    @property
    def active(self) -> bool:
        return self.sequence is not None

    @property
    def current(self) -> DialogueLine | None:
        if self.sequence is None or not self.sequence.lines:
            return None
        return self.sequence.lines[self.index]

    @property
    def visible_text(self) -> str:
        line = self.current
        if line is None:
            return ""
        return line.text[: self.reveal_count]

    @property
    def fully_revealed(self) -> bool:
        line = self.current
        return line is None or self.reveal_count >= len(line.text)

    def update(self, dt: float) -> str:
        """Advance the typewriter and return newly revealed text."""
        line = self.current
        if line is None or self.fully_revealed:
            return ""
        previous = self.reveal_count
        self._reveal_progress += max(0.0, dt) * self.chars_per_second
        self.reveal_count = min(len(line.text), int(self._reveal_progress))
        return line.text[previous:self.reveal_count]

    def reveal_all(self) -> None:
        line = self.current
        if line is None:
            return
        self.reveal_count = len(line.text)
        self._reveal_progress = float(self.reveal_count)

    def _reset_reveal(self) -> None:
        self.reveal_count = 0
        self._reveal_progress = 0.0

    def start(self, sequence: DialogueSequence) -> None:
        self.sequence = sequence
        self.index = 0
        self._reset_reveal()
        if not sequence.lines:
            self.finish()

    def advance(self) -> None:
        if self.sequence is None:
            return
        self.index += 1
        if self.index >= len(self.sequence.lines):
            self.finish()
        else:
            self._reset_reveal()

    def finish(self) -> None:
        sequence = self.sequence
        self.sequence = None
        self.index = 0
        self._reset_reveal()
        if sequence and sequence.on_complete:
            sequence.on_complete()
