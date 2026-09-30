from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from random import Random
from typing import Callable, Any

from mystery_engine.core.inventory import ItemDefinition
from mystery_engine.core.models import Character
from mystery_engine.core.types import GridPos

from .floor import DungeonFloor, GroundItem
from .generation import (
    GENERATION_PROFILES,
    GeneratorConfig,
    OpenRoomConfig,
    OpenRoomGenerator,
    RoomsAndCorridorsGenerator,
    generation_profile_settings,
)


def floor_spec_matches(spec: str | int | None, floor_number: int, floor_total: int) -> bool:
    """Return whether a floor selector includes floor_number.

    Supported forms are intentionally author-friendly: `all`, `*`, `4`,
    `2-7`, `5+`, and comma-separated combinations such as `1-3,8,12+`.
    """
    if spec is None:
        return True
    if isinstance(spec, int):
        return floor_number == spec
    text = str(spec).strip().lower()
    if not text or text in {"all", "*"}:
        return True
    for part in (p.strip() for p in text.split(",")):
        if not part:
            continue
        if part.endswith("+"):
            try:
                if floor_number >= int(part[:-1]):
                    return True
            except ValueError:
                continue
        elif "-" in part:
            left, right = part.split("-", 1)
            try:
                start = int(left) if left else 1
                end = int(right) if right else floor_total
            except ValueError:
                continue
            if start <= floor_number <= end:
                return True
        else:
            try:
                if floor_number == int(part):
                    return True
            except ValueError:
                continue
    return False


@dataclass
class SpawnRule:
    content_id: str
    floors: str = "all"
    weight: float = 1.0
    min_per_floor: int = 0
    max_per_floor: int = 999
    hp_percent: float = 100.0
    attack_percent: float = 100.0
    defense_percent: float = 100.0
    name_override: str | None = None
    sprite_override: str | None = None
    resistances: dict[str, float] = field(default_factory=dict)
    extra_attacks: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any], key: str) -> "SpawnRule":
        modifiers = dict(payload.get("modifiers") or {})
        return cls(
            content_id=str(payload.get(key, "")),
            floors=str(payload.get("floors", "all")),
            weight=max(0.0, float(payload.get("weight", 1.0))),
            min_per_floor=max(0, int(payload.get("min_per_floor", payload.get("min", 0)))),
            max_per_floor=max(0, int(payload.get("max_per_floor", payload.get("max", 999)))),
            hp_percent=max(1.0, float(modifiers.get("hp_percent", 100.0))),
            attack_percent=max(0.0, float(modifiers.get("attack_percent", 100.0))),
            defense_percent=max(0.0, float(modifiers.get("defense_percent", 100.0))),
            name_override=(str(modifiers["name"]) if modifiers.get("name") else None),
            sprite_override=(str(modifiers["sprite"]) if modifiers.get("sprite") else None),
            resistances={str(k): max(0.0, float(v)) for k, v in dict(modifiers.get("resistances", {})).items()},
            extra_attacks=[str(v) for v in modifiers.get("attacks", [])],
        )

    def to_dict(self, key: str) -> dict[str, Any]:
        data: dict[str, Any] = {
            key: self.content_id,
            "floors": self.floors,
            "weight": self.weight,
            "min_per_floor": self.min_per_floor,
            "max_per_floor": self.max_per_floor,
        }
        modifiers: dict[str, Any] = {}
        if self.hp_percent != 100.0:
            modifiers["hp_percent"] = self.hp_percent
        if self.attack_percent != 100.0:
            modifiers["attack_percent"] = self.attack_percent
        if self.defense_percent != 100.0:
            modifiers["defense_percent"] = self.defense_percent
        if self.name_override:
            modifiers["name"] = self.name_override
        if self.sprite_override:
            modifiers["sprite"] = self.sprite_override
        if self.resistances:
            modifiers["resistances"] = dict(sorted(self.resistances.items()))
        if self.extra_attacks:
            modifiers["attacks"] = list(self.extra_attacks)
        if modifiers:
            data["modifiers"] = modifiers
        return data


