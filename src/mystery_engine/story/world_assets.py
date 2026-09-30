from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from mystery_engine.core import Direction, Vec2
from .exploration import (
    ExplorationActor,
    ExplorationInteractable,
    ExplorationMap,
    ExplorationMarker,
    ExplorationScenery,
    ObstacleShape,
    PolygonObstacle,
    RectObstacle,
    TerrainTileMap,
)


def _parse_collision(data: object) -> ObstacleShape | None:
    if isinstance(data, list) and len(data) == 4:
        return RectObstacle(*[float(v) for v in data])
    if isinstance(data, dict):
        kind = str(data.get("type", "")).lower()
        if kind == "rect":
            if all(k in data for k in ("x", "y", "w", "h")):
                return RectObstacle(float(data["x"]), float(data["y"]), float(data["w"]), float(data["h"]))
        if kind == "polygon":
            points = data.get("points")
            if isinstance(points, list) and len(points) >= 3:
                return PolygonObstacle(tuple((float(p[0]), float(p[1])) for p in points))
    return None


def _serialize_collision(collision: ObstacleShape) -> object:
    if isinstance(collision, RectObstacle):
        return [collision.x, collision.y, collision.w, collision.h]
    if isinstance(collision, PolygonObstacle):
        return {
            "type": "polygon",
            "points": [[x, y] for x, y in collision.points],
        }
    raise TypeError(f"Unsupported collision type: {type(collision)!r}")


@dataclass(frozen=True)
class WorldAssetDefinition:
    """Game-provided definition for one placeable exploration asset.

    The editor consumes these definitions generically; the engine never needs to
    know what a "tree", "waystone", or game-specific prop is.
    """

    id: str
    category: str  # scenery | interactable | actor
    sprite_key: str | None
    display_name: str
    size: tuple[int, int] = (64, 64)
    anchor: str = "bottom_center"
    collision: ObstacleShape | None = None
    collision_radius: float = 0.0
    draw_behind_actors: bool = False
    label: str | None = None
    action_id: str | None = None
    actor_name: str | None = None
    color_key: str = "neutral"
    radius: float = 28.0
    # Semantic sound cues keyed by event name (for example "interact" or "use").
    # Scene instances may override these without changing the game-wide asset.
    sound_cues: Mapping[str, str] = field(default_factory=dict)
    # Runtime-invisible assets (notably scene portals) are still shown by the
    # editor using a generated marker rather than a game sprite.
    runtime_visible: bool = True


@dataclass(frozen=True)
class WorldAssetCatalog:
    assets: Mapping[str, WorldAssetDefinition]

    def get(self, asset_id: str) -> WorldAssetDefinition:
        try:
            return self.assets[asset_id]
        except KeyError as exc:
            raise KeyError(f"Unknown world asset: {asset_id}") from exc

    def by_category(self, *categories: str) -> list[WorldAssetDefinition]:
        wanted = set(categories)
        return sorted((a for a in self.assets.values() if a.category in wanted), key=lambda a: a.display_name.lower())


@dataclass
class SceneObjectData:
    id: str
    asset: str
    x: float
    y: float
    action: str | None = None
    label: str | None = None
    enabled: bool = True
    # None inherits the asset default; False disables collision for this placed
    # instance; True explicitly enables it. This is separate from the collision
    # shape so level designers can toggle a collider without losing its geometry.
    collision_enabled: bool | None = None
    # Optional per-instance collision shape, local to the object's anchor.
    # When omitted, the asset catalog's default collision is inherited.
    collision: ObstacleShape | None = None
    # Scene-portal metadata. `target_scene` is stored relative to the current
    # scene file when possible; `target_door` names the destination portal to
    # arrive beside. `portal_facing` controls which side of the destination
    # portal the party is placed on (N/E/S/W). `portal_mode` is editor metadata:
    # normal doors default to a maintained reciprocal pair, while one-way links
    # keep only the outgoing transition.
    target_scene: str | None = None
    target_door: str | None = None
    portal_facing: str = "S"
    portal_mode: str = "two_way"
    # Optional per-instance semantic sound-cue overrides.
    sound_cues: dict[str, str] = field(default_factory=dict)
    # Generic dungeon-entrance metadata. This is a stable dungeon ID, not a
    # game-specific Python callback.
    target_dungeon: str | None = None
    # Generic story interaction metadata. Actor/interactable instances can launch
    # a project story graph without a game-specific Python callback.
    target_story: str | None = None
    # Optional per-instance sprite key. Used by dungeon entrances and other
    # authorable interactables without creating a new global asset definition.
    sprite_override: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "SceneObjectData":
        return cls(
            id=str(data["id"]),
            asset=str(data["asset"]),
            x=float(data["x"]),
            y=float(data["y"]),
            action=data.get("action"),
            label=data.get("label"),
            enabled=bool(data.get("enabled", True)),
            collision_enabled=(bool(data["collision_enabled"]) if "collision_enabled" in data else None),
            collision=_parse_collision(data.get("collision")),
            target_scene=data.get("target_scene"),
            target_door=data.get("target_door"),
            portal_facing=str(data.get("portal_facing", "S")).upper(),
            portal_mode=("one_way" if str(data.get("portal_mode", "two_way")).lower() == "one_way" else "two_way"),
            sound_cues={str(k): str(v) for k, v in dict(data.get("sound_cues", {})).items() if v},
            target_dungeon=(str(data["target_dungeon"]) if data.get("target_dungeon") else None),
            target_story=(str(data["target_story"]) if data.get("target_story") else None),
            sprite_override=(str(data["sprite_override"]) if data.get("sprite_override") else None),
        )

    def to_dict(self) -> dict:
        data: dict[str, object] = {"id": self.id, "asset": self.asset, "x": self.x, "y": self.y}
        if self.action:
            data["action"] = self.action
        if self.label:
            data["label"] = self.label
        if not self.enabled:
            data["enabled"] = False
        if self.collision_enabled is not None:
            data["collision_enabled"] = self.collision_enabled
        if self.collision is not None:
            data["collision"] = _serialize_collision(self.collision)
        if self.target_scene:
            data["target_scene"] = self.target_scene
        if self.target_door:
            data["target_door"] = self.target_door
        if self.portal_facing and self.portal_facing != "S":
            data["portal_facing"] = self.portal_facing
        if self.portal_mode == "one_way":
            data["portal_mode"] = "one_way"
        if self.sound_cues:
            data["sound_cues"] = dict(sorted(self.sound_cues.items()))
        if self.target_dungeon:
            data["target_dungeon"] = self.target_dungeon
        if self.target_story:
            data["target_story"] = self.target_story
        if self.sprite_override:
            data["sprite_override"] = self.sprite_override
        return data


