from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class DialogueLine:
    speaker: str
    text: str
    portrait_key: str | None = None
    expression: str = "neutral"


@dataclass
class DialogueSequence:
    lines: list[DialogueLine]
    on_complete: Callable[[], None] | None = None


class DialogueController:
    def __init__(self) -> None:
        self.sequence: DialogueSequence | None = None
        self.index: int = 0

    @property
    def active(self) -> bool:
        return self.sequence is not None

    @property
    def current(self) -> DialogueLine | None:
        if self.sequence is None or not self.sequence.lines:
            return None
        return self.sequence.lines[self.index]

    def start(self, sequence: DialogueSequence) -> None:
        self.sequence = sequence
        self.index = 0
        if not sequence.lines:
            self.finish()

    def advance(self) -> None:
        if self.sequence is None:
            return
        self.index += 1
        if self.index >= len(self.sequence.lines):
            self.finish()

    def finish(self) -> None:
        sequence = self.sequence
        self.sequence = None
        self.index = 0
        if sequence and sequence.on_complete:
            sequence.on_complete()