@dataclass
class DungeonDefinition:
    id: str
    name: str
    floor_count: int = 3
    tileset: str = "dungeon"
    generation: dict[str, Any] = field(default_factory=lambda: {
        "type": "rooms_and_corridors",
        "width": 38,
        "height": 28,
        "room_count_min": 6,
        "room_count_max": 9,
        "room_w_min": 4,
        "room_w_max": 9,
        "room_h_min": 4,
        "room_h_max": 8,
    })
    music: dict[str, Any] = field(default_factory=lambda: {"track": None, "volume": 1.0, "overrides": []})
    enemy_count: dict[str, Any] = field(default_factory=lambda: {"base": 2, "per_floor": 0, "max": 8})
    item_count: dict[str, Any] = field(default_factory=lambda: {"min": 2, "max": 4})
    enemies: list[SpawnRule] = field(default_factory=list)
    items: list[SpawnRule] = field(default_factory=list)
    floor_rules: list[dict[str, Any]] = field(default_factory=list)
    generation_profile_rules: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def blank(cls, dungeon_id: str = "new_dungeon", name: str = "New Dungeon") -> "DungeonDefinition":
        return cls(id=dungeon_id, name=name)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DungeonDefinition":
        generation = dict(payload.get("generation") or {})
        if "type" not in generation:
            generation["type"] = "rooms_and_corridors"
        music_payload = payload.get("music")
        if isinstance(music_payload, str):
            music = {"track": music_payload, "volume": 1.0, "overrides": []}
        else:
            music = dict(music_payload or {})
            music.setdefault("track", None)
            music.setdefault("volume", 1.0)
            music.setdefault("overrides", [])
        return cls(
            id=str(payload.get("id") or "dungeon"),
            name=str(payload.get("name") or payload.get("id") or "Dungeon"),
            floor_count=max(1, int(payload.get("floors", payload.get("floor_count", 1)))),
            tileset=str(payload.get("tileset") or "dungeon"),
            generation=generation,
            music=music,
            enemy_count=dict(payload.get("enemy_count") or {"base": 2, "per_floor": 0, "max": 8}),
            item_count=dict(payload.get("item_count") or {"min": 2, "max": 4}),
            enemies=[SpawnRule.from_dict(item, "enemy") for item in payload.get("enemies", []) if item.get("enemy")],
            items=[SpawnRule.from_dict(item, "item") for item in payload.get("items", []) if item.get("item")],
            floor_rules=[dict(rule) for rule in payload.get("floor_rules", [])],
            generation_profile_rules=[dict(rule) for rule in payload.get("generation_profile_rules", [])],
        )

    @classmethod
    def load(cls, path: Path) -> "DungeonDefinition":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "floors": self.floor_count,
            "tileset": self.tileset,
            "generation": self.generation,
            "music": self.music,
            "enemy_count": self.enemy_count,
            "item_count": self.item_count,
            "enemies": [rule.to_dict("enemy") for rule in self.enemies],
            "items": [rule.to_dict("item") for rule in self.items],
            "floor_rules": self.floor_rules,
            "generation_profile_rules": self.generation_profile_rules,
        }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    def settings_for_floor(self, floor_number: int) -> dict[str, Any]:
        if not 1 <= floor_number <= self.floor_count:
            raise ValueError(f"Floor {floor_number} is outside 1-{self.floor_count}")
        settings: dict[str, Any] = {
            "tileset": self.tileset,
            "generation": dict(self.generation),
            "enemy_count": dict(self.enemy_count),
            "item_count": dict(self.item_count),
        }

        track = self.music.get("track")
        volume = float(self.music.get("volume", 1.0))
        for override in self.music.get("overrides", []):
            if floor_spec_matches(override.get("floors", "all"), floor_number, self.floor_count):
                if "track" in override:
                    track = override.get("track")
                if "volume" in override:
                    volume = float(override.get("volume", volume))
        settings["music"] = track
        settings["music_volume"] = max(0.0, min(1.0, volume))

        for rule in self.floor_rules:
            if not floor_spec_matches(rule.get("floors", "all"), floor_number, self.floor_count):
                continue
            if "tileset" in rule:
                settings["tileset"] = str(rule["tileset"])
            if "generation" in rule:
                merged = dict(settings["generation"])
                merged.update(dict(rule["generation"]))
                settings["generation"] = merged
            if "enemy_count" in rule:
                merged = dict(settings["enemy_count"])
                merged.update(dict(rule["enemy_count"]))
                settings["enemy_count"] = merged
            if "item_count" in rule:
                merged = dict(settings["item_count"])
                merged.update(dict(rule["item_count"]))
                settings["item_count"] = merged
            if "music" in rule:
                music_rule = rule["music"]
                if isinstance(music_rule, str) or music_rule is None:
                    settings["music"] = music_rule
                elif isinstance(music_rule, dict):
                    if "track" in music_rule:
                        settings["music"] = music_rule.get("track")
                    if "volume" in music_rule:
                        settings["music_volume"] = max(0.0, min(1.0, float(music_rule["volume"])))
        return settings

    def active_enemies(self, floor_number: int) -> list[SpawnRule]:
        return [r for r in self.enemies if floor_spec_matches(r.floors, floor_number, self.floor_count)]

    def active_items(self, floor_number: int) -> list[SpawnRule]:
        return [r for r in self.items if floor_spec_matches(r.floors, floor_number, self.floor_count)]

    def active_generation_profiles(self, floor_number: int) -> list[dict[str, Any]]:
        active: list[dict[str, Any]] = []
        for rule in self.generation_profile_rules:
            if not floor_spec_matches(rule.get("floors", "all"), floor_number, self.floor_count):
                continue
            profile_id = str(rule.get("profile", "default"))
            if profile_id not in GENERATION_PROFILES:
                continue
            weight = max(0.0, float(rule.get("weight", 1.0)))
            if weight <= 0:
                continue
            active.append({"profile": profile_id, "weight": weight})
        return active

    def choose_generation_profile(self, floor_number: int, rng: Random) -> str:
        active = self.active_generation_profiles(floor_number)
        if not active:
            return "default"
        return str(rng.choices(
            [rule["profile"] for rule in active],
            weights=[rule["weight"] for rule in active],
            k=1,
        )[0])

    def generation_for_floor(self, floor_number: int, rng: Random) -> tuple[str, dict[str, Any]]:
        settings = self.settings_for_floor(floor_number)
        profile_id = self.choose_generation_profile(floor_number, rng)
        raw = dict(settings["generation"])
        if profile_id != "default":
            raw.update(generation_profile_settings(profile_id))
        return profile_id, raw

    def generate_layout(self, floor_number: int, rng: Random) -> DungeonFloor:
        settings = self.settings_for_floor(floor_number)
        profile_id, raw = self.generation_for_floor(floor_number, rng)
        kind = str(raw.pop("type", "rooms_and_corridors"))

        if kind == "open_room":
            allowed = OpenRoomConfig.__dataclass_fields__.keys()
            config = OpenRoomConfig(**{k: raw[k] for k in allowed if k in raw})
            floor = OpenRoomGenerator(config=config, rng=rng).generate()
        else:
            allowed = GeneratorConfig.__dataclass_fields__.keys()
            config = GeneratorConfig(**{k: raw[k] for k in allowed if k in raw})
            floor = RoomsAndCorridorsGenerator(config=config, rng=rng).generate()

        floor.tileset = str(settings["tileset"])
        floor.music = settings.get("music")
        floor.music_volume = float(settings.get("music_volume", 1.0))
        floor.dungeon_name = self.name
        floor.generation_profile = profile_id
        return floor

    def build_floor(
        self,
        floor_number: int,
        rng: Random,
        enemy_factory: Callable[[str, str], Character],
        item_lookup: Callable[[str], ItemDefinition],
        enemy_modifier: Callable[[Character, SpawnRule], Character] | None = None,
    ) -> DungeonFloor:
        floor = self.generate_layout(floor_number, rng)
        valid = [
            GridPos(x, y)
            for y in range(floor.height)
            for x in range(floor.width)
            if floor.tile(GridPos(x, y)).walkable
            and GridPos(x, y) not in {floor.player_spawn, floor.stairs_pos}
            and (floor.player_spawn is None or floor.player_spawn.chebyshev(GridPos(x, y)) >= 6)
        ]
        rng.shuffle(valid)

        enemy_rules = self.active_enemies(floor_number)
        enemy_target = self._resolve_count(self.settings_for_floor(floor_number)["enemy_count"], floor_number, rng)
        self._spawn_enemies(
            floor, floor_number, enemy_target, enemy_rules, valid, rng,
            enemy_factory, enemy_modifier,
        )

        item_rules = self.active_items(floor_number)
        item_target = self._resolve_count(self.settings_for_floor(floor_number)["item_count"], floor_number, rng)
        self._spawn_items(floor, item_target, item_rules, valid, rng, item_lookup)
        return floor

    @staticmethod
    def _resolve_count(spec: dict[str, Any], floor_number: int, rng: Random) -> int:
        if "base" in spec or "per_floor" in spec:
            value = int(spec.get("base", 0)) + int(spec.get("per_floor", 0)) * max(0, floor_number - 1)
            value = max(int(spec.get("min", 0)), value)
            if spec.get("max") is not None:
                value = min(value, int(spec["max"]))
            return max(0, value)
        low = max(0, int(spec.get("min", 0)))
        high = max(low, int(spec.get("max", low)))
        return rng.randint(low, high)

    @staticmethod
    def _weighted_rule(rules: list[SpawnRule], counts: dict[str, int], rng: Random) -> SpawnRule | None:
        available = [r for r in rules if counts.get(r.content_id, 0) < r.max_per_floor and r.weight > 0]
        if not available:
            return None
        return rng.choices(available, weights=[r.weight for r in available], k=1)[0]

    def _spawn_enemies(
        self,
        floor: DungeonFloor,
        floor_number: int,
        target: int,
        rules: list[SpawnRule],
        valid: list[GridPos],
        rng: Random,
        factory: Callable[[str, str], Character],
        modifier: Callable[[Character, SpawnRule], Character] | None = None,
    ) -> None:
        counts: dict[str, int] = {}
        serial = 0

        def place(rule: SpawnRule) -> bool:
            nonlocal serial
            if not valid or counts.get(rule.content_id, 0) >= rule.max_per_floor:
                return False
            serial += 1
            enemy = factory(rule.content_id, f"{rule.content_id}_f{floor_number}_{serial}")
            if modifier is not None:
                enemy = modifier(enemy, rule)
            enemy.grid_pos = valid.pop()
            floor.entities.append(enemy)
            counts[rule.content_id] = counts.get(rule.content_id, 0) + 1
            return True

        for rule in rules:
            for _ in range(min(rule.min_per_floor, rule.max_per_floor)):
                if len(floor.entities) >= target or not place(rule):
                    break
        while len(floor.entities) < target and valid:
            rule = self._weighted_rule(rules, counts, rng)
            if rule is None or not place(rule):
                break

    def _spawn_items(
        self,
        floor: DungeonFloor,
        target: int,
        rules: list[SpawnRule],
        valid: list[GridPos],
        rng: Random,
        lookup: Callable[[str], ItemDefinition],
    ) -> None:
        counts: dict[str, int] = {}

        def place(rule: SpawnRule) -> bool:
            if not valid or counts.get(rule.content_id, 0) >= rule.max_per_floor:
                return False
            floor.ground_items.append(GroundItem(lookup(rule.content_id), valid.pop()))
            counts[rule.content_id] = counts.get(rule.content_id, 0) + 1
            return True

        for rule in rules:
            for _ in range(min(rule.min_per_floor, rule.max_per_floor)):
                if len(floor.ground_items) >= target or not place(rule):
                    break
        while len(floor.ground_items) < target and valid:
            rule = self._weighted_rule(rules, counts, rng)
            if rule is None or not place(rule):
                break
