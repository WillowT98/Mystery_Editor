from __future__ import annotations

import json
from pathlib import Path

from .world_assets import ExplorationSceneData


def load_exploration_scene(path: Path) -> ExplorationSceneData:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Exploration scene root must be a JSON object")
    return ExplorationSceneData.from_dict(data)


def save_exploration_scene(scene: ExplorationSceneData, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scene.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
