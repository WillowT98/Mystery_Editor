from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import re
import shutil
from typing import Any

from mystery_engine.core import (
    AITactic,
    Character,
    ItemDefinition,
    RangePattern,
    SkillDefinition,
    SkillRuntime,
    Stats,
    TargetKind,
)
from mystery_engine.dungeon import DungeonDefinition, SpawnRule
from mystery_engine.localization import LocalizationEntry, ProjectLocalization
from mystery_engine.story import (
    ObstacleShape,
    PolygonObstacle,
    RectObstacle,
    StoryGraph,
    WorldAssetCatalog,
    WorldAssetDefinition,
)


def slugify(value: str, fallback: str = "content") -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return text or fallback


@dataclass(frozen=True)
class AttackDefinitionData:
    id: str
    name: str
    description: str = ""
    target: str = "enemy"
    range: int = 1
    power: int = 0
    heal: int = 0
    damage_type: str | None = None
    costs: dict[str, int] = field(default_factory=dict)
    max_charges: int | None = None
    accuracy: float = 1.0
    sfx_cue: str | None = None
    impact_sfx_cue: str | None = None
    projectile_key: str | None = None
    projectile_arc_px: float = 0.0
    range_pattern: str = "adjacent"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AttackDefinitionData":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            description=str(data.get("description") or ""),
            target=str(data.get("target", "enemy")).lower(),
            range=max(0, int(data.get("range", 1))),
            power=max(0, int(data.get("power", 0))),
            heal=max(0, int(data.get("heal", 0))),
            damage_type=(str(data["damage_type"]) if data.get("damage_type") else None),
            costs={str(k): max(0, int(v)) for k, v in dict(data.get("costs", {})).items()},
            max_charges=(None if data.get("max_charges") is None else max(0, int(data["max_charges"]))),
            accuracy=max(0.0, min(1.0, float(data.get("accuracy", 1.0)))),
            sfx_cue=(str(data["sfx_cue"]) if data.get("sfx_cue") else None),
            impact_sfx_cue=(str(data["impact_sfx_cue"]) if data.get("impact_sfx_cue") else None),
            projectile_key=(str(data["projectile_key"]) if data.get("projectile_key") else None),
            projectile_arc_px=float(data.get("projectile_arc_px", 0.0)),
            range_pattern=str(data.get("range_pattern", "adjacent")).lower(),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "format": 1,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "target": self.target,
            "range": self.range,
            "power": self.power,
            "heal": self.heal,
            "range_pattern": self.range_pattern,
            "accuracy": self.accuracy,
        }
        if self.damage_type:
            data["damage_type"] = self.damage_type
        if self.costs:
            data["costs"] = dict(sorted(self.costs.items()))
        data["max_charges"] = self.max_charges
        if self.sfx_cue:
            data["sfx_cue"] = self.sfx_cue
        if self.impact_sfx_cue:
            data["impact_sfx_cue"] = self.impact_sfx_cue
        if self.projectile_key:
            data["projectile_key"] = self.projectile_key
        if self.projectile_arc_px:
            data["projectile_arc_px"] = self.projectile_arc_px
        return data

    def to_skill_definition(self) -> SkillDefinition:
        try:
            target = TargetKind[self.target.upper()]
        except KeyError as exc:
            raise ValueError(f"Unknown target kind for attack {self.id}: {self.target}") from exc
        try:
            pattern = RangePattern(self.range_pattern)
        except ValueError as exc:
            raise ValueError(f"Unknown range pattern for attack {self.id}: {self.range_pattern}") from exc
        return SkillDefinition(
            id=self.id,
            name=self.name,
            description=self.description,
            target=target,
            range=self.range,
            power=self.power,
            heal=self.heal,
            damage_type=self.damage_type,
            costs=dict(self.costs),
            max_charges=self.max_charges,
            accuracy=self.accuracy,
            sfx_cue=self.sfx_cue,
            impact_sfx_cue=self.impact_sfx_cue,
            projectile_key=self.projectile_key,
            projectile_arc_px=self.projectile_arc_px,
            range_pattern=pattern,
        )


@dataclass(frozen=True)
class ItemDefinitionData:
    id: str
    name: str
    description: str = ""
    heal: int = 0
    throwable_damage: int = 0
    damage_type: str | None = None
    droppable: bool = True
    key_item: bool = False
    sfx_cue: str | None = None
    impact_sfx_cue: str | None = None
    projectile_key: str | None = None
    projectile_arc_px: float = 0.0
    sprite_key: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ItemDefinitionData":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            description=str(data.get("description") or ""),
            heal=max(0, int(data.get("heal", 0))),
            throwable_damage=max(0, int(data.get("throwable_damage", 0))),
            damage_type=(str(data["damage_type"]) if data.get("damage_type") else None),
            droppable=bool(data.get("droppable", True)),
            key_item=bool(data.get("key_item", False)),
            sfx_cue=(str(data["sfx_cue"]) if data.get("sfx_cue") else None),
            impact_sfx_cue=(str(data["impact_sfx_cue"]) if data.get("impact_sfx_cue") else None),
            projectile_key=(str(data["projectile_key"]) if data.get("projectile_key") else None),
            projectile_arc_px=float(data.get("projectile_arc_px", 0.0)),
            sprite_key=(str(data["sprite_key"]) if data.get("sprite_key") else None),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "format": 1,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "heal": self.heal,
            "throwable_damage": self.throwable_damage,
            "droppable": self.droppable,
            "key_item": self.key_item,
        }
        if self.damage_type:
            data["damage_type"] = self.damage_type
        if self.sfx_cue:
            data["sfx_cue"] = self.sfx_cue
        if self.impact_sfx_cue:
            data["impact_sfx_cue"] = self.impact_sfx_cue
        if self.projectile_key:
            data["projectile_key"] = self.projectile_key
        if self.projectile_arc_px:
            data["projectile_arc_px"] = self.projectile_arc_px
        if self.sprite_key:
            data["sprite_key"] = self.sprite_key
        return data

    def to_item_definition(self) -> ItemDefinition:
        return ItemDefinition(
            id=self.id,
            name=self.name,
            description=self.description,
            heal=self.heal,
            throwable_damage=self.throwable_damage,
            damage_type=self.damage_type,
            droppable=self.droppable,
            key_item=self.key_item,
            sfx_cue=self.sfx_cue,
            impact_sfx_cue=self.impact_sfx_cue,
            projectile_key=self.projectile_key,
            projectile_arc_px=self.projectile_arc_px,
            sprite_key=self.sprite_key,
        )