@dataclass
class ExplorationSceneData:
    id: str
    tile_size: int
    width_tiles: int
    height_tiles: int
    terrain: list[list[str]]
    elevations: list[list[int]]
    objects: list[SceneObjectData] = field(default_factory=list)
    blocked_terrain: list[str] = field(default_factory=lambda: ["water", "void"])
    elevation_face_depth: int = 44
    # Optional looping background music, stored relative to the game's asset root.
    # Scene gain is multiplied by the player's global in-game music volume.
    music: str | None = None
    music_volume: float = 1.0
    ambience_cue: str | None = None
    ambience_volume: float = 1.0
    background_key: str | None = None
    background_mode: str = "stretch"

    @property
    def width(self) -> int:
        return self.width_tiles * self.tile_size

    @property
    def height(self) -> int:
        return self.height_tiles * self.tile_size

    @classmethod
    def blank(cls, scene_id: str, width_tiles: int = 40, height_tiles: int = 24, tile_size: int = 64) -> "ExplorationSceneData":
        return cls(
            id=scene_id,
            tile_size=tile_size,
            width_tiles=width_tiles,
            height_tiles=height_tiles,
            terrain=[["grass" for _ in range(width_tiles)] for _ in range(height_tiles)],
            elevations=[[0 for _ in range(width_tiles)] for _ in range(height_tiles)],
        )

    @classmethod
    def from_dict(cls, data: dict) -> "ExplorationSceneData":
        width = int(data["width_tiles"])
        height = int(data["height_tiles"])
        terrain = [[str(v) for v in row] for row in data["terrain"]]
        elevations = [[int(v) for v in row] for row in data["elevations"]]
        if len(terrain) != height or any(len(row) != width for row in terrain):
            raise ValueError("Scene terrain dimensions do not match width_tiles/height_tiles")
        if len(elevations) != height or any(len(row) != width for row in elevations):
            raise ValueError("Scene elevation dimensions do not match width_tiles/height_tiles")
        return cls(
            id=str(data["id"]),
            tile_size=int(data.get("tile_size", 64)),
            width_tiles=width,
            height_tiles=height,
            terrain=terrain,
            elevations=elevations,
            objects=[SceneObjectData.from_dict(v) for v in data.get("objects", [])],
            blocked_terrain=[str(v) for v in data.get("blocked_terrain", ["water", "void"])],
            elevation_face_depth=int(data.get("elevation_face_depth", 44)),
            music=(str(data["music"]) if data.get("music") else None),
            music_volume=max(0.0, min(1.0, float(data.get("music_volume", 1.0)))),
            ambience_cue=(str(data["ambience_cue"]) if data.get("ambience_cue") else None),
            ambience_volume=max(0.0, min(1.0, float(data.get("ambience_volume", 1.0)))),
            background_key=(str(data["background_key"]) if data.get("background_key") else None),
            background_mode=("tile" if str(data.get("background_mode", "stretch")).lower() == "tile" else "stretch"),
        )

    def to_dict(self) -> dict:
        data = {
            "format": 1,
            "id": self.id,
            "tile_size": self.tile_size,
            "width_tiles": self.width_tiles,
            "height_tiles": self.height_tiles,
            "blocked_terrain": list(self.blocked_terrain),
            "elevation_face_depth": self.elevation_face_depth,
            "terrain": self.terrain,
            "elevations": self.elevations,
            "objects": [obj.to_dict() for obj in self.objects],
        }
        if self.music:
            data["music"] = self.music
        if self.music_volume != 1.0:
            data["music_volume"] = round(max(0.0, min(1.0, self.music_volume)), 3)
        if self.ambience_cue:
            data["ambience_cue"] = self.ambience_cue
        if self.ambience_volume != 1.0:
            data["ambience_volume"] = round(max(0.0, min(1.0, self.ambience_volume)), 3)
        if self.background_key:
            data["background_key"] = self.background_key
            data["background_mode"] = self.background_mode
        return data


