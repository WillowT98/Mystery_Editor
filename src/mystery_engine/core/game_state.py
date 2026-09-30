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
    animation_name: str | None = None
    animation_override: bool = False
    animation_loop: bool | None = None


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
class DungeonActorState:
    id: str
    definition_id: str | None
    name: str
    hostile: bool
    x: int | None
    y: int | None
    facing: str = "S"
    incapacitated: bool = False
    max_hp: int = 1
    current_hp: int = 1
    attack: int = 0
    defense: int = 0
    resources: dict[str, int] = field(default_factory=dict)
    resistances: dict[str, float] = field(default_factory=dict)
    skill_charges: dict[str, int | None] = field(default_factory=dict)
    skill_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DungeonGroundItemState:
    item_id: str
    x: int
    y: int


@dataclass
class DungeonState:
    dungeon_id: str
    floor_number: int
    width: int
    height: int
    tiles: list[list[dict[str, Any]]]
    rooms: list[list[int]] = field(default_factory=list)
    player_spawn: tuple[int, int] | None = None
    stairs_pos: tuple[int, int] | None = None
    tileset: str = "dungeon"
    music: str | None = None
    music_volume: float = 1.0
    dungeon_name: str = "Dungeon"
    generation_profile: str = "default"
    actors: list[DungeonActorState] = field(default_factory=list)
    ground_items: list[DungeonGroundItemState] = field(default_factory=list)
    discovered: list[tuple[int, int]] = field(default_factory=list)
    visible: list[tuple[int, int]] = field(default_factory=list)
    turn_count: int = 0
    rng_state: Any = None


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
    dungeon: DungeonState | None = None

    @property
    def leader(self) -> Character:
        leader = next((c for c in self.party if c.leader), None)
        if leader is None:
            raise RuntimeError("Party has no leader")
        return leader


class SaveManager:
    """Stable-ID JSON serializer. Game definitions reconstruct content objects."""

    SAVE_FORMAT = 3

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
            "dungeon": self._dungeon_payload(state.dungeon),
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
        if actor.animation_name is not None:
            data["animation_name"] = actor.animation_name
        if actor.animation_override:
            data["animation_override"] = True
        if actor.animation_loop is not None:
            data["animation_loop"] = actor.animation_loop
        return data

    @staticmethod
    def _dungeon_actor_payload(actor: DungeonActorState) -> dict[str, Any]:
        return {
            "id": actor.id,
            "definition_id": actor.definition_id,
            "name": actor.name,
            "hostile": actor.hostile,
            "position": ([actor.x, actor.y] if actor.x is not None and actor.y is not None else None),
            "facing": actor.facing,
            "incapacitated": actor.incapacitated,
            "stats": {
                "max_hp": actor.max_hp,
                "current_hp": actor.current_hp,
                "attack": actor.attack,
                "defense": actor.defense,
            },
            "resources": actor.resources,
            "resistances": actor.resistances,
            "skill_charges": actor.skill_charges,
            "skill_ids": actor.skill_ids,
            "metadata": actor.metadata,
        }

    @classmethod
    def _dungeon_payload(cls, dungeon: DungeonState | None) -> dict[str, Any] | None:
        if dungeon is None:
            return None
        return {
            "dungeon_id": dungeon.dungeon_id,
            "floor_number": dungeon.floor_number,
            "width": dungeon.width,
            "height": dungeon.height,
            "tiles": dungeon.tiles,
            "rooms": dungeon.rooms,
            "player_spawn": list(dungeon.player_spawn) if dungeon.player_spawn else None,
            "stairs_pos": list(dungeon.stairs_pos) if dungeon.stairs_pos else None,
            "tileset": dungeon.tileset,
            "music": dungeon.music,
            "music_volume": dungeon.music_volume,
            "dungeon_name": dungeon.dungeon_name,
            "generation_profile": dungeon.generation_profile,
            "actors": [cls._dungeon_actor_payload(actor) for actor in dungeon.actors],
            "ground_items": [
                {"item_id": item.item_id, "x": item.x, "y": item.y}
                for item in dungeon.ground_items
            ],
            "memory": {
                "discovered": [list(pos) for pos in dungeon.discovered],
                "visible": [list(pos) for pos in dungeon.visible],
            },
            "turn_count": dungeon.turn_count,
            "rng_state": dungeon.rng_state,
        }

    def load_raw(self, path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Save file root must be a JSON object.")
        return data
