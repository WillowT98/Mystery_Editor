from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from mystery_engine.core import StoryState
from .dialogue import DialogueController, DialogueLine, DialogueSequence


@dataclass
class SceneContext:
    story: StoryState
    dialogue: DialogueController
    call: Callable[[str, dict], None] | None = None


class SceneCommand(Protocol):
    def begin(self, context: SceneContext) -> None: ...
    def update(self, context: SceneContext, dt: float) -> bool: ...


@dataclass
class Say:
    line: DialogueLine
    _started: bool = False

    def begin(self, context: SceneContext) -> None:
        self._started = True
        context.dialogue.start(DialogueSequence([self.line]))

    def update(self, context: SceneContext, dt: float) -> bool:
        return self._started and not context.dialogue.active


@dataclass
class SetFlag:
    name: str
    value: bool = True

    def begin(self, context: SceneContext) -> None:
        context.story.set_flag(self.name, self.value)

    def update(self, context: SceneContext, dt: float) -> bool:
        return True


@dataclass
class Wait:
    duration: float
    elapsed: float = 0.0

    def begin(self, context: SceneContext) -> None:
        self.elapsed = 0.0

    def update(self, context: SceneContext, dt: float) -> bool:
        self.elapsed += dt
        return self.elapsed >= self.duration


@dataclass
class Call:
    name: str
    payload: dict

    def begin(self, context: SceneContext) -> None:
        if context.call:
            context.call(self.name, self.payload)

    def update(self, context: SceneContext, dt: float) -> bool:
        return True


class SceneRunner:
    def __init__(self, context: SceneContext) -> None:
        self.context = context
        self.commands: list[SceneCommand] = []
        self.index = 0
        self.running = False
        self._begun = False

    def start(self, commands: list[SceneCommand]) -> None:
        self.commands = commands
        self.index = 0
        self.running = bool(commands)
        self._begun = False

    def update(self, dt: float) -> None:
        if not self.running:
            return
        command = self.commands[self.index]
        if not self._begun:
            command.begin(self.context)
            self._begun = True
        if command.update(self.context, dt):
            self.index += 1
            self._begun = False
            if self.index >= len(self.commands):
                self.running = False