InteractionRegistry = Mapping[str, Callable[[], None]]


def build_exploration_map(
    scene: ExplorationSceneData,
    catalog: WorldAssetCatalog,
    interactions: InteractionRegistry | None = None,
    portal_transition_factory: Callable[[SceneObjectData], Callable[[], None]] | None = None,
    dungeon_transition_factory: Callable[[SceneObjectData], Callable[[], None]] | None = None,
    story_transition_factory: Callable[[SceneObjectData], Callable[[], None]] | None = None,
    terrain_styles: Mapping[str, Mapping[str, object]] | None = None,
) -> ExplorationMap:
    interactions = interactions or {}
    scenery: list[ExplorationScenery] = []
    actors: list[ExplorationActor] = []
    interactables: list[ExplorationInteractable] = []
    markers: list[ExplorationMarker] = []

    for placed in scene.objects:
        definition = catalog.get(placed.asset)
        pos = Vec2(placed.x, placed.y)
        action_id = placed.action or definition.action_id
        interaction = interactions.get(action_id) if action_id else None
        if placed.target_story and story_transition_factory is not None:
            interaction = story_transition_factory(placed)
        collision = placed.collision if placed.collision is not None else definition.collision
        if placed.collision_enabled is False:
            collision = None

        if definition.category == "scenery":
            scenery.append(
                ExplorationScenery(
                    placed.id,
                    definition.sprite_key,
                    pos,
                    definition.size,
                    anchor=definition.anchor,
                    draw_behind_actors=definition.draw_behind_actors,
                    visible=definition.runtime_visible,
                    collision=collision,
                )
            )
        elif definition.category == "actor":
            actors.append(
                ExplorationActor(
                    placed.id,
                    definition.actor_name or definition.display_name,
                    pos,
                    radius=definition.radius,
                    facing=Direction.S,
                    color_key=definition.color_key,
                    sprite_key=definition.sprite_key,
                    interaction=interaction,
                    enabled=placed.enabled,
                    interaction_sound=placed.sound_cues.get("interact") or definition.sound_cues.get("interact"),
                )
            )
        elif definition.category == "marker":
            markers.append(ExplorationMarker(placed.id, pos))
        elif definition.category in {"interactable", "portal", "dungeon"}:
            # Portals and dungeon entrances are generic links. The game definition supplies the
            # transition callback factory, while ordinary interactables still use
            # named action IDs from the interaction registry.
            if definition.category == "portal" and portal_transition_factory is not None:
                callback = portal_transition_factory(placed)
            elif definition.category == "dungeon" and dungeon_transition_factory is not None:
                callback = dungeon_transition_factory(placed)
            else:
                callback = interaction or (lambda: None)
            interactables.append(
                ExplorationInteractable(
                    placed.id,
                    pos,
                    callback,
                    label=placed.label or definition.label or definition.display_name,
                    icon_key=placed.sprite_override or definition.sprite_key,
                    enabled=placed.enabled,
                    collision_radius=(0.0 if placed.collision_enabled is False else definition.collision_radius),
                    collision=collision,
                    anchor=definition.anchor,
                    visible=definition.runtime_visible,
                    portal_facing=placed.portal_facing if definition.category == "portal" else None,
                    interaction_sound=placed.sound_cues.get("interact") or placed.sound_cues.get("use") or definition.sound_cues.get("interact") or definition.sound_cues.get("use"),
                )
            )
        else:
            raise ValueError(f"Unsupported world asset category: {definition.category}")

    terrain = TerrainTileMap(
        tile_size=scene.tile_size,
        width_tiles=scene.width_tiles,
        height_tiles=scene.height_tiles,
        tiles=[row[:] for row in scene.terrain],
        elevations=[row[:] for row in scene.elevations],
        elevation_face_depth=scene.elevation_face_depth,
        default_terrain="void",
        default_elevation=0,
    )
    return ExplorationMap(
        id=scene.id,
        width=scene.width,
        height=scene.height,
        terrain=terrain,
        scenery=scenery,
        actors=actors,
        interactables=interactables,
        markers=markers,
        blocked_terrain=frozenset(
            set(scene.blocked_terrain)
            | {key for key, style in dict(terrain_styles or {}).items() if bool(style.get("blocked", False))}
        ),
        music=scene.music,
        music_volume=scene.music_volume,
        ambience_cue=scene.ambience_cue,
        ambience_volume=scene.ambience_volume,
        terrain_styles=dict(terrain_styles or {}),
        background_key=scene.background_key,
        background_mode=scene.background_mode,
    )
