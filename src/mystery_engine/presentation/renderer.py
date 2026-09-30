from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pygame

from mystery_engine.config import EngineConfig
from mystery_engine.core import Character, GridPos
from mystery_engine.dungeon import DungeonFloor, ExplorationMemory, TileKind
from mystery_engine.story import DialogueController, ExplorationMap
from mystery_engine.core.autotile import autotile_asset, dungeon_walkable_mask, elevation_cliff_assets, elevation_higher_mask, oriented_neighbor_mask
from mystery_engine.ui import MenuController


@dataclass
class _ExplorationWalkState:
    position: tuple[float, float]
    started_at: float
    moving: bool = False


@dataclass
class _DungeonWalkState:
    logical: tuple[int, int]
    start: tuple[float, float]
    target: tuple[float, float]
    started_at: float
    duration: float
    walk_started_at: float


class Renderer:
    _WALK_COLUMNS = 8
    _WALK_ROWS = 4
    _WALK_FPS = 12.0
    _DUNGEON_STEP_SECONDS = 0.11
    def __init__(self, config: EngineConfig, asset_root: Path | None = None) -> None:
        self.config = config
        self.asset_root = Path(asset_root) if asset_root else None
        self.canvas = pygame.Surface(config.logical_size)
        self.font_small = pygame.font.Font(None, 28)
        self.font = pygame.font.Font(None, 34)
        self.font_large = pygame.font.Font(None, 42)
        self.font_title = pygame.font.Font(None, 50)

        self.bg = pygame.Color("#11151c")
        self.panel = pygame.Color("#202733")
        self.panel2 = pygame.Color("#2b3442")
        self.text = pygame.Color("#f4f1e8")
        self.muted = pygame.Color("#b7bdc8")
        self.accent = pygame.Color("#e6c15a")
        self.floor = pygame.Color("#6e6756")
        self.wall = pygame.Color("#26252b")
        self.stairs = pygame.Color("#d9b650")
        self.unknown = pygame.Color("#101318")
        self.player = pygame.Color("#cf744e")
        self.ally = pygame.Color("#7752a5")
        self.enemy = pygame.Color("#9b3c42")
        self.item = pygame.Color("#76b981")
        self.hp_good = pygame.Color("#77b56a")
        self.hp_low = pygame.Color("#d46a5f")
        self._surface_cache: dict[tuple[str, tuple[int, int]], pygame.Surface | None] = {}
        self._exploration_walk_states: dict[str, _ExplorationWalkState] = {}
        self._dungeon_walk_states: dict[str, _DungeonWalkState] = {}
        self._dungeon_walk_floor_token: int | None = None

    def begin(self) -> pygame.Surface:
        self.canvas.fill(self.bg)
        return self.canvas

    def present(self, display: pygame.Surface) -> None:
        dw, dh = display.get_size()
        lw, lh = self.config.logical_size
        scale = min(dw / lw, dh / lh)
        target = (max(1, int(lw * scale)), max(1, int(lh * scale)))
        # Keep the deliberately pixel-art presentation crisp. Smooth-scaling the
        # whole 1080p canvas made small labels and sprite edges shimmer while the
        # camera moved. At the native target resolution this is a no-op; resized
        # development windows use nearest-neighbor scaling.
        frame = self.canvas if target == self.config.logical_size else pygame.transform.scale(self.canvas, target)
        display.fill((0, 0, 0))
        display.blit(frame, ((dw - target[0]) // 2, (dh - target[1]) // 2))
        pygame.display.flip()

    # ---------- exploration ----------

    def draw_exploration(self, world: ExplorationMap, player_id: str) -> None:
        now = pygame.time.get_ticks() / 1000.0
        viewport = pygame.Rect(0, 0, self.config.logical_width, self.config.logical_height)
        player = world.actor(player_id)
        camera_subject = player.position
        if world.camera_follow:
            try:
                camera_subject = world.target_position(world.camera_follow)
            except KeyError:
                world.camera_follow = None
        if world.camera_override is not None:
            camera_subject = world.camera_override
        camera_x = max(0.0, min(world.width - viewport.w, camera_subject.x - viewport.w / 2)) if world.width > viewport.w else 0.0
        camera_y = max(0.0, min(world.height - viewport.h, camera_subject.y - viewport.h / 2)) if world.height > viewport.h else 0.0
        shake_x = shake_y = 0
        if world.camera_shake_time > 0 and world.camera_shake_strength > 0:
            phase = pygame.time.get_ticks() / 35.0
            shake_x = round(math.sin(phase * 1.7) * world.camera_shake_strength)
            shake_y = round(math.cos(phase * 2.3) * world.camera_shake_strength * 0.7)
        camera_ix = round(camera_x) + shake_x
        camera_iy = round(camera_y) + shake_y

        self.canvas.fill(self.bg, viewport)
        self._draw_exploration_background(world, camera_ix, camera_iy, viewport)
        self._draw_exploration_terrain(world, camera_ix, camera_iy, viewport)
        self._draw_exploration_elevation_faces(world, camera_ix, camera_iy, viewport)

        # Ground-hugging decorations can deliberately sit below the depth-sorted
        # world pass. Physical props such as trees, fences, waystones and actors
        # all participate in the same Y-sort so approaching them from north/south
        # produces the expected occlusion.
        for deco in sorted([s for s in world.scenery if s.visible and s.draw_behind_actors], key=lambda s: s.position.y):
            self._draw_scenery(deco, camera_ix, camera_iy)

        labels: list[tuple[str, int, int]] = []
        drawables: list[tuple[float, int, str, object]] = []
        # type-order resolves equal baselines: props first, actors second.
        for scenery in world.scenery:
            if scenery.visible and not scenery.draw_behind_actors:
                drawables.append((scenery.position.y, 0, "scenery", scenery))
        for item in world.interactables:
            if item.enabled:
                drawables.append((item.position.y, 0, "interactable", item))
        for actor in world.actors:
            if actor.enabled:
                drawables.append((actor.position.y + actor.radius, 1, "actor", actor))

        for _, _, kind, obj in sorted(drawables, key=lambda t: (t[0], t[1])):
            if kind == "scenery":
                self._draw_scenery(obj, camera_ix, camera_iy)
            elif kind == "interactable":
                item = obj
                rect = self._draw_interactable(item, camera_ix, camera_iy)
                if rect is not None:
                    labels.append((item.label, rect.centerx, rect.bottom + 8))
            else:
                actor = obj
                sx, sy = round(actor.position.x) - camera_ix, round(actor.position.y) - camera_iy
                sprite_key = actor.sprite_key or actor.id
                suffix = self._facing_suffix(actor.facing)
                walk_frame = self._exploration_walk_frame(actor.id, actor.position.x, actor.position.y, now)
                sprite = self._load_character_walk_frame(sprite_key, suffix, walk_frame, (84, 84))
                if sprite is None:
                    sprite = self._load_character_sprite(sprite_key, suffix, (84, 84))
                if sprite is None:
                    sprite = self._load_surface(f"characters/{sprite_key}.png", (84, 84))
                if sprite is not None:
                    self.canvas.blit(sprite, sprite.get_rect(center=(sx, sy)))
                else:
                    color = self.player if actor.id == player_id else self.ally
                    pygame.draw.circle(self.canvas, color, (sx, sy), int(actor.radius))
                    self._draw_facing_marker((sx, sy), actor.facing, color)
                labels.append((actor.name, sx, sy - round(actor.radius) - 38))

        # Labels are UI, not world geometry, so keep them readable after depth sorting.
        for label, lx, ly in labels:
            self._draw_world_label(label, lx, ly)

        hint = self.font_small.render("WASD move  •  Shift sprint  •  Space interact  •  E menu", True, self.text)
        self.canvas.blit(hint, (28, 24))

    # ---------- dungeon ----------

    def draw_dungeon(
        self,
        floor: DungeonFloor,
        memory: ExplorationMemory,
        party: list[Character],
        floor_number: int,
        floor_total: int,
        preserve_entity_ids: set[str] | None = None,
    ) -> None:
        preserve_entity_ids = preserve_entity_ids or set()
        now = pygame.time.get_ticks() / 1000.0
        self._sync_dungeon_walk_states(floor, now)
        view = pygame.Rect(0, 0, self.config.dungeon_view_width, self.config.logical_height)
        self.canvas.fill(self.unknown, view)
        leader = next(c for c in party if c.leader)
        if leader.grid_pos is None:
            return
        tile = self.config.tile_px
        center_x, center_y = self.config.dungeon_view_width // 2, self.config.logical_height // 2
        leader_sprite_key = leader.metadata.get("sprite_key", leader.id)
        if self._has_character_walk_sheet(leader_sprite_key):
            leader_x, leader_y, _ = self._dungeon_walk_sample(leader, now)
        else:
            leader_x, leader_y = float(leader.grid_pos.x), float(leader.grid_pos.y)
        camera_world_x = leader_x * tile + tile / 2 - center_x
        camera_world_y = leader_y * tile + tile / 2 - center_y

        stairs_tile = self._load_surface("tiles/stairs.png", (tile, tile))

        min_x = max(0, int(camera_world_x // tile) - 1)
        max_x = min(floor.width, int((camera_world_x + view.w) // tile) + 2)
        min_y = max(0, int(camera_world_y // tile) - 1)
        max_y = min(floor.height, int((camera_world_y + view.h) // tile) + 2)

        # First pass: solid terrain. Walkable dungeon tiles draw their own baked-in
        # wall boundary via explicit autotiles. Wall cells still exist in the
        # simulation, but on the main view they render as void/darkness so the
        # room edge is represented only once.
        for y in range(min_y, max_y):
            for x in range(min_x, max_x):
                pos = GridPos(x, y)
                rect = pygame.Rect(int(x * tile - camera_world_x), int(y * tile - camera_world_y), tile, tile)
                if pos not in memory.discovered:
                    pygame.draw.rect(self.canvas, self.unknown, rect)
                    continue

                t = floor.tile(pos)
                visible = pos in memory.visible
                if t.kind is TileKind.WALL:
                    # Experimental wall-void mode: wall grid cells still exist for
                    # generation, collision, and line-of-sight, but on the main
                    # dungeon view they are rendered as void. The visible masonry
                    # belongs to the explicit boundary baked into adjacent walkable
                    # dungeon autotiles instead of to the wall cell itself.
                    pygame.draw.rect(self.canvas, self.unknown, rect)
                    continue
                else:
                    walk_mask = dungeon_walkable_mask(floor, x, y)
                    tileset_key = getattr(floor, "tileset", "dungeon")
                    custom_key = f"tiles/{tileset_key}_auto_{walk_mask:03d}.png"
                    floor_tile = self._load_surface(custom_key, (tile, tile))
                    if floor_tile is None:
                        floor_tile = self._load_surface(autotile_asset("dungeon_floor", walk_mask), (tile, tile))
                    if floor_tile is None:
                        floor_variant = self._stable_variant(x, y, 3)
                        floor_tile = self._load_surface(f"tiles/{tileset_key}_floor_{floor_variant}.png", (tile, tile)) or self._load_surface(f"tiles/dungeon_floor_{floor_variant}.png", (tile, tile)) or self._load_surface("tiles/floor.png", (tile, tile))
                    if floor_tile is not None:
                        self.canvas.blit(floor_tile, rect)
                    else:
                        pygame.draw.rect(self.canvas, self.floor, rect)
                    if t.kind is TileKind.STAIRS:
                        if stairs_tile is not None:
                            stairs_rect = pygame.Rect(0, 0, int(tile * 0.78), int(tile * 0.78))
                            stairs_rect.center = rect.center
                            self.canvas.blit(pygame.transform.scale(stairs_tile, stairs_rect.size), stairs_rect)
                        else:
                            pygame.draw.rect(self.canvas, self.stairs, rect.inflate(-12, -12), border_radius=6)

                if not visible:
                    shade = pygame.Surface(rect.size, pygame.SRCALPHA)
                    shade.fill((10, 12, 18, 120))
                    self.canvas.blit(shade, rect)


        for ground in floor.ground_items:
            if ground.pos not in memory.visible:
                continue
            rect = pygame.Rect(int(ground.pos.x * tile - camera_world_x), int(ground.pos.y * tile - camera_world_y), tile, tile)
            sprite = self._load_item_sprite(ground.item.sprite_key or ground.item.id, (40, 40))
            if sprite is not None:
                self.canvas.blit(sprite, sprite.get_rect(center=rect.center))
            else:
                pygame.draw.circle(self.canvas, self.item, rect.center, 10)

        for entity in floor.entities:
            if (not entity.active and entity.id not in preserve_entity_ids) or entity.grid_pos is None or entity.grid_pos not in memory.visible:
                continue
            sprite_key = entity.metadata.get("sprite_key", entity.id)
            suffix = self._facing_suffix(entity.facing)
            if self._has_character_walk_sheet(sprite_key):
                visual_x, visual_y, walk_frame = self._dungeon_walk_sample(entity, now)
            else:
                visual_x, visual_y, walk_frame = float(entity.grid_pos.x), float(entity.grid_pos.y), 0
            rect = pygame.Rect(0, 0, tile, tile)
            rect.center = (
                round(visual_x * tile + tile / 2 - camera_world_x),
                round(visual_y * tile + tile / 2 - camera_world_y),
            )
            sprite = self._load_character_walk_frame(sprite_key, suffix, walk_frame, (56, 56))
            if sprite is None:
                sprite = self._load_character_sprite(sprite_key, suffix, (56, 56))
            if sprite is None:
                sprite = self._load_surface(f"characters/{sprite_key}.png", (56, 56))
            if sprite is not None:
                self.canvas.blit(sprite, sprite.get_rect(center=rect.center))
            else:
                color = self.enemy if entity.hostile else (self.player if entity.leader else self.ally)
                pygame.draw.circle(self.canvas, color, rect.center, 24)
                self._draw_facing_marker(rect.center, entity.facing, color)
            self._draw_world_label(entity.name[:11], rect.centerx, rect.y - 20)

        self._draw_sidebar(floor, memory, party, floor_number, floor_total)

    def draw_projectile(self, animation, floor: DungeonFloor, party: list[Character]) -> None:
        event = animation.event
        leader = next((c for c in party if c.leader), None)
        if leader is None or leader.grid_pos is None:
            return
        now = pygame.time.get_ticks() / 1000.0
        self._sync_dungeon_walk_states(floor, now)
        tile = self.config.tile_px
        center_x, center_y = self.config.dungeon_view_width // 2, self.config.logical_height // 2
        leader_sprite_key = leader.metadata.get("sprite_key", leader.id)
        if self._has_character_walk_sheet(leader_sprite_key):
            leader_x, leader_y, _ = self._dungeon_walk_sample(leader, now)
        else:
            leader_x, leader_y = float(leader.grid_pos.x), float(leader.grid_pos.y)
        camera_world_x = leader_x * tile + tile / 2 - center_x
        camera_world_y = leader_y * tile + tile / 2 - center_y

        sx = event.source_pos.x * tile + tile / 2 - camera_world_x
        sy = event.source_pos.y * tile + tile / 2 - camera_world_y
        tx = event.target_pos.x * tile + tile / 2 - camera_world_x
        ty = event.target_pos.y * tile + tile / 2 - camera_world_y

        if animation.in_impact:
            px, py = tx, ty
        else:
            t = animation.progress
            px = sx + (tx - sx) * t
            py = sy + (ty - sy) * t - math.sin(math.pi * t) * float(event.arc_px)

        sheet = self._load_native_surface(f"projectiles/{event.projectile_key}.png")
        if sheet is None:
            pygame.draw.circle(self.canvas, self.accent, (round(px), round(py)), 10)
            return
        frames = 6
        fw = sheet.get_width() // frames
        fh = sheet.get_height()
        index = max(0, min(frames - 1, animation.frame_index))
        frame = pygame.Surface((fw, fh), pygame.SRCALPHA)
        frame.blit(sheet, (0, 0), pygame.Rect(index * fw, 0, fw, fh))
        bounds = frame.get_bounding_rect()
        if bounds.width > 0 and bounds.height > 0:
            frame = frame.subsurface(bounds).copy()

        if index < 4:
            angle = math.degrees(math.atan2(-(ty - sy), tx - sx))
            frame = pygame.transform.rotate(frame, angle)
        self.canvas.blit(frame, frame.get_rect(center=(round(px), round(py))))

    def _draw_sidebar(self, floor: DungeonFloor, memory: ExplorationMemory, party: list[Character], floor_number: int, floor_total: int) -> None:
        x0 = self.config.dungeon_view_width
        sidebar = pygame.Rect(x0, 0, self.config.sidebar_width, self.config.logical_height)
        pygame.draw.rect(self.canvas, self.panel, sidebar)
        pygame.draw.line(self.canvas, self.accent, (x0, 0), (x0, self.config.logical_height), 3)

        title = self.font_large.render(f"{getattr(floor, 'dungeon_name', 'Dungeon')}  {floor_number}/{floor_total}F", True, self.text)
        self.canvas.blit(title, (x0 + 24, 22))

        map_size = self.config.map_panel_px
        map_rect = pygame.Rect(x0 + 24, 84, map_size, map_size)
        pygame.draw.rect(self.canvas, self.bg, map_rect, border_radius=8)
        pygame.draw.rect(self.canvas, self.panel2, map_rect, 2, border_radius=8)
        self._draw_minimap(floor, memory, party, map_rect)

        y = map_rect.bottom + 26
        for member in party[:4]:
            self._draw_party_row(member, pygame.Rect(x0 + 20, y, self.config.sidebar_width - 40, 106))
            y += 116

    def _draw_minimap(self, floor: DungeonFloor, memory: ExplorationMemory, party: list[Character], rect: pygame.Rect) -> None:
        scale = min(rect.w / floor.width, rect.h / floor.height)
        ox = rect.x + (rect.w - floor.width * scale) / 2
        oy = rect.y + (rect.h - floor.height * scale) / 2
        for pos in memory.mapped_tiles(floor):
            t = floor.tile(pos)
            color = self.stairs if t.kind is TileKind.STAIRS else pygame.Color("#767c82")
            r = pygame.Rect(int(ox + pos.x * scale), int(oy + pos.y * scale), max(1, math.ceil(scale)), max(1, math.ceil(scale)))
            pygame.draw.rect(self.canvas, color, r)
        for ground in floor.ground_items:
            if ground.pos in memory.visible:
                cx = int(ox + (ground.pos.x + 0.5) * scale)
                cy = int(oy + (ground.pos.y + 0.5) * scale)
                pygame.draw.circle(self.canvas, self.item, (cx, cy), max(2, int(scale * 0.35)))
        for entity in floor.entities:
            if not entity.active or entity.grid_pos is None or entity.grid_pos not in memory.visible:
                continue
            cx = int(ox + (entity.grid_pos.x + 0.5) * scale)
            cy = int(oy + (entity.grid_pos.y + 0.5) * scale)
            color = self.enemy if entity.hostile else (self.player if entity.leader else self.ally)
            pygame.draw.circle(self.canvas, color, (cx, cy), max(3, int(scale * 0.45)))

    def _draw_party_row(self, member: Character, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.canvas, self.panel2, rect, border_radius=10)
        portrait = pygame.Rect(rect.x + 12, rect.y + 12, 76, 76)
        portrait_key = member.metadata.get("portrait_key", member.metadata.get("sprite_key", member.id))
        portrait_surf = self._load_surface(f"portraits/{portrait_key}.png", portrait.size)
        if portrait_surf is not None:
            self.canvas.blit(portrait_surf, portrait)
        else:
            color = self.player if member.leader else self.ally
            pygame.draw.rect(self.canvas, color, portrait, border_radius=8)
            initials = self.font_large.render(member.name[:1], True, self.text)
            self.canvas.blit(initials, initials.get_rect(center=portrait.center))

        name = self.font.render(member.name, True, self.text)
        self.canvas.blit(name, (rect.x + 104, rect.y + 10))
        tactic = self.font_small.render(member.ai_tactic.value if not member.hostile else "Enemy", True, self.muted)
        self.canvas.blit(tactic, (rect.x + 104, rect.y + 42))
        hp_text = f"HP {member.stats.current_hp}/{member.stats.max_hp}"
        hp = self.font_small.render(hp_text, True, self.text)
        self.canvas.blit(hp, (rect.x + 104, rect.y + 64))
        bar = pygame.Rect(rect.x + 104, rect.y + 84, rect.w - 122, 12)
        pygame.draw.rect(self.canvas, self.bg, bar, border_radius=5)
        fill = bar.copy()
        fill.w = int(bar.w * member.stats.hp_ratio)
        pygame.draw.rect(self.canvas, self.hp_good if member.stats.hp_ratio > 0.3 else self.hp_low, fill, border_radius=5)

    # ---------- overlays ----------

    def draw_cinematic_overlay(self, overlay) -> None:
        """Draw full-screen fades/flashes and temporary title banners."""
        if overlay is None:
            return
        if getattr(overlay, "fade_alpha", 0.0) > 0:
            alpha = max(0, min(255, round(float(overlay.fade_alpha) * 255)))
            layer = pygame.Surface(self.config.logical_size, pygame.SRCALPHA)
            color = getattr(overlay, "fade_color", pygame.Color("black"))
            layer.fill((color.r, color.g, color.b, alpha))
            self.canvas.blit(layer, (0, 0))

        text = getattr(overlay, "banner_text", None)
        if text:
            width = min(self.config.logical_width - 160, max(520, self.font_title.size(text)[0] + 100))
            rect = pygame.Rect((self.config.logical_width - width) // 2, 90, width, 100)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.fill((18, 22, 30, 225))
            self.canvas.blit(panel, rect.topleft)
            pygame.draw.rect(self.canvas, self.accent, rect, 2, border_radius=10)
            surf = self.font_title.render(text, True, self.text)
            self.canvas.blit(surf, surf.get_rect(center=rect.center))

    def draw_dialogue(self, dialogue: DialogueController, max_width: int | None = None) -> None:
        line = dialogue.current
        if line is None:
            return
        width = max_width or self.config.logical_width
        h = self.config.dialogue_height
        rect = pygame.Rect(20, self.config.logical_height - h - 20, width - 40, h)
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((24, 28, 38, 245))
        self.canvas.blit(overlay, rect.topleft)
        pygame.draw.rect(self.canvas, self.accent, rect, 3, border_radius=12)

        portrait = pygame.Rect(rect.x + 28, rect.y + 38, self.config.portrait_px, self.config.portrait_px)
        key = line.portrait_key or line.speaker.lower().replace(" ", "_")
        portrait_surf = self._load_surface(f"portraits/{key}.png", portrait.size)
        if portrait_surf is not None:
            self.canvas.blit(portrait_surf, portrait)
        else:
            pygame.draw.rect(self.canvas, self.panel2, portrait, border_radius=12)
            initial = self.font_title.render(line.speaker[:1], True, self.text)
            self.canvas.blit(initial, initial.get_rect(center=portrait.center))
        speaker = self.font_large.render(line.speaker, True, self.accent)
        self.canvas.blit(speaker, (portrait.right + 30, rect.y + 30))
        self._draw_wrapped(line.text, self.font, self.text, portrait.right + 30, rect.y + 82, rect.right - portrait.right - 65, 40)
        advance = self.font_small.render("Space", True, self.muted)
        self.canvas.blit(advance, (rect.right - advance.get_width() - 22, rect.bottom - advance.get_height() - 14))

    def draw_menu(self, menu: MenuController) -> None:
        if not menu.active:
            return
        base_x, base_y = 86, 90
        for depth, level in enumerate(menu.stack):
            x = base_x + depth * 54
            y = base_y + depth * 34
            width = 520
            row_h = 58
            height = 62 + max(1, len(level.entries)) * row_h + 18
            rect = pygame.Rect(x, y, width, height)
            pygame.draw.rect(self.canvas, self.panel, rect, border_radius=12)
            pygame.draw.rect(self.canvas, self.accent, rect, 3, border_radius=12)
            title = self.font_large.render(level.title, True, self.accent)
            self.canvas.blit(title, (x + 24, y + 16))
            for i, entry in enumerate(level.entries):
                ry = y + 65 + i * row_h
                selected = i == level.selected
                if selected:
                    pygame.draw.rect(self.canvas, self.panel2, pygame.Rect(x + 14, ry, width - 28, row_h - 4), border_radius=8)
                color = self.text if entry.enabled else self.muted
                prefix = "> " if selected else "  "
                label = self.font.render(prefix + entry.label, True, color)
                self.canvas.blit(label, (x + 25, ry + 10))
                if entry.detail:
                    detail = self.font_small.render(entry.detail, True, self.muted if entry.enabled else color)
                    self.canvas.blit(detail, (rect.right - detail.get_width() - 50, ry + 16))
                if entry.resolve_children():
                    arrow = self.font.render("›", True, color)
                    self.canvas.blit(arrow, (rect.right - 45, ry + 10))

    def draw_message_log(self, messages: list[str], dungeon: bool) -> None:
        if not messages:
            return
        max_width = self.config.dungeon_view_width if dungeon else self.config.logical_width
        lines = messages[-4:]
        width = min(900, max_width - 60)
        rect = pygame.Rect(28, 72, width, 36 * len(lines) + 20)
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((10, 12, 18, 185))
        self.canvas.blit(overlay, rect.topleft)
        for i, message in enumerate(lines):
            text = self.font_small.render(message, True, self.text)
            self.canvas.blit(text, (rect.x + 12, rect.y + 8 + i * 34))

    # ---------- helpers ----------

    def _draw_exploration_background(self, world: ExplorationMap, camera_ix: int, camera_iy: int, viewport: pygame.Rect) -> None:
        if not world.background_key:
            return
        surface = self._load_native_surface(f"backgrounds/{world.background_key}.png")
        if surface is None:
            return
        if world.background_mode == "tile":
            tw, th = surface.get_size()
            for y in range(-camera_iy % th - th, viewport.h + th, th):
                for x in range(-camera_ix % tw - tw, viewport.w + tw, tw):
                    self.canvas.blit(surface, (x, y))
            return
        target_size = (max(1, round(world.width)), max(1, round(world.height)))
        scaled = self._load_surface(f"backgrounds/{world.background_key}.png", target_size)
        if scaled is None:
            return
        source = pygame.Rect(camera_ix, camera_iy, viewport.w, viewport.h)
        self.canvas.blit(scaled, (0, 0), source)

    def _terrain_style_sprite(self, world: ExplorationMap, terrain, tx: int, ty: int, kind: str, tile: int) -> pygame.Surface | None:
        style = world.terrain_styles.get(kind)
        if not style:
            return None
        mode = str(style.get("mode", "single"))
        sprites = [str(v) for v in style.get("sprite_keys", [])]
        if mode == "autotile":
            mask = oriented_neighbor_mask(terrain, tx, ty, kind)
            return self._load_surface(f"terrain/{kind}/auto_{mask:03d}.png", (tile, tile))
        if not sprites:
            return None
        index = self._stable_variant(tx, ty, len(sprites)) if mode == "variants" else 0
        return self._load_surface(f"terrain/{sprites[index]}.png", (tile, tile))

    def _draw_exploration_terrain(self, world: ExplorationMap, camera_ix: int, camera_iy: int, viewport: pygame.Rect) -> None:
        terrain = world.terrain
        tile = terrain.tile_size if terrain is not None else 64
        if terrain is None:
            grass = self._load_surface("tiles/grass_0.png", (tile, tile)) or self._load_surface("tiles/grass.png", (tile, tile))
            if grass is not None:
                for y in range(-camera_iy % tile - tile, viewport.h + tile, tile):
                    for x in range(-camera_ix % tile - tile, viewport.w + tile, tile):
                        self.canvas.blit(grass, (x, y))
            return

        min_tx = max(0, camera_ix // tile - 1)
        max_tx = min(terrain.width_tiles, (camera_ix + viewport.w) // tile + 2)
        min_ty = max(0, camera_iy // tile - 1)
        max_ty = min(terrain.height_tiles, (camera_iy + viewport.h) // tile + 2)

        for ty in range(min_ty, max_ty):
            for tx in range(min_tx, max_tx):
                kind = terrain.terrain_at(tx, ty)
                rect = pygame.Rect(tx * tile - camera_ix, ty * tile - camera_iy, tile, tile)
                sprite = self._terrain_style_sprite(world, terrain, tx, ty, kind, tile)
                if sprite is None:
                    if kind in ("grass", "upper_grass"):
                        weighted = (0, 0, 0, 2, 0, 1, 0, 4, 0, 3, 0, 2)
                        variant = weighted[self._stable_variant(tx, ty, len(weighted))]
                        sprite = self._load_surface(f"tiles/grass_{variant}.png", (tile, tile)) or self._load_surface("tiles/grass.png", (tile, tile))
                    elif kind in ("path", "water"):
                        sprite = self._compose_blob_terrain_tile(terrain, tx, ty, kind, tile)

                if sprite is not None:
                    self.canvas.blit(sprite, rect)
                else:
                    style = world.terrain_styles.get(kind, {})
                    if bool(style.get("transparent", False)):
                        continue
                    configured = style.get("fallback_color")
                    fallback = pygame.Color(str(configured)) if configured else {
                        "grass": pygame.Color("#6aa65d"),
                        "upper_grass": pygame.Color("#6aa65d"),
                        "path": pygame.Color("#b68c59"),
                        "water": pygame.Color("#377fa4"),
                        "void": self.bg,
                    }.get(kind, pygame.Color("#526f49"))
                    pygame.draw.rect(self.canvas, fallback, rect)

    def _draw_exploration_elevation_faces(self, world: ExplorationMap, camera_ix: int, camera_iy: int, viewport: pygame.Rect) -> None:
        terrain = world.terrain
        if terrain is None or not terrain.elevations:
            return
        tile = terrain.tile_size
        min_tx = max(0, camera_ix // tile - 1)
        max_tx = min(terrain.width_tiles, (camera_ix + viewport.w) // tile + 2)
        min_ty = max(0, camera_iy // tile - 1)
        max_ty = min(terrain.height_tiles, (camera_iy + viewport.h) // tile + 2)

        # Cliff faces belong visually to the lower cell. The upper cell remains a
        # real terrain surface, so this layer can later support walkable plateaus,
        # stairs, ramps, or multiple elevation changes without changing the art
        # model.
        for ty in range(min_ty, max_ty):
            for tx in range(min_tx, max_tx):
                if terrain.terrain_at(tx, ty) == "void":
                    continue
                kind = terrain.terrain_at(tx, ty)
                mask = elevation_higher_mask(terrain, tx, ty)
                custom = self._load_surface(f"terrain/{kind}/cliff_{mask:03d}.png", (tile, tile)) if mask else None
                if custom is not None:
                    self.canvas.blit(custom, (tx * tile - camera_ix, ty * tile - camera_iy))
                    continue
                for asset in elevation_cliff_assets(terrain, tx, ty):
                    sprite = self._load_surface(asset, (tile, tile))
                    if sprite is None:
                        continue
                    self.canvas.blit(sprite, (tx * tile - camera_ix, ty * tile - camera_iy))

    def _compose_blob_terrain_tile(self, terrain, tx: int, ty: int, kind: str, tile: int) -> pygame.Surface | None:
        if kind == 'path':
            return self._select_explicit_blob_tile(terrain, tx, ty, tile, 'path')
        return self._select_explicit_blob_tile(terrain, tx, ty, tile, 'water')

    def _select_explicit_blob_tile(self, terrain, tx: int, ty: int, tile: int, kind: str) -> pygame.Surface | None:
        # Every oriented variant is a real pre-generated PNG. The renderer only
        # computes the local topology mask and selects the corresponding asset.
        mask = oriented_neighbor_mask(terrain, tx, ty, kind)
        key = autotile_asset(kind, mask)
        surf = self._load_surface(key, (tile, tile))
        if surf is not None:
            return surf
        fallback = 'tiles/path_center.png' if kind == 'path' else 'tiles/water_center.png'
        return self._load_surface(fallback, (tile, tile))

    @staticmethod
    def _stable_variant(x: int, y: int, count: int) -> int:
        return ((x * 73856093) ^ (y * 19349663)) % count

    def _draw_scenery(self, scenery, camera_ix: int, camera_iy: int) -> None:
        # Scenery is authored at its in-game display size. Do not resample it:
        # scaling these concept-derived sprites was the source of the fuzzy borders.
        sprite = self._load_native_surface(f"objects/{scenery.sprite_key}.png")
        x = round(scenery.position.x) - camera_ix
        y = round(scenery.position.y) - camera_iy
        if sprite is not None:
            if scenery.anchor == "bottom_center":
                rect = sprite.get_rect(midbottom=(x, y))
            else:
                rect = sprite.get_rect(center=(x, y))
            self.canvas.blit(sprite, rect)
        else:
            pygame.draw.rect(self.canvas, pygame.Color("#5d6a58"), pygame.Rect(x - scenery.size[0] // 2, y - scenery.size[1], scenery.size[0], scenery.size[1]))

    def _draw_interactable(self, item, camera_ix: int, camera_iy: int) -> pygame.Rect | None:
        if not getattr(item, "visible", True):
            return None
        sprite = self._load_native_surface(f"objects/{item.icon_key or item.id}.png")
        sx = round(item.position.x) - camera_ix
        sy = round(item.position.y) - camera_iy
        if sprite is None:
            rect = pygame.Rect(sx - 20, sy - 40, 40, 40)
            pygame.draw.rect(self.canvas, self.accent, rect, border_radius=6)
            return rect
        if item.anchor == "bottom_center":
            rect = sprite.get_rect(midbottom=(sx, sy))
        else:
            rect = sprite.get_rect(center=(sx, sy))
        self.canvas.blit(sprite, rect)
        return rect

    def _load_native_surface(self, relative: str) -> pygame.Surface | None:
        if self.asset_root is None:
            return None
        path = self.asset_root / relative
        key = (f"native:{relative}", (-1, -1))
        if key in self._surface_cache:
            return self._surface_cache[key]
        if not path.exists():
            self._surface_cache[key] = None
            return None
        surface = pygame.image.load(path.as_posix()).convert_alpha()
        self._surface_cache[key] = surface
        return surface

    def _load_surface(self, relative: str, size: tuple[int, int]) -> pygame.Surface | None:
        if self.asset_root is None:
            return None
        key = (relative, size)
        cached = self._surface_cache.get(key)
        if cached is not None:
            return cached
        path = self.asset_root / relative
        if not path.exists():
            self._surface_cache[key] = None  # type: ignore[assignment]
            return None
        surface = pygame.image.load(path.as_posix()).convert_alpha()
        if surface.get_size() != size:
            surface = pygame.transform.scale(surface, size)
        self._surface_cache[key] = surface
        return surface

    def _draw_tiled_rect(self, rect: pygame.Rect, sprite: pygame.Surface | None) -> None:
        if sprite is None:
            pygame.draw.rect(self.canvas, pygame.Color("#536052"), rect)
            return
        tw, th = sprite.get_size()
        old_clip = self.canvas.get_clip()
        self.canvas.set_clip(rect)
        for y in range(rect.top, rect.bottom, th):
            for x in range(rect.left, rect.right, tw):
                self.canvas.blit(sprite, (x, y))
        self.canvas.set_clip(old_clip)

    def _exploration_walk_frame(self, actor_id: str, x: float, y: float, now: float) -> int:
        current = (float(x), float(y))
        state = self._exploration_walk_states.get(actor_id)
        if state is None:
            self._exploration_walk_states[actor_id] = _ExplorationWalkState(current, now)
            return 0

        distance = math.hypot(current[0] - state.position[0], current[1] - state.position[1])
        if distance > 128.0:
            # Scene changes and scripted teleports should not play a giant walk step.
            state.moving = False
            state.started_at = now
        elif distance > 0.1:
            if not state.moving:
                state.started_at = now
            state.moving = True
        else:
            state.moving = False

        state.position = current
        if not state.moving:
            return 0
        return int(max(0.0, now - state.started_at) * self._WALK_FPS) % self._WALK_COLUMNS

    def _sync_dungeon_walk_states(self, floor: DungeonFloor, now: float) -> None:
        floor_token = id(floor)
        if floor_token != self._dungeon_walk_floor_token:
            self._dungeon_walk_states.clear()
            self._dungeon_walk_floor_token = floor_token

        active_ids: set[str] = set()
        for entity in floor.entities:
            if entity.grid_pos is None:
                continue
            active_ids.add(entity.id)
            logical = (entity.grid_pos.x, entity.grid_pos.y)
            state = self._dungeon_walk_states.get(entity.id)
            if state is None:
                point = (float(logical[0]), float(logical[1]))
                self._dungeon_walk_states[entity.id] = _DungeonWalkState(
                    logical=logical,
                    start=point,
                    target=point,
                    started_at=now,
                    duration=self._DUNGEON_STEP_SECONDS,
                    walk_started_at=now,
                )
                continue
            if logical == state.logical:
                continue

            visual_x, visual_y, moving = self._sample_dungeon_state(state, now)
            if not moving:
                state.walk_started_at = now
            state.logical = logical
            state.start = (visual_x, visual_y)
            state.target = (float(logical[0]), float(logical[1]))
            state.started_at = now
            state.duration = self._DUNGEON_STEP_SECONDS

        for entity_id in tuple(self._dungeon_walk_states):
            if entity_id not in active_ids:
                del self._dungeon_walk_states[entity_id]

    @staticmethod
    def _sample_dungeon_state(state: _DungeonWalkState, now: float) -> tuple[float, float, bool]:
        if state.duration <= 0:
            return state.target[0], state.target[1], False
        progress = max(0.0, min(1.0, (now - state.started_at) / state.duration))
        x = state.start[0] + (state.target[0] - state.start[0]) * progress
        y = state.start[1] + (state.target[1] - state.start[1]) * progress
        return x, y, progress < 1.0

    def _dungeon_walk_sample(self, entity: Character, now: float) -> tuple[float, float, int]:
        if entity.grid_pos is None:
            return 0.0, 0.0, 0
        state = self._dungeon_walk_states.get(entity.id)
        if state is None:
            return float(entity.grid_pos.x), float(entity.grid_pos.y), 0
        x, y, moving = self._sample_dungeon_state(state, now)
        if not moving:
            return x, y, 0
        frame = int(max(0.0, now - state.walk_started_at) * self._WALK_FPS) % self._WALK_COLUMNS
        return x, y, frame

    def _has_character_walk_sheet(self, sprite_key: str) -> bool:
        return self._load_native_surface(f"characters/{sprite_key}_walk.png") is not None

    def _load_character_walk_frame(
        self,
        sprite_key: str,
        suffix: str,
        frame_index: int,
        size: tuple[int, int],
    ) -> pygame.Surface | None:
        frame_index %= self._WALK_COLUMNS
        row = {"n": 0, "e": 1, "s": 2, "w": 3}.get(suffix, 2)
        cache_key = (f"characters/{sprite_key}_walk.png#{suffix}:{frame_index}", size)
        if cache_key in self._surface_cache:
            return self._surface_cache[cache_key]

        sheet = self._load_native_surface(f"characters/{sprite_key}_walk.png")
        if sheet is None:
            self._surface_cache[cache_key] = None
            return None

        # Walking atlases use a true, uniform 8x4 grid: north, east, south, west.
        # Each frame is authored inside an equal cell, so no per-character crop
        # guesses or alpha-bound trimming are needed at runtime.
        x0 = round(frame_index * sheet.get_width() / self._WALK_COLUMNS)
        x1 = round((frame_index + 1) * sheet.get_width() / self._WALK_COLUMNS)
        y0 = round(row * sheet.get_height() / self._WALK_ROWS)
        y1 = round((row + 1) * sheet.get_height() / self._WALK_ROWS)

        frame = pygame.Surface((max(1, x1 - x0), max(1, y1 - y0)), pygame.SRCALPHA)
        frame.blit(sheet, (0, 0), pygame.Rect(x0, y0, x1 - x0, y1 - y0))
        if frame.get_size() != size:
            frame = pygame.transform.scale(frame, size)
        self._surface_cache[cache_key] = frame
        return frame

    def _load_character_sprite(self, sprite_key: str, suffix: str, size: tuple[int, int]) -> pygame.Surface | None:
        # Prefer a shared 2x2 directional sheet when present. Layout:
        # top-left=north, top-right=east, bottom-left=south, bottom-right=west.
        cache_key = (f"characters/{sprite_key}_sheet.png#{suffix}", size)
        if cache_key in self._surface_cache:
            return self._surface_cache[cache_key]

        if self.asset_root is not None:
            sheet_path = self.asset_root / f"characters/{sprite_key}_sheet.png"
            if sheet_path.exists():
                sheet = pygame.image.load(sheet_path.as_posix()).convert_alpha()
                fw = sheet.get_width() // 2
                fh = sheet.get_height() // 2
                sx, sy = {"n": (0, 0), "e": (1, 0), "s": (0, 1), "w": (1, 1)}.get(suffix, (0, 1))
                frame = pygame.Surface((fw, fh), pygame.SRCALPHA)
                frame.blit(sheet, (0, 0), pygame.Rect(sx * fw, sy * fh, fw, fh))
                if frame.get_bounding_rect().width > 0:
                    frame = frame.subsurface(frame.get_bounding_rect()).copy()
                if frame.get_size() != size:
                    frame = pygame.transform.scale(frame, size)
                self._surface_cache[cache_key] = frame
                return frame

        sprite = self._load_surface(f"characters/{sprite_key}_{suffix}.png", size)
        self._surface_cache[cache_key] = sprite
        return sprite

    def _load_item_sprite(self, item_id: str, size: tuple[int, int]) -> pygame.Surface | None:
        return self._load_surface(f"items/{item_id}.png", size)

    def _draw_textured_rect(self, rect: pygame.Rect, sprite: pygame.Surface | None) -> None:
        if rect.w <= 0 or rect.h <= 0:
            return
        if sprite is None:
            pygame.draw.rect(self.canvas, pygame.Color("#666861"), rect)
            return
        tw, th = sprite.get_size()
        old_clip = self.canvas.get_clip()
        self.canvas.set_clip(rect)
        for y in range(rect.top, rect.bottom, th):
            for x in range(rect.left, rect.right, tw):
                self.canvas.blit(sprite, (x, y))
        self.canvas.set_clip(old_clip)

    @staticmethod
    def _facing_suffix(facing) -> str:
        # We currently have four-direction temporary art. Diagonals use their
        # horizontal component so A/D always visibly turns the sprite left/right;
        # pure vertical movement selects the front/back frames.
        if facing.dx > 0:
            return "e"
        if facing.dx < 0:
            return "w"
        return "s" if facing.dy > 0 else "n"

    def _draw_world_label(self, text: str, center_x: int, y: int) -> None:
        # Floating labels need a stable contrast surface; anti-aliased white text
        # directly over moving terrain appeared to fade in and out.
        surf = self.font_small.render(text, True, self.text)
        rect = surf.get_rect(midtop=(center_x, y)).inflate(12, 6)
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill((14, 18, 24, 225))
        self.canvas.blit(bg, rect.topleft)
        pygame.draw.rect(self.canvas, pygame.Color("#0a0d12"), rect, 1)
        self.canvas.blit(surf, surf.get_rect(center=rect.center))

    def _draw_facing_marker(self, center: tuple[int, int], facing, color: pygame.Color) -> None:
        dx, dy = facing.dx, facing.dy
        ex = center[0] + dx * 36
        ey = center[1] + dy * 36
        pygame.draw.line(self.canvas, self.text, center, (ex, ey), 5)

    def _draw_wrapped(self, text: str, font: pygame.font.Font, color: pygame.Color, x: int, y: int, width: int, line_height: int) -> None:
        words = text.split()
        line = ""
        yy = y
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if font.size(candidate)[0] <= width:
                line = candidate
            else:
                surf = font.render(line, True, color)
                self.canvas.blit(surf, (x, yy))
                yy += line_height
                line = word
        if line:
            self.canvas.blit(font.render(line, True, color), (x, yy))