@dataclass(frozen=True)
class PlayableCharacterDefinitionData:
    id: str
    pawn_id: str
    max_hp: int
    attack: int
    defense: int
    attacks: tuple[str, ...] = ()
    resistances: dict[str, float] = field(default_factory=dict)
    resources: dict[str, int] = field(default_factory=dict)
    ai_tactic: str = "follow"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayableCharacterDefinitionData":
        stats = dict(data.get("stats", {}))
        return cls(
            id=str(data["id"]),
            pawn_id=str(data.get("pawn") or data["id"]),
            max_hp=max(1, int(stats.get("max_hp", data.get("max_hp", 1)))),
            attack=max(0, int(stats.get("attack", data.get("attack", 0)))),
            defense=max(0, int(stats.get("defense", data.get("defense", 0)))),
            attacks=tuple(str(v) for v in data.get("attacks", [])),
            resistances={str(k): max(0.0, float(v)) for k, v in dict(data.get("resistances", {})).items()},
            resources={str(k): max(0, int(v)) for k, v in dict(data.get("resources", {})).items()},
            ai_tactic=str(data.get("ai_tactic", "follow")).lower(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": 1,
            "id": self.id,
            "pawn": self.pawn_id,
            "stats": {
                "max_hp": self.max_hp,
                "attack": self.attack,
                "defense": self.defense,
            },
            "attacks": list(self.attacks),
            "resistances": dict(sorted(self.resistances.items())),
            "resources": dict(sorted(self.resources.items())),
            "ai_tactic": self.ai_tactic,
        }

    def make_character(
        self,
        pawn: "PawnDefinitionData",
        attack_catalog: dict[str, SkillDefinition],
        *,
        leader: bool = False,
    ) -> Character:
        skills = [
            SkillRuntime.from_definition(attack_catalog[attack_id])
            for attack_id in self.attacks
        ]
        tactic_map = {
            "follow": AITactic.FOLLOW,
            "attack": AITactic.ATTACK,
            "protect": AITactic.PROTECT,
            "conserve": AITactic.CONSERVE,
        }
        metadata = {"sprite_key": pawn.sprite_key}
        if pawn.portrait_key:
            metadata["portrait_key"] = pawn.portrait_key
        return Character(
            id=self.id,
            name=pawn.name,
            stats=Stats(max_hp=self.max_hp, attack=self.attack, defense=self.defense),
            skills=skills,
            resources=dict(self.resources),
            resistances=dict(self.resistances),
            party_member=True,
            leader=leader,
            ai_tactic=tactic_map.get(self.ai_tactic, AITactic.FOLLOW),
            metadata=metadata,
        )


@dataclass(frozen=True)
class GameSettingsData:
    title: str
    version: str = "0.1.0"
    starting_scene: str | None = None
    starting_marker: str | None = None
    default_dungeon: str | None = None
    bag_capacity: int = 20
    storage_capacity: int = 40
    starting_carried_money: int = 0
    starting_stored_money: int = 0
    defeat_money_loss_fraction: float = 0.5
    defeat_item_loss_chance: float = 0.3
    starting_party: tuple[str, ...] = ()
    leader: str | None = None
    starting_items: dict[str, int] = field(default_factory=dict)
    starting_storage: dict[str, int] = field(default_factory=dict)
    starting_flags: dict[str, bool] = field(default_factory=dict)
    starting_variables: dict[str, Any] = field(default_factory=dict)
    dungeon_result_stories: dict[str, str] = field(default_factory=dict)
    sfx_event_cues: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any], fallback_name: str) -> "GameSettingsData":
        game = dict(manifest.get("game") or {})
        start = dict(game.get("start") or {})
        defeat = dict(game.get("defeat") or {})
        inventory = dict(game.get("inventory") or {})
        return cls(
            title=str(game.get("title") or manifest.get("name") or fallback_name),
            version=str(game.get("version", "0.1.0")),
            starting_scene=(str(start["scene"]) if start.get("scene") else None),
            starting_marker=(str(start["marker"]) if start.get("marker") else None),
            default_dungeon=(str(game["default_dungeon"]) if game.get("default_dungeon") else (
                str(manifest["default_dungeon"]) if manifest.get("default_dungeon") else None
            )),
            bag_capacity=max(1, int(inventory.get("bag_capacity", 20))),
            storage_capacity=max(1, int(inventory.get("storage_capacity", 40))),
            starting_carried_money=max(0, int(inventory.get("carried_money", 0))),
            starting_stored_money=max(0, int(inventory.get("stored_money", 0))),
            defeat_money_loss_fraction=max(0.0, min(1.0, float(defeat.get("money_loss_fraction", 0.5)))),
            defeat_item_loss_chance=max(0.0, min(1.0, float(defeat.get("item_loss_chance", 0.3)))),
            starting_party=tuple(str(v) for v in start.get("party", [])),
            leader=(str(start["leader"]) if start.get("leader") else None),
            starting_items={str(k): max(0, int(v)) for k, v in dict(start.get("items", {})).items()},
            starting_storage={str(k): max(0, int(v)) for k, v in dict(start.get("storage", {})).items()},
            starting_flags={str(k): bool(v) for k, v in dict(start.get("flags", {})).items()},
            starting_variables=dict(start.get("variables", {})),
            dungeon_result_stories={str(k): str(v) for k, v in dict(game.get("dungeon_result_stories", {})).items() if v},
            sfx_event_cues={str(k): str(v) for k, v in dict(game.get("sfx_event_cues", {})).items() if v},
        )

    def to_manifest_game(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "version": self.version,
            "default_dungeon": self.default_dungeon,
            "inventory": {
                "bag_capacity": self.bag_capacity,
                "storage_capacity": self.storage_capacity,
                "carried_money": self.starting_carried_money,
                "stored_money": self.starting_stored_money,
            },
            "defeat": {
                "money_loss_fraction": self.defeat_money_loss_fraction,
                "item_loss_chance": self.defeat_item_loss_chance,
            },
            "start": {
                "scene": self.starting_scene,
                "marker": self.starting_marker,
                "party": list(self.starting_party),
                "leader": self.leader,
                "items": dict(sorted(self.starting_items.items())),
                "storage": dict(sorted(self.starting_storage.items())),
                "flags": dict(sorted(self.starting_flags.items())),
                "variables": self.starting_variables,
            },
            "dungeon_result_stories": dict(sorted(self.dungeon_result_stories.items())),
            "sfx_event_cues": dict(sorted(self.sfx_event_cues.items())),
        }


