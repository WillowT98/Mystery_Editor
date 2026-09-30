from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import pygame

from mystery_engine.project import AttackDefinitionData, EnemyDefinitionData, ProjectRegistry, slugify


def _root(title: str, geometry: str = "720x760") -> tk.Tk:
    root = tk.Tk()
    root.title(title)
    root.geometry(geometry)
    root.attributes("-topmost", True)
    return root


def choose_catalog_id(title: str, labels: dict[str, str], initial: str | None = None) -> str | None:
    if not labels:
        return None
    root = _root(title, "520x150")
    result: dict[str, str | None] = {"value": None}
    tk.Label(root, text=title, anchor="w").pack(fill="x", padx=14, pady=(14, 6))
    values = [f"{label}  [{key}]" for key, label in labels.items()]
    by_display = {display: key for display, key in zip(values, labels.keys())}
    combo = ttk.Combobox(root, values=values, state="readonly")
    combo.pack(fill="x", padx=14)
    initial_display = next((d for d, key in by_display.items() if key == initial), values[0])
    combo.set(initial_display)

    def accept() -> None:
        result["value"] = by_display.get(combo.get())
        root.destroy()

    row = tk.Frame(root)
    row.pack(fill="x", padx=14, pady=14)
    tk.Button(row, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(row, text="Choose", command=accept).pack(side="right")
    root.mainloop()
    return result["value"]


def edit_attack_dialog(registry: ProjectRegistry, attack_id: str | None = None) -> str | None:
    current = registry.attacks_data.get(attack_id) if attack_id else None
    root = _root("Attack Editor", "720x720")
    result: dict[str, str | None] = {"id": None}

    frame = tk.Frame(root)
    frame.pack(fill="both", expand=True, padx=16, pady=12)
    fields: dict[str, tk.Variable] = {}

    def row_entry(label: str, key: str, value: object = "") -> None:
        r = tk.Frame(frame)
        r.pack(fill="x", pady=3)
        tk.Label(r, text=label, width=20, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value))
        fields[key] = var
        tk.Entry(r, textvariable=var).pack(side="left", fill="x", expand=True)

    row_entry("ID", "id", current.id if current else "")
    row_entry("Name", "name", current.name if current else "")
    row_entry("Description", "description", current.description if current else "")

    def combo_row(label: str, key: str, values: list[str], value: str) -> None:
        r = tk.Frame(frame)
        r.pack(fill="x", pady=3)
        tk.Label(r, text=label, width=20, anchor="w").pack(side="left")
        var = tk.StringVar(value=value)
        fields[key] = var
        ttk.Combobox(r, textvariable=var, values=values, state="readonly").pack(side="left", fill="x", expand=True)

    combo_row("Target", "target", ["enemy", "ally", "self"], current.target if current else "enemy")
    combo_row(
        "Range pattern", "range_pattern",
        ["adjacent", "two_tiles", "line", "room", "self"],
        current.range_pattern if current else "adjacent",
    )
    combo_row(
        "Damage type", "damage_type",
        [""] + registry.damage_types,
        current.damage_type or "" if current else "",
    )
    row_entry("Range", "range", current.range if current else 1)
    row_entry("Power", "power", current.power if current else 0)
    row_entry("Healing", "heal", current.heal if current else 0)
    row_entry("Accuracy %", "accuracy", round((current.accuracy if current else 1.0) * 100))
    row_entry("Charges (blank=∞)", "charges", "" if current is None or current.max_charges is None else current.max_charges)
    row_entry("Launch SFX cue", "sfx", current.sfx_cue or "" if current else "")
    row_entry("Impact SFX cue", "impact_sfx", current.impact_sfx_cue or "" if current else "")
    row_entry("Projectile key", "projectile", current.projectile_key or "" if current else "")
    row_entry("Projectile arc px", "arc", current.projectile_arc_px if current else 0)

    def save() -> None:
        try:
            ident = fields["id"].get().strip() or slugify(fields["name"].get(), "attack")
            if current is not None and ident != current.id:
                raise ValueError("IDs are stable after creation; duplicate the attack instead of changing its ID.")
            charges_text = fields["charges"].get().strip()
            data = AttackDefinitionData(
                id=ident,
                name=fields["name"].get().strip() or ident,
                description=fields["description"].get().strip(),
                target=fields["target"].get(),
                range=max(0, int(fields["range"].get())),
                power=max(0, int(fields["power"].get())),
                heal=max(0, int(fields["heal"].get())),
                damage_type=fields["damage_type"].get() or None,
                max_charges=None if not charges_text else max(0, int(charges_text)),
                accuracy=max(0.0, min(1.0, float(fields["accuracy"].get()) / 100.0)),
                sfx_cue=fields["sfx"].get().strip() or None,
                impact_sfx_cue=fields["impact_sfx"].get().strip() or None,
                projectile_key=fields["projectile"].get().strip() or None,
                projectile_arc_px=float(fields["arc"].get() or 0),
                range_pattern=fields["range_pattern"].get(),
            )
            registry.save_attack(data)
        except Exception as exc:
            messagebox.showerror("Could not save attack", str(exc), parent=root)
            return
        result["id"] = data.id
        root.destroy()

    buttons = tk.Frame(frame)
    buttons.pack(fill="x", pady=(14, 0))
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="Save Attack", command=save).pack(side="right")
    root.mainloop()
    return result["id"]


