from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import sys
from typing import Iterable

import pygame

from mystery_engine.presentation.sfx import SoundCueCatalog
from mystery_engine.core.autotile import autotile_asset, elevation_cliff_assets, oriented_neighbor_mask
from mystery_engine.story import (
    ExplorationSceneData,
    ObstacleShape,
    PolygonObstacle,
    RectObstacle,
    SceneObjectData,
    TerrainTileMap,
    WorldAssetCatalog,
    WorldAssetDefinition,
    load_exploration_scene,
    save_exploration_scene,
)
from .history import SnapshotHistory


@dataclass
class PaletteItem:
    key: str
    label: str
    rect: pygame.Rect
    value: object


class ExplorationSceneEditor:
    """Desktop-first visual editor for exploration scenes.

    It edits semantic terrain/elevation data and game-provided world assets, so
    all path/water/cliff orientation remains a runtime rendering concern rather
    than something the author must place tile-by-tile.
    """

    TOP_H = 58
    SIDE_W = 330
    STATUS_H = 30

    def __init__(
        self,
        scene: ExplorationSceneData,
        scene_path: Path,
        catalog: WorldAssetCatalog,
        asset_root: Path,
        *,
        project_root: Path | None = None,
        window_size: tuple[int, int] = (1600, 900),
    ) -> None:
        self.scene = scene
        self.scene_path = Path(scene_path)
        self.catalog = catalog
        self.asset_root = Path(asset_root)
        self.project_root = Path(project_root) if project_root else None
        self.window_size = window_size

        self.mode = "terrain"  # terrain | elevation | objects | select | audio
        self.terrain_brush = "grass"
        self.elevation_brush = 0
        self.asset_brush = next((a.id for a in catalog.by_category("scenery", "interactable", "actor")), "")
        self.snap = 16
        self.zoom = 1.0
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.grid = True
        self.show_collision = False
        self.show_elevation = False
        self.selected_object: int | None = None
        self.hover_tile: tuple[int, int] | None = None
        self.status = "Ready"
        self.dirty = False

        self.history = SnapshotHistory()
        self._stroke_before: dict | None = None
        self._stroke_last_tile: tuple[int, int] | None = None
        self._rect_start: tuple[int, int] | None = None
        self._drag_object_offset: tuple[float, float] | None = None
        self._pan_anchor: tuple[int, int] | None = None
        self._pan_camera_anchor: tuple[float, float] | None = None
        self._palette_scroll = 0
        self._music_previewing = False
        self._sfx_preview_channel: pygame.mixer.Channel | None = None
        self.sfx_catalog = SoundCueCatalog.load(self.asset_root / "sfx_cues.json")
        # Scene-link navigation. Opening a portal pushes the current scene so
        # Alt+Left / the sidebar Back button can return immediately.
        self.scene_nav_stack: list[Path] = []

        # Per-instance collision editing. A selected object can inherit its
        # catalog collider or store an explicit scene override.
        self.collision_edit = False
        self._collision_drag_handle: str | None = None
        self._collision_drag_start_world: tuple[float, float] | None = None
        self._collision_drag_start_shape: ObstacleShape | None = None
        self._collision_selected_vertex: int | None = None

        # Tiny inline text editor for interactable action IDs and labels.
        self._text_edit_field: str | None = None
        self._text_edit_buffer = ""
        self._text_edit_before: dict | None = None

        self._surface_cache: dict[Path, pygame.Surface | None] = {}
        self._scaled_cache: dict[tuple[Path, int, int], pygame.Surface | None] = {}
        # Actor previews must use the same directional 2x2 sheets as runtime.
        # Cache the extracted/scaled frame separately from ordinary file assets.
        self._actor_surface_cache: dict[tuple[str, str, int, int], pygame.Surface | None] = {}
        self._palette_items: list[PaletteItem] = []

        self.screen: pygame.Surface | None = None
        self.font: pygame.font.Font | None = None
        self.font_small: pygame.font.Font | None = None
        self.font_large: pygame.font.Font | None = None

    # ---------- coordinate helpers ----------

    @property
    def canvas_rect(self) -> pygame.Rect:
        w, h = self.screen.get_size() if self.screen else self.window_size
        return pygame.Rect(0, self.TOP_H, w - self.SIDE_W, h - self.TOP_H - self.STATUS_H)

    @property
    def sidebar_rect(self) -> pygame.Rect:
        w, h = self.screen.get_size() if self.screen else self.window_size
        return pygame.Rect(w - self.SIDE_W, self.TOP_H, self.SIDE_W, h - self.TOP_H - self.STATUS_H)

    def screen_to_world(self, pos: tuple[int, int]) -> tuple[float, float]:
        rect = self.canvas_rect
        return (
            self.camera_x + (pos[0] - rect.x) / self.zoom,
            self.camera_y + (pos[1] - rect.y) / self.zoom,
        )

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        rect = self.canvas_rect
        return (
            round(rect.x + (x - self.camera_x) * self.zoom),
            round(rect.y + (y - self.camera_y) * self.zoom),
        )

    def screen_to_tile(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        if not self.canvas_rect.collidepoint(pos):
            return None
        wx, wy = self.screen_to_world(pos)
        tx, ty = int(wx // self.scene.tile_size), int(wy // self.scene.tile_size)
        if 0 <= tx < self.scene.width_tiles and 0 <= ty < self.scene.height_tiles:
            return tx, ty
        return None

    def _terrain_proxy(self) -> TerrainTileMap:
        return TerrainTileMap(
            tile_size=self.scene.tile_size,
            width_tiles=self.scene.width_tiles,
            height_tiles=self.scene.height_tiles,
            default_terrain="void",
            default_elevation=0,
            tiles=self.scene.terrain,
            elevations=self.scene.elevations,
            elevation_face_depth=self.scene.elevation_face_depth,
        )

    # ---------- file/history ----------

    def save(self) -> None:
        save_exploration_scene(self.scene, self.scene_path)
        self.dirty = False
        self.status = f"Saved {self.scene_path.name}"

    def _begin_change(self) -> None:
        if self._stroke_before is None:
            self._stroke_before = self.history.snapshot(self.scene)

    def _commit_change(self) -> None:
        if self._stroke_before is not None:
            self.history.remember(self._stroke_before)
            self._stroke_before = None
            self.dirty = True

    def undo(self) -> None:
        new_scene = self.history.undo(self.scene)
        if new_scene is not self.scene:
            self.scene = new_scene
            self.selected_object = None
            self.collision_edit = False
            self._text_edit_field = None
            self.dirty = True
            self.status = "Undo"

    def redo(self) -> None:
        new_scene = self.history.redo(self.scene)
        if new_scene is not self.scene:
            self.scene = new_scene
            self.selected_object = None
            self.collision_edit = False
            self._text_edit_field = None
            self.dirty = True
            self.status = "Redo"

    # ---------- asset helpers ----------

    def _native_surface(self, relative: str) -> pygame.Surface | None:
        if not relative:
            return None
        path = self.asset_root / relative
        if path in self._surface_cache:
            return self._surface_cache[path]
        try:
            surf = pygame.image.load(str(path)).convert_alpha()
        except (pygame.error, FileNotFoundError):
            surf = None
        self._surface_cache[path] = surf
        return surf

    def _scaled_surface(self, relative: str, size: tuple[int, int]) -> pygame.Surface | None:
        path = self.asset_root / relative
        key = (path, size[0], size[1])
        if key in self._scaled_cache:
            return self._scaled_cache[key]
        surf = self._native_surface(relative)
        if surf is None:
            self._scaled_cache[key] = None
            return None
        scaled = surf if surf.get_size() == size else pygame.transform.scale(surf, size)
        self._scaled_cache[key] = scaled
        return scaled

    def _world_asset_path(self, definition: WorldAssetDefinition) -> str:
        """Return a direct-file path for non-actor assets.

        Actors deliberately do not use this helper for rendering: the runtime
        prefers a shared 2x2 directional sheet, so the editor now does too.
        """
        if not definition.sprite_key or definition.category == "portal":
            return ""
        if definition.category == "actor":
            return f"characters/{definition.sprite_key}_s.png"
        return f"objects/{definition.sprite_key}.png"

    def _actor_direction_surface(
        self,
        sprite_key: str,
        suffix: str = "s",
        size: tuple[int, int] = (84, 84),
    ) -> pygame.Surface | None:
        """Load an actor exactly the way the exploration runtime does.

        Preferred source is the 2x2 directional sheet:
        north/east on the top row, south/west on the bottom row. The selected
        frame is cropped to its non-transparent bounds and then scaled to the
        runtime exploration size. Standalone directional files remain a
        compatibility fallback only.
        """
        cache_key = (sprite_key, suffix, size[0], size[1])
        if cache_key in self._actor_surface_cache:
            return self._actor_surface_cache[cache_key]

        sheet_path = self.asset_root / f"characters/{sprite_key}_sheet.png"
        surface: pygame.Surface | None = None
        if sheet_path.exists():
            try:
                sheet = pygame.image.load(str(sheet_path)).convert_alpha()
                fw = sheet.get_width() // 2
                fh = sheet.get_height() // 2
                sx, sy = {"n": (0, 0), "e": (1, 0), "s": (0, 1), "w": (1, 1)}.get(suffix, (0, 1))
                frame = pygame.Surface((fw, fh), pygame.SRCALPHA)
                frame.blit(sheet, (0, 0), pygame.Rect(sx * fw, sy * fh, fw, fh))
                bounds = frame.get_bounding_rect()
                if bounds.width > 0 and bounds.height > 0:
                    frame = frame.subsurface(bounds).copy()
                surface = frame if frame.get_size() == size else pygame.transform.scale(frame, size)
            except pygame.error:
                surface = None

        if surface is None:
            relative = f"characters/{sprite_key}_{suffix}.png"
            fallback = self._native_surface(relative)
            if fallback is not None:
                surface = fallback if fallback.get_size() == size else pygame.transform.scale(fallback, size)

        self._actor_surface_cache[cache_key] = surface
        return surface

    def _world_asset_native_surface(self, definition: WorldAssetDefinition) -> pygame.Surface | None:
        if not definition.sprite_key or definition.category == "portal":
            return None
        if definition.category == "actor":
            # Runtime exploration actors are drawn at 84x84.
            return self._actor_direction_surface(definition.sprite_key, "s", (84, 84))
        return self._native_surface(self._world_asset_path(definition))

    def _effective_collision(self, obj: SceneObjectData, definition: WorldAssetDefinition) -> ObstacleShape | None:
        return obj.collision if obj.collision is not None else definition.collision

    @staticmethod
    def _copy_collision(shape: ObstacleShape | None) -> ObstacleShape | None:
        if shape is None:
            return None
        if isinstance(shape, RectObstacle):
            return RectObstacle(shape.x, shape.y, shape.w, shape.h)
        return PolygonObstacle(tuple((x, y) for x, y in shape.points))

    @staticmethod
    def _rect_to_polygon(rect: RectObstacle) -> PolygonObstacle:
        return PolygonObstacle(rect.polygon_points())

    @staticmethod
    def _polygon_to_rect(polygon: PolygonObstacle) -> RectObstacle:
        return polygon.bounds()

    def _selected_pair(self) -> tuple[SceneObjectData, WorldAssetDefinition] | None:
        if self.selected_object is None or not (0 <= self.selected_object < len(self.scene.objects)):
            return None
        obj = self.scene.objects[self.selected_object]
        return obj, self.catalog.get(obj.asset)

    def _default_collision_for(self, definition: WorldAssetDefinition) -> RectObstacle:
        if isinstance(definition.collision, RectObstacle):
            c = definition.collision
            return RectObstacle(c.x, c.y, c.w, c.h)
        if isinstance(definition.collision, PolygonObstacle):
            return definition.collision.bounds()
        # New assets without a catalog collider get a conservative base box.
        w, h = definition.size
        return RectObstacle(-w * 0.30, -h * 0.22, w * 0.60, max(12.0, h * 0.22))

    def _ensure_collision_override(self, *, prefer_polygon: bool = False) -> ObstacleShape | None:
        pair = self._selected_pair()
        if pair is None:
            return None
        obj, definition = pair
        if definition.category in {"actor", "portal"}:
            return None
        if obj.collision is None:
            base = self._effective_collision(obj, definition)
            if base is None:
                base = self._default_collision_for(definition)
            obj.collision = self._copy_collision(base)
        if prefer_polygon and isinstance(obj.collision, RectObstacle):
            obj.collision = self._rect_to_polygon(obj.collision)
        return obj.collision

    def _collision_screen_rect(self, obj: SceneObjectData, definition: WorldAssetDefinition) -> pygame.Rect | None:
        c = self._effective_collision(obj, definition)
        if not isinstance(c, RectObstacle):
            return None
        sx, sy = self.world_to_screen(obj.x + c.x, obj.y + c.y)
        return pygame.Rect(sx, sy, max(1, round(c.w * self.zoom)), max(1, round(c.h * self.zoom)))

    def _collision_screen_points(self, obj: SceneObjectData, poly: PolygonObstacle) -> list[tuple[int, int]]:
        return [self.world_to_screen(obj.x + px, obj.y + py) for px, py in poly.points]

    @staticmethod
    def _collision_handles(rect: pygame.Rect) -> dict[str, tuple[int, int]]:
        return {
            "nw": rect.topleft, "n": (rect.centerx, rect.top), "ne": rect.topright,
            "e": (rect.right, rect.centery), "se": rect.bottomright,
            "s": (rect.centerx, rect.bottom), "sw": rect.bottomleft,
            "w": (rect.left, rect.centery),
        }

    @staticmethod
    def _distance_sq_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
        abx = bx - ax
        aby = by - ay
        denom = abx * abx + aby * aby
        if denom <= 1e-9:
            dx = px - ax
            dy = py - ay
            return dx * dx + dy * dy
        t = ((px - ax) * abx + (py - ay) * aby) / denom
        t = max(0.0, min(1.0, t))
        qx = ax + t * abx
        qy = ay + t * aby
        dx = px - qx
        dy = py - qy
        return dx * dx + dy * dy

    @staticmethod
    def _screen_polygon_contains(points: list[tuple[int, int]], pos: tuple[int, int]) -> bool:
        x, y = pos
        inside = False
        for i, (ax, ay) in enumerate(points):
            bx, by = points[(i + 1) % len(points)]
            if ((ay > y) != (by > y)) and (x < (bx - ax) * (y - ay) / ((by - ay) or 1e-9) + ax):
                inside = not inside
        return inside

    def _polygon_edge_hit(self, pos: tuple[int, int]) -> int | None:
        pair = self._selected_pair()
        if pair is None or not self.collision_edit:
            return None
        obj, definition = pair
        c = self._effective_collision(obj, definition)
        if not isinstance(c, PolygonObstacle):
            return None
        points = self._collision_screen_points(obj, c)
        if len(points) < 2:
            return None
        threshold_sq = 11 ** 2
        best: tuple[float, int] | None = None
        for i, (ax, ay) in enumerate(points):
            bx, by = points[(i + 1) % len(points)]
            dist_sq = self._distance_sq_point_to_segment(pos[0], pos[1], ax, ay, bx, by)
            if dist_sq <= threshold_sq and (best is None or dist_sq < best[0]):
                best = (dist_sq, i)
        return None if best is None else best[1]

    def _collision_handle_hit(self, pos: tuple[int, int]) -> str | None:
        pair = self._selected_pair()
        if pair is None or not self.collision_edit:
            return None
        obj, definition = pair
        shape = self._effective_collision(obj, definition)
        if isinstance(shape, RectObstacle):
            rect = self._collision_screen_rect(obj, definition)
            if rect is None:
                return None
            radius = 10
            for name, hp in self._collision_handles(rect).items():
                if (pos[0]-hp[0])**2 + (pos[1]-hp[1])**2 <= radius**2:
                    return name
            return "move" if rect.collidepoint(pos) else None
        if isinstance(shape, PolygonObstacle):
            points = self._collision_screen_points(obj, shape)
            radius = 10
            for index, hp in enumerate(points):
                if (pos[0]-hp[0])**2 + (pos[1]-hp[1])**2 <= radius**2:
                    return f"vertex:{index}"
            return "move_poly" if self._screen_polygon_contains(points, pos) else None
        return None

    def add_or_edit_collision(self) -> None:
        pair = self._selected_pair()
        if pair is None or pair[1].category in {"actor", "portal"}:
            self.status = "This asset does not use a collision box"
            return
        before = self.history.snapshot(self.scene)
        created = pair[0].collision is None and pair[1].collision is None
        self._ensure_collision_override()
        if created:
            self.history.remember(before)
            self.dirty = True
        self.collision_edit = True
        self.show_collision = True
        self.status = "Collision edit: B edits current shape; P polygon; X box; R resets"

    def convert_selected_collision_to_polygon(self) -> None:
        pair = self._selected_pair()
        if pair is None or pair[1].category in {"actor", "portal"}:
            self.status = "This asset does not use a collision polygon"
            return
        before = self.history.snapshot(self.scene)
        current = self._ensure_collision_override(prefer_polygon=True)
        if current is None:
            return
        self.history.remember(before)
        self.collision_edit = True
        self.show_collision = True
        self.dirty = True
        self.status = "Polygon collision: drag vertices; Shift+click edge adds vertex; Delete removes vertex"

    def convert_selected_collision_to_rect(self) -> None:
        pair = self._selected_pair()
        if pair is None or pair[1].category in {"actor", "portal"}:
            self.status = "This asset does not use a collision box"
            return
        obj, definition = pair
        before = self.history.snapshot(self.scene)
        shape = self._ensure_collision_override()
        if isinstance(shape, PolygonObstacle):
            obj.collision = self._polygon_to_rect(shape)
            self.history.remember(before)
            self.dirty = True
        self.collision_edit = True
        self.show_collision = True
        self._collision_selected_vertex = None
        self.status = "Rectangle collision active"

    def reset_collision_override(self) -> None:
        pair = self._selected_pair()
        if pair is None or pair[0].collision is None:
            return
        before = self.history.snapshot(self.scene)
        pair[0].collision = None
        self.history.remember(before)
        self.dirty = True
        self.collision_edit = False
        self._collision_selected_vertex = None
        self.status = "Collision reset to asset default"

    def _start_text_edit(self, field: str) -> None:
        pair = self._selected_pair()
        if pair is None:
            return
        obj, definition = pair
        if field in {"action", "label"} and definition.category != "interactable":
            return
        if field in {"target_scene", "target_door"} and definition.category != "portal":
            return
        self._text_edit_field = field
        if field == "action":
            self._text_edit_buffer = obj.action or definition.action_id or ""
        elif field == "label":
            self._text_edit_buffer = obj.label or definition.label or definition.display_name
        elif field == "target_scene":
            self._text_edit_buffer = obj.target_scene or ""
        elif field == "target_door":
            self._text_edit_buffer = obj.target_door or ""
        self._text_edit_before = self.history.snapshot(self.scene)
        self.status = f"Editing {field.replace('_', ' ')}: Enter saves, Esc cancels"

    def _commit_text_edit(self) -> None:
        pair = self._selected_pair()
        if pair is None or self._text_edit_field is None:
            self._text_edit_field = None
            return
        obj, _ = pair
        field = self._text_edit_field
        value = self._text_edit_buffer.strip() or None
        if field == "action":
            obj.action = value
        elif field == "label":
            obj.label = value
        elif field == "target_scene":
            obj.target_scene = value
        elif field == "target_door":
            obj.target_door = value
        if self._text_edit_before is not None:
            self.history.remember(self._text_edit_before)
        self._text_edit_before = None
        self._text_edit_field = None
        self.dirty = True
        if field in {"target_scene", "target_door"} and obj.target_scene:
            if not self._sync_selected_portal_pair():
                self.status = "Property updated; open destination to finish linking"
        else:
            self.status = "Property updated"

    def _cancel_text_edit(self) -> None:
        self._text_edit_field = None
        self._text_edit_buffer = ""
        self._text_edit_before = None
        self.status = "Property edit cancelled"

    # ---------- scene portal helpers ----------

    def _resolve_target_scene_path(self, target_scene: str) -> Path:
        path = Path(target_scene)
        if not path.suffix:
            path = path.with_suffix(".json")
        if not path.is_absolute():
            path = self.scene_path.parent / path
        return path.resolve()

    def _relative_scene_ref(self, path: Path, from_path: Path | None = None) -> str:
        from_path = from_path or self.scene_path
        try:
            return str(path.resolve().relative_to(from_path.parent.resolve()))
        except ValueError:
            return os.path.relpath(path.resolve(), from_path.parent.resolve())

    def _switch_scene(self, path: Path, *, select_object_id: str | None = None, push_current: bool = True) -> None:
        self._stop_music_preview()
        self._stop_sfx_preview()
        path = Path(path).resolve()
        if push_current:
            self.save()
            self.scene_nav_stack.append(self.scene_path.resolve())
        self.scene_path = path
        self.scene = load_exploration_scene(path)
        self.history = SnapshotHistory()
        self.selected_object = None
        self.collision_edit = False
        self._text_edit_field = None
        self.camera_x = 0.0
        self.camera_y = 0.0
        self._palette_scroll = 0
        self.dirty = False
        if select_object_id:
            self.selected_object = next((i for i, obj in enumerate(self.scene.objects) if obj.id == select_object_id), None)
            if self.selected_object is not None:
                self.mode = "select"
        self._clamp_camera()
        self.status = f"Opened {path.name}"

    @staticmethod
    def _unique_object_id(scene: ExplorationSceneData, base: str) -> str:
        existing = {o.id for o in scene.objects}
        if base not in existing:
            return base
        i = 2
        while f"{base}_{i}" in existing:
            i += 1
        return f"{base}_{i}"

    @staticmethod
    def _find_scene_object(scene: ExplorationSceneData, object_id: str | None) -> SceneObjectData | None:
        if not object_id:
            return None
        return next((o for o in scene.objects if o.id == object_id), None)

    def _ensure_destination_anchor(
        self,
        source_obj: SceneObjectData,
        target: ExplorationSceneData,
        target_path: Path,
    ) -> SceneObjectData:
        """Return/create the destination portal used as an arrival anchor.

        Two-way doors maintain a reciprocal transition. One-way doors still use
        an invisible destination portal as an arrival marker, but that marker is
        disabled so it cannot be used to travel back.
        """
        partner = self._find_scene_object(target, source_obj.target_door)
        if partner is None or partner.asset != "scene_door":
            base = "return_door" if source_obj.portal_mode == "two_way" else f"{source_obj.id}_arrival"
            partner = SceneObjectData(
                id=self._unique_object_id(target, base),
                asset="scene_door",
                x=target.width / 2,
                y=target.height - target.tile_size * 1.5,
                label="Back" if source_obj.portal_mode == "two_way" else "Arrival",
                portal_facing="N",
            )
            target.objects.append(partner)
            source_obj.target_door = partner.id

        if source_obj.portal_mode == "two_way":
            partner.enabled = True
            partner.portal_mode = "two_way"
            partner.target_scene = self._relative_scene_ref(self.scene_path, target_path)
            partner.target_door = source_obj.id
        else:
            partner.enabled = False
            partner.portal_mode = "one_way"
            partner.target_scene = None
            partner.target_door = None

        return partner

    def _sync_selected_portal_pair(self) -> bool:
        """Persist the selected door's reciprocal/arrival anchor when possible."""
        pair = self._selected_pair()
        if pair is None or pair[1].category != "portal":
            return False
        obj, _ = pair
        if not obj.target_scene:
            return False
        target_path = self._resolve_target_scene_path(obj.target_scene)
        if not target_path.exists():
            return False
        target = load_exploration_scene(target_path)
        partner = self._ensure_destination_anchor(obj, target, target_path)
        save_exploration_scene(target, target_path)
        self.dirty = True
        self.status = (
            f"Two-way connection synced with {target_path.name} → {partner.id}"
            if obj.portal_mode == "two_way"
            else f"One-way connection synced to {target_path.name}"
        )
        return True

    def toggle_portal_mode(self) -> None:
        pair = self._selected_pair()
        if pair is None or pair[1].category != "portal":
            self.status = "Select a scene door first"
            return
        obj, _ = pair
        before = self.history.snapshot(self.scene)
        obj.portal_mode = "one_way" if obj.portal_mode == "two_way" else "two_way"
        self.history.remember(before)
        self.dirty = True
        if obj.target_scene:
            self._sync_selected_portal_pair()
        else:
            self.status = f"Door mode: {'Two-way' if obj.portal_mode == 'two_way' else 'One-way'}"

    def unlink_selected_portal(self) -> None:
        pair = self._selected_pair()
        if pair is None or pair[1].category != "portal":
            self.status = "Select a scene door first"
            return
        obj, _ = pair
        before = self.history.snapshot(self.scene)

        # If this is a maintained pair, clear the partner's backlink without
        # deleting the destination object; it remains a harmless arrival marker.
        if obj.target_scene and obj.target_door:
            target_path = self._resolve_target_scene_path(obj.target_scene)
            if target_path.exists():
                target = load_exploration_scene(target_path)
                partner = self._find_scene_object(target, obj.target_door)
                if partner is not None and partner.asset == "scene_door":
                    source_ref = self._relative_scene_ref(self.scene_path, target_path)
                    if partner.target_scene == source_ref and partner.target_door == obj.id:
                        partner.target_scene = None
                        partner.target_door = None
                        partner.enabled = False
                        partner.portal_mode = "one_way"
                        save_exploration_scene(target, target_path)

        obj.target_scene = None
        obj.target_door = None
        self.history.remember(before)
        self.dirty = True
        self.status = "Door unlinked"

    def open_linked_scene(self) -> None:
        pair = self._selected_pair()
        if pair is None or pair[1].category != "portal":
            self.status = "Select a scene door first"
            return
        obj, _ = pair
        before = self.history.snapshot(self.scene)
        if not obj.target_scene:
            obj.target_scene = f"{self.scene_path.stem}_{obj.id}.json"
            self.history.remember(before)
            self.dirty = True
        target_path = self._resolve_target_scene_path(obj.target_scene)

        if not target_path.exists():
            target = ExplorationSceneData.blank(target_path.stem, 16, 12, self.scene.tile_size)
            partner = self._ensure_destination_anchor(obj, target, target_path)
            save_exploration_scene(target, target_path)
            self.save()
            self._switch_scene(target_path, select_object_id=partner.id, push_current=True)
            self.status = (
                f"Created two-way linked scene {target_path.name}"
                if obj.portal_mode == "two_way"
                else f"Created one-way linked scene {target_path.name}"
            )
            return

        target = load_exploration_scene(target_path)
        partner = self._ensure_destination_anchor(obj, target, target_path)
        save_exploration_scene(target, target_path)
        self.save()
        self._switch_scene(target_path, select_object_id=partner.id, push_current=True)

    def back_scene(self) -> None:
        if not self.scene_nav_stack:
            self.status = "No previous scene"
            return
        self.save()
        path = self.scene_nav_stack.pop()
        self._switch_scene(path, push_current=False)

    def cycle_portal_facing(self) -> None:
        pair = self._selected_pair()
        if pair is None or pair[1].category != "portal":
            return
        before = self.history.snapshot(self.scene)
        order = ["N", "E", "S", "W"]
        current = pair[0].portal_facing if pair[0].portal_facing in order else "S"
        pair[0].portal_facing = order[(order.index(current) + 1) % len(order)]
        self.history.remember(before)
        self.dirty = True
        self.status = f"Door arrival facing: {pair[0].portal_facing}"

    # ---------- scene music ----------

    @property
    def _music_dir(self) -> Path:
        return self.asset_root / "music"

    def _music_tracks(self) -> list[Path]:
        self._music_dir.mkdir(parents=True, exist_ok=True)
        supported = {".ogg", ".wav", ".mp3", ".flac"}
        return sorted(
            (p for p in self._music_dir.iterdir() if p.is_file() and p.suffix.lower() in supported),
            key=lambda p: p.name.lower(),
        )

    def _select_music_track(self, relative: str | None) -> None:
        before = self.history.snapshot(self.scene)
        self.scene.music = relative
        self.history.remember(before)
        self.dirty = True
        self.status = "Scene music cleared" if relative is None else f"Scene music: {Path(relative).name}"
        self._stop_music_preview()

    def _set_scene_music_volume(self, delta: float) -> None:
        before = self.history.snapshot(self.scene)
        self.scene.music_volume = max(0.0, min(1.0, round(self.scene.music_volume + delta, 2)))
        self.history.remember(before)
        self.dirty = True
        self.status = f"Scene music gain: {round(self.scene.music_volume * 100)}%"
        if self._music_previewing:
            try:
                pygame.mixer.music.set_volume(self.scene.music_volume)
            except pygame.error:
                pass

    def _import_music_path(self, source: Path) -> None:
        source = Path(source)
        supported = {".ogg", ".wav", ".mp3", ".flac"}
        if source.suffix.lower() not in supported:
            self.status = "Supported audio: OGG, WAV, MP3, FLAC"
            return
        if not source.exists():
            self.status = f"Audio file not found: {source.name}"
            return
        self._music_dir.mkdir(parents=True, exist_ok=True)
        dest = self._music_dir / source.name
        try:
            if source.resolve() != dest.resolve():
                shutil.copy2(source, dest)
        except OSError as exc:
            self.status = f"Could not import audio: {exc}"
            return
        self._select_music_track(f"music/{dest.name}")
        self.status = f"Imported {dest.name}"

    def _import_music_dialog(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            chosen = filedialog.askopenfilename(
                title="Import scene music",
                filetypes=[
                    ("Audio files", "*.ogg *.wav *.mp3 *.flac"),
                    ("OGG", "*.ogg"), ("WAV", "*.wav"),
                    ("MP3", "*.mp3"), ("FLAC", "*.flac"),
                    ("All files", "*.*"),
                ],
            )
            root.destroy()
        except Exception as exc:
            self.status = f"File picker unavailable: {exc}"
            return
        if chosen:
            self._import_music_path(Path(chosen))

    def _preview_scene_music(self) -> None:
        if not self.scene.music:
            self.status = "Choose a music track first"
            return
        path = self.asset_root / self.scene.music
        if not path.exists():
            self.status = f"Missing music file: {path.name}"
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(self.scene.music_volume)
            pygame.mixer.music.play(loops=-1, fade_ms=150)
            self._music_previewing = True
            self.status = f"Previewing {path.name}"
        except pygame.error as exc:
            self.status = f"Could not preview audio: {exc}"

    def _stop_music_preview(self) -> None:
        try:
            if pygame.mixer.get_init() is not None:
                pygame.mixer.music.stop()
        except pygame.error:
            pass
        self._music_previewing = False

    # ---------- semantic SFX / ambience ----------

    def _preview_sound_cue(self, cue_id: str | None) -> None:
        self._stop_sfx_preview()
        cue = self.sfx_catalog.get(cue_id)
        if cue is None:
            self.status = "No sound cue selected"
            return
        if not cue.variants:
            self.status = f"Cue has no variants: {cue.label}"
            return
        path = self.asset_root / cue.variants[0]
        if not path.exists():
            self.status = f"Missing SFX file: {path.name}"
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            sound = pygame.mixer.Sound(str(path))
            channel = pygame.mixer.find_channel(True)
            if channel is None:
                self.status = "No free audio channel"
                return
            channel.set_volume(cue.volume)
            channel.play(sound, loops=-1 if cue.loop else 0)
            self._sfx_preview_channel = channel
            self.status = f"Previewing cue: {cue.label}"
        except pygame.error as exc:
            self.status = f"Could not preview SFX: {exc}"

    def _stop_sfx_preview(self) -> None:
        if self._sfx_preview_channel is not None:
            try:
                self._sfx_preview_channel.stop()
            except pygame.error:
                pass
        self._sfx_preview_channel = None

    def _set_scene_ambience(self, cue_id: str | None) -> None:
        before = self.history.snapshot(self.scene)
        self.scene.ambience_cue = cue_id
        self.history.remember(before)
        self.dirty = True
        self._stop_sfx_preview()
        cue = self.sfx_catalog.get(cue_id)
        self.status = "Scene ambience cleared" if cue is None else f"Scene ambience: {cue.label}"

    def _set_scene_ambience_volume(self, delta: float) -> None:
        before = self.history.snapshot(self.scene)
        self.scene.ambience_volume = max(0.0, min(1.0, round(self.scene.ambience_volume + delta, 2)))
        self.history.remember(before)
        self.dirty = True
        self.status = f"Ambience gain: {round(self.scene.ambience_volume * 100)}%"

    def _effective_object_sound(self, obj: SceneObjectData, definition: WorldAssetDefinition) -> str | None:
        event = "use" if definition.category == "portal" else "interact"
        return obj.sound_cues.get(event) or definition.sound_cues.get(event)

    def _object_sound_candidates(self) -> list[str]:
        allowed = {"Ui", "Magic", "Combat"}
        return [cue.id for cue in self.sfx_catalog.all() if cue.category in allowed]

    def _cycle_selected_object_sound(self, delta: int) -> None:
        pair = self._selected_pair()
        if pair is None:
            return
        obj, definition = pair
        if definition.category not in {"interactable", "portal", "actor"}:
            self.status = "This object has no interaction sound event"
            return
        candidates = self._object_sound_candidates()
        if not candidates:
            self.status = "No SFX cues are registered"
            return
        event = "use" if definition.category == "portal" else "interact"
        current = self._effective_object_sound(obj, definition)
        if current in candidates:
            index = (candidates.index(current) + delta) % len(candidates)
        else:
            index = 0 if delta >= 0 else len(candidates) - 1
        before = self.history.snapshot(self.scene)
        obj.sound_cues[event] = candidates[index]
        self.history.remember(before)
        self.dirty = True
        cue = self.sfx_catalog.get(candidates[index])
        self.status = f"{event.title()} sound: {cue.label if cue else candidates[index]}"

    def _reset_selected_object_sound(self) -> None:
        pair = self._selected_pair()
        if pair is None:
            return
        obj, definition = pair
        event = "use" if definition.category == "portal" else "interact"
        if event not in obj.sound_cues:
            return
        before = self.history.snapshot(self.scene)
        obj.sound_cues.pop(event, None)
        self.history.remember(before)
        self.dirty = True
        self.status = "Sound reset to asset default"

    # ---------- rendering ----------

    def draw(self) -> None:
        assert self.screen and self.font and self.font_small and self.font_large
        self.screen.fill((17, 21, 28))
        self._draw_toolbar()
        self._draw_canvas()
        self._draw_sidebar()
        self._draw_statusbar()

    def _draw_toolbar(self) -> None:
        assert self.screen and self.font
        pygame.draw.rect(self.screen, (30, 36, 47), (0, 0, self.screen.get_width(), self.TOP_H))
        buttons = [
            ("terrain", "1 Terrain"), ("elevation", "2 Elevation"), ("objects", "3 Assets"),
            ("select", "4 Select"), ("audio", "5 Audio"),
        ]
        x = 12
        for key, label in buttons:
            rect = pygame.Rect(x, 9, 130, 40)
            pygame.draw.rect(self.screen, (76, 91, 112) if self.mode == key else (47, 56, 70), rect, border_radius=7)
            self.screen.blit(self.font.render(label, True, (245, 242, 232)), (rect.x + 10, rect.y + 9))
            x += 140
        x += 10
        for label, active in [("G Grid", self.grid), ("C Collision", self.show_collision), ("V Elevation", self.show_elevation)]:
            rect = pygame.Rect(x, 9, 130, 40)
            pygame.draw.rect(self.screen, (67, 96, 76) if active else (47, 56, 70), rect, border_radius=7)
            self.screen.blit(self.font.render(label, True, (245, 242, 232)), (rect.x + 10, rect.y + 9))
            x += 140
        save_rect = pygame.Rect(self.screen.get_width() - self.SIDE_W - 110, 9, 96, 40)
        pygame.draw.rect(self.screen, (116, 94, 47), save_rect, border_radius=7)
        self.screen.blit(self.font.render("Ctrl+S", True, (255, 248, 222)), (save_rect.x + 13, save_rect.y + 9))

    def _draw_canvas(self) -> None:
        assert self.screen and self.font_small
        rect = self.canvas_rect
        pygame.draw.rect(self.screen, (10, 14, 22), rect)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(rect)
        proxy = self._terrain_proxy()
        tile = self.scene.tile_size
        min_tx = max(0, int(self.camera_x // tile) - 1)
        max_tx = min(self.scene.width_tiles, int((self.camera_x + rect.w / self.zoom) // tile) + 2)
        min_ty = max(0, int(self.camera_y // tile) - 1)
        max_ty = min(self.scene.height_tiles, int((self.camera_y + rect.h / self.zoom) // tile) + 2)
        draw_size = max(1, round(tile * self.zoom))

        # base terrain
        for ty in range(min_ty, max_ty):
            for tx in range(min_tx, max_tx):
                kind = self.scene.terrain[ty][tx]
                sx, sy = self.world_to_screen(tx * tile, ty * tile)
                dest = pygame.Rect(sx, sy, draw_size + 1, draw_size + 1)
                surf: pygame.Surface | None = None
                if kind in ("grass", "upper_grass"):
                    variant = ((tx * 73856093) ^ (ty * 19349663)) % 5
                    surf = self._scaled_surface(f"tiles/grass_{variant}.png", (draw_size, draw_size)) or self._scaled_surface("tiles/grass_0.png", (draw_size, draw_size))
                elif kind in ("path", "water"):
                    mask = oriented_neighbor_mask(proxy, tx, ty, kind)
                    surf = self._scaled_surface(autotile_asset(kind, mask), (draw_size, draw_size))
                if surf:
                    self.screen.blit(surf, dest)
                else:
                    color = {"void": (11, 14, 22), "water": (55, 127, 164), "path": (182, 140, 89)}.get(kind, (92, 137, 76))
                    pygame.draw.rect(self.screen, color, dest)

        # elevation cliff overlays (same assets as game)
        for ty in range(min_ty, max_ty):
            for tx in range(min_tx, max_tx):
                if self.scene.terrain[ty][tx] == "void":
                    continue
                sx, sy = self.world_to_screen(tx * tile, ty * tile)
                for key in elevation_cliff_assets(proxy, tx, ty):
                    surf = self._scaled_surface(key, (draw_size, draw_size))
                    if surf:
                        self.screen.blit(surf, (sx, sy))

        if self.show_elevation:
            for ty in range(min_ty, max_ty):
                for tx in range(min_tx, max_tx):
                    elev = self.scene.elevations[ty][tx]
                    if elev == 0:
                        continue
                    sx, sy = self.world_to_screen(tx * tile, ty * tile)
                    overlay = pygame.Surface((draw_size, draw_size), pygame.SRCALPHA)
                    overlay.fill((80 + min(120, elev * 35), 80, 170, 52))
                    self.screen.blit(overlay, (sx, sy))
                    txt = self.font_small.render(str(elev), True, (255, 255, 255))
                    self.screen.blit(txt, (sx + 4, sy + 2))

        # ground decorations / normal world objects, y sorted
        indexed = list(enumerate(self.scene.objects))
        indexed.sort(key=lambda pair: pair[1].y)
        for index, obj in indexed:
            definition = self.catalog.get(obj.asset)
            self._draw_object(index, obj, definition)

        if self.show_collision:
            self._draw_collisions()

        if self.grid:
            grid_col = (255, 255, 255, 30)
            grid_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            for tx in range(min_tx, max_tx + 1):
                sx, _ = self.world_to_screen(tx * tile, 0)
                pygame.draw.line(grid_surf, grid_col, (sx - rect.x, 0), (sx - rect.x, rect.h))
            for ty in range(min_ty, max_ty + 1):
                _, sy = self.world_to_screen(0, ty * tile)
                pygame.draw.line(grid_surf, grid_col, (0, sy - rect.y), (rect.w, sy - rect.y))
            self.screen.blit(grid_surf, rect.topleft)

        if self.hover_tile and self.mode in ("terrain", "elevation"):
            tx, ty = self.hover_tile
            sx, sy = self.world_to_screen(tx * tile, ty * tile)
            pygame.draw.rect(self.screen, (255, 226, 116), (sx, sy, draw_size, draw_size), width=max(1, round(2 * self.zoom)))

        self.screen.set_clip(old_clip)
        pygame.draw.rect(self.screen, (50, 59, 73), rect, width=1)

    def _draw_object(self, index: int, obj: SceneObjectData, definition: WorldAssetDefinition) -> None:
        assert self.screen and self.font_small
        sx, sy = self.world_to_screen(obj.x, obj.y)
        if definition.category == "portal":
            # Scene portals are intentionally invisible at runtime, but the editor
            # needs a clear marker. Draw a translucent doorway glyph and arrow.
            w = max(36, round(definition.size[0] * self.zoom))
            h = max(30, round(definition.size[1] * self.zoom))
            dest = pygame.Rect(0, 0, w, h)
            dest.midbottom = (sx, sy)
            marker = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(marker, (56, 194, 218, 72), marker.get_rect(), border_radius=max(4, round(8*self.zoom)))
            pygame.draw.rect(marker, (102, 232, 246, 230), marker.get_rect(), width=max(2, round(2*self.zoom)), border_radius=max(4, round(8*self.zoom)))
            # Door opening
            dw = max(12, int(w * 0.34)); dh = max(16, int(h * 0.62))
            door = pygame.Rect((w-dw)//2, h-dh-3, dw, dh)
            pygame.draw.rect(marker, (9, 20, 30, 180), door, border_radius=max(2, round(3*self.zoom)))
            facing = obj.portal_facing if obj.portal_facing in {"N","E","S","W"} else "S"
            cx, cy = w//2, h//2
            vec = {"N":(0,-1),"E":(1,0),"S":(0,1),"W":(-1,0)}[facing]
            ex, ey = cx + vec[0]*max(8,w//5), cy + vec[1]*max(8,h//5)
            pygame.draw.line(marker, (255, 239, 138, 255), (cx,cy), (ex,ey), width=max(2,round(2*self.zoom)))
            pygame.draw.circle(marker, (255, 239, 138, 255), (ex,ey), max(2,round(3*self.zoom)))
            self.screen.blit(marker, dest)
            if obj.target_scene:
                name = Path(obj.target_scene).stem
                label = self.font_small.render(name, True, (187, 241, 247))
                self.screen.blit(label, (dest.centerx-label.get_width()//2, dest.top-label.get_height()-2))
        else:
            native = self._world_asset_native_surface(definition)
            if native:
                scaled_size = (max(1, round(native.get_width() * self.zoom)), max(1, round(native.get_height() * self.zoom)))
                surf = native if native.get_size() == scaled_size else pygame.transform.scale(native, scaled_size)
                if definition.anchor == "bottom_center":
                    dest = surf.get_rect(midbottom=(sx, sy))
                else:
                    dest = surf.get_rect(center=(sx, sy))
                self.screen.blit(surf, dest)
            else:
                r = max(4, round(18 * self.zoom))
                dest = pygame.Rect(sx-r, sy-r, r*2, r*2)
                pygame.draw.rect(self.screen, (180, 90, 120), dest)

        if self.selected_object == index:
            pygame.draw.rect(self.screen, (255, 218, 91), dest.inflate(8, 8), width=3, border_radius=5)
            anchor_r = max(3, round(4 * self.zoom))
            pygame.draw.circle(self.screen, (255, 95, 95), (sx, sy), anchor_r)
            label = self.font_small.render(obj.id, True, (255, 248, 220))
            self.screen.blit(label, (dest.left, dest.top - label.get_height() - 3))
            if self.collision_edit and definition.category not in {"actor", "portal"}:
                shape = self._effective_collision(obj, definition)
                if isinstance(shape, RectObstacle):
                    crect = self._collision_screen_rect(obj, definition)
                    if crect is not None:
                        pygame.draw.rect(self.screen, (255, 196, 75), crect, width=2)
                        for hp in self._collision_handles(crect).values():
                            pygame.draw.circle(self.screen, (255, 239, 168), hp, 6)
                            pygame.draw.circle(self.screen, (95, 67, 24), hp, 6, width=2)
                elif isinstance(shape, PolygonObstacle):
                    points = self._collision_screen_points(obj, shape)
                    if len(points) >= 3:
                        pygame.draw.polygon(self.screen, (255, 196, 75), points, width=2)
                        for i, hp in enumerate(points):
                            fill = (255, 239, 168) if i != self._collision_selected_vertex else (255, 162, 96)
                            pygame.draw.circle(self.screen, fill, hp, 7)
                            pygame.draw.circle(self.screen, (95, 67, 24), hp, 7, width=2)

    def _draw_collisions(self) -> None:
        assert self.screen
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for obj in self.scene.objects:
            definition = self.catalog.get(obj.asset)
            c = self._effective_collision(obj, definition)
            if isinstance(c, RectObstacle):
                sx, sy = self.world_to_screen(obj.x + c.x, obj.y + c.y)
                rect = pygame.Rect(sx, sy, max(1, round(c.w * self.zoom)), max(1, round(c.h * self.zoom)))
                pygame.draw.rect(overlay, (235, 69, 82, 76), rect)
                pygame.draw.rect(overlay, (255, 120, 125, 220), rect, width=2)
            elif isinstance(c, PolygonObstacle):
                points = self._collision_screen_points(obj, c)
                if len(points) >= 3:
                    pygame.draw.polygon(overlay, (235, 69, 82, 76), points)
                    pygame.draw.polygon(overlay, (255, 120, 125, 220), points, width=2)
            elif definition.collision_radius > 0:
                sx, sy = self.world_to_screen(obj.x, obj.y)
                pygame.draw.circle(overlay, (235, 69, 82, 76), (sx, sy), round(definition.collision_radius * self.zoom))
        self.screen.blit(overlay, (0, 0))

    def _draw_sidebar(self) -> None:
        assert self.screen and self.font and self.font_small and self.font_large
        rect = self.sidebar_rect
        pygame.draw.rect(self.screen, (27, 33, 43), rect)
        pygame.draw.line(self.screen, (65, 75, 91), rect.topleft, rect.bottomleft, width=2)
        title = {
            "terrain": "Terrain Brush", "elevation": "Elevation Brush",
            "objects": "Asset Palette", "select": "Selection", "audio": "Scene Audio",
        }[self.mode]
        self.screen.blit(self.font_large.render(title, True, (244, 241, 231)), (rect.x + 18, rect.y + 14))
        self._palette_items.clear()
        y = rect.y + 66 - self._palette_scroll

        if self.mode == "terrain":
            for key, label, color in [("grass", "Grass", (93, 150, 79)), ("path", "Path", (186, 144, 91)), ("water", "Water", (54, 127, 164)), ("void", "Void", (12, 15, 23))]:
                item_rect = pygame.Rect(rect.x + 18, y, rect.w - 36, 54)
                self._palette_items.append(PaletteItem(key, label, item_rect, key))
                pygame.draw.rect(self.screen, (77, 93, 112) if self.terrain_brush == key else (43, 51, 65), item_rect, border_radius=7)
                pygame.draw.rect(self.screen, color, (item_rect.x + 8, item_rect.y + 8, 38, 38), border_radius=5)
                self.screen.blit(self.font.render(label, True, (242, 240, 232)), (item_rect.x + 58, item_rect.y + 14))
                y += 62
            self._draw_sidebar_help(y + 10, ["Drag: paint", "Shift+drag: rectangle", "F: flood fill", "Ctrl+Z/Y: undo/redo"])

        elif self.mode == "elevation":
            for elev in range(0, 5):
                item_rect = pygame.Rect(rect.x + 18, y, rect.w - 36, 50)
                self._palette_items.append(PaletteItem(str(elev), f"Elevation {elev}", item_rect, elev))
                pygame.draw.rect(self.screen, (77, 93, 112) if self.elevation_brush == elev else (43, 51, 65), item_rect, border_radius=7)
                self.screen.blit(self.font.render(f"Elevation {elev}", True, (242, 240, 232)), (item_rect.x + 14, item_rect.y + 12))
                y += 58
            self._draw_sidebar_help(y + 10, ["Paint heights, not cliff tiles.", "Cliffs are generated automatically.", "F: flood fill"])

        elif self.mode == "objects":
            for definition in self.catalog.by_category("scenery", "interactable", "portal", "actor"):
                item_rect = pygame.Rect(rect.x + 14, y, rect.w - 28, 74)
                self._palette_items.append(PaletteItem(definition.id, definition.display_name, item_rect, definition.id))
                pygame.draw.rect(self.screen, (77, 93, 112) if self.asset_brush == definition.id else (43, 51, 65), item_rect, border_radius=7)
                icon = self._world_asset_native_surface(definition)
                if definition.category == "portal":
                    pr = pygame.Rect(item_rect.x + 19, item_rect.y + 16, 42, 42)
                    pygame.draw.rect(self.screen, (48, 142, 164), pr, border_radius=6)
                    pygame.draw.rect(self.screen, (112, 231, 244), pr, width=2, border_radius=6)
                    pygame.draw.rect(self.screen, (10, 25, 34), (pr.x+14, pr.y+11, 14, 28), border_radius=3)
                elif icon:
                    max_side = 58
                    scale = min(max_side / icon.get_width(), max_side / icon.get_height(), 1.0)
                    thumb_size = (max(1, round(icon.get_width()*scale)), max(1, round(icon.get_height()*scale)))
                    thumb = icon if icon.get_size() == thumb_size else pygame.transform.scale(icon, thumb_size)
                    thumb_rect = thumb.get_rect(center=(item_rect.x + 40, item_rect.centery))
                    self.screen.blit(thumb, thumb_rect)
                self.screen.blit(self.font.render(definition.display_name, True, (242, 240, 232)), (item_rect.x + 78, item_rect.y + 12))
                cat = self.font_small.render(definition.category, True, (173, 184, 199))
                self.screen.blit(cat, (item_rect.x + 78, item_rect.y + 40))
                y += 82
            self._draw_sidebar_help(y + 8, [f"Snap: {self.snap or 'Off'} px", "[ / ] changes snap", "Click canvas to place"])

        elif self.mode == "audio":
            current = Path(self.scene.music).name if self.scene.music else "None"
            self._draw_sidebar_help(y, [f"Current track: {current}", f"Scene gain: {round(self.scene.music_volume * 100)}%"] )
            y += 62

            for key, caption in (
                ("__music_import", "Import audio file…"),
                ("__music_preview", "Stop preview" if self._music_previewing else "Preview current track"),
                ("__music_clear", "Clear scene music"),
            ):
                br = pygame.Rect(rect.x + 18, y, rect.w - 36, 36)
                self._palette_items.append(PaletteItem(key, caption, br, None))
                pygame.draw.rect(self.screen, (49, 86, 76) if key == "__music_preview" and self._music_previewing else (55, 66, 82), br, border_radius=6)
                self.screen.blit(self.font_small.render(caption, True, (235, 238, 232)), (br.x + 10, br.y + 8))
                y += 42

            minus = pygame.Rect(rect.x + 18, y, (rect.w - 42)//2, 34)
            plus = pygame.Rect(minus.right + 6, y, minus.w, 34)
            self._palette_items.append(PaletteItem("__music_quieter", "-10%", minus, None))
            self._palette_items.append(PaletteItem("__music_louder", "+10%", plus, None))
            for br, caption in ((minus, "−10% scene gain"), (plus, "+10% scene gain")):
                pygame.draw.rect(self.screen, (55, 66, 82), br, border_radius=6)
                label = self.font_small.render(caption, True, (235, 238, 232))
                self.screen.blit(label, (br.centerx - label.get_width()//2, br.y + 7))
            y += 48

            self._draw_sidebar_help(y, ["Available tracks"]); y += 31
            tracks = self._music_tracks()
            if not tracks:
                self._draw_sidebar_help(y, ["No audio imported yet.", "Use Import audio file…", "or drop a file onto the editor."])
                y += 86
            else:
                for path in tracks:
                    relative = f"music/{path.name}"
                    br = pygame.Rect(rect.x + 14, y, rect.w - 28, 42)
                    self._palette_items.append(PaletteItem(f"__music_track::{relative}", path.name, br, relative))
                    active = self.scene.music == relative
                    pygame.draw.rect(self.screen, (76, 91, 112) if active else (43, 51, 65), br, border_radius=6)
                    shown = path.name if len(path.name) <= 30 else path.name[:27] + "…"
                    self.screen.blit(self.font_small.render(shown, True, (242, 240, 232)), (br.x + 10, br.y + 9))
                    y += 48
            self._draw_sidebar_help(y + 8, ["Scene music loops automatically in game.", "Global volume: Esc → Audio."])
            y += 66

            ambience = self.sfx_catalog.get(self.scene.ambience_cue)
            ambience_name = ambience.label if ambience else "None"
            self._draw_sidebar_help(y, ["Ambience", f"Current: {ambience_name}", f"Scene gain: {round(self.scene.ambience_volume * 100)}%"])
            y += 84

            for key, caption in (
                ("__ambience_preview", "Preview ambience"),
                ("__ambience_clear", "Clear ambience"),
            ):
                br = pygame.Rect(rect.x + 18, y, rect.w - 36, 34)
                self._palette_items.append(PaletteItem(key, caption, br, None))
                pygame.draw.rect(self.screen, (55, 66, 82), br, border_radius=6)
                self.screen.blit(self.font_small.render(caption, True, (235, 238, 232)), (br.x + 10, br.y + 7))
                y += 40

            minus = pygame.Rect(rect.x + 18, y, (rect.w - 42)//2, 34)
            plus = pygame.Rect(minus.right + 6, y, minus.w, 34)
            self._palette_items.append(PaletteItem("__ambience_quieter", "-10%", minus, None))
            self._palette_items.append(PaletteItem("__ambience_louder", "+10%", plus, None))
            for br, caption in ((minus, "−10% ambience"), (plus, "+10% ambience")):
                pygame.draw.rect(self.screen, (55, 66, 82), br, border_radius=6)
                label = self.font_small.render(caption, True, (235, 238, 232))
                self.screen.blit(label, (br.centerx - label.get_width()//2, br.y + 7))
            y += 48

            ambience_cues = self.sfx_catalog.by_category("Ambience")
            if ambience_cues:
                self._draw_sidebar_help(y, ["Available ambience cues"]); y += 31
                for cue in ambience_cues:
                    br = pygame.Rect(rect.x + 14, y, rect.w - 28, 38)
                    self._palette_items.append(PaletteItem(f"__ambience_cue::{cue.id}", cue.label, br, cue.id))
                    active = self.scene.ambience_cue == cue.id
                    pygame.draw.rect(self.screen, (76, 91, 112) if active else (43, 51, 65), br, border_radius=6)
                    self.screen.blit(self.font_small.render(cue.label, True, (242, 240, 232)), (br.x + 10, br.y + 7))
                    y += 44
            else:
                self._draw_sidebar_help(y, ["No ambience cues registered.", "Add assets/sfx_cues.json to enable them."])

        else:
            if self.selected_object is None or not (0 <= self.selected_object < len(self.scene.objects)):
                self._draw_sidebar_help(y, ["Click an object to select it.", "Drag to move.", "Delete removes it.", "Arrow keys nudge."])
            else:
                obj = self.scene.objects[self.selected_object]
                definition = self.catalog.get(obj.asset)
                lines = [
                    f"ID: {obj.id}", f"Type: {definition.display_name}", f"Category: {definition.category}",
                    f"X: {obj.x:.1f}", f"Y: {obj.y:.1f}",
                ]
                self._draw_sidebar_help(y, lines)
                y += len(lines) * 27 + 8

                if definition.category not in {"actor", "portal"}:
                    c = self._effective_collision(obj, definition)
                    inherited = obj.collision is None
                    if c is None:
                        ctext = "Collision: none"
                    elif isinstance(c, RectObstacle):
                        ctext = f"Box: {c.x:.0f},{c.y:.0f}  {c.w:.0f}×{c.h:.0f}"
                    else:
                        bounds = c.bounds()
                        ctext = f"Polygon: {len(c.points)} verts  {bounds.w:.0f}×{bounds.h:.0f}"
                    self._draw_sidebar_help(y, [ctext, "Inherited" if inherited else "Instance override", "[B] edit current   [P] polygon   [X] box"])
                    y += 82
                    edit_rect = pygame.Rect(rect.x + 18, y, rect.w - 36, 38)
                    self._palette_items.append(PaletteItem("__collision_edit", "Edit collision", edit_rect, None))
                    pygame.draw.rect(self.screen, (118, 91, 48) if self.collision_edit else (55, 66, 82), edit_rect, border_radius=6)
                    self.screen.blit(self.font_small.render("Edit collision shape  [B]", True, (245, 239, 220)), (edit_rect.x + 10, edit_rect.y + 9))
                    y += 44
                    poly_rect = pygame.Rect(rect.x + 18, y, rect.w - 36, 34)
                    self._palette_items.append(PaletteItem("__collision_polygon", "Polygon collision", poly_rect, None))
                    pygame.draw.rect(self.screen, (66, 79, 64), poly_rect, border_radius=6)
                    self.screen.blit(self.font_small.render("Convert to polygon  [P]", True, (232, 240, 228)), (poly_rect.x + 10, poly_rect.y + 7))
                    y += 40
                    box_rect = pygame.Rect(rect.x + 18, y, rect.w - 36, 34)
                    self._palette_items.append(PaletteItem("__collision_rect", "Box collision", box_rect, None))
                    pygame.draw.rect(self.screen, (64, 69, 79), box_rect, border_radius=6)
                    self.screen.blit(self.font_small.render("Convert to box  [X]", True, (230, 234, 240)), (box_rect.x + 10, box_rect.y + 7))
                    y += 40
                    if obj.collision is not None:
                        reset_rect = pygame.Rect(rect.x + 18, y, rect.w - 36, 34)
                        self._palette_items.append(PaletteItem("__collision_reset", "Reset collision", reset_rect, None))
                        pygame.draw.rect(self.screen, (66, 58, 65), reset_rect, border_radius=6)
                        self.screen.blit(self.font_small.render("Reset to asset default  [R]", True, (220, 211, 217)), (reset_rect.x + 10, reset_rect.y + 7))
                        y += 42

                if definition.category == "portal":
                    target = obj.target_scene or "— not linked —"
                    target_door = obj.target_door or "—"
                    mode_label = "Two-way" if obj.portal_mode == "two_way" else "One-way"
                    self._draw_sidebar_help(y, [
                        f"Connection: {mode_label}",
                        f"Destination: {target}",
                        f"Destination door: {target_door}",
                        f"Arrival facing: {obj.portal_facing}",
                    ])
                    y += 104
                    for key, caption in (
                        ("__portal_open", "Open / create destination  [O]"),
                        ("__portal_mode", f"Make {'one-way' if obj.portal_mode == 'two_way' else 'two-way'}  [M]"),
                        ("__portal_unlink", "Unlink connection  [U]"),
                        ("__edit_target_scene", "Edit target scene  [T]"),
                        ("__edit_target_door", "Edit target door ID  [D]"),
                        ("__portal_facing", "Cycle arrival facing  [Q]"),
                    ):
                        br = pygame.Rect(rect.x + 18, y, rect.w - 36, 34)
                        self._palette_items.append(PaletteItem(key, caption, br, None))
                        pygame.draw.rect(self.screen, (50, 83, 96) if key == "__portal_open" else (55, 66, 82), br, border_radius=6)
                        self.screen.blit(self.font_small.render(caption, True, (232, 238, 232)), (br.x + 10, br.y + 7))
                        y += 40
                    if self.scene_nav_stack:
                        br = pygame.Rect(rect.x + 18, y, rect.w - 36, 34)
                        self._palette_items.append(PaletteItem("__portal_back", "Back to previous scene", br, None))
                        pygame.draw.rect(self.screen, (68, 62, 82), br, border_radius=6)
                        self.screen.blit(self.font_small.render("← Back to previous scene  [Alt+Left]", True, (232, 232, 225)), (br.x + 10, br.y + 7))
                        y += 40
                    if self._text_edit_field in {"target_scene", "target_door"}:
                        field_name = self._text_edit_field.replace("_", " ").title()
                        self._draw_sidebar_help(y + 4, [f"{field_name}:", self._text_edit_buffer + "|"])
                        y += 62

                if definition.category == "interactable":
                    action = obj.action or definition.action_id or "—"
                    label = obj.label or definition.label or definition.display_name
                    self._draw_sidebar_help(y, [f"Action: {action}", f"Label: {label}"])
                    y += 58
                    for key, caption in (("__edit_action", "Edit action ID  [A]"), ("__edit_label", "Edit label  [L]")):
                        br = pygame.Rect(rect.x + 18, y, rect.w - 36, 34)
                        self._palette_items.append(PaletteItem(key, caption, br, None))
                        pygame.draw.rect(self.screen, (55, 66, 82), br, border_radius=6)
                        self.screen.blit(self.font_small.render(caption, True, (232, 232, 225)), (br.x + 10, br.y + 7))
                        y += 40
                    if self._text_edit_field:
                        field_name = self._text_edit_field.capitalize()
                        self._draw_sidebar_help(y + 4, [f"{field_name}:", self._text_edit_buffer + "|"])
                        y += 62

                if definition.category in {"interactable", "portal", "actor"}:
                    cue_id = self._effective_object_sound(obj, definition)
                    cue = self.sfx_catalog.get(cue_id)
                    cue_name = cue.label if cue else (cue_id or "None")
                    inherited_sound = not bool(obj.sound_cues.get("use" if definition.category == "portal" else "interact"))
                    self._draw_sidebar_help(y, [
                        "Interaction sound",
                        f"Cue: {cue_name}",
                        "Asset default" if inherited_sound else "Instance override",
                    ])
                    y += 82
                    for key, caption in (
                        ("__sound_prev", "← Previous cue"),
                        ("__sound_preview", "Preview cue"),
                        ("__sound_next", "Next cue →"),
                        ("__sound_reset", "Reset to asset default"),
                    ):
                        br = pygame.Rect(rect.x + 18, y, rect.w - 36, 32)
                        self._palette_items.append(PaletteItem(key, caption, br, None))
                        pygame.draw.rect(self.screen, (55, 66, 82), br, border_radius=6)
                        self.screen.blit(self.font_small.render(caption, True, (232, 238, 232)), (br.x + 10, br.y + 6))
                        y += 37

                self._draw_sidebar_help(y + 8, ["Drag: move object", "Ctrl+D: duplicate", "Delete: remove", "Arrows: nudge"])

    def _draw_sidebar_help(self, y: int, lines: Iterable[str]) -> None:
        assert self.screen and self.font_small
        for line in lines:
            surf = self.font_small.render(line, True, (188, 197, 209))
            self.screen.blit(surf, (self.sidebar_rect.x + 18, y))
            y += 27

    def _draw_statusbar(self) -> None:
        assert self.screen and self.font_small
        y = self.screen.get_height() - self.STATUS_H
        pygame.draw.rect(self.screen, (25, 30, 39), (0, y, self.screen.get_width(), self.STATUS_H))
        tile_text = f"Tile {self.hover_tile[0]}, {self.hover_tile[1]}" if self.hover_tile else ""
        scene_text = f"{self.scene.id}  {self.scene.width_tiles}×{self.scene.height_tiles} tiles  zoom {self.zoom:.2f}×"
        dirty = "  • unsaved" if self.dirty else ""
        left = self.font_small.render(scene_text + dirty, True, (207, 214, 224))
        right = self.font_small.render(f"{tile_text}    {self.status}", True, (207, 214, 224))
        self.screen.blit(left, (10, y + 5))
        self.screen.blit(right, (self.screen.get_width() - right.get_width() - 10, y + 5))

    # ---------- editing ----------

    def _paint_tile(self, tile_pos: tuple[int, int]) -> None:
        tx, ty = tile_pos
        if self.mode == "terrain":
            if self.scene.terrain[ty][tx] != self.terrain_brush:
                self.scene.terrain[ty][tx] = self.terrain_brush
                self.dirty = True
        elif self.mode == "elevation":
            if self.scene.elevations[ty][tx] != self.elevation_brush:
                self.scene.elevations[ty][tx] = self.elevation_brush
                self.dirty = True

    def _fill_rect(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        x0, x1 = sorted((a[0], b[0])); y0, y1 = sorted((a[1], b[1]))
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                self._paint_tile((tx, ty))

    def flood_fill(self, tile_pos: tuple[int, int]) -> None:
        tx, ty = tile_pos
        before = self.history.snapshot(self.scene)
        if self.mode == "terrain":
            old, new = self.scene.terrain[ty][tx], self.terrain_brush
            if old == new:
                return
            values = self.scene.terrain
        elif self.mode == "elevation":
            old, new = self.scene.elevations[ty][tx], self.elevation_brush
            if old == new:
                return
            values = self.scene.elevations
        else:
            return
        stack = [(tx, ty)]; seen = set()
        while stack:
            x, y = stack.pop()
            if (x, y) in seen or not (0 <= x < self.scene.width_tiles and 0 <= y < self.scene.height_tiles):
                continue
            seen.add((x, y))
            if values[y][x] != old:
                continue
            values[y][x] = new
            stack.extend(((x+1,y),(x-1,y),(x,y+1),(x,y-1)))
        self.history.remember(before)
        self.dirty = True
        self.status = "Flood fill"

    def _unique_id(self, asset_id: str) -> str:
        existing = {obj.id for obj in self.scene.objects}
        if asset_id not in existing:
            return asset_id
        i = 2
        while f"{asset_id}_{i}" in existing:
            i += 1
        return f"{asset_id}_{i}"

    def _snap_value(self, value: float) -> float:
        return round(value / self.snap) * self.snap if self.snap else round(value)

    def place_object(self, screen_pos: tuple[int, int]) -> None:
        if not self.asset_brush:
            return
        wx, wy = self.screen_to_world(screen_pos)
        definition = self.catalog.get(self.asset_brush)
        before = self.history.snapshot(self.scene)
        obj = SceneObjectData(
            id=self._unique_id(definition.id), asset=definition.id,
            x=self._snap_value(wx), y=self._snap_value(wy), action=definition.action_id,
            label=definition.label,
        )
        self.scene.objects.append(obj)
        self.history.remember(before)
        self.selected_object = len(self.scene.objects) - 1
        self.dirty = True
        self.status = f"Placed {definition.display_name}"

    def _object_hit(self, pos: tuple[int, int]) -> int | None:
        wx, wy = self.screen_to_world(pos)
        best: tuple[float, int] | None = None
        for index, obj in enumerate(self.scene.objects):
            d = self.catalog.get(obj.asset)
            native = self._world_asset_native_surface(d)
            if native:
                w, h = native.get_size()
            else:
                w, h = d.size
            if d.anchor == "bottom_center":
                hit = (obj.x - w/2 <= wx <= obj.x + w/2 and obj.y - h <= wy <= obj.y)
            else:
                hit = (obj.x - w/2 <= wx <= obj.x + w/2 and obj.y - h/2 <= wy <= obj.y + h/2)
            if hit:
                dist = (obj.x - wx) ** 2 + (obj.y - wy) ** 2
                if best is None or dist < best[0]:
                    best = (dist, index)
        return best[1] if best else None

    def delete_selected(self) -> None:
        if self.selected_object is None or not (0 <= self.selected_object < len(self.scene.objects)):
            return
        before = self.history.snapshot(self.scene)
        removed = self.scene.objects.pop(self.selected_object)
        self.history.remember(before)
        self.selected_object = None
        self.collision_edit = False
        self._text_edit_field = None
        self.dirty = True
        self.status = f"Deleted {removed.id}"

    def duplicate_selected(self) -> None:
        if self.selected_object is None or not (0 <= self.selected_object < len(self.scene.objects)):
            return
        before = self.history.snapshot(self.scene)
        src = self.scene.objects[self.selected_object]
        copied_collision = self._copy_collision(src.collision)
        dup = SceneObjectData(
            id=self._unique_id(src.asset), asset=src.asset, x=src.x + 16, y=src.y + 16,
            action=src.action, label=src.label, enabled=src.enabled, collision=copied_collision,
            target_scene=src.target_scene, target_door=src.target_door, portal_facing=src.portal_facing,
            portal_mode=src.portal_mode, sound_cues=dict(src.sound_cues),
        )
        self.scene.objects.append(dup)
        self.history.remember(before)
        self.selected_object = len(self.scene.objects) - 1
        self.dirty = True
        self.status = f"Duplicated {src.id}"

    def nudge_selected(self, dx: float, dy: float) -> None:
        if self.selected_object is None or not (0 <= self.selected_object < len(self.scene.objects)):
            return
        before = self.history.snapshot(self.scene)
        obj = self.scene.objects[self.selected_object]
        obj.x += dx; obj.y += dy
        self.history.remember(before)
        self.dirty = True

    # ---------- events ----------

    def _palette_click(self, pos: tuple[int, int]) -> bool:
        for item in self._palette_items:
            if item.rect.collidepoint(pos):
                if self.mode == "terrain": self.terrain_brush = str(item.value)
                elif self.mode == "elevation": self.elevation_brush = int(item.value)
                elif self.mode == "objects": self.asset_brush = str(item.value)
                elif self.mode == "audio":
                    if item.key == "__music_import": self._import_music_dialog()
                    elif item.key == "__music_preview":
                        self._stop_music_preview() if self._music_previewing else self._preview_scene_music()
                    elif item.key == "__music_clear": self._select_music_track(None)
                    elif item.key == "__music_quieter": self._set_scene_music_volume(-0.10)
                    elif item.key == "__music_louder": self._set_scene_music_volume(0.10)
                    elif item.key.startswith("__music_track::"): self._select_music_track(str(item.value))
                    elif item.key == "__ambience_preview": self._preview_sound_cue(self.scene.ambience_cue)
                    elif item.key == "__ambience_clear": self._set_scene_ambience(None)
                    elif item.key == "__ambience_quieter": self._set_scene_ambience_volume(-0.10)
                    elif item.key == "__ambience_louder": self._set_scene_ambience_volume(0.10)
                    elif item.key.startswith("__ambience_cue::"): self._set_scene_ambience(str(item.value))
                elif self.mode == "select":
                    if item.key == "__collision_edit": self.add_or_edit_collision()
                    elif item.key == "__collision_polygon": self.convert_selected_collision_to_polygon()
                    elif item.key == "__collision_rect": self.convert_selected_collision_to_rect()
                    elif item.key == "__collision_reset": self.reset_collision_override()
                    elif item.key == "__edit_action": self._start_text_edit("action")
                    elif item.key == "__edit_label": self._start_text_edit("label")
                    elif item.key == "__portal_open": self.open_linked_scene()
                    elif item.key == "__portal_mode": self.toggle_portal_mode()
                    elif item.key == "__portal_unlink": self.unlink_selected_portal()
                    elif item.key == "__edit_target_scene": self._start_text_edit("target_scene")
                    elif item.key == "__edit_target_door": self._start_text_edit("target_door")
                    elif item.key == "__portal_facing": self.cycle_portal_facing()
                    elif item.key == "__portal_back": self.back_scene()
                    elif item.key == "__sound_prev": self._cycle_selected_object_sound(-1)
                    elif item.key == "__sound_next": self._cycle_selected_object_sound(1)
                    elif item.key == "__sound_preview":
                        pair = self._selected_pair()
                        if pair: self._preview_sound_cue(self._effective_object_sound(*pair))
                    elif item.key == "__sound_reset": self._reset_selected_object_sound()
                return True
        return False

    def _toolbar_click(self, pos: tuple[int, int]) -> bool:
        if pos[1] >= self.TOP_H:
            return False
        for i, key in enumerate(("terrain", "elevation", "objects", "select", "audio")):
            if pygame.Rect(12 + 140*i, 9, 130, 40).collidepoint(pos):
                self.mode = key; self._palette_scroll = 0; return True
        return False

    def _change_zoom(self, delta: int, mouse_pos: tuple[int, int]) -> None:
        if not self.canvas_rect.collidepoint(mouse_pos):
            return
        before_world = self.screen_to_world(mouse_pos)
        factors = [0.5, 0.67, 0.8, 1.0, 1.25, 1.5, 2.0]
        idx = min(range(len(factors)), key=lambda i: abs(factors[i]-self.zoom))
        idx = max(0, min(len(factors)-1, idx + (1 if delta > 0 else -1)))
        self.zoom = factors[idx]
        after_world = self.screen_to_world(mouse_pos)
        self.camera_x += before_world[0] - after_world[0]
        self.camera_y += before_world[1] - after_world[1]
        self._clamp_camera()

    def _clamp_camera(self) -> None:
        rect = self.canvas_rect
        max_x = max(0.0, self.scene.width - rect.w / self.zoom)
        max_y = max(0.0, self.scene.height - rect.h / self.zoom)
        self.camera_x = max(0.0, min(max_x, self.camera_x))
        self.camera_y = max(0.0, min(max_y, self.camera_y))

    def handle_event(self, event: pygame.event.Event) -> bool:
        mods = pygame.key.get_mods()
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.VIDEORESIZE:
            self._clamp_camera()
        elif event.type == pygame.MOUSEMOTION:
            self.hover_tile = self.screen_to_tile(event.pos)
            if self._pan_anchor and self._pan_camera_anchor:
                dx = (event.pos[0] - self._pan_anchor[0]) / self.zoom
                dy = (event.pos[1] - self._pan_anchor[1]) / self.zoom
                self.camera_x = self._pan_camera_anchor[0] - dx
                self.camera_y = self._pan_camera_anchor[1] - dy
                self._clamp_camera()
            elif self._collision_drag_handle is not None and self.selected_object is not None and self._collision_drag_start_world and self._collision_drag_start_shape is not None:
                wx, wy = self.screen_to_world(event.pos)
                sx, sy = self._collision_drag_start_world
                dx, dy = wx - sx, wy - sy
                handle = self._collision_drag_handle
                obj = self.scene.objects[self.selected_object]
                start_shape = self._collision_drag_start_shape
                if isinstance(start_shape, RectObstacle):
                    r = start_shape
                    left, top, right, bottom = r.x, r.y, r.x + r.w, r.y + r.h
                    if handle == "move":
                        left += dx; right += dx; top += dy; bottom += dy
                    else:
                        if handle in ("w", "nw", "sw"): left += dx
                        if handle in ("e", "ne", "se"): right += dx
                        if handle in ("n", "nw", "ne"): top += dy
                        if handle in ("s", "sw", "se"): bottom += dy
                    min_size = 4.0
                    if right - left < min_size:
                        if "w" in handle or handle == "w": left = right - min_size
                        else: right = left + min_size
                    if bottom - top < min_size:
                        if "n" in handle or handle == "n": top = bottom - min_size
                        else: bottom = top + min_size
                    obj.collision = RectObstacle(round(left), round(top), round(right-left), round(bottom-top))
                elif isinstance(start_shape, PolygonObstacle):
                    points = [list(p) for p in start_shape.points]
                    if handle == "move_poly":
                        for p in points:
                            p[0] = round(p[0] + dx)
                            p[1] = round(p[1] + dy)
                    elif handle.startswith("vertex:"):
                        index = int(handle.split(":", 1)[1])
                        points[index][0] = round(start_shape.points[index][0] + dx)
                        points[index][1] = round(start_shape.points[index][1] + dy)
                        self._collision_selected_vertex = index
                    obj.collision = PolygonObstacle(tuple((p[0], p[1]) for p in points))
                self.dirty = True
            elif self._drag_object_offset is not None and self.selected_object is not None:
                wx, wy = self.screen_to_world(event.pos)
                ox, oy = self._drag_object_offset
                obj = self.scene.objects[self.selected_object]
                obj.x, obj.y = self._snap_value(wx - ox), self._snap_value(wy - oy)
                self.dirty = True
            elif event.buttons[0] and self._stroke_before is not None and self.mode in ("terrain", "elevation") and not (mods & pygame.KMOD_SHIFT):
                tile = self.screen_to_tile(event.pos)
                if tile and tile != self._stroke_last_tile:
                    self._paint_tile(tile); self._stroke_last_tile = tile
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3 and self.canvas_rect.collidepoint(event.pos):
                self._pan_anchor = event.pos; self._pan_camera_anchor = (self.camera_x, self.camera_y)
            elif event.button == 1:
                if self._toolbar_click(event.pos) or self._palette_click(event.pos):
                    return True
                if not self.canvas_rect.collidepoint(event.pos):
                    return True
                if self.mode in ("terrain", "elevation"):
                    tile = self.screen_to_tile(event.pos)
                    if tile:
                        self._begin_change(); self._stroke_last_tile = tile
                        if mods & pygame.KMOD_SHIFT:
                            self._rect_start = tile
                        else:
                            self._paint_tile(tile)
                elif self.mode == "objects":
                    self.place_object(event.pos)
                elif self.mode == "audio":
                    return True
                else:
                    handle = self._collision_handle_hit(event.pos)
                    pair = self._selected_pair()
                    current_shape = self._effective_collision(*pair) if pair else None
                    edge_hit = self._polygon_edge_hit(event.pos) if (mods & pygame.KMOD_SHIFT) else None
                    if handle is not None:
                        self._begin_change()
                        current = self._ensure_collision_override(prefer_polygon=isinstance(current_shape, PolygonObstacle))
                        if current is not None:
                            self._collision_drag_handle = handle
                            self._collision_drag_start_world = self.screen_to_world(event.pos)
                            self._collision_drag_start_shape = self._copy_collision(current)
                            if handle.startswith("vertex:"):
                                self._collision_selected_vertex = int(handle.split(":", 1)[1])
                    elif edge_hit is not None and pair is not None and isinstance(current_shape, PolygonObstacle):
                        self._begin_change()
                        current = self._ensure_collision_override(prefer_polygon=True)
                        if isinstance(current, PolygonObstacle):
                            obj, _definition = pair
                            wx, wy = self.screen_to_world(event.pos)
                            local = (round(wx - obj.x), round(wy - obj.y))
                            points = list(current.points)
                            insert_index = edge_hit + 1
                            points.insert(insert_index, local)
                            poly = PolygonObstacle(tuple(points))
                            obj.collision = poly
                            self._collision_selected_vertex = insert_index
                            self._collision_drag_handle = f"vertex:{insert_index}"
                            self._collision_drag_start_world = self.screen_to_world(event.pos)
                            self._collision_drag_start_shape = poly
                            self.dirty = True
                    else:
                        new_selection = self._object_hit(event.pos)
                        if new_selection != self.selected_object:
                            self.collision_edit = False
                            self._text_edit_field = None
                            self._collision_selected_vertex = None
                        self.selected_object = new_selection
                        if self.selected_object is not None:
                            obj = self.scene.objects[self.selected_object]
                            definition = self.catalog.get(obj.asset)
                            if definition.category == "portal" and getattr(event, "clicks", 1) >= 2:
                                self.open_linked_scene()
                                return True
                            wx, wy = self.screen_to_world(event.pos)
                            self._drag_object_offset = (wx - obj.x, wy - obj.y)
                            self._begin_change()
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 3:
                self._pan_anchor = None; self._pan_camera_anchor = None
            elif event.button == 1:
                if self._rect_start is not None and self.mode in ("terrain", "elevation"):
                    tile = self.screen_to_tile(event.pos)
                    if tile:
                        self._fill_rect(self._rect_start, tile)
                self._rect_start = None; self._stroke_last_tile = None
                if self._drag_object_offset is not None:
                    self._drag_object_offset = None
                if self._collision_drag_handle is not None:
                    self._collision_drag_handle = None
                    self._collision_drag_start_world = None
                    self._collision_drag_start_shape = None
                self._commit_change()
        elif event.type == pygame.MOUSEWHEEL:
            mouse = pygame.mouse.get_pos()
            if self.sidebar_rect.collidepoint(mouse):
                self._palette_scroll = max(0, self._palette_scroll - event.y * 44)
            else:
                self._change_zoom(event.y, mouse)
        elif event.type == pygame.DROPFILE:
            dropped = Path(event.file)
            if dropped.suffix.lower() in {".ogg", ".wav", ".mp3", ".flac"}:
                self._import_music_path(dropped)
                self.mode = "audio"
            else:
                self.status = "Dropped file is not supported audio"
        elif event.type == pygame.KEYDOWN:
            if self._text_edit_field is not None:
                if event.key == pygame.K_ESCAPE:
                    self._cancel_text_edit()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._commit_text_edit()
                elif event.key == pygame.K_BACKSPACE:
                    self._text_edit_buffer = self._text_edit_buffer[:-1]
                elif event.unicode and event.unicode.isprintable():
                    self._text_edit_buffer += event.unicode
                return True
            ctrl = bool(mods & pygame.KMOD_CTRL); shift = bool(mods & pygame.KMOD_SHIFT)
            if ctrl and event.key == pygame.K_s: self.save()
            elif ctrl and event.key == pygame.K_z and not shift: self.undo()
            elif (ctrl and event.key == pygame.K_y) or (ctrl and shift and event.key == pygame.K_z): self.redo()
            elif ctrl and event.key == pygame.K_d: self.duplicate_selected()
            elif event.key == pygame.K_F5: self.playtest()
            elif event.key == pygame.K_1: self.mode = "terrain"
            elif event.key == pygame.K_2: self.mode = "elevation"
            elif event.key == pygame.K_3: self.mode = "objects"
            elif event.key == pygame.K_4: self.mode = "select"
            elif event.key == pygame.K_5: self.mode = "audio"
            elif event.key == pygame.K_g: self.grid = not self.grid
            elif event.key == pygame.K_c: self.show_collision = not self.show_collision
            elif event.key == pygame.K_v: self.show_elevation = not self.show_elevation
            elif event.key == pygame.K_b and self.mode == "select": self.add_or_edit_collision()
            elif event.key == pygame.K_p and self.mode == "select": self.convert_selected_collision_to_polygon()
            elif event.key == pygame.K_x and self.mode == "select": self.convert_selected_collision_to_rect()
            elif event.key == pygame.K_r and self.mode == "select" and self.collision_edit: self.reset_collision_override()
            elif event.key == pygame.K_a and self.mode == "select": self._start_text_edit("action")
            elif event.key == pygame.K_l and self.mode == "select": self._start_text_edit("label")
            elif event.key == pygame.K_o and self.mode == "select": self.open_linked_scene()
            elif event.key == pygame.K_m and self.mode == "select": self.toggle_portal_mode()
            elif event.key == pygame.K_u and self.mode == "select": self.unlink_selected_portal()
            elif event.key == pygame.K_t and self.mode == "select": self._start_text_edit("target_scene")
            elif event.key == pygame.K_d and self.mode == "select" and not ctrl: self._start_text_edit("target_door")
            elif event.key == pygame.K_q and self.mode == "select": self.cycle_portal_facing()
            elif event.key == pygame.K_LEFT and (mods & pygame.KMOD_ALT): self.back_scene()
            elif event.key == pygame.K_DELETE and self.mode == "select" and self.collision_edit:
                pair = self._selected_pair()
                if pair is not None:
                    obj, definition = pair
                    shape = self._effective_collision(obj, definition)
                    if isinstance(shape, PolygonObstacle) and self._collision_selected_vertex is not None and len(shape.points) > 3:
                        before = self.history.snapshot(self.scene)
                        new_points = list(shape.points)
                        new_points.pop(self._collision_selected_vertex)
                        obj.collision = PolygonObstacle(tuple(new_points))
                        self.history.remember(before)
                        self._collision_selected_vertex = min(self._collision_selected_vertex, len(new_points) - 1)
                        self.dirty = True
                        self.status = "Removed polygon vertex"
                    else:
                        self.delete_selected()
                else:
                    self.delete_selected()
            elif event.key == pygame.K_DELETE: self.delete_selected()
            elif event.key == pygame.K_f and self.hover_tile: self.flood_fill(self.hover_tile)
            elif event.key == pygame.K_LEFTBRACKET: self.snap = {64:32,32:16,16:8,8:0,0:0}.get(self.snap, 16)
            elif event.key == pygame.K_RIGHTBRACKET: self.snap = {0:8,8:16,16:32,32:64,64:64}.get(self.snap, 16)
            elif self.mode == "select" and event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                step = 16 if shift else 1
                dx = (-step if event.key == pygame.K_LEFT else step if event.key == pygame.K_RIGHT else 0)
                dy = (-step if event.key == pygame.K_UP else step if event.key == pygame.K_DOWN else 0)
                self.nudge_selected(dx, dy)
        return True

    def playtest(self) -> None:
        if self.project_root is None:
            self.status = "Playtest unavailable: no project root"
            return
        self.save()
        env = os.environ.copy()
        env["MYSTERY_SCENE_PATH"] = str(self.scene_path.resolve())
        try:
            subprocess.Popen([sys.executable, str(self.project_root / "run_game.py")], cwd=self.project_root, env=env)
            self.status = "Playtest launched"
        except OSError as exc:
            self.status = f"Playtest failed: {exc}"

    def _keyboard_pan(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        speed = 700 / self.zoom
        dx = (keys[pygame.K_d] - keys[pygame.K_a]) * speed * dt
        dy = (keys[pygame.K_s] - keys[pygame.K_w]) * speed * dt
        if dx or dy:
            self.camera_x += dx; self.camera_y += dy; self._clamp_camera()

    # ---------- lifecycle ----------

    def run(self, *, screenshot: Path | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("Mystery Engine — Exploration Scene Editor")
        self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        self.font_small = pygame.font.Font(None, 24)
        self.font = pygame.font.Font(None, 30)
        self.font_large = pygame.font.Font(None, 38)
        self._clamp_camera()
        clock = pygame.time.Clock()

        # A screenshot mode is useful both for tests and for showing the editor
        # without requiring user interaction.
        if screenshot is not None:
            self.draw(); pygame.display.flip(); pygame.image.save(self.screen, str(screenshot)); pygame.quit(); return

        running = True
        while running:
            dt = min(0.05, clock.tick(60) / 1000.0)
            for event in pygame.event.get():
                running = self.handle_event(event)
                if not running: break
            self._keyboard_pan(dt)
            self.draw()
            pygame.display.flip()
        self._stop_music_preview()
        self._stop_sfx_preview()
        pygame.quit()


def run_editor(
    scene_path: Path,
    catalog: WorldAssetCatalog,
    asset_root: Path,
    *,
    project_root: Path | None = None,
    new_width: int = 40,
    new_height: int = 24,
    screenshot: Path | None = None,
) -> None:
    scene_path = Path(scene_path)
    if scene_path.exists():
        scene = load_exploration_scene(scene_path)
    else:
        scene = ExplorationSceneData.blank(scene_path.stem, new_width, new_height)
    editor = ExplorationSceneEditor(scene, scene_path, catalog, asset_root, project_root=project_root)
    editor.run(screenshot=screenshot)