@dataclass(frozen=True)
class EnemyDefinitionData:
    id: str
    name: str
    max_hp: int
    attack: int
    defense: int
    sprite_key: str
    portrait_key: str | None = None
    attacks: tuple[str, ...] = ()
    resistances: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnemyDefinitionData":
        stats = dict(data.get("stats", {}))
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            max_hp=max(1, int(stats.get("max_hp", data.get("max_hp", 1)))),
            attack=max(0, int(stats.get("attack", data.get("attack", 0)))),
            defense=max(0, int(stats.get("defense", data.get("defense", 0)))),
            sprite_key=str(data.get("sprite_key") or data["id"]),
            portrait_key=(str(data["portrait_key"]) if data.get("portrait_key") else None),
            attacks=tuple(str(v) for v in data.get("attacks", [])),
            resistances={str(k): max(0.0, float(v)) for k, v in dict(data.get("resistances", {})).items()},
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "format": 1,
            "id": self.id,
            "name": self.name,
            "sprite_key": self.sprite_key,
            "stats": {
                "max_hp": self.max_hp,
                "attack": self.attack,
                "defense": self.defense,
            },
            "attacks": list(self.attacks),
            "resistances": dict(sorted(self.resistances.items())),
        }
        if self.portrait_key:
            data["portrait_key"] = self.portrait_key
        return data

    def make_character(
        self,
        identifier: str,
        attack_catalog: dict[str, SkillDefinition],
    ) -> Character:
        skills: list[SkillRuntime] = []
        for attack_id in self.attacks:
            try:
                definition = attack_catalog[attack_id]
            except KeyError as exc:
                raise KeyError(f"Enemy {self.id} references unknown attack: {attack_id}") from exc
            skills.append(SkillRuntime.from_definition(definition))
        metadata = {"sprite_key": self.sprite_key}
        if self.portrait_key:
            metadata["portrait_key"] = self.portrait_key
        return Character(
            id=identifier,
            name=self.name,
            stats=Stats(max_hp=self.max_hp, attack=self.attack, defense=self.defense),
            skills=skills,
            resistances=dict(self.resistances),
            hostile=True,
            metadata=metadata,
        )


@dataclass(frozen=True)
class TerrainDefinitionData:
    id: str
    name: str
    mode: str = "single"  # single | variants | autotile
    sprite_keys: tuple[str, ...] = ()
    blocked: bool = False
    fallback_color: str = "#526f49"
    transparent: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TerrainDefinitionData":
        mode = str(data.get("mode", "single")).lower()
        if mode not in {"single", "variants", "autotile"}:
            mode = "single"
        sprites = data.get("sprite_keys", [])
        if isinstance(sprites, str):
            sprites = [sprites]
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            mode=mode,
            sprite_keys=tuple(str(v) for v in sprites),
            blocked=bool(data.get("blocked", False)),
            fallback_color=str(data.get("fallback_color", "#526f49")),
            transparent=bool(data.get("transparent", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": 1,
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "sprite_keys": list(self.sprite_keys),
            "blocked": self.blocked,
            "fallback_color": self.fallback_color,
            "transparent": self.transparent,
        }

    def runtime_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "sprite_keys": list(self.sprite_keys),
            "blocked": self.blocked,
            "fallback_color": self.fallback_color,
            "transparent": self.transparent,
        }


@dataclass(frozen=True)
class WorldObjectDefinitionData:
    id: str
    name: str
    category: str = "scenery"
    sprite_key: str | None = None
    width: int = 64
    height: int = 64
    anchor: str = "bottom_center"
    collider_enabled: bool = False
    collision: ObstacleShape | None = None
    collision_radius: float = 0.0
    draw_behind_actors: bool = False
    runtime_visible: bool = True
    label: str | None = None
    action_id: str | None = None
    sound_cues: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def _collision_from_dict(data: object) -> ObstacleShape | None:
        if isinstance(data, list) and len(data) == 4:
            return RectObstacle(*[float(v) for v in data])
        if isinstance(data, dict):
            kind = str(data.get("type", "")).lower()
            if kind == "rect" and all(k in data for k in ("x", "y", "w", "h")):
                return RectObstacle(float(data["x"]), float(data["y"]), float(data["w"]), float(data["h"]))
            if kind == "polygon":
                points = data.get("points")
                if isinstance(points, list) and len(points) >= 3:
                    return PolygonObstacle(tuple((float(p[0]), float(p[1])) for p in points))
        return None

    @staticmethod
    def _collision_to_dict(shape: ObstacleShape | None) -> object | None:
        if shape is None:
            return None
        if isinstance(shape, RectObstacle):
            return [shape.x, shape.y, shape.w, shape.h]
        if isinstance(shape, PolygonObstacle):
            return {"type": "polygon", "points": [[x, y] for x, y in shape.points]}
        return None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldObjectDefinitionData":
        category = str(data.get("category", "scenery")).lower()
        if category not in {"scenery", "interactable"}:
            category = "scenery"
        collision = cls._collision_from_dict(data.get("collision"))
        collider_enabled = bool(data.get("collider_enabled", collision is not None or float(data.get("collision_radius", 0.0)) > 0))
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            category=category,
            sprite_key=(str(data["sprite_key"]) if data.get("sprite_key") else None),
            width=max(1, int(data.get("width", data.get("size", [64, 64])[0] if isinstance(data.get("size"), list) else 64))),
            height=max(1, int(data.get("height", data.get("size", [64, 64])[1] if isinstance(data.get("size"), list) else 64))),
            anchor=str(data.get("anchor", "bottom_center")),
            collider_enabled=collider_enabled,
            collision=collision,
            collision_radius=max(0.0, float(data.get("collision_radius", 0.0))),
            draw_behind_actors=bool(data.get("draw_behind_actors", False)),
            runtime_visible=bool(data.get("runtime_visible", True)),
            label=(str(data["label"]) if data.get("label") else None),
            action_id=(str(data["action_id"]) if data.get("action_id") else None),
            sound_cues={str(k): str(v) for k, v in dict(data.get("sound_cues", {})).items() if v},
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "format": 1,
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "sprite_key": self.sprite_key,
            "size": [self.width, self.height],
            "anchor": self.anchor,
            "collider_enabled": self.collider_enabled,
            "collision_radius": self.collision_radius,
            "draw_behind_actors": self.draw_behind_actors,
            "runtime_visible": self.runtime_visible,
        }
        collision = self._collision_to_dict(self.collision)
        if collision is not None:
            data["collision"] = collision
        if self.label:
            data["label"] = self.label
        if self.action_id:
            data["action_id"] = self.action_id
        if self.sound_cues:
            data["sound_cues"] = dict(sorted(self.sound_cues.items()))
        return data

    def to_world_asset(self) -> WorldAssetDefinition:
        return WorldAssetDefinition(
            id=self.id,
            category=self.category,
            sprite_key=self.sprite_key,
            display_name=self.name,
            size=(self.width, self.height),
            anchor=self.anchor,
            collision=self.collision if self.collider_enabled else None,
            collision_radius=self.collision_radius if self.collider_enabled else 0.0,
            draw_behind_actors=self.draw_behind_actors,
            label=self.label,
            action_id=self.action_id,
            sound_cues=dict(self.sound_cues),
            runtime_visible=self.runtime_visible,
        )


