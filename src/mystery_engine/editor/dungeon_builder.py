from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random
import os
import subprocess
import sys
import pygame

from mystery_engine.dungeon import DungeonDefinition, SpawnRule


@dataclass
class Hit:
    rect: pygame.Rect
    action: str
    value: object | None = None


class DungeonBuilderEditor:
    """Visual authoring tool for data-driven dungeon definitions.

    The builder deliberately edits whole-dungeon rules rather than individual
    generated floors. Floor ranges are used for enemy/item pools and overrides,
    while the preview regenerates a concrete floor from the current definition.
    """

    TABS = ("Overview", "Generation", "Enemies", "Items", "Audio", "Preview")

    def __init__(
        self,
        definition: DungeonDefinition,
        path: Path,
        asset_root: Path,
        enemy_labels: dict[str, str],
        item_labels: dict[str, str],
        *,
        project_root: Path | None = None,
        window_size: tuple[int, int] = (1500, 900),
    ) -> None:
        self.definition = definition
        self.path = Path(path)
        self.asset_root = Path(asset_root)
        self.enemy_labels = dict(enemy_labels)
        self.item_labels = dict(item_labels)
        self.project_root = Path(project_root) if project_root else None
        self.window_size = window_size

        self.tab = "Overview"
        self.floor_number = 1
        self.seed = 1
        self.preview_floor = None
        self.status = "Ready"
        self.dirty = False
        self.hits: list[Hit] = []

        self.screen: pygame.Surface | None = None
        self.font: pygame.font.Font | None = None
        self.font_small: pygame.font.Font | None = None
        self.font_large: pygame.font.Font | None = None

        self._regenerate_preview()

    # ---------- dialogs ----------

    @staticmethod
    def _tk_root():
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return root

    def _ask_text(self, title: str, prompt: str, initial: str) -> str | None:
        from tkinter import simpledialog
        root = self._tk_root()
        try:
            return simpledialog.askstring(title, prompt, initialvalue=initial, parent=root)
        finally:
            root.destroy()

    def _ask_int(self, title: str, prompt: str, initial: int, minimum: int = 0) -> int | None:
        from tkinter import simpledialog
        root = self._tk_root()
        try:
            return simpledialog.askinteger(title, prompt, initialvalue=initial, minvalue=minimum, parent=root)
        finally:
            root.destroy()

    def _ask_float(self, title: str, prompt: str, initial: float, minimum: float = 0.0, maximum: float = 1.0) -> float | None:
        from tkinter import simpledialog
        root = self._tk_root()
        try:
            return simpledialog.askfloat(title, prompt, initialvalue=initial, minvalue=minimum, maxvalue=maximum, parent=root)
        finally:
            root.destroy()

    def _choose_music(self) -> str | None:
        music_dir = self.asset_root / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        from tkinter import filedialog
        root = self._tk_root()
        try:
            chosen = filedialog.askopenfilename(
                parent=root,
                title="Choose dungeon music",
                initialdir=music_dir,
                filetypes=[("Audio", "*.ogg *.wav *.mp3 *.flac"), ("All files", "*.*")],
            )
        finally:
            root.destroy()
        if not chosen:
            return None
        path = Path(chosen).resolve()
        try:
            return path.relative_to(self.asset_root.resolve()).as_posix()
        except ValueError:
            self.status = "Music must be inside the game assets folder"
            return None

    # ---------- model ----------

    def save(self) -> None:
        self.definition.save(self.path)
        self.dirty = False
        self.status = f"Saved {self.path.name}"

    def _changed(self, message: str) -> None:
        self.dirty = True
        self.status = message
        self.floor_number = max(1, min(self.floor_number, self.definition.floor_count))
        self._regenerate_preview()

    def _regenerate_preview(self) -> None:
        try:
            self.preview_floor = self.definition.generate_layout(self.floor_number, Random(self.seed))
            self.status = self.status if self.status != "Ready" else f"Preview floor {self.floor_number}"
        except Exception as exc:
            self.preview_floor = None
            self.status = f"Preview error: {exc}"

    def _edit_generation_value(self, key: str) -> None:
        current = int(self.definition.generation.get(key, 0))
        value = self._ask_int("Generation", key.replace("_", " ").title(), current, 1)
        if value is not None:
            self.definition.generation[key] = value
            self._changed(f"{key} = {value}")

    def _cycle_generator(self) -> None:
        current = str(self.definition.generation.get("type", "rooms_and_corridors"))
        self.definition.generation["type"] = "open_room" if current == "rooms_and_corridors" else "rooms_and_corridors"
        self._changed(f"Generator: {self.definition.generation['type']}")

    def _edit_rule(self, kind: str, index: int) -> None:
        rules = self.definition.enemies if kind == "enemy" else self.definition.items
        if not 0 <= index < len(rules):
            return
        rule = rules[index]
        floors = self._ask_text("Floor range", "Examples: 1-5, 8, 10+", rule.floors)
        if floors is None:
            return
        weight = self._ask_float("Spawn weight", "Relative spawn weight", rule.weight, 0.0, 10000.0)
        if weight is None:
            return
        minimum = self._ask_int("Minimum", "Minimum spawns per floor", rule.min_per_floor, 0)
        if minimum is None:
            return
        maximum = self._ask_int("Maximum", "Maximum spawns per floor", rule.max_per_floor, 0)
        if maximum is None:
            return
        rule.floors = floors
        rule.weight = weight
        rule.min_per_floor = minimum
        rule.max_per_floor = max(minimum, maximum)
        self._changed(f"Updated {rule.content_id}")

    def _add_rule(self, kind: str) -> None:
        catalog = self.enemy_labels if kind == "enemy" else self.item_labels
        if not catalog:
            self.status = f"No {kind} catalog entries"
            return
        choices = "\n".join(f"{key}: {label}" for key, label in catalog.items())
        content_id = self._ask_text(f"Add {kind}", f"Enter ID:\n\n{choices}", next(iter(catalog)))
        if content_id is None:
            return
        content_id = content_id.strip()
        if content_id not in catalog:
            self.status = f"Unknown {kind}: {content_id}"
            return
        floors = self._ask_text("Floor range", "Examples: 1-5, 8, 10+", "all")
        if floors is None:
            return
        rule = SpawnRule(content_id=content_id, floors=floors, weight=50.0, min_per_floor=0, max_per_floor=4)
        (self.definition.enemies if kind == "enemy" else self.definition.items).append(rule)
        self._changed(f"Added {catalog[content_id]}")

    # ---------- drawing ----------

    def _button(self, rect: pygame.Rect, text: str, action: str, value=None, selected: bool = False) -> None:
        assert self.screen and self.font
        pygame.draw.rect(self.screen, (64, 73, 88) if not selected else (104, 88, 52), rect, border_radius=7)
        pygame.draw.rect(self.screen, (125, 132, 145), rect, 1, border_radius=7)
        label = self.font.render(text, True, (245, 243, 235))
        self.screen.blit(label, label.get_rect(center=rect.center))
        self.hits.append(Hit(rect, action, value))

    def _field(self, y: int, label: str, value: str, action: str, payload=None) -> int:
        assert self.screen and self.font and self.font_small
        self.screen.blit(self.font_small.render(label, True, (180, 188, 200)), (48, y))
        rect = pygame.Rect(250, y - 8, 430, 38)
        pygame.draw.rect(self.screen, (37, 44, 55), rect, border_radius=6)
        pygame.draw.rect(self.screen, (92, 104, 120), rect, 1, border_radius=6)
        self.screen.blit(self.font.render(value, True, (245, 243, 235)), (rect.x + 10, rect.y + 7))
        self.hits.append(Hit(rect, action, payload))
        return y + 50

    def draw(self) -> None:
        assert self.screen and self.font and self.font_small and self.font_large
        self.hits = []
        self.screen.fill((20, 24, 31))

        pygame.draw.rect(self.screen, (31, 38, 49), (0, 0, self.screen.get_width(), 64))
        x = 14
        for tab in self.TABS:
            width = 145 if tab != "Generation" else 165
            self._button(pygame.Rect(x, 12, width, 40), tab, "tab", tab, self.tab == tab)
            x += width + 8
        self._button(pygame.Rect(self.screen.get_width() - 130, 12, 110, 40), "Save", "save")

        if self.tab == "Overview":
            self._draw_overview()
        elif self.tab == "Generation":
            self._draw_generation()
        elif self.tab == "Enemies":
            self._draw_rules("enemy")
        elif self.tab == "Items":
            self._draw_rules("item")
        elif self.tab == "Audio":
            self._draw_audio()
        else:
            self._draw_preview(full=True)

        pygame.draw.rect(self.screen, (31, 38, 49), (0, self.screen.get_height() - 36, self.screen.get_width(), 36))
        suffix = " *" if self.dirty else ""
        self.screen.blit(self.font_small.render(self.status + suffix, True, (210, 214, 220)), (16, self.screen.get_height() - 29))

    def _draw_overview(self) -> None:
        y = 105
        y = self._field(y, "Dungeon ID", self.definition.id, "edit_text", "id")
        y = self._field(y, "Display name", self.definition.name, "edit_text", "name")
        y = self._field(y, "Floor count", str(self.definition.floor_count), "edit_int", "floor_count")
        y = self._field(y, "Tileset key", self.definition.tileset, "edit_text", "tileset")
        self._draw_preview(origin=(760, 120), size=(650, 650))

    def _draw_generation(self) -> None:
        y = 105
        gen = self.definition.generation
        y = self._field(y, "Generator", str(gen.get("type", "rooms_and_corridors")), "cycle_generator")
        for key in ("width", "height"):
            y = self._field(y, key.title(), str(gen.get(key, "")), "edit_generation", key)
        if gen.get("type", "rooms_and_corridors") == "rooms_and_corridors":
            for key in ("room_count_min", "room_count_max", "room_w_min", "room_w_max", "room_h_min", "room_h_max"):
                y = self._field(y, key.replace("_", " ").title(), str(gen.get(key, "")), "edit_generation", key)
        else:
            y = self._field(y, "Margin", str(gen.get("margin", 2)), "edit_generation", "margin")
        self._draw_preview(origin=(790, 110), size=(610, 610))

    def _draw_rules(self, kind: str) -> None:
        rules = self.definition.enemies if kind == "enemy" else self.definition.items
        catalog = self.enemy_labels if kind == "enemy" else self.item_labels
        self._button(pygame.Rect(48, 92, 180, 40), f"+ Add {kind}", "add_rule", kind)
        y = 150
        for i, rule in enumerate(rules):
            rect = pygame.Rect(48, y, 720, 72)
            pygame.draw.rect(self.screen, (35, 42, 53), rect, border_radius=7)
            label = catalog.get(rule.content_id, rule.content_id)
            self.screen.blit(self.font.render(label, True, (245, 243, 235)), (62, y + 9))
            detail = f"Floors {rule.floors}   weight {rule.weight:g}   min {rule.min_per_floor}   max {rule.max_per_floor}"
            self.screen.blit(self.font_small.render(detail, True, (177, 187, 201)), (62, y + 40))
            self._button(pygame.Rect(790, y + 14, 110, 40), "Edit", "edit_rule", (kind, i))
            self._button(pygame.Rect(910, y + 14, 110, 40), "Delete", "delete_rule", (kind, i))
            y += 84

    def _draw_audio(self) -> None:
        music = self.definition.music
        y = 105
        y = self._field(y, "Default music", str(music.get("track") or "(none)"), "choose_music")
        y = self._field(y, "Music gain", f"{float(music.get('volume', 1.0)):.2f}", "edit_music_volume")
        self.screen.blit(self.font_small.render("Floor-specific tracks can be added in floor_rules JSON; the runtime already honors them.", True, (177, 187, 201)), (48, y + 10))

    def _draw_preview(self, origin=(48, 145), size=(1000, 650), full: bool = False) -> None:
        assert self.screen and self.font_small
        if full:
            self._button(pygame.Rect(48, 88, 130, 38), "Prev floor", "floor_delta", -1)
            self._button(pygame.Rect(188, 88, 130, 38), "Next floor", "floor_delta", 1)
            self._button(pygame.Rect(328, 88, 140, 38), "New seed", "new_seed")
            self._button(pygame.Rect(478, 88, 160, 38), "Play this floor", "playtest")
            origin = (48, 145)
            size = (self.screen.get_width() - 96, self.screen.get_height() - 210)

        floor = self.preview_floor
        if floor is None:
            return
        ox, oy = origin
        w, h = size
        pygame.draw.rect(self.screen, (12, 15, 20), (ox, oy, w, h), border_radius=8)
        scale = min((w - 20) / floor.width, (h - 50) / floor.height)
        px = ox + (w - floor.width * scale) / 2
        py = oy + 36 + (h - 46 - floor.height * scale) / 2
        for y in range(floor.height):
            for x in range(floor.width):
                tile = floor.tiles[y][x]
                color = (102, 97, 82) if tile.walkable else (23, 27, 34)
                if floor.stairs_pos and floor.stairs_pos.x == x and floor.stairs_pos.y == y:
                    color = (213, 181, 79)
                pygame.draw.rect(self.screen, color, (int(px + x * scale), int(py + y * scale), max(1, int(scale + 0.5)), max(1, int(scale + 0.5))))
        title = f"{self.definition.name} — floor {self.floor_number}/{self.definition.floor_count} — seed {self.seed}"
        self.screen.blit(self.font_small.render(title, True, (225, 226, 224)), (ox + 12, oy + 10))

    # ---------- events ----------

    def _handle_action(self, hit: Hit) -> None:
        action, value = hit.action, hit.value
        if action == "tab":
            self.tab = str(value)
        elif action == "save":
            self.save()
        elif action == "cycle_generator":
            self._cycle_generator()
        elif action == "edit_generation":
            self._edit_generation_value(str(value))
        elif action == "edit_text":
            current = str(getattr(self.definition, value))
            new = self._ask_text("Dungeon", str(value).replace("_", " ").title(), current)
            if new is not None and new.strip():
                setattr(self.definition, value, new.strip())
                self._changed(f"Updated {value}")
        elif action == "edit_int":
            current = int(getattr(self.definition, value))
            new = self._ask_int("Dungeon", str(value).replace("_", " ").title(), current, 1)
            if new is not None:
                setattr(self.definition, value, new)
                self._changed(f"Updated {value}")
        elif action == "add_rule":
            self._add_rule(str(value))
        elif action == "edit_rule":
            self._edit_rule(value[0], value[1])
        elif action == "delete_rule":
            rules = self.definition.enemies if value[0] == "enemy" else self.definition.items
            if 0 <= value[1] < len(rules):
                removed = rules.pop(value[1])
                self._changed(f"Removed {removed.content_id}")
        elif action == "choose_music":
            track = self._choose_music()
            if track:
                self.definition.music["track"] = track
                self._changed(f"Music: {Path(track).name}")
        elif action == "edit_music_volume":
            new = self._ask_float("Music gain", "0.0 to 1.0", float(self.definition.music.get("volume", 1.0)))
            if new is not None:
                self.definition.music["volume"] = new
                self._changed(f"Music gain: {new:.2f}")
        elif action == "floor_delta":
            self.floor_number = max(1, min(self.definition.floor_count, self.floor_number + int(value)))
            self._regenerate_preview()
        elif action == "new_seed":
            self.seed += 1
            self._regenerate_preview()
        elif action == "playtest":
            self.playtest()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for hit in reversed(self.hits):
                if hit.rect.collidepoint(event.pos):
                    self._handle_action(hit)
                    break
        elif event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            if event.key == pygame.K_ESCAPE:
                return False
            if mods & pygame.KMOD_CTRL and event.key == pygame.K_s:
                self.save()
            elif event.key == pygame.K_r:
                self.seed += 1
                self._regenerate_preview()
            elif event.key == pygame.K_F5:
                self.playtest()
        return True

    def playtest(self) -> None:
        if self.project_root is None:
            self.status = "Playtest unavailable: no project root"
            return
        self.save()
        env = os.environ.copy()
        env["MYSTERY_DUNGEON_PATH"] = str(self.path.resolve())
        env["MYSTERY_DUNGEON_PLAYTEST"] = "1"
        env["MYSTERY_DUNGEON_START_FLOOR"] = str(self.floor_number)
        try:
            subprocess.Popen([sys.executable, str(self.project_root / "run_game.py")], cwd=self.project_root, env=env)
            self.status = f"Playtest launched for floor {self.floor_number}"
        except OSError as exc:
            self.status = f"Playtest failed: {exc}"

    def run(self) -> None:
        pygame.init()
        pygame.display.set_caption("Mystery Engine — Dungeon Builder")
        self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        self.font_small = pygame.font.Font(None, 24)
        self.font = pygame.font.Font(None, 29)
        self.font_large = pygame.font.Font(None, 38)
        clock = pygame.time.Clock()
        running = True
        while running:
            clock.tick(60)
            for event in pygame.event.get():
                running = self.handle_event(event)
                if not running:
                    break
            self.draw()
            pygame.display.flip()
        pygame.quit()


def run_dungeon_builder(
    dungeon_path: Path,
    asset_root: Path,
    enemy_labels: dict[str, str],
    item_labels: dict[str, str],
    *,
    project_root: Path | None = None,
) -> None:
    dungeon_path = Path(dungeon_path)
    definition = DungeonDefinition.load(dungeon_path) if dungeon_path.exists() else DungeonDefinition.blank(dungeon_path.stem)
    DungeonBuilderEditor(
        definition,
        dungeon_path,
        asset_root,
        enemy_labels,
        item_labels,
        project_root=project_root,
    ).run()
