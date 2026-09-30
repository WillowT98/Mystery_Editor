from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import shutil
from typing import Any

from mystery_engine.core import (
    Character,
    RangePattern,
    SkillDefinition,
    SkillRuntime,
    Stats,
    TargetKind,
)
from mystery_engine.dungeon import DungeonDefinition, SpawnRule


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
        self.dungeon_dir = self.game_root / str(content.get("dungeons", "dungeons"))
        self.scene_dir = self.game_root / str(content.get("scenes", "scenes"))
        self.asset_root = self.game_root / str(content.get("assets", "assets"))
        for directory in (self.attack_dir, self.enemy_dir, self.dungeon_dir, self.scene_dir, self.asset_root):
            directory.mkdir(parents=True, exist_ok=True)
        self.reload()

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
                "dungeons": "dungeons",
                "scenes": "scenes",
                "assets": "assets",
            },
            "damage_types": ["physical"],
        }

    @property
    def project_id(self) -> str:
        return str(self.manifest.get("id") or self.game_root.name)

    @property
    def project_name(self) -> str:
        return str(self.manifest.get("name") or self.project_id)

    @property
    def default_dungeon_id(self) -> str | None:
        value = self.manifest.get("default_dungeon")
        return str(value) if value else None

    @property
    def damage_types(self) -> list[str]:
        return [str(v) for v in self.manifest.get("damage_types", ["physical"])]

    def reload(self) -> None:
        self.attacks_data: dict[str, AttackDefinitionData] = {}
        self.attacks: dict[str, SkillDefinition] = {}
        self.enemies: dict[str, EnemyDefinitionData] = {}

        if self.attack_dir.exists():
            for path in sorted(self.attack_dir.glob("*.json")):
                data = AttackDefinitionData.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.attacks_data[data.id] = data
                self.attacks[data.id] = data.to_skill_definition()

        if self.enemy_dir.exists():
            for path in sorted(self.enemy_dir.glob("*.json")):
                data = EnemyDefinitionData.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.enemies[data.id] = data

    @property
    def attack_labels(self) -> dict[str, str]:
        return {key: value.name for key, value in sorted(self.attacks_data.items())}

    @property
    def enemy_labels(self) -> dict[str, str]:
        return {key: value.name for key, value in sorted(self.enemies.items())}

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
        return enemy.make_character(identifier, self.attacks)

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
                labels[dungeon_id] = str(data.get("name") or dungeon_id)
            except (OSError, json.JSONDecodeError):
                labels[dungeon_id] = dungeon_id
        return labels

    def load_dungeon(self, dungeon_id: str) -> DungeonDefinition:
        paths = self.dungeon_paths()
        try:
            return DungeonDefinition.load(paths[dungeon_id])
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