def edit_enemy_dialog(registry: ProjectRegistry, enemy_id: str | None = None) -> str | None:
    current = registry.enemies.get(enemy_id) if enemy_id else None
    root = _root("Enemy Editor", "820x860")
    result: dict[str, str | None] = {"id": None}

    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=16, pady=12)
    fields: dict[str, tk.StringVar] = {}

    def entry_row(label: str, key: str, value: object = "") -> None:
        r = tk.Frame(outer)
        r.pack(fill="x", pady=3)
        tk.Label(r, text=label, width=18, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value))
        fields[key] = var
        tk.Entry(r, textvariable=var).pack(side="left", fill="x", expand=True)

    entry_row("ID", "id", current.id if current else "")
    entry_row("Name", "name", current.name if current else "")
    entry_row("HP", "hp", current.max_hp if current else 16)
    entry_row("Attack", "attack", current.attack if current else 3)
    entry_row("Defense", "defense", current.defense if current else 2)

    sprite_row = tk.Frame(outer)
    sprite_row.pack(fill="x", pady=3)
    tk.Label(sprite_row, text="Sprite", width=18, anchor="w").pack(side="left")
    sprite_var = tk.StringVar(value=current.sprite_key if current else "")
    fields["sprite"] = sprite_var
    sprite_combo = ttk.Combobox(
        sprite_row, textvariable=sprite_var,
        values=registry.asset_keys("characters", {".png"}), state="normal",
    )
    sprite_combo.pack(side="left", fill="x", expand=True)

    def import_sprite() -> None:
        chosen = filedialog.askopenfilename(
            parent=root, title="Import enemy sprite",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not chosen:
            return
        try:
            key, _ = registry.import_asset(Path(chosen), "characters", allowed_suffixes={".png"})
        except Exception as exc:
            messagebox.showerror("Could not import sprite", str(exc), parent=root)
            return
        sprite_var.set(key)
        sprite_combo["values"] = registry.asset_keys("characters", {".png"})

    tk.Button(sprite_row, text="Import…", command=import_sprite).pack(side="left", padx=(6, 0))

    tk.Label(outer, text="Attacks", anchor="w", font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=(12, 3))
    attack_box = tk.Listbox(outer, selectmode="multiple", height=8, exportselection=False)
    attack_box.pack(fill="x")
    attack_ids = list(registry.attack_labels)
    for attack_id in attack_ids:
        attack_box.insert("end", f"{registry.attack_labels[attack_id]}  [{attack_id}]")
        if current and attack_id in current.attacks:
            attack_box.selection_set(len(attack_ids[:attack_ids.index(attack_id)+1])-1)

    def new_attack() -> None:
        created = edit_attack_dialog(registry)
        if created:
            attack_ids[:] = list(registry.attack_labels)
            attack_box.delete(0, "end")
            for aid in attack_ids:
                attack_box.insert("end", f"{registry.attack_labels[aid]}  [{aid}]")
                if current and aid in current.attacks or aid == created:
                    attack_box.selection_set("end")

    tk.Button(outer, text="+ Create Attack", command=new_attack).pack(anchor="w", pady=(4, 0))

    tk.Label(outer, text="Resistances / vulnerabilities (damage multiplier)", anchor="w",
             font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=(12, 3))
    resistance_vars: dict[str, tuple[tk.BooleanVar, tk.StringVar]] = {}
    resist_frame = tk.Frame(outer)
    resist_frame.pack(fill="x")
    for row_index, damage_type in enumerate(registry.damage_types):
        enabled = tk.BooleanVar(value=current is not None and damage_type in current.resistances)
        multiplier = tk.StringVar(value=str(current.resistances.get(damage_type, 1.0) if current else 1.0))
        resistance_vars[damage_type] = (enabled, multiplier)
        tk.Checkbutton(resist_frame, text=damage_type, variable=enabled, width=16, anchor="w").grid(row=row_index//2, column=(row_index%2)*2, sticky="w")
        tk.Entry(resist_frame, textvariable=multiplier, width=8).grid(row=row_index//2, column=(row_index%2)*2+1, sticky="w", padx=(0, 18))

    def save() -> None:
        try:
            ident = fields["id"].get().strip() or slugify(fields["name"].get(), "enemy")
            if current is not None and ident != current.id:
                raise ValueError("IDs are stable after creation; use the display name for renaming.")
            selected_attacks = tuple(attack_ids[i] for i in attack_box.curselection())
            resistances = {
                dtype: max(0.0, float(mult.get()))
                for dtype, (enabled, mult) in resistance_vars.items()
                if enabled.get()
            }
            data = EnemyDefinitionData(
                id=ident,
                name=fields["name"].get().strip() or ident,
                max_hp=max(1, int(fields["hp"].get())),
                attack=max(0, int(fields["attack"].get())),
                defense=max(0, int(fields["defense"].get())),
                sprite_key=fields["sprite"].get().strip() or ident,
                attacks=selected_attacks,
                resistances=resistances,
            )
            registry.save_enemy(data)
        except Exception as exc:
            messagebox.showerror("Could not save enemy", str(exc), parent=root)
            return
        result["id"] = data.id
        root.destroy()

    buttons = tk.Frame(outer)
    buttons.pack(fill="x", pady=(14, 0))
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="Save Enemy", command=save).pack(side="right")
    root.mainloop()
    return result["id"]


class ProjectEditor:
    """Project-level authoring shell.

    It provides one project navigation surface for scenes, dungeons, enemies,
    attacks and assets. Specialized scene/dungeon editors temporarily take over
    the same authoring process and return here when closed.
    """

    SECTIONS = ("Scenes", "Dungeons", "Enemies", "Attacks", "Assets")

    def __init__(self, registry: ProjectRegistry, world_assets, project_root: Path) -> None:
        self.registry = registry
        self.world_assets = world_assets
        self.project_root = Path(project_root)
        self.section = "Dungeons"
        self.selected = 0
        self.screen: pygame.Surface | None = None
        self.font = None
        self.font_small = None
        self.items: list[tuple[str, str]] = []
        self.status = "Ready"

    def _refresh(self) -> None:
        self.registry.reload()
        if self.section == "Scenes":
            labels = self.registry.scene_labels()
        elif self.section == "Dungeons":
            labels = self.registry.dungeon_labels()
        elif self.section == "Enemies":
            labels = self.registry.enemy_labels
        elif self.section == "Attacks":
            labels = self.registry.attack_labels
        else:
            labels = {key: key for key in self.registry.asset_keys("characters", {".png"})}
        self.items = list(labels.items())
        self.selected = max(0, min(self.selected, max(0, len(self.items) - 1)))

    def _button(self, rect: pygame.Rect, text: str, active: bool = False) -> None:
        pygame.draw.rect(self.screen, (87, 75, 48) if active else (54, 63, 78), rect, border_radius=7)
        pygame.draw.rect(self.screen, (112, 123, 140), rect, 1, border_radius=7)
        surf = self.font.render(text, True, (244, 242, 235))
        self.screen.blit(surf, surf.get_rect(center=rect.center))

    def draw(self) -> None:
        self.screen.fill((19, 23, 30))
        pygame.draw.rect(self.screen, (29, 35, 45), (0, 0, 245, self.screen.get_height()))
        title = self.font.render(self.registry.project_name, True, (247, 241, 222))
        self.screen.blit(title, (20, 20))
        for index, section in enumerate(self.SECTIONS):
            rect = pygame.Rect(18, 72 + index * 50, 209, 40)
            self._button(rect, section, self.section == section)

        x0 = 270
        heading = self.font.render(self.section, True, (247, 241, 222))
        self.screen.blit(heading, (x0, 24))
        self._button(pygame.Rect(self.screen.get_width()-300, 18, 130, 42), "+ New")
        self._button(pygame.Rect(self.screen.get_width()-155, 18, 130, 42), "Edit")

        y = 86
        for index, (item_id, label) in enumerate(self.items):
            rect = pygame.Rect(x0, y, self.screen.get_width()-x0-32, 48)
            pygame.draw.rect(self.screen, (63, 74, 91) if index == self.selected else (35, 42, 54), rect, border_radius=6)
            shown = self.font.render(label, True, (241, 240, 234))
            sub = self.font_small.render(item_id, True, (164, 176, 192))
            self.screen.blit(shown, (rect.x+12, rect.y+6))
            self.screen.blit(sub, (rect.right-sub.get_width()-12, rect.y+13))
            y += 54
            if y > self.screen.get_height()-70:
                break
        status = self.font_small.render(self.status, True, (190, 199, 211))
        self.screen.blit(status, (x0, self.screen.get_height()-30))

    def _new(self) -> None:
        if self.section == "Enemies":
            created = edit_enemy_dialog(self.registry)
            self.status = f"Created {created}" if created else "Cancelled"
        elif self.section == "Attacks":
            created = edit_attack_dialog(self.registry)
            self.status = f"Created {created}" if created else "Cancelled"
        elif self.section == "Dungeons":
            name = simpledialog.askstring("New dungeon", "Dungeon name:")
            if name:
                floors = simpledialog.askinteger("New dungeon", "Number of floors:", initialvalue=3, minvalue=1) or 3
                dungeon, _ = self.registry.create_dungeon(name, floors=floors)
                self.status = f"Created {dungeon.name}"
        elif self.section == "Scenes":
            name = simpledialog.askstring("New scene", "Scene name / ID:")
            if name:
                from mystery_engine.story import ExplorationSceneData, save_exploration_scene
                scene_id = slugify(name, "scene")
                path = self.registry.scene_dir / f"{scene_id}.json"
                if path.exists():
                    messagebox.showerror("Scene exists", f"{scene_id}.json already exists")
                else:
                    save_exploration_scene(ExplorationSceneData.blank(scene_id), path)
                    self.status = f"Created {scene_id}"
        elif self.section == "Assets":
            chosen = filedialog.askopenfilename(title="Import character sprite", filetypes=[("PNG image", "*.png")])
            if chosen:
                key, _ = self.registry.import_asset(Path(chosen), "characters", allowed_suffixes={".png"})
                self.status = f"Imported {key}"
        self._refresh()

    def _edit(self) -> None:
        if not self.items:
            return
        item_id = self.items[self.selected][0]
        if self.section == "Enemies":
            edit_enemy_dialog(self.registry, item_id)
        elif self.section == "Attacks":
            edit_attack_dialog(self.registry, item_id)
        elif self.section == "Dungeons":
            from mystery_engine.editor.dungeon_builder import DungeonBuilderEditor
            path = self.registry.dungeon_path(item_id)
            definition = self.registry.load_dungeon(item_id)
            editor = DungeonBuilderEditor(
                definition, path, self.registry.asset_root,
                self.registry.enemy_labels, {},
                project_root=self.project_root, project_registry=self.registry,
            )
            editor.run()
            self._reinit_display()
        elif self.section == "Scenes":
            from mystery_engine.editor.app import ExplorationSceneEditor
            path = self.registry.scene_paths()[item_id]
            from mystery_engine.story import load_exploration_scene
            editor = ExplorationSceneEditor(
                load_exploration_scene(path), path, self.world_assets, self.registry.asset_root,
                project_root=self.project_root, project_registry=self.registry,
            )
            editor.run()
            self._reinit_display()
        self._refresh()

    def _reinit_display(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((1500, 900), pygame.RESIZABLE)
        pygame.display.set_caption("Mystery Engine — Project Editor")
        self.font = pygame.font.Font(None, 30)
        self.font_small = pygame.font.Font(None, 23)

    def run(self) -> None:
        self._reinit_display()
        self._refresh()
        clock = pygame.time.Clock()
        running = True
        while running:
            clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for index, section in enumerate(self.SECTIONS):
                        if pygame.Rect(18, 72 + index*50, 209, 40).collidepoint(event.pos):
                            self.section = section
                            self.selected = 0
                            self._refresh()
                    if pygame.Rect(self.screen.get_width()-300, 18, 130, 42).collidepoint(event.pos):
                        self._new()
                    elif pygame.Rect(self.screen.get_width()-155, 18, 130, 42).collidepoint(event.pos):
                        self._edit()
                    else:
                        x0, y = 270, 86
                        for index in range(len(self.items)):
                            rect = pygame.Rect(x0, y + index*54, self.screen.get_width()-x0-32, 48)
                            if rect.collidepoint(event.pos):
                                self.selected = index
                                if getattr(event, "clicks", 1) >= 2:
                                    self._edit()
                                break
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        self._edit()
                    elif event.key == pygame.K_n and pygame.key.get_mods() & pygame.KMOD_CTRL:
                        self._new()
                    elif event.key == pygame.K_UP:
                        self.selected = max(0, self.selected-1)
                    elif event.key == pygame.K_DOWN:
                        self.selected = min(max(0, len(self.items)-1), self.selected+1)
            self.draw()
            pygame.display.flip()
        pygame.quit()


def run_project_editor(game_root: Path, world_assets, project_root: Path) -> None:
    ProjectEditor(ProjectRegistry.load(game_root), world_assets, project_root).run()
