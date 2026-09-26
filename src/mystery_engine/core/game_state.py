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
class PersistentGameState:
    game_id: str
    game_version: str
    party: list[Character]
    bag: Inventory
    storage: Inventory
    wallet: Wallet
    story: StoryState = field(default_factory=StoryState)

    @property
    def leader(self) -> Character:
        leader = next((c for c in self.party if c.leader), None)
        if leader is None:
            raise RuntimeError("Party has no leader")
        return leader


class SaveManager:
    """Small stable-ID JSON serializer. Game definitions reconstruct content objects."""

    def __init__(self, engine_version: str = "0.1.0") -> None:
        self.engine_version = engine_version

    def dump(self, state: PersistentGameState, path: Path) -> None:
        payload = {
            "engine_version": self.engine_version,
            "game_id": state.game_id,
            "game_version": state.game_version,
            "story": {"flags": state.story.flags, "variables": state.story.variables},
            "wallet": {"carried": state.wallet.carried, "stored": state.wallet.stored},
            "bag": [{"item_id": s.item.id, "quantity": s.quantity} for s in state.bag.stacks],
            "storage": [{"item_id": s.item.id, "quantity": s.quantity} for s in state.storage.stacks],
            "characters": [
                {
                    "id": c.id,
                    "hp": c.stats.current_hp,
                    "resources": c.resources,
                    "skill_charges": {s.definition.id: s.charges for s in c.skills},
                }
                for c in state.party
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_raw(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
