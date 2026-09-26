from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from mystery_engine.story import ExplorationSceneData


@dataclass
class SnapshotHistory:
    limit: int = 100
    undo_stack: list[dict] = field(default_factory=list)
    redo_stack: list[dict] = field(default_factory=list)

    @staticmethod
    def snapshot(scene: ExplorationSceneData) -> dict:
        return deepcopy(scene.to_dict())

    def remember(self, before: dict) -> None:
        self.undo_stack.append(deepcopy(before))
        if len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self, scene: ExplorationSceneData) -> ExplorationSceneData:
        if not self.undo_stack:
            return scene
        self.redo_stack.append(self.snapshot(scene))
        return ExplorationSceneData.from_dict(self.undo_stack.pop())

    def redo(self, scene: ExplorationSceneData) -> ExplorationSceneData:
        if not self.redo_stack:
            return scene
        self.undo_stack.append(self.snapshot(scene))
        return ExplorationSceneData.from_dict(self.redo_stack.pop())
