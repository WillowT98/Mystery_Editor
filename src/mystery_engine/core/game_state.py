from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any

from .inventory import Inventory, Wallet
from .models import Character


@dataclass
class StoryState:
    flags: dict[str, bool] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)

    def flag(self, name: str) -> bool:
        return bool(self.flags.get(name, False))

    def set_flag(self, name: str, value: bool = True) -> None:
        self.flags[name] = value


@dataclass
class SceneActorState:
    x: float
    y: float
    facing: str = "S"
    enabled: bool = True
    sprite_key: str | None = None


@dataclass
class SceneObjectState:
    enabled: bool = True


@dataclass
class SceneState:
    actors: dict[str, SceneActorState] = field(default_factory=dict)
    objects: dict[str, SceneObjectState] = field(default_factory=dict)


@dataclass
class PersistentWorldState:
    current_scene: str | None = None
    party_positions: dict[str, SceneActorState] = field(default_factory=dict)
    scenes: dict[str, SceneState] = field(default_factory=dict)


@dataclass
class PersistentGameState:
    game_id: str
    game_version: str
    party: list[Character]
    bag: Inventory
    storage: Inventory
    wallet: Wallet
    story: StoryState = field(default_factory=StoryState)
    world: PersistentWorldState = field(default_factory=PersistentWorldState)

    @property
    def leader(self) -> Character:
        leader = next((c for c in self.party if c.leader), None)
        if leader is None:
            raise RuntimeError("Party has no leader")
        return leader


class SaveManager:
    """Stable-ID JSON serializer. Game definitions reconstruct content objects."""

    SAVE_FORMAT = 2

    def __init__(self, engine_version: str = "0.1.0") -> None:
        self.engine_version = engine_version

    def dump(self, state: PersistentGameState, path: Path) -> None:
        payload = {
            "format": self.SAVE_FORMAT,
            "engine_version": self.engine_version,
            "game_id": state.game_id,
            "game_version": state.game_version,
            "story": {"flags": state.story.flags, "variables": state.story.variables},
            "wallet": {"carried": state.wallet.carried, "stored": state.wallet.stored},
            "inventory_capacities": {"bag": state.bag.capacity, "storage": state.storage.capacity},
            "bag": [{"item_id": s.item.id, "quantity": s.quantity} for s in state.bag.stacks],
            "storage": [{"item_id": s.item.id, "quantity": s.quantity} for s in state.storage.stacks],
            "characters": [
                {
                    "id": c.id,
                    "leader": c.leader,
                    "hp": c.stats.current_hp,
                    "resources": c.resources,
                    "ai_tactic": c.ai_tactic.value,
                    "skill_charges": {s.definition.id: s.charges for s in c.skills},
                }
                for c in state.party
            ],
            "world": {
                "current_scene": state.world.current_scene,
                "party_positions": {
                    actor_id: self._actor_state_payload(actor)
                    for actor_id, actor in state.world.party_positions.items()
                },
                "scenes": {
                    scene_id: {
                        "actors": {
                            actor_id: self._actor_state_payload(actor)
                            for actor_id, actor in scene.actors.items()
                        },
                        "objects": {
                            object_id: {"enabled": obj.enabled}
                            for object_id, obj in scene.objects.items()
                        },
                    }
                    for scene_id, scene in state.world.scenes.items()
                },
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _actor_state_payload(actor: SceneActorState) -> dict[str, Any]:
        data: dict[str, Any] = {
            "x": actor.x,
            "y": actor.y,
            "facing": actor.facing,
            "enabled": actor.enabled,
        }
        if actor.sprite_key is not None:
            data["sprite_key"] = actor.sprite_key
        return data

    def load_raw(self, path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Save file root must be a JSON object.")
        return data