@dataclass(frozen=True)
class PawnDefinitionData:
    id: str
    name: str
    sprite_key: str
    portrait_key: str | None = None
    radius: float = 28.0
    color_key: str = "neutral"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PawnDefinitionData":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            sprite_key=str(data.get("sprite_key") or data["id"]),
            portrait_key=(str(data["portrait_key"]) if data.get("portrait_key") else None),
            radius=max(1.0, float(data.get("radius", 28.0))),
            color_key=str(data.get("color_key", "neutral")),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "format": 1,
            "id": self.id,
            "name": self.name,
            "sprite_key": self.sprite_key,
            "radius": self.radius,
            "color_key": self.color_key,
        }
        if self.portrait_key:
            data["portrait_key"] = self.portrait_key
        return data

    def to_world_asset(self) -> WorldAssetDefinition:
        return WorldAssetDefinition(
            id=self.id,
            category="actor",
            sprite_key=self.sprite_key,
            display_name=self.name,
            actor_name=self.name,
            color_key=self.color_key,
            radius=self.radius,
        )


class ProjectRegistry:
    """Data-backed registry used by runtime content and the authoring UI.

    Ordinary attacks and enemies are JSON resources. Dungeons and scenes retain
    their existing file formats. Assets are copied into the project's asset tree
    when imported so game content never depends on arbitrary external paths.
    """

    def __init__(self, game_root: Path) -> None:
        self.game_root = Path(game_root).resolve()
        self.manifest_path = self.game_root / "project.json"
        self.manifest = self._load_manifest()
        content = dict(self.manifest.get("content", {}))
        self.attack_dir = self.game_root / str(content.get("attacks", "content/attacks"))
        self.enemy_dir = self.game_root / str(content.get("enemies", "content/enemies"))
        self.item_dir = self.game_root / str(content.get("items", "content/items"))
        self.character_dir = self.game_root / str(content.get("characters", "content/characters"))
        self.object_dir = self.game_root / str(content.get("objects", "content/objects"))
        self.terrain_dir = self.game_root / str(content.get("terrain", "content/terrain"))
        self.pawn_dir = self.game_root / str(content.get("pawns", "content/pawns"))
        self.dungeon_dir = self.game_root / str(content.get("dungeons", "dungeons"))
        self.scene_dir = self.game_root / str(content.get("scenes", "scenes"))
        self.story_dir = self.game_root / str(content.get("stories", "stories"))
        self.locale_dir = self.game_root / str(content.get("locales", "locales"))
        self.asset_root = self.game_root / str(content.get("assets", "assets"))
        for directory in (
            self.attack_dir, self.enemy_dir, self.item_dir, self.character_dir,
            self.object_dir, self.terrain_dir, self.pawn_dir, self.dungeon_dir,
            self.scene_dir, self.story_dir, self.locale_dir, self.asset_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self.localization = self._build_localization()
        self.reload()

    @classmethod
    def create_project(cls, game_root: Path, name: str) -> "ProjectRegistry":
        root = Path(game_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        project_id = slugify(name, root.name or "game")
        manifest = {
            "format": 1,
            "id": project_id,
            "name": name.strip() or project_id,
            "content": {
                "attacks": "content/attacks",
                "enemies": "content/enemies",
                "items": "content/items",
                "characters": "content/characters",
                "objects": "content/objects",
                "terrain": "content/terrain",
                "pawns": "content/pawns",
                "dungeons": "dungeons",
                "scenes": "scenes",
                "stories": "stories",
                "locales": "locales",
                "assets": "assets",
            },
            "damage_types": ["physical"],
            "localization": {
                "source_locale": "en-US",
                "default_locale": "en-US",
                "supported_locales": ["en-US"],
                "locale_names": {"en-US": "English (US)"},
            },
            "game": {
                "title": name.strip() or project_id,
                "version": "0.1.0",
                "default_dungeon": None,
                "inventory": {"bag_capacity": 20, "storage_capacity": 40, "carried_money": 0, "stored_money": 0},
                "defeat": {"money_loss_fraction": 0.5, "item_loss_chance": 0.3},
                "start": {"scene": None, "marker": None, "party": [], "leader": None, "items": {}, "storage": {}, "flags": {}, "variables": {}},
                "dungeon_result_stories": {},
                "sfx_event_cues": {},
            },
        }
        (root / "project.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        registry = cls(root)
        registry.save_terrain(TerrainDefinitionData("grass", "Grass", "single", (), False, "#6aa65d"))
        registry.save_terrain(TerrainDefinitionData("void", "Void", "single", (), True, "#0c0f17"))
        registry.save_terrain(TerrainDefinitionData("background", "Background Only", "single", (), False, "#000000", True))
        return registry

    @classmethod
    def load(cls, game_root: Path) -> "ProjectRegistry":
        return cls(game_root)

    def _load_manifest(self) -> dict[str, Any]:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {
            "format": 1,
            "id": self.game_root.name,
            "name": self.game_root.name.replace("_", " ").title(),
            "content": {
                "attacks": "content/attacks",
                "enemies": "content/enemies",
                "items": "content/items",
                "characters": "content/characters",
                "objects": "content/objects",
                "terrain": "content/terrain",
                "pawns": "content/pawns",
                "dungeons": "dungeons",
                "scenes": "scenes",
                "stories": "stories",
                "locales": "locales",
                "assets": "assets",
            },
            "damage_types": ["physical"],
            "localization": {
                "source_locale": "en-US",
                "default_locale": "en-US",
                "supported_locales": ["en-US"],
                "locale_names": {"en-US": "English (US)"},
            },
        }

    def _build_localization(self) -> ProjectLocalization:
        config = dict(self.manifest.get("localization") or {})
        source = str(config.get("source_locale") or "en-US")
        default = str(config.get("default_locale") or source)
        supported = [str(v) for v in config.get("supported_locales", [source])]
        names = {str(k): str(v) for k, v in dict(config.get("locale_names", {})).items()}
        return ProjectLocalization(
            self.locale_dir,
            source_locale=source,
            default_locale=default,
            supported_locales=supported,
            locale_names=names,
        )

    def save_localization_config(self) -> None:
        self.manifest["localization"] = {
            "source_locale": self.localization.source_locale,
            "default_locale": self.localization.default_locale,
            "supported_locales": list(self.localization.supported_locales),
            "locale_names": dict(sorted(self.localization.locale_names.items())),
        }
        self.manifest_path.write_text(
            json.dumps(self.manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.manifest = self._load_manifest()

    def add_locale(self, locale: str, label: str | None = None) -> None:
        self.localization.add_locale(locale, label)
        self.save_localization_config()

    def remove_locale(self, locale: str) -> None:
        self.localization.remove_locale(locale)
        self.save_localization_config()

    def set_default_locale(self, locale: str) -> None:
        if locale not in self.localization.supported_locales:
            raise ValueError(f"Unsupported locale: {locale}")
        self.localization.default_locale = locale
        self.save_localization_config()

    def set_active_locale(self, locale: str | None) -> str:
        selected = self.localization.set_active_locale(locale)
        self.reload()
        return selected

    def text(self, key: str, source: str, variables: dict[str, Any] | None = None) -> str:
        return self.localization.translate(key, source, variables=variables)

    @property
    def project_id(self) -> str:
        return str(self.manifest.get("id") or self.game_root.name)

    @property
    def project_name(self) -> str:
        return str(self.manifest.get("name") or self.project_id)

    @property
    def game_settings(self) -> GameSettingsData:
        return GameSettingsData.from_manifest(self.manifest, self.game_root.name)

    def save_game_settings(self, settings: GameSettingsData) -> None:
        self.manifest["name"] = settings.title
        self.manifest["default_dungeon"] = settings.default_dungeon
        self.manifest["game"] = settings.to_manifest_game()
        self.manifest_path.write_text(
            json.dumps(self.manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.manifest = self._load_manifest()

    @property
    def default_dungeon_id(self) -> str | None:
        return self.game_settings.default_dungeon

    @property
    def damage_types(self) -> list[str]:
        return [str(v) for v in self.manifest.get("damage_types", ["physical"])]

    def reload(self) -> None:
        self.attacks_data: dict[str, AttackDefinitionData] = {}
        self.attacks: dict[str, SkillDefinition] = {}
        self.enemies: dict[str, EnemyDefinitionData] = {}
        self.items_data: dict[str, ItemDefinitionData] = {}
        self.items: dict[str, ItemDefinition] = {}
        self.characters: dict[str, PlayableCharacterDefinitionData] = {}
        self.objects: dict[str, WorldObjectDefinitionData] = {}
        self.terrain: dict[str, TerrainDefinitionData] = {}
        self.pawns: dict[str, PawnDefinitionData] = {}

        if self.attack_dir.exists():
            for path in sorted(self.attack_dir.glob("*.json")):
                data = AttackDefinitionData.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.attacks_data[data.id] = data
                definition = data.to_skill_definition()
                definition = replace(
                    definition,
                    name=self.text(f"attack.{data.id}.name", data.name),
                    description=self.text(f"attack.{data.id}.description", data.description),
                )
                self.attacks[data.id] = definition

        if self.enemy_dir.exists():
            for path in sorted(self.enemy_dir.glob("*.json")):
                data = EnemyDefinitionData.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.enemies[data.id] = data

        if self.item_dir.exists():
            for path in sorted(self.item_dir.glob("*.json")):
                data = ItemDefinitionData.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.items_data[data.id] = data
                definition = data.to_item_definition()
                definition = replace(
                    definition,
                    name=self.text(f"item.{data.id}.name", data.name),
                    description=self.text(f"item.{data.id}.description", data.description),
                )
                self.items[data.id] = definition

        if self.character_dir.exists():
            for path in sorted(self.character_dir.glob("*.json")):
                data = PlayableCharacterDefinitionData.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.characters[data.id] = data

        if self.object_dir.exists():
            for path in sorted(self.object_dir.glob("*.json")):
                data = WorldObjectDefinitionData.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.objects[data.id] = data

        if self.terrain_dir.exists():
            for path in sorted(self.terrain_dir.glob("*.json")):
                data = TerrainDefinitionData.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.terrain[data.id] = data

        if self.pawn_dir.exists():
            for path in sorted(self.pawn_dir.glob("*.json")):
                data = PawnDefinitionData.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.pawns[data.id] = data

    @property
    def attack_labels(self) -> dict[str, str]:
        return {key: value.name for key, value in sorted(self.attacks_data.items())}

    @property
    def enemy_labels(self) -> dict[str, str]:
        return {key: value.name for key, value in sorted(self.enemies.items())}

    @property
    def pawn_labels(self) -> dict[str, str]:
        return {key: value.name for key, value in sorted(self.pawns.items())}

    @property
    def object_labels(self) -> dict[str, str]:
        return {key: value.name for key, value in sorted(self.objects.items())}

    @property
    def terrain_labels(self) -> dict[str, str]:
        return {key: value.name for key, value in sorted(self.terrain.items())}

    def save_terrain(self, data: TerrainDefinitionData) -> Path:
        self.terrain_dir.mkdir(parents=True, exist_ok=True)
        path = self.terrain_dir / f"{data.id}.json"
        path.write_text(json.dumps(data.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.reload()
        return path

    def terrain_runtime(self) -> dict[str, dict[str, Any]]:
        return {key: value.runtime_dict() for key, value in self.terrain.items()}

    def save_object(self, data: WorldObjectDefinitionData) -> Path:
        self.object_dir.mkdir(parents=True, exist_ok=True)
        path = self.object_dir / f"{data.id}.json"
        path.write_text(json.dumps(data.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.reload()
        return path

    @property
    def item_labels(self) -> dict[str, str]:
        return {key: value.name for key, value in sorted(self.items_data.items())}

    @property
    def character_labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for key, character in sorted(self.characters.items()):
            pawn = self.pawns.get(character.pawn_id)
            labels[key] = pawn.name if pawn is not None else key
        return labels

    def save_item(self, data: ItemDefinitionData) -> Path:
        self.item_dir.mkdir(parents=True, exist_ok=True)
        path = self.item_dir / f"{data.id}.json"
        path.write_text(json.dumps(data.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.reload()
        return path

    def item(self, item_id: str) -> ItemDefinition:
        try:
            return self.items[item_id]
        except KeyError as exc:
            raise KeyError(f"Unknown item: {item_id}") from exc

    def save_character(self, data: PlayableCharacterDefinitionData) -> Path:
        self.character_dir.mkdir(parents=True, exist_ok=True)
        path = self.character_dir / f"{data.id}.json"
        path.write_text(json.dumps(data.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.reload()
        return path

    def make_character(self, character_id: str, *, leader: bool = False) -> Character:
        try:
            definition = self.characters[character_id]
        except KeyError as exc:
            raise KeyError(f"Unknown playable character: {character_id}") from exc
        pawn = self.pawn(definition.pawn_id)
        character = definition.make_character(pawn, self.attacks, leader=leader)
        character.name = self.text(f"pawn.{pawn.id}.name", pawn.name)
        return character

    def save_pawn(self, data: PawnDefinitionData) -> Path:
        self.pawn_dir.mkdir(parents=True, exist_ok=True)
        path = self.pawn_dir / f"{data.id}.json"
        path.write_text(json.dumps(data.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.reload()
        return path

    def pawn(self, pawn_id: str) -> PawnDefinitionData:
        try:
            return self.pawns[pawn_id]
        except KeyError as exc:
            raise KeyError(f"Unknown pawn: {pawn_id}") from exc

    def resolve_story_pawn(self, pawn_id: str) -> tuple[str, str | None]:
        pawn = self.pawn(pawn_id)
        return self.text(f"pawn.{pawn.id}.name", pawn.name), pawn.portrait_key or pawn.sprite_key

    def world_asset_catalog(self, base: WorldAssetCatalog) -> WorldAssetCatalog:
        merged = dict(base.assets)
        for object_data in self.objects.values():
            definition = object_data.to_world_asset()
            merged[object_data.id] = replace(
                definition,
                display_name=self.text(f"object.{object_data.id}.name", object_data.name),
                label=(
                    self.text(f"object.{object_data.id}.label", object_data.label)
                    if object_data.label else None
                ),
            )
        for pawn in self.pawns.values():
            existing = merged.get(pawn.id)
            if existing is not None and existing.category == "actor":
                merged[pawn.id] = replace(
                    existing,
                    sprite_key=pawn.sprite_key,
                    display_name=self.text(f"pawn.{pawn.id}.name", pawn.name),
                    actor_name=self.text(f"pawn.{pawn.id}.name", pawn.name),
                    color_key=pawn.color_key,
                    radius=pawn.radius,
                )
            else:
                definition = pawn.to_world_asset()
                merged[pawn.id] = replace(
                    definition,
                    display_name=self.text(f"pawn.{pawn.id}.name", pawn.name),
                    actor_name=self.text(f"pawn.{pawn.id}.name", pawn.name),
                )
        return WorldAssetCatalog(assets=merged)

    def save_attack(self, data: AttackDefinitionData) -> Path:
        self.attack_dir.mkdir(parents=True, exist_ok=True)
        path = self.attack_dir / f"{data.id}.json"
        path.write_text(json.dumps(data.to_dict(), indent=2) + "\n", encoding="utf-8")
        self.reload()
        return path

    def save_enemy(self, data: EnemyDefinitionData) -> Path:
        self.enemy_dir.mkdir(parents=True, exist_ok=True)
        path = self.enemy_dir / f"{data.id}.json"
        path.write_text(json.dumps(data.to_dict(), indent=2) + "\n", encoding="utf-8")
        self.reload()
        return path

    def attack_skill(self, attack_id: str) -> SkillDefinition:
        try:
            return self.attacks[attack_id]
        except KeyError as exc:
            raise KeyError(f"Unknown attack: {attack_id}") from exc

    def make_enemy(self, enemy_id: str, identifier: str) -> Character:
        try:
            enemy = self.enemies[enemy_id]
        except KeyError as exc:
            raise KeyError(f"Unknown enemy: {enemy_id}") from exc
        character = enemy.make_character(identifier, self.attacks)
        character.name = self.text(f"enemy.{enemy.id}.name", enemy.name)
        return character

    def apply_spawn_modifiers(self, character: Character, rule: SpawnRule) -> Character:
        character.name = rule.name_override or character.name
        if rule.sprite_override:
            character.metadata["sprite_key"] = rule.sprite_override

        hp = max(1, round(character.stats.max_hp * rule.hp_percent / 100.0))
        attack = max(0, round(character.stats.attack * rule.attack_percent / 100.0))
        defense = max(0, round(character.stats.defense * rule.defense_percent / 100.0))
        character.stats.max_hp = hp
        character.stats.current_hp = hp
        character.stats.attack = attack
        character.stats.defense = defense

        character.resistances.update(rule.resistances)
        existing = {skill.definition.id for skill in character.skills}
        for attack_id in rule.extra_attacks:
            if attack_id in existing:
                continue
            character.skills.append(SkillRuntime.from_definition(self.attack_skill(attack_id)))
            existing.add(attack_id)
        return character

    def dungeon_paths(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for path in sorted(self.dungeon_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            dungeon_id = str(data.get("id") or path.stem)
            result[dungeon_id] = path
        return result

    def dungeon_labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for dungeon_id, path in self.dungeon_paths().items():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                source_name = str(data.get("name") or dungeon_id)
                labels[dungeon_id] = self.text(f"dungeon.{dungeon_id}.name", source_name)
            except (OSError, json.JSONDecodeError):
                labels[dungeon_id] = dungeon_id
        return labels

    def load_dungeon(self, dungeon_id: str) -> DungeonDefinition:
        paths = self.dungeon_paths()
        try:
            dungeon = DungeonDefinition.load(paths[dungeon_id])
            dungeon.name = self.text(f"dungeon.{dungeon.id}.name", dungeon.name)
            return dungeon
        except KeyError as exc:
            raise KeyError(f"Unknown dungeon: {dungeon_id}") from exc

    def dungeon_path(self, dungeon_id: str) -> Path:
        try:
            return self.dungeon_paths()[dungeon_id]
        except KeyError as exc:
            raise KeyError(f"Unknown dungeon: {dungeon_id}") from exc

    def create_dungeon(self, name: str, dungeon_id: str | None = None, floors: int = 3) -> tuple[DungeonDefinition, Path]:
        base = slugify(dungeon_id or name, "dungeon")
        dungeon_id = self._unique_resource_id(base, set(self.dungeon_paths()))
        dungeon = DungeonDefinition.blank(dungeon_id, name.strip() or dungeon_id)
        dungeon.floor_count = max(1, int(floors))
        path = self.dungeon_dir / f"{dungeon_id}.json"
        dungeon.save(path)
        return dungeon, path

    def scene_paths(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for path in sorted(self.scene_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            scene_id = str(data.get("id") or path.stem)
            result[scene_id] = path
        return result

    def scene_labels(self) -> dict[str, str]:
        return {scene_id: path.stem for scene_id, path in self.scene_paths().items()}

    def story_paths(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for path in sorted(self.story_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            story_id = str(data.get("id") or path.stem)
            result[story_id] = path
        return result

    def story_labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for story_id, path in self.story_paths().items():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                source_name = str(data.get("name") or story_id).replace("_", " ")
                labels[story_id] = self.text(f"story.{story_id}.name", source_name)
            except (OSError, json.JSONDecodeError):
                labels[story_id] = story_id
        return labels

    def stories_for_scene(self, scene_id: str) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for story_id, path in self.story_paths().items():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(data.get("scene") or "") == scene_id:
                result[story_id] = path
        return result

    def load_story(self, story_id: str) -> StoryGraph:
        try:
            return StoryGraph.load(self.story_paths()[story_id])
        except KeyError as exc:
            raise KeyError(f"Unknown story: {story_id}") from exc

    def story_path(self, story_id: str) -> Path:
        try:
            return self.story_paths()[story_id]
        except KeyError as exc:
            raise KeyError(f"Unknown story: {story_id}") from exc

    def create_story(
        self,
        name: str,
        scene_id: str,
        story_id: str | None = None,
    ) -> tuple[StoryGraph, Path]:
        base = slugify(story_id or name, "story")
        story_id = self._unique_resource_id(base, set(self.story_paths()))
        graph = StoryGraph.blank(story_id)
        graph.name = name.strip() or story_id
        graph.scene_id = scene_id
        path = self.story_dir / f"{story_id}.json"
        graph.save(path)
        return graph, path

    @staticmethod
    def _entry(entries: list[LocalizationEntry], key: str, source: object, context: str) -> None:
        text = str(source or "")
        if text:
            entries.append(LocalizationEntry(key, text, context))

    def ensure_story_string_ids(self) -> int:
        changed_count = 0
        for story_id, path in self.story_paths().items():
            graph = StoryGraph.load(path)
            changed = False
            for node_id, node in graph.nodes.items():
                if str(node.get("type", "")).lower() == "dialogue":
                    used: set[str] = set()
                    for index, line in enumerate(node.get("lines", []) or [], start=1):
                        if not isinstance(line, dict):
                            continue
                        line_id = str(line.get("id") or "")
                        if not line_id or line_id in used:
                            base = f"line_{index:03d}"
                            line_id = base
                            suffix = 2
                            while line_id in used:
                                line_id = f"{base}_{suffix}"
                                suffix += 1
                            line["id"] = line_id
                            changed = True
                        used.add(line_id)
                elif str(node.get("type", "")).lower() == "choice":
                    used: set[str] = set()
                    for index, choice in enumerate(node.get("choices", []) or [], start=1):
                        if not isinstance(choice, dict):
                            continue
                        choice_id = str(choice.get("id") or "")
                        if not choice_id or choice_id in used:
                            base = f"choice_{index:03d}"
                            choice_id = base
                            suffix = 2
                            while choice_id in used:
                                choice_id = f"{base}_{suffix}"
                                suffix += 1
                            choice["id"] = choice_id
                            changed = True
                        used.add(choice_id)
            if changed:
                graph.save(path)
                changed_count += 1
        return changed_count

    def localization_entries(self) -> list[LocalizationEntry]:
        self.ensure_story_string_ids()
        entries: list[LocalizationEntry] = []
        settings = self.game_settings
        self._entry(entries, "game.title", settings.title, "Game title")

        for data in self.attacks_data.values():
            self._entry(entries, f"attack.{data.id}.name", data.name, f"Attack name · {data.id}")
            self._entry(entries, f"attack.{data.id}.description", data.description, f"Attack description · {data.id}")
        for data in self.items_data.values():
            self._entry(entries, f"item.{data.id}.name", data.name, f"Item name · {data.id}")
            self._entry(entries, f"item.{data.id}.description", data.description, f"Item description · {data.id}")
        for data in self.enemies.values():
            self._entry(entries, f"enemy.{data.id}.name", data.name, f"Enemy name · {data.id}")
        for data in self.pawns.values():
            self._entry(entries, f"pawn.{data.id}.name", data.name, f"Pawn / character name · {data.id}")
        for data in self.objects.values():
            self._entry(entries, f"object.{data.id}.name", data.name, f"World object name · {data.id}")
            self._entry(entries, f"object.{data.id}.label", data.label, f"Interaction label · {data.id}")
        for data in self.terrain.values():
            self._entry(entries, f"terrain.{data.id}.name", data.name, f"Terrain name · {data.id}")

        for dungeon_id, path in self.dungeon_paths().items():
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._entry(entries, f"dungeon.{dungeon_id}.name", payload.get("name") or dungeon_id, f"Dungeon name · {dungeon_id}")

        for scene_id, path in self.scene_paths().items():
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._entry(entries, f"scene.{scene_id}.name", payload.get("name"), f"Scene name · {scene_id}")
            for obj in payload.get("objects", []):
                if not isinstance(obj, dict) or not obj.get("label"):
                    continue
                object_id = str(obj.get("id") or "object")
                self._entry(
                    entries,
                    f"scene.{scene_id}.object.{object_id}.label",
                    obj.get("label"),
                    f"Placed object label · scene {scene_id} · {object_id}",
                )

        for story_id, path in self.story_paths().items():
            graph = StoryGraph.load(path)
            self._entry(entries, f"story.{story_id}.name", graph.name or story_id, f"Story name · {story_id}")
            for node_id, node in graph.nodes.items():
                node_type = str(node.get("type", "")).lower()
                if node_type == "dialogue":
                    for index, line in enumerate(node.get("lines", []) or [], start=1):
                        if not isinstance(line, dict):
                            continue
                        line_id = str(line.get("id") or f"line_{index:03d}")
                        base = f"story.{story_id}.{node_id}.{line_id}"
                        self._entry(
                            entries,
                            f"{base}.text",
                            line.get("text"),
                            f"Dialogue · story {story_id} · node {node_id} · line {index}",
                        )
                        if line.get("speaker") and not line.get("pawn"):
                            self._entry(
                                entries,
                                f"{base}.speaker",
                                line.get("speaker"),
                                f"Custom speaker · story {story_id} · node {node_id} · line {index}",
                            )
                elif node_type == "choice":
                    self._entry(
                        entries,
                        f"story.{story_id}.{node_id}.title",
                        node.get("title"),
                        f"Choice title · story {story_id} · node {node_id}",
                    )
                    for index, choice in enumerate(node.get("choices", []) or [], start=1):
                        if not isinstance(choice, dict):
                            continue
                        choice_id = str(choice.get("id") or f"choice_{index:03d}")
                        base = f"story.{story_id}.{node_id}.{choice_id}"
                        self._entry(entries, f"{base}.text", choice.get("text"), f"Choice · story {story_id} · node {node_id} · option {index}")
                        self._entry(entries, f"{base}.detail", choice.get("detail"), f"Choice detail · story {story_id} · node {node_id} · option {index}")

        deduped: dict[str, LocalizationEntry] = {}
        for entry in entries:
            deduped[entry.key] = entry
        return [deduped[key] for key in sorted(deduped)]

    def localize_scene(self, scene):
        from mystery_engine.story import ExplorationSceneData
        localized = ExplorationSceneData.from_dict(scene.to_dict())
        for obj in localized.objects:
            if obj.label:
                obj.label = self.text(
                    f"scene.{localized.id}.object.{obj.id}.label",
                    obj.label,
                )
        return localized

    def localize_story(self, graph: StoryGraph) -> StoryGraph:
        localized = StoryGraph.from_dict(graph.to_dict(), source_path=graph.source_path)
        localized.name = self.text(f"story.{graph.id}.name", graph.name or graph.id)
        for node_id, node in localized.nodes.items():
            node_type = str(node.get("type", "")).lower()
            if node_type == "dialogue":
                for index, line in enumerate(node.get("lines", []) or [], start=1):
                    if not isinstance(line, dict):
                        continue
                    line_id = str(line.get("id") or f"line_{index:03d}")
                    base = f"story.{graph.id}.{node_id}.{line_id}"
                    line["text"] = self.text(f"{base}.text", str(line.get("text", "")))
                    if line.get("speaker") and not line.get("pawn"):
                        line["speaker"] = self.text(f"{base}.speaker", str(line.get("speaker", "")))
            elif node_type == "choice":
                if node.get("title"):
                    node["title"] = self.text(f"story.{graph.id}.{node_id}.title", str(node["title"]))
                for index, choice in enumerate(node.get("choices", []) or [], start=1):
                    if not isinstance(choice, dict):
                        continue
                    choice_id = str(choice.get("id") or f"choice_{index:03d}")
                    base = f"story.{graph.id}.{node_id}.{choice_id}"
                    choice["text"] = self.text(f"{base}.text", str(choice.get("text", "")))
                    if choice.get("detail"):
                        choice["detail"] = self.text(f"{base}.detail", str(choice["detail"]))
        return localized

    def import_terrain_cliffs(self, terrain_id: str, source_dir: Path) -> int:
        source_dir = Path(source_dir).resolve()
        if not source_dir.is_dir():
            raise NotADirectoryError(source_dir)
        destination = self.asset_root / "terrain" / terrain_id
        destination.mkdir(parents=True, exist_ok=True)
        copied = 0
        for path in source_dir.iterdir():
            if not path.is_file() or path.suffix.lower() != ".png":
                continue
            stem = path.stem.lower()
            mask_text = None
            if stem.isdigit():
                mask_text = stem
            elif stem.startswith("cliff_") and stem[6:].isdigit():
                mask_text = stem[6:]
            elif "_" in stem and stem.rsplit("_", 1)[-1].isdigit():
                mask_text = stem.rsplit("_", 1)[-1]
            if mask_text is None:
                continue
            mask = int(mask_text)
            if not 0 <= mask <= 255:
                continue
            shutil.copy2(path, destination / f"cliff_{mask:03d}.png")
            copied += 1
        return copied

    def import_terrain_autotiles(self, terrain_id: str, source_dir: Path) -> int:
        source_dir = Path(source_dir).resolve()
        if not source_dir.is_dir():
            raise NotADirectoryError(source_dir)
        destination = self.asset_root / "terrain" / terrain_id
        destination.mkdir(parents=True, exist_ok=True)
        copied = 0
        for path in source_dir.iterdir():
            if not path.is_file() or path.suffix.lower() != ".png":
                continue
            stem = path.stem.lower()
            mask_text = None
            if stem.isdigit():
                mask_text = stem
            elif stem.startswith("auto_") and stem[5:].isdigit():
                mask_text = stem[5:]
            elif stem.endswith(tuple(f"_{i:03d}" for i in range(256))):
                tail = stem.rsplit("_", 1)[-1]
                if tail.isdigit():
                    mask_text = tail
            if mask_text is None:
                continue
            mask = int(mask_text)
            if not 0 <= mask <= 255:
                continue
            shutil.copy2(path, destination / f"auto_{mask:03d}.png")
            copied += 1
        return copied

    def import_asset(
        self,
        source: Path,
        category: str,
        *,
        preferred_id: str | None = None,
        allowed_suffixes: set[str] | None = None,
    ) -> tuple[str, Path]:
        source = Path(source).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        if allowed_suffixes and source.suffix.lower() not in {s.lower() for s in allowed_suffixes}:
            raise ValueError(f"Unsupported asset type: {source.suffix}")
        category = category.strip("/\\")
        destination_dir = self.asset_root / category
        destination_dir.mkdir(parents=True, exist_ok=True)
        base = slugify(preferred_id or source.stem, "asset")
        candidate = base
        index = 2
        while (destination_dir / f"{candidate}{source.suffix.lower()}").exists():
            candidate = f"{base}_{index}"
            index += 1
        destination = destination_dir / f"{candidate}{source.suffix.lower()}"
        shutil.copy2(source, destination)
        return candidate, destination

    def asset_keys(self, category: str, suffixes: set[str] | None = None) -> list[str]:
        directory = self.asset_root / category
        if not directory.exists():
            return []
        wanted = {s.lower() for s in suffixes} if suffixes else None
        return sorted(
            path.stem
            for path in directory.iterdir()
            if path.is_file() and (wanted is None or path.suffix.lower() in wanted)
        )

    @staticmethod
    def _unique_resource_id(base: str, existing: set[str]) -> str:
        if base not in existing:
            return base
        index = 2
        while f"{base}_{index}" in existing:
            index += 1
        return f"{base}_{index}"
