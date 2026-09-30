from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import pygame

from mystery_engine.story import RectObstacle
from mystery_engine.project import (
    AttackDefinitionData,
    EnemyDefinitionData,
    GameSettingsData,
    ItemDefinitionData,
    PawnDefinitionData,
    PlayableCharacterDefinitionData,
    ProjectRegistry,
    TerrainDefinitionData,
    WorldObjectDefinitionData,
    slugify,
)


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

    projectile_row = tk.Frame(frame)
    projectile_row.pack(fill="x", pady=3)
    tk.Label(projectile_row, text="Projectile key", width=20, anchor="w").pack(side="left")
    projectile_var = tk.StringVar(value=current.projectile_key or "" if current else "")
    fields["projectile"] = projectile_var
    projectile_combo = ttk.Combobox(
        projectile_row, textvariable=projectile_var,
        values=[""] + registry.asset_keys("projectiles", {".png"}), state="normal",
    )
    projectile_combo.pack(side="left", fill="x", expand=True)

    def import_projectile() -> None:
        chosen = filedialog.askopenfilename(
            parent=root, title="Import projectile sprite sheet",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not chosen:
            return
        try:
            key, _ = registry.import_asset(Path(chosen), "projectiles", allowed_suffixes={".png"})
        except Exception as exc:
            messagebox.showerror("Could not import projectile", str(exc), parent=root)
            return
        projectile_var.set(key)
        projectile_combo["values"] = [""] + registry.asset_keys("projectiles", {".png"})

    tk.Button(projectile_row, text="Import…", command=import_projectile).pack(side="left", padx=(6, 0))
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


def edit_item_dialog(registry: ProjectRegistry, item_id: str | None = None) -> str | None:
    current = registry.items_data.get(item_id) if item_id else None
    root = _root("Item Editor", "760x700")
    result: dict[str, str | None] = {"id": None}
    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=16, pady=12)
    fields: dict[str, tk.StringVar] = {}

    def entry_row(label: str, key: str, value: object = "") -> None:
        row = tk.Frame(outer); row.pack(fill="x", pady=3)
        tk.Label(row, text=label, width=20, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value)); fields[key] = var
        tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)

    entry_row("ID", "id", current.id if current else "")
    entry_row("Name", "name", current.name if current else "")
    entry_row("Description", "description", current.description if current else "")
    entry_row("Heal amount", "heal", current.heal if current else 0)
    entry_row("Throw damage", "throw_damage", current.throwable_damage if current else 0)

    damage_row = tk.Frame(outer); damage_row.pack(fill="x", pady=3)
    tk.Label(damage_row, text="Damage type", width=20, anchor="w").pack(side="left")
    damage_var = tk.StringVar(value=current.damage_type or "" if current else "")
    ttk.Combobox(damage_row, textvariable=damage_var, values=[""] + registry.damage_types, state="readonly").pack(side="left", fill="x", expand=True)

    droppable = tk.BooleanVar(value=current.droppable if current else True)
    key_item = tk.BooleanVar(value=current.key_item if current else False)
    checks = tk.Frame(outer); checks.pack(fill="x", pady=6)
    tk.Checkbutton(checks, text="Droppable on defeat", variable=droppable).pack(side="left")
    tk.Checkbutton(checks, text="Key item", variable=key_item).pack(side="left", padx=(18, 0))

    sprite_row = tk.Frame(outer); sprite_row.pack(fill="x", pady=3)
    tk.Label(sprite_row, text="Ground sprite", width=20, anchor="w").pack(side="left")
    sprite_var = tk.StringVar(value=current.sprite_key or current.id if current else "")
    sprite_combo = ttk.Combobox(sprite_row, textvariable=sprite_var, values=registry.asset_keys("items", {".png"}), state="normal")
    sprite_combo.pack(side="left", fill="x", expand=True)

    def import_sprite() -> None:
        chosen = filedialog.askopenfilename(parent=root, title="Import item sprite", filetypes=[("PNG image", "*.png"), ("All files", "*.*")])
        if not chosen: return
        try:
            key, _ = registry.import_asset(Path(chosen), "items", allowed_suffixes={".png"})
        except Exception as exc:
            messagebox.showerror("Could not import sprite", str(exc), parent=root); return
        sprite_var.set(key)
        sprite_combo["values"] = registry.asset_keys("items", {".png"})

    tk.Button(sprite_row, text="Import…", command=import_sprite).pack(side="left", padx=(6, 0))

    projectile_row = tk.Frame(outer); projectile_row.pack(fill="x", pady=3)
    tk.Label(projectile_row, text="Projectile", width=20, anchor="w").pack(side="left")
    projectile_var = tk.StringVar(value=current.projectile_key or "" if current else "")
    projectile_combo = ttk.Combobox(projectile_row, textvariable=projectile_var, values=[""] + registry.asset_keys("projectiles", {".png"}), state="normal")
    projectile_combo.pack(side="left", fill="x", expand=True)

    def import_projectile() -> None:
        chosen = filedialog.askopenfilename(parent=root, title="Import projectile sheet", filetypes=[("PNG image", "*.png"), ("All files", "*.*")])
        if not chosen: return
        try:
            key, _ = registry.import_asset(Path(chosen), "projectiles", allowed_suffixes={".png"})
        except Exception as exc:
            messagebox.showerror("Could not import projectile", str(exc), parent=root); return
        projectile_var.set(key)
        projectile_combo["values"] = [""] + registry.asset_keys("projectiles", {".png"})

    tk.Button(projectile_row, text="Import…", command=import_projectile).pack(side="left", padx=(6, 0))
    entry_row("Projectile arc px", "arc", current.projectile_arc_px if current else 0)
    entry_row("Use SFX cue", "sfx", current.sfx_cue or "" if current else "")
    entry_row("Impact SFX cue", "impact_sfx", current.impact_sfx_cue or "" if current else "")

    def save() -> None:
        try:
            ident = fields["id"].get().strip() or slugify(fields["name"].get(), "item")
            if current is not None and ident != current.id:
                raise ValueError("Item IDs are stable after creation.")
            data = ItemDefinitionData(
                id=ident,
                name=fields["name"].get().strip() or ident,
                description=fields["description"].get().strip(),
                heal=max(0, int(fields["heal"].get() or 0)),
                throwable_damage=max(0, int(fields["throw_damage"].get() or 0)),
                damage_type=damage_var.get() or None,
                droppable=bool(droppable.get()),
                key_item=bool(key_item.get()),
                sfx_cue=fields["sfx"].get().strip() or None,
                impact_sfx_cue=fields["impact_sfx"].get().strip() or None,
                projectile_key=projectile_var.get().strip() or None,
                projectile_arc_px=float(fields["arc"].get() or 0),
                sprite_key=sprite_var.get().strip() or None,
            )
            registry.save_item(data)
        except Exception as exc:
            messagebox.showerror("Could not save item", str(exc), parent=root); return
        result["id"] = data.id; root.destroy()

    buttons = tk.Frame(outer); buttons.pack(fill="x", pady=(14, 0))
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="Save Item", command=save).pack(side="right")
    root.mainloop()
    return result["id"]


def edit_character_dialog(registry: ProjectRegistry, character_id: str | None = None) -> str | None:
    current = registry.characters.get(character_id) if character_id else None
    root = _root("Playable Character Editor", "820x860")
    result: dict[str, str | None] = {"id": None}
    outer = tk.Frame(root); outer.pack(fill="both", expand=True, padx=16, pady=12)
    fields: dict[str, tk.StringVar] = {}

    def entry_row(label: str, key: str, value: object = "") -> None:
        row = tk.Frame(outer); row.pack(fill="x", pady=3)
        tk.Label(row, text=label, width=18, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value)); fields[key] = var
        tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)

    entry_row("ID", "id", current.id if current else "")
    pawn_row = tk.Frame(outer); pawn_row.pack(fill="x", pady=3)
    tk.Label(pawn_row, text="Pawn", width=18, anchor="w").pack(side="left")
    pawn_ids = list(registry.pawn_labels)
    pawn_var = tk.StringVar(value=current.pawn_id if current else (pawn_ids[0] if pawn_ids else ""))
    ttk.Combobox(pawn_row, textvariable=pawn_var, values=pawn_ids, state="readonly").pack(side="left", fill="x", expand=True)

    entry_row("HP", "hp", current.max_hp if current else 30)
    entry_row("Attack", "attack", current.attack if current else 5)
    entry_row("Defense", "defense", current.defense if current else 3)

    tactic_row = tk.Frame(outer); tactic_row.pack(fill="x", pady=3)
    tk.Label(tactic_row, text="AI tactic", width=18, anchor="w").pack(side="left")
    tactic_var = tk.StringVar(value=current.ai_tactic if current else "follow")
    ttk.Combobox(tactic_row, textvariable=tactic_var, values=["follow", "attack", "protect", "conserve"], state="readonly").pack(side="left", fill="x", expand=True)

    tk.Label(outer, text="Attacks", anchor="w", font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=(10, 3))
    attack_ids = list(registry.attack_labels)
    attack_box = tk.Listbox(outer, selectmode="multiple", height=8, exportselection=False); attack_box.pack(fill="x")
    for i, aid in enumerate(attack_ids):
        attack_box.insert("end", f"{registry.attack_labels[aid]}  [{aid}]")
        if current and aid in current.attacks: attack_box.selection_set(i)

    tk.Label(outer, text="Resistances / vulnerabilities", anchor="w", font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=(10, 3))
    resistance_vars: dict[str, tuple[tk.BooleanVar, tk.StringVar]] = {}
    rf = tk.Frame(outer); rf.pack(fill="x")
    for i, dtype in enumerate(registry.damage_types):
        enabled = tk.BooleanVar(value=current is not None and dtype in current.resistances)
        mult = tk.StringVar(value=str(current.resistances.get(dtype, 1.0) if current else 1.0))
        resistance_vars[dtype] = (enabled, mult)
        tk.Checkbutton(rf, text=dtype, variable=enabled, width=14, anchor="w").grid(row=i//2, column=(i%2)*2, sticky="w")
        tk.Entry(rf, textvariable=mult, width=8).grid(row=i//2, column=(i%2)*2+1, sticky="w", padx=(0,16))

    def save() -> None:
        try:
            ident = fields["id"].get().strip() or pawn_var.get().strip() or "character"
            if current is not None and ident != current.id:
                raise ValueError("Character IDs are stable after creation.")
            if not pawn_var.get(): raise ValueError("Choose a pawn.")
            data = PlayableCharacterDefinitionData(
                id=ident,
                pawn_id=pawn_var.get(),
                max_hp=max(1, int(fields["hp"].get())),
                attack=max(0, int(fields["attack"].get())),
                defense=max(0, int(fields["defense"].get())),
                attacks=tuple(attack_ids[i] for i in attack_box.curselection()),
                resistances={dtype:max(0.0,float(mult.get())) for dtype,(enabled,mult) in resistance_vars.items() if enabled.get()},
                ai_tactic=tactic_var.get(),
            )
            registry.save_character(data)
        except Exception as exc:
            messagebox.showerror("Could not save character", str(exc), parent=root); return
        result["id"] = data.id; root.destroy()

    buttons = tk.Frame(outer); buttons.pack(fill="x", pady=(14, 0))
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8,0))
    tk.Button(buttons, text="Save Character", command=save).pack(side="right")
    root.mainloop()
    return result["id"]


def edit_game_settings_dialog(registry: ProjectRegistry) -> bool:
    current = registry.game_settings
    root = _root("Game Settings", "850x860")
    saved = {"ok": False}
    outer = tk.Frame(root); outer.pack(fill="both", expand=True, padx=16, pady=12)
    fields: dict[str, tk.StringVar] = {}

    def entry_row(label: str, key: str, value: object = "") -> None:
        row = tk.Frame(outer); row.pack(fill="x", pady=3)
        tk.Label(row, text=label, width=24, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value)); fields[key] = var
        tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)

    entry_row("Game title", "title", current.title)
    entry_row("Version", "version", current.version)

    def combo_row(label: str, var: tk.StringVar, values: list[str]) -> None:
        row = tk.Frame(outer); row.pack(fill="x", pady=3)
        tk.Label(row, text=label, width=24, anchor="w").pack(side="left")
        ttk.Combobox(row, textvariable=var, values=[""] + values, state="readonly").pack(side="left", fill="x", expand=True)

    scene_var = tk.StringVar(value=current.starting_scene or "")
    combo_row("Starting scene", scene_var, list(registry.scene_labels()))
    marker_var = tk.StringVar(value=current.starting_marker or "")
    entry_row("Starting marker (optional)", "marker", current.starting_marker or "")
    dungeon_var = tk.StringVar(value=current.default_dungeon or "")
    combo_row("Default dungeon", dungeon_var, list(registry.dungeon_labels()))

    entry_row("Bag capacity", "bag", current.bag_capacity)
    entry_row("Storage capacity", "storage", current.storage_capacity)
    entry_row("Starting carried money", "money", current.starting_carried_money)
    entry_row("Starting stored money", "stored_money", current.starting_stored_money)
    entry_row("Defeat money loss %", "money_loss", round(current.defeat_money_loss_fraction*100))
    entry_row("Defeat item loss %", "item_loss", round(current.defeat_item_loss_chance*100))

    tk.Label(outer, text="Starting party", anchor="w", font=("TkDefaultFont",10,"bold")).pack(fill="x", pady=(10,3))
    char_ids = list(registry.character_labels)
    party_box = tk.Listbox(outer, selectmode="multiple", height=6, exportselection=False); party_box.pack(fill="x")
    for i,cid in enumerate(char_ids):
        party_box.insert("end", f"{registry.character_labels[cid]}  [{cid}]")
        if cid in current.starting_party: party_box.selection_set(i)

    leader_row = tk.Frame(outer); leader_row.pack(fill="x", pady=4)
    tk.Label(leader_row, text="Leader", width=24, anchor="w").pack(side="left")
    leader_var = tk.StringVar(value=current.leader or "")
    ttk.Combobox(leader_row, textvariable=leader_var, values=[""] + char_ids, state="readonly").pack(side="left", fill="x", expand=True)

    tk.Label(outer, text="Starting items (one per line: item_id=quantity)", anchor="w", font=("TkDefaultFont",10,"bold")).pack(fill="x", pady=(10,3))
    items_text = tk.Text(outer, height=5, wrap="none"); items_text.pack(fill="x")
    items_text.insert("1.0", "\n".join(f"{k}={v}" for k,v in current.starting_items.items()))

    tk.Label(outer, text="Starting flags (one per line: flag=true/false)", anchor="w", font=("TkDefaultFont",10,"bold")).pack(fill="x", pady=(10,3))
    flags_text = tk.Text(outer, height=4, wrap="none"); flags_text.pack(fill="x")
    flags_text.insert("1.0", "\n".join(f"{k}={'true' if v else 'false'}" for k,v in current.starting_flags.items()))

    def parse_pairs(text_widget, *, boolean=False):
        result = {}
        for raw in text_widget.get("1.0","end").splitlines():
            raw=raw.strip()
            if not raw: continue
            if "=" not in raw: raise ValueError(f"Expected key=value: {raw}")
            key,value=[part.strip() for part in raw.split("=",1)]
            result[key] = value.lower() in {"true","1","yes","on"} if boolean else max(0,int(value))
        return result

    def save() -> None:
        try:
            party = tuple(char_ids[i] for i in party_box.curselection())
            leader = leader_var.get() or (party[0] if party else None)
            if leader and leader not in party: raise ValueError("Leader must be in the starting party.")
            settings = GameSettingsData(
                title=fields["title"].get().strip() or registry.project_name,
                version=fields["version"].get().strip() or "0.1.0",
                starting_scene=scene_var.get() or None,
                starting_marker=fields["marker"].get().strip() or None,
                default_dungeon=dungeon_var.get() or None,
                bag_capacity=max(1,int(fields["bag"].get())),
                storage_capacity=max(1,int(fields["storage"].get())),
                starting_carried_money=max(0,int(fields["money"].get())),
                starting_stored_money=max(0,int(fields["stored_money"].get())),
                defeat_money_loss_fraction=max(0,min(1,float(fields["money_loss"].get())/100)),
                defeat_item_loss_chance=max(0,min(1,float(fields["item_loss"].get())/100)),
                starting_party=party,
                leader=leader,
                starting_items=parse_pairs(items_text),
                starting_flags=parse_pairs(flags_text, boolean=True),
                starting_variables=current.starting_variables,
                starting_storage=current.starting_storage,
                dungeon_result_stories=current.dungeon_result_stories,
                sfx_event_cues=current.sfx_event_cues,
            )
            for iid in settings.starting_items:
                if iid not in registry.items: raise ValueError(f"Unknown starting item: {iid}")
            registry.save_game_settings(settings)
        except Exception as exc:
            messagebox.showerror("Could not save game settings", str(exc), parent=root); return
        saved["ok"]=True; root.destroy()

    buttons=tk.Frame(outer); buttons.pack(fill="x", pady=(14,0))
    tk.Button(buttons,text="Cancel",command=root.destroy).pack(side="right",padx=(8,0))
    tk.Button(buttons,text="Save Game Settings",command=save).pack(side="right")
    root.mainloop()
    return bool(saved["ok"])


def edit_terrain_dialog(registry: ProjectRegistry, terrain_id: str | None = None) -> str | None:
    current = registry.terrain.get(terrain_id) if terrain_id else None
    root = _root("Terrain Editor", "760x620")
    result: dict[str, str | None] = {"id": None}
    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=16, pady=12)

    id_var = tk.StringVar(value=current.id if current else "")
    name_var = tk.StringVar(value=current.name if current else "")
    mode_var = tk.StringVar(value=current.mode if current else "single")
    blocked_var = tk.BooleanVar(value=current.blocked if current else False)
    transparent_var = tk.BooleanVar(value=current.transparent if current else False)
    color_var = tk.StringVar(value=current.fallback_color if current else "#526f49")
    sprite_keys = list(current.sprite_keys if current else ())

    def row(label: str, var: tk.Variable) -> None:
        frame = tk.Frame(outer); frame.pack(fill="x", pady=4)
        tk.Label(frame, text=label, width=20, anchor="w").pack(side="left")
        tk.Entry(frame, textvariable=var).pack(side="left", fill="x", expand=True)

    row("ID", id_var)
    row("Name", name_var)

    mode_row = tk.Frame(outer); mode_row.pack(fill="x", pady=4)
    tk.Label(mode_row, text="Render mode", width=20, anchor="w").pack(side="left")
    ttk.Combobox(
        mode_row, textvariable=mode_var,
        values=["single", "variants", "autotile"], state="readonly",
    ).pack(side="left", fill="x", expand=True)

    blocked_row = tk.Frame(outer); blocked_row.pack(fill="x", pady=4)
    tk.Label(blocked_row, text="", width=20).pack(side="left")
    tk.Checkbutton(blocked_row, text="Blocks movement", variable=blocked_var).pack(side="left")
    tk.Checkbutton(blocked_row, text="Transparent / show scene background", variable=transparent_var).pack(side="left", padx=(18, 0))

    row("Fallback color", color_var)

    tk.Label(
        outer,
        text="Terrain images",
        anchor="w",
        font=("TkDefaultFont", 10, "bold"),
    ).pack(fill="x", pady=(14, 4))
    image_box = tk.Listbox(outer, height=8, exportselection=False)
    image_box.pack(fill="both", expand=True)

    def refresh_images() -> None:
        image_box.delete(0, "end")
        if mode_var.get() == "autotile":
            terrain_key = id_var.get().strip() or slugify(name_var.get(), "terrain")
            folder = registry.asset_root / "terrain" / terrain_key
            count = len(list(folder.glob("auto_*.png"))) if folder.exists() else 0
            image_box.insert("end", f"{count} autotile masks imported to terrain/{terrain_key}/")
        elif sprite_keys:
            for key in sprite_keys:
                image_box.insert("end", key)
        else:
            image_box.insert("end", "(no image yet; fallback color will be used)")

    def import_images() -> None:
        ident = id_var.get().strip() or slugify(name_var.get(), "terrain")
        if mode_var.get() == "autotile":
            chosen = filedialog.askdirectory(parent=root, title="Choose folder containing 000.png…255.png or auto_000.png…")
            if not chosen:
                return
            try:
                count = registry.import_terrain_autotiles(ident, Path(chosen))
            except Exception as exc:
                messagebox.showerror("Could not import autotiles", str(exc), parent=root)
                return
            messagebox.showinfo(
                "Autotiles imported",
                f"Copied {count} PNG masks. Missing masks will use the fallback color.",
                parent=root,
            )
        else:
            chosen = filedialog.askopenfilenames(
                parent=root,
                title="Choose terrain PNG" if mode_var.get() == "single" else "Choose terrain variants",
                filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
            )
            if not chosen:
                return
            if mode_var.get() == "single":
                chosen = chosen[:1]
                sprite_keys.clear()
            start_index = len(sprite_keys)
            for index, source in enumerate(chosen):
                preferred = ident if mode_var.get() == "single" else f"{ident}_{start_index+index}"
                try:
                    key, _ = registry.import_asset(
                        Path(source), "terrain", preferred_id=preferred, allowed_suffixes={".png"}
                    )
                except Exception as exc:
                    messagebox.showerror("Could not import terrain", str(exc), parent=root)
                    return
                sprite_keys.append(key)
        refresh_images()

    tk.Button(outer, text="Import terrain image(s)…", command=import_images).pack(anchor="w", pady=(5, 3))

    def import_cliffs() -> None:
        ident = id_var.get().strip() or slugify(name_var.get(), "terrain")
        chosen = filedialog.askdirectory(
            parent=root,
            title="Choose folder containing cliff masks 000.png…255.png or cliff_000.png…",
        )
        if not chosen:
            return
        try:
            count = registry.import_terrain_cliffs(ident, Path(chosen))
        except Exception as exc:
            messagebox.showerror("Could not import cliff masks", str(exc), parent=root)
            return
        messagebox.showinfo(
            "Cliff masks imported",
            f"Copied {count} cliff masks for {ident}. Missing masks fall back to the engine cliff art.",
            parent=root,
        )

    tk.Button(outer, text="Import elevation/cliff masks…", command=import_cliffs).pack(anchor="w", pady=(2, 3))
    tk.Label(
        outer,
        text=(
            "Single uses one tile everywhere. Variants randomly chooses among imported tiles. "
            "Autotile uses 8-neighbor masks; import a folder containing masks 000–255. "
            "Optional cliff masks use the same numbering and override the default elevation art. "
            "All source files are copied into the project."
        ),
        justify="left", wraplength=700, fg="#555555",
    ).pack(fill="x", pady=(3, 10))

    def save() -> None:
        try:
            ident = id_var.get().strip() or slugify(name_var.get(), "terrain")
            if current is not None and ident != current.id:
                raise ValueError("Terrain IDs are stable after creation.")
            data = TerrainDefinitionData(
                id=ident,
                name=name_var.get().strip() or ident,
                mode=mode_var.get(),
                sprite_keys=tuple(sprite_keys),
                blocked=bool(blocked_var.get()),
                fallback_color=color_var.get().strip() or "#526f49",
                transparent=bool(transparent_var.get()),
            )
            registry.save_terrain(data)
        except Exception as exc:
            messagebox.showerror("Could not save terrain", str(exc), parent=root)
            return
        result["id"] = data.id
        root.destroy()

    buttons = tk.Frame(outer); buttons.pack(fill="x", pady=(12, 0))
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="Save Terrain", command=save).pack(side="right")
    refresh_images()
    root.mainloop()
    return result["id"]


def edit_world_object_dialog(registry: ProjectRegistry, object_id: str | None = None) -> str | None:
    current = registry.objects.get(object_id) if object_id else None
    root = _root("World Object Editor", "820x820")
    result: dict[str, str | None] = {"id": None}
    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=16, pady=12)
    fields: dict[str, tk.StringVar] = {}

    def entry_row(label: str, key: str, value: object = "") -> None:
        row = tk.Frame(outer); row.pack(fill="x", pady=3)
        tk.Label(row, text=label, width=22, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value)); fields[key] = var
        tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)

    entry_row("ID", "id", current.id if current else "")
    entry_row("Display name", "name", current.name if current else "")

    cat_row = tk.Frame(outer); cat_row.pack(fill="x", pady=3)
    tk.Label(cat_row, text="Category", width=22, anchor="w").pack(side="left")
    category_var = tk.StringVar(value=current.category if current else "scenery")
    ttk.Combobox(cat_row, textvariable=category_var, values=["scenery", "interactable"], state="readonly").pack(side="left", fill="x", expand=True)

    sprite_row = tk.Frame(outer); sprite_row.pack(fill="x", pady=3)
    tk.Label(sprite_row, text="Sprite", width=22, anchor="w").pack(side="left")
    sprite_var = tk.StringVar(value=current.sprite_key or "" if current else "")
    sprite_combo = ttk.Combobox(
        sprite_row, textvariable=sprite_var,
        values=[""] + registry.asset_keys("objects", {".png"}), state="normal",
    )
    sprite_combo.pack(side="left", fill="x", expand=True)

    def import_sprite() -> None:
        chosen = filedialog.askopenfilename(
            parent=root, title="Import object sprite",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not chosen:
            return
        try:
            key, destination = registry.import_asset(Path(chosen), "objects", allowed_suffixes={".png"})
            # Use actual image dimensions as a useful authoring default when pygame can read it.
            try:
                surf = pygame.image.load(str(destination))
                fields["width"].set(str(surf.get_width()))
                fields["height"].set(str(surf.get_height()))
            except pygame.error:
                pass
        except Exception as exc:
            messagebox.showerror("Could not import object sprite", str(exc), parent=root)
            return
        sprite_var.set(key)
        sprite_combo["values"] = [""] + registry.asset_keys("objects", {".png"})

    tk.Button(sprite_row, text="Import…", command=import_sprite).pack(side="left", padx=(6, 0))

    entry_row("Display width", "width", current.width if current else 64)
    entry_row("Display height", "height", current.height if current else 64)

    anchor_row = tk.Frame(outer); anchor_row.pack(fill="x", pady=3)
    tk.Label(anchor_row, text="Anchor", width=22, anchor="w").pack(side="left")
    anchor_var = tk.StringVar(value=current.anchor if current else "bottom_center")
    ttk.Combobox(anchor_row, textvariable=anchor_var, values=["bottom_center", "center"], state="readonly").pack(side="left", fill="x", expand=True)

    draw_behind = tk.BooleanVar(value=current.draw_behind_actors if current else False)
    runtime_visible = tk.BooleanVar(value=current.runtime_visible if current else True)
    check_row = tk.Frame(outer); check_row.pack(fill="x", pady=5)
    tk.Checkbutton(check_row, text="Draw behind actors", variable=draw_behind).pack(side="left")
    tk.Checkbutton(check_row, text="Visible at runtime", variable=runtime_visible).pack(side="left", padx=(18, 0))

    tk.Label(outer, text="Default collider", anchor="w", font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=(12, 4))
    collider_enabled = tk.BooleanVar(value=current.collider_enabled if current else False)
    tk.Checkbutton(
        outer,
        text="Collider enabled by default (individual placed objects can toggle this on/off)",
        variable=collider_enabled,
    ).pack(anchor="w")

    rect = current.collision if current and isinstance(current.collision, RectObstacle) else None
    collider_frame = tk.Frame(outer); collider_frame.pack(fill="x", pady=4)
    collider_fields: dict[str, tk.StringVar] = {}
    defaults = {
        "x": rect.x if rect else -20,
        "y": rect.y if rect else -20,
        "w": rect.w if rect else 40,
        "h": rect.h if rect else 20,
    }
    for key, label in (("x", "X"), ("y", "Y"), ("w", "Width"), ("h", "Height")):
        tk.Label(collider_frame, text=label).pack(side="left", padx=(0, 4))
        var = tk.StringVar(value=str(defaults[key])); collider_fields[key] = var
        tk.Entry(collider_frame, textvariable=var, width=9).pack(side="left", padx=(0, 12))

    entry_row("Collision radius", "radius", current.collision_radius if current else 0)
    tk.Label(
        outer,
        text="The scene editor can visually resize the rectangle or convert individual placements to polygon colliders.",
        justify="left", wraplength=760, fg="#555555",
    ).pack(fill="x", pady=(0, 8))

    tk.Label(outer, text="Interaction defaults", anchor="w", font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=(8, 4))
    entry_row("Interaction label", "label", current.label or "" if current else "")
    entry_row("Legacy action ID", "action", current.action_id or "" if current else "")
    entry_row("Interact SFX cue", "sfx", current.sound_cues.get("interact", "") if current else "")
    tk.Label(
        outer,
        text="For no-code interactions, place the object in a room and assign a Story to that instance. Action ID remains for legacy/custom code hooks.",
        justify="left", wraplength=760, fg="#555555",
    ).pack(fill="x", pady=(2, 8))

    def save() -> None:
        try:
            ident = fields["id"].get().strip() or slugify(fields["name"].get(), "object")
            if current is not None and ident != current.id:
                raise ValueError("Object IDs are stable after creation.")
            collision = None
            if collider_enabled.get():
                collision = RectObstacle(
                    float(collider_fields["x"].get()),
                    float(collider_fields["y"].get()),
                    max(1.0, float(collider_fields["w"].get())),
                    max(1.0, float(collider_fields["h"].get())),
                )
            sound = fields["sfx"].get().strip()
            data = WorldObjectDefinitionData(
                id=ident,
                name=fields["name"].get().strip() or ident,
                category=category_var.get(),
                sprite_key=sprite_var.get().strip() or None,
                width=max(1, int(fields["width"].get())),
                height=max(1, int(fields["height"].get())),
                anchor=anchor_var.get(),
                collider_enabled=bool(collider_enabled.get()),
                collision=collision,
                collision_radius=max(0.0, float(fields["radius"].get() or 0)),
                draw_behind_actors=bool(draw_behind.get()),
                runtime_visible=bool(runtime_visible.get()),
                label=fields["label"].get().strip() or None,
                action_id=fields["action"].get().strip() or None,
                sound_cues=({"interact": sound} if sound else {}),
            )
            registry.save_object(data)
        except Exception as exc:
            messagebox.showerror("Could not save object", str(exc), parent=root)
            return
        result["id"] = data.id
        root.destroy()

    buttons = tk.Frame(outer); buttons.pack(fill="x", pady=(14, 0))
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="Save Object", command=save).pack(side="right")
    root.mainloop()
    return result["id"]


def edit_pawn_dialog(registry: ProjectRegistry, pawn_id: str | None = None) -> str | None:
    current = registry.pawns.get(pawn_id) if pawn_id else None
    root = _root("Pawn Editor", "760x520")
    result: dict[str, str | None] = {"id": None}
    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=16, pady=12)
    fields: dict[str, tk.StringVar] = {}

    def entry_row(label: str, key: str, value: object = "") -> None:
        row = tk.Frame(outer)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, width=18, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value))
        fields[key] = var
        tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)

    entry_row("ID", "id", current.id if current else "")
    entry_row("Name", "name", current.name if current else "")
    entry_row("Radius", "radius", current.radius if current else 28)
    entry_row("Color key", "color", current.color_key if current else "neutral")

    sprite_row = tk.Frame(outer)
    sprite_row.pack(fill="x", pady=4)
    tk.Label(sprite_row, text="World sprite", width=18, anchor="w").pack(side="left")
    sprite_var = tk.StringVar(value=current.sprite_key if current else "")
    fields["sprite"] = sprite_var
    sprite_combo = ttk.Combobox(
        sprite_row, textvariable=sprite_var,
        values=registry.asset_keys("characters", {".png"}), state="normal",
    )
    sprite_combo.pack(side="left", fill="x", expand=True)

    def import_sprite() -> None:
        chosen = filedialog.askopenfilename(
            parent=root, title="Import pawn sprite",
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

    portrait_row = tk.Frame(outer)
    portrait_row.pack(fill="x", pady=4)
    tk.Label(portrait_row, text="Dialogue portrait", width=18, anchor="w").pack(side="left")
    portrait_var = tk.StringVar(value=current.portrait_key or "" if current else "")
    fields["portrait"] = portrait_var
    portrait_combo = ttk.Combobox(
        portrait_row, textvariable=portrait_var,
        values=[""] + registry.asset_keys("portraits", {".png"}), state="normal",
    )
    portrait_combo.pack(side="left", fill="x", expand=True)

    def import_portrait() -> None:
        chosen = filedialog.askopenfilename(
            parent=root, title="Import dialogue portrait",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not chosen:
            return
        try:
            key, _ = registry.import_asset(Path(chosen), "portraits", allowed_suffixes={".png"})
        except Exception as exc:
            messagebox.showerror("Could not import portrait", str(exc), parent=root)
            return
        portrait_var.set(key)
        portrait_combo["values"] = [""] + registry.asset_keys("portraits", {".png"})

    tk.Button(portrait_row, text="Import…", command=import_portrait).pack(side="left", padx=(6, 0))

    note = (
        "A single PNG is enough for a static pawn. Directional/walk sheets with the same "
        "sprite key can be added later and the renderer will use them automatically."
    )
    tk.Label(outer, text=note, justify="left", wraplength=700, fg="#555555").pack(fill="x", pady=(14, 6))

    def save() -> None:
        try:
            ident = fields["id"].get().strip() or slugify(fields["name"].get(), "pawn")
            if current is not None and ident != current.id:
                raise ValueError("Pawn IDs are stable after creation; edit the display name instead.")
            data = PawnDefinitionData(
                id=ident,
                name=fields["name"].get().strip() or ident,
                sprite_key=fields["sprite"].get().strip() or ident,
                portrait_key=fields["portrait"].get().strip() or None,
                radius=max(1.0, float(fields["radius"].get() or 28)),
                color_key=fields["color"].get().strip() or "neutral",
            )
            registry.save_pawn(data)
        except Exception as exc:
            messagebox.showerror("Could not save pawn", str(exc), parent=root)
            return
        result["id"] = data.id
        root.destroy()

    buttons = tk.Frame(outer)
    buttons.pack(fill="x", pady=(16, 0))
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="Save Pawn", command=save).pack(side="right")
    root.mainloop()
    return result["id"]


def edit_dialogue_node_dialog(registry: ProjectRegistry, scene, graph, node_id: str) -> bool:
    node = graph.nodes.get(node_id)
    if not isinstance(node, dict) or str(node.get("type", "")) != "dialogue":
        return False

    root = _root(f"Dialogue — {node_id}", "900x680")
    working = [dict(line) for line in node.get("lines", []) if isinstance(line, dict)]
    saved = {"ok": False}

    placed_pawn_ids: list[str] = []
    for obj in scene.objects:
        if obj.asset in registry.pawns and obj.asset not in placed_pawn_ids:
            placed_pawn_ids.append(obj.asset)
    pawn_labels = {
        pawn_id: registry.pawn_labels.get(pawn_id, pawn_id)
        for pawn_id in placed_pawn_ids
    }

    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=14, pady=12)
    tk.Label(
        outer,
        text=f"Room: {scene.id}    Story: {graph.name or graph.id}",
        anchor="w",
        font=("TkDefaultFont", 10, "bold"),
    ).pack(fill="x", pady=(0, 8))

    line_box = tk.Listbox(outer, height=18, exportselection=False)
    line_box.pack(fill="both", expand=True)

    def display(line: dict) -> str:
        pawn_id = str(line.get("pawn") or "")
        speaker = pawn_labels.get(pawn_id) or str(line.get("speaker") or pawn_id or "Narrator")
        text = str(line.get("text") or "").replace("\n", " ")
        return f"{speaker}: {text}"

    def refresh(select: int | None = None) -> None:
        line_box.delete(0, "end")
        for line in working:
            line_box.insert("end", display(line))
        if working:
            index = max(0, min(select if select is not None else 0, len(working)-1))
            line_box.selection_set(index)
            line_box.see(index)

    def edit_line(index: int | None) -> None:
        current = dict(working[index]) if index is not None else {}
        win = tk.Toplevel(root)
        win.title("Edit dialogue line" if index is not None else "Add dialogue line")
        win.geometry("760x430")
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True, padx=14, pady=12)

        tk.Label(frame, text="Speaker pawn", anchor="w").pack(fill="x")
        displays = [f"{pawn_labels[p]}  [{p}]" for p in placed_pawn_ids]
        by_display = {f"{pawn_labels[p]}  [{p}]": p for p in placed_pawn_ids}
        custom_label = "Custom / narrator"
        displays.append(custom_label)
        pawn_var = tk.StringVar(value=custom_label)
        current_pawn = str(current.get("pawn") or "")
        if current_pawn in pawn_labels:
            pawn_var.set(f"{pawn_labels[current_pawn]}  [{current_pawn}]")
        pawn_combo = ttk.Combobox(frame, textvariable=pawn_var, values=displays, state="readonly")
        pawn_combo.pack(fill="x", pady=(2, 8))

        tk.Label(frame, text="Custom speaker name", anchor="w").pack(fill="x")
        speaker_var = tk.StringVar(value=str(current.get("speaker") or ""))
        tk.Entry(frame, textvariable=speaker_var).pack(fill="x", pady=(2, 8))

        tk.Label(frame, text="Dialogue", anchor="w").pack(fill="x")
        text_widget = tk.Text(frame, height=8, wrap="word")
        text_widget.pack(fill="both", expand=True, pady=(2, 8))
        text_widget.insert("1.0", str(current.get("text") or ""))

        tk.Label(frame, text="Expression", anchor="w").pack(fill="x")
        expression_var = tk.StringVar(value=str(current.get("expression") or "neutral"))
        tk.Entry(frame, textvariable=expression_var).pack(fill="x", pady=(2, 8))

        def accept() -> None:
            selected_pawn = by_display.get(pawn_var.get())
            if current.get("id"):
                line_id = str(current["id"])
            else:
                used = {str(value.get("id")) for value in working if isinstance(value, dict) and value.get("id")}
                number = 1
                line_id = f"line_{number:03d}"
                while line_id in used:
                    number += 1
                    line_id = f"line_{number:03d}"
            line = {
                "id": line_id,
                "text": text_widget.get("1.0", "end").rstrip("\n"),
                "expression": expression_var.get().strip() or "neutral",
            }
            if selected_pawn:
                line["pawn"] = selected_pawn
            else:
                line["speaker"] = speaker_var.get().strip()
            if current.get("portrait_key"):
                line["portrait_key"] = current["portrait_key"]
            if index is None:
                working.append(line)
                select = len(working)-1
            else:
                working[index] = line
                select = index
            refresh(select)
            win.destroy()

        buttons = tk.Frame(frame)
        buttons.pack(fill="x")
        tk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=(8, 0))
        tk.Button(buttons, text="OK", command=accept).pack(side="right")
        win.transient(root)
        win.grab_set()

    def selected_index() -> int | None:
        selected = line_box.curselection()
        return int(selected[0]) if selected else None

    controls = tk.Frame(outer)
    controls.pack(fill="x", pady=8)
    tk.Button(controls, text="+ Line", command=lambda: edit_line(None)).pack(side="left")
    tk.Button(controls, text="Edit", command=lambda: edit_line(selected_index()) if selected_index() is not None else None).pack(side="left", padx=5)

    def delete_line() -> None:
        index = selected_index()
        if index is None:
            return
        working.pop(index)
        refresh(min(index, len(working)-1))

    def move(delta: int) -> None:
        index = selected_index()
        if index is None:
            return
        target = index + delta
        if not 0 <= target < len(working):
            return
        working[index], working[target] = working[target], working[index]
        refresh(target)

    tk.Button(controls, text="Delete", command=delete_line).pack(side="left")
    tk.Button(controls, text="↑", command=lambda: move(-1)).pack(side="left", padx=(12, 2))
    tk.Button(controls, text="↓", command=lambda: move(1)).pack(side="left")

    next_var = tk.StringVar(value=str(node.get("next") or ""))
    next_row = tk.Frame(outer)
    next_row.pack(fill="x", pady=(0, 8))
    tk.Label(next_row, text="Next node", width=12, anchor="w").pack(side="left")
    ttk.Combobox(
        next_row, textvariable=next_var,
        values=[""] + list(graph.nodes), state="normal",
    ).pack(side="left", fill="x", expand=True)

    def save() -> None:
        node["lines"] = working
        node["next"] = next_var.get().strip()
        saved["ok"] = True
        root.destroy()

    buttons = tk.Frame(outer)
    buttons.pack(fill="x")
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="Save Dialogue", command=save).pack(side="right")
    refresh()
    root.mainloop()
    return bool(saved["ok"])


def add_locale_dialog(registry: ProjectRegistry) -> str | None:
    root = _root("Add Language", "560x250")
    result: dict[str, str | None] = {"locale": None}
    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=16, pady=14)

    tk.Label(
        outer,
        text="Add a game translation",
        anchor="w",
        font=("TkDefaultFont", 11, "bold"),
    ).pack(fill="x", pady=(0, 10))

    locale_var = tk.StringVar()
    label_var = tk.StringVar()

    for label, var, hint in (
        ("Locale code", locale_var, "Examples: fr-FR, ja-JP, de-DE, es-419"),
        ("Display name", label_var, "Example: Français"),
    ):
        row = tk.Frame(outer)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, width=16, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
        tk.Label(outer, text=hint, anchor="w", fg="#666666").pack(fill="x", padx=(112, 0))

    def accept() -> None:
        locale = locale_var.get().strip()
        if not locale:
            messagebox.showerror("Missing locale", "Enter a locale code such as fr-FR or ja-JP.", parent=root)
            return
        try:
            registry.add_locale(locale, label_var.get().strip() or locale)
        except Exception as exc:
            messagebox.showerror("Could not add language", str(exc), parent=root)
            return
        result["locale"] = locale
        root.destroy()

    buttons = tk.Frame(outer)
    buttons.pack(fill="x", pady=(18, 0))
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="Add Language", command=accept).pack(side="right")
    root.mainloop()
    return result["locale"]


def edit_localization_workspace(registry: ProjectRegistry, locale: str) -> None:
    entries = registry.localization_entries()
    loc = registry.localization
    root = _root(f"Localization — {loc.locale_label(locale)}", "1180x820")
    root.minsize(900, 650)

    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=12, pady=10)

    translated, stale, total = loc.coverage(entries, locale)
    source_locale = locale == loc.source_locale
    summary_var = tk.StringVar()
    filter_var = tk.StringVar()
    current_key: dict[str, str | None] = {"key": None}

    def update_summary() -> None:
        t, s, n = loc.coverage(entries, locale)
        if source_locale:
            summary_var.set(f"{loc.locale_label(locale)} · source language · {n} strings")
        else:
            pct = 100 if n == 0 else round((t / n) * 100)
            summary_var.set(
                f"{loc.locale_label(locale)} · {t}/{n} current ({pct}%) · "
                f"{s} stale · {max(0, n-t-s)} missing"
            )

    header = tk.Frame(outer)
    header.pack(fill="x", pady=(0, 8))
    tk.Label(header, textvariable=summary_var, anchor="w", font=("TkDefaultFont", 11, "bold")).pack(side="left", fill="x", expand=True)

    if locale != loc.default_locale:
        def make_default() -> None:
            try:
                registry.set_default_locale(locale)
            except Exception as exc:
                messagebox.showerror("Could not set default", str(exc), parent=root)
                return
            messagebox.showinfo("Default language", f"{loc.locale_label(locale)} is now the default game language.", parent=root)
        tk.Button(header, text="Set as Default", command=make_default).pack(side="right")

    search_row = tk.Frame(outer)
    search_row.pack(fill="x", pady=(0, 8))
    tk.Label(search_row, text="Filter", width=8, anchor="w").pack(side="left")
    tk.Entry(search_row, textvariable=filter_var).pack(side="left", fill="x", expand=True)

    paned = tk.PanedWindow(outer, orient="horizontal", sashrelief="raised")
    paned.pack(fill="both", expand=True)

    left = tk.Frame(paned)
    right = tk.Frame(paned)
    paned.add(left, minsize=420)
    paned.add(right, minsize=420)

    listbox = tk.Listbox(left, exportselection=False)
    listbox.pack(fill="both", expand=True)

    key_var = tk.StringVar()
    context_var = tk.StringVar()
    status_var = tk.StringVar()

    tk.Label(right, textvariable=key_var, anchor="w", font=("TkDefaultFont", 10, "bold"), wraplength=650).pack(fill="x")
    tk.Label(right, textvariable=context_var, anchor="w", fg="#555555", wraplength=650).pack(fill="x", pady=(2, 4))
    tk.Label(right, textvariable=status_var, anchor="w").pack(fill="x", pady=(0, 8))

    tk.Label(right, text=f"Source ({loc.locale_label(loc.source_locale)})", anchor="w", font=("TkDefaultFont", 10, "bold")).pack(fill="x")
    source_text = tk.Text(right, height=8, wrap="word")
    source_text.pack(fill="both", expand=True, pady=(2, 10))
    source_text.configure(state="disabled")

    tk.Label(
        right,
        text="Translation" if not source_locale else "Source text is edited in its normal content editor",
        anchor="w",
        font=("TkDefaultFont", 10, "bold"),
    ).pack(fill="x")
    translation_text = tk.Text(right, height=9, wrap="word")
    translation_text.pack(fill="both", expand=True, pady=(2, 8))
    if source_locale:
        translation_text.configure(state="disabled")

    visible_entries: list = []

    def entry_status(entry) -> str:
        return loc.status(entry, locale)

    def display_status(status: str) -> str:
        return {
            "source": "SOURCE",
            "translated": "OK",
            "stale": "STALE",
            "missing": "MISSING",
        }.get(status, status.upper())

    def refresh_list(select_key: str | None = None) -> None:
        query = filter_var.get().strip().lower()
        visible_entries.clear()
        listbox.delete(0, "end")
        for entry in entries:
            status = entry_status(entry)
            haystack = f"{entry.key} {entry.context} {entry.source} {status}".lower()
            if query and query not in haystack:
                continue
            visible_entries.append(entry)
            excerpt = entry.source.replace("\n", " ")
            if len(excerpt) > 62:
                excerpt = excerpt[:59] + "…"
            listbox.insert("end", f"[{display_status(status):7}]  {excerpt}")
        if visible_entries:
            index = 0
            if select_key:
                index = next((i for i, entry in enumerate(visible_entries) if entry.key == select_key), 0)
            listbox.selection_set(index)
            listbox.see(index)
            load_selected()
        else:
            current_key["key"] = None
            key_var.set("")
            context_var.set("")
            status_var.set("")
            source_text.configure(state="normal")
            source_text.delete("1.0", "end")
            source_text.configure(state="disabled")
            if not source_locale:
                translation_text.delete("1.0", "end")
        update_summary()

    def load_selected(_event=None) -> None:
        selected = listbox.curselection()
        if not selected or not visible_entries:
            return
        entry = visible_entries[int(selected[0])]
        current_key["key"] = entry.key
        key_var.set(entry.key)
        context_var.set(entry.context)
        status = entry_status(entry)
        status_var.set(f"Status: {display_status(status)}")

        source_text.configure(state="normal")
        source_text.delete("1.0", "end")
        source_text.insert("1.0", entry.source)
        source_text.configure(state="disabled")

        if not source_locale:
            translation_text.delete("1.0", "end")
            record = loc.load_locale(locale).get(entry.key)
            if record:
                translation_text.insert("1.0", record.text)

    def save_translation() -> None:
        if source_locale or not current_key["key"]:
            return
        entry = next((value for value in entries if value.key == current_key["key"]), None)
        if entry is None:
            return
        try:
            loc.set_translation(locale, entry, translation_text.get("1.0", "end").rstrip("\n"))
        except Exception as exc:
            messagebox.showerror("Could not save translation", str(exc), parent=root)
            return
        refresh_list(entry.key)

    listbox.bind("<<ListboxSelect>>", load_selected)
    filter_var.trace_add("write", lambda *_: refresh_list(current_key["key"]))

    actions = tk.Frame(outer)
    actions.pack(fill="x", pady=(9, 0))
    if not source_locale:
        tk.Button(actions, text="Save Translation", command=save_translation).pack(side="left")

    def export_csv() -> None:
        path = filedialog.asksaveasfilename(
            parent=root,
            title="Export translation CSV",
            defaultextension=".csv",
            initialfile=f"{registry.project_id}_{locale}.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if path:
            loc.export_csv(Path(path), locale, entries)

    def import_csv() -> None:
        path = filedialog.askopenfilename(parent=root, title="Import translation CSV", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        imported, skipped = loc.import_csv(Path(path), locale, entries)
        refresh_list(current_key["key"])
        messagebox.showinfo("Translation import", f"Imported {imported} translations; skipped {skipped}.", parent=root)

    def export_xliff() -> None:
        path = filedialog.asksaveasfilename(
            parent=root,
            title="Export XLIFF",
            defaultextension=".xlf",
            initialfile=f"{registry.project_id}_{locale}.xlf",
            filetypes=[("XLIFF", "*.xlf *.xliff")],
        )
        if path:
            loc.export_xliff(Path(path), locale, entries)

    def import_xliff() -> None:
        path = filedialog.askopenfilename(parent=root, title="Import XLIFF", filetypes=[("XLIFF", "*.xlf *.xliff"), ("All files", "*.*")])
        if not path:
            return
        imported, skipped = loc.import_xliff(Path(path), locale, entries)
        refresh_list(current_key["key"])
        messagebox.showinfo("XLIFF import", f"Imported {imported} translations; skipped {skipped}.", parent=root)

    tk.Button(actions, text="Export CSV…", command=export_csv).pack(side="left", padx=(8, 0))
    tk.Button(actions, text="Export XLIFF…", command=export_xliff).pack(side="left", padx=(6, 0))
    if not source_locale:
        tk.Button(actions, text="Import CSV…", command=import_csv).pack(side="left", padx=(18, 0))
        tk.Button(actions, text="Import XLIFF…", command=import_xliff).pack(side="left", padx=(6, 0))
    tk.Button(actions, text="Close", command=root.destroy).pack(side="right")

    update_summary()
    refresh_list()
    root.mainloop()


def edit_spawn_rule_dialog(registry: ProjectRegistry, rule) -> bool:
    root = _root("Dungeon Enemy Modifiers", "820x860")
    saved = {"ok": False}

    fields: dict[str, tk.StringVar] = {}
    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=16, pady=12)

    def entry_row(label: str, key: str, value: object = "") -> None:
        row = tk.Frame(outer)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, width=22, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(value))
        fields[key] = var
        tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)

    entry_row("Floor range", "floors", rule.floors)
    entry_row("Spawn weight", "weight", rule.weight)
    entry_row("Minimum per floor", "min", rule.min_per_floor)
    entry_row("Maximum per floor", "max", rule.max_per_floor)
    entry_row("HP %", "hp", rule.hp_percent)
    entry_row("Attack %", "attack", rule.attack_percent)
    entry_row("Defense %", "defense", rule.defense_percent)
    entry_row("Name override", "name", rule.name_override or "")

    sprite_row = tk.Frame(outer)
    sprite_row.pack(fill="x", pady=3)
    tk.Label(sprite_row, text="Sprite override", width=22, anchor="w").pack(side="left")
    sprite_var = tk.StringVar(value=rule.sprite_override or "")
    fields["sprite"] = sprite_var
    sprite_combo = ttk.Combobox(
        sprite_row, textvariable=sprite_var,
        values=[""] + registry.asset_keys("characters", {".png"}), state="normal",
    )
    sprite_combo.pack(side="left", fill="x", expand=True)

    def import_sprite() -> None:
        chosen = filedialog.askopenfilename(
            parent=root, title="Import enemy sprite override",
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
        sprite_combo["values"] = [""] + registry.asset_keys("characters", {".png"})

    tk.Button(sprite_row, text="Import…", command=import_sprite).pack(side="left", padx=(6, 0))

    tk.Label(outer, text="Resistance overrides", anchor="w",
             font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=(12, 3))
    resistance_vars: dict[str, tuple[tk.BooleanVar, tk.StringVar]] = {}
    resist_frame = tk.Frame(outer)
    resist_frame.pack(fill="x")
    for row_index, damage_type in enumerate(registry.damage_types):
        enabled = tk.BooleanVar(value=damage_type in rule.resistances)
        multiplier = tk.StringVar(value=str(rule.resistances.get(damage_type, 1.0)))
        resistance_vars[damage_type] = (enabled, multiplier)
        tk.Checkbutton(resist_frame, text=damage_type, variable=enabled, width=16, anchor="w").grid(
            row=row_index//2, column=(row_index%2)*2, sticky="w"
        )
        tk.Entry(resist_frame, textvariable=multiplier, width=8).grid(
            row=row_index//2, column=(row_index%2)*2+1, sticky="w", padx=(0, 18)
        )

    tk.Label(outer, text="Additional attacks", anchor="w",
             font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=(12, 3))
    attack_box = tk.Listbox(outer, selectmode="multiple", height=9, exportselection=False)
    attack_box.pack(fill="x")
    attack_ids = list(registry.attack_labels)
    for index, attack_id in enumerate(attack_ids):
        attack_box.insert("end", f"{registry.attack_labels[attack_id]}  [{attack_id}]")
        if attack_id in rule.extra_attacks:
            attack_box.selection_set(index)

    def new_attack() -> None:
        created = edit_attack_dialog(registry)
        if created:
            attack_ids[:] = list(registry.attack_labels)
            attack_box.delete(0, "end")
            for index, attack_id in enumerate(attack_ids):
                attack_box.insert("end", f"{registry.attack_labels[attack_id]}  [{attack_id}]")
                if attack_id in rule.extra_attacks or attack_id == created:
                    attack_box.selection_set(index)

    tk.Button(outer, text="+ Create Attack", command=new_attack).pack(anchor="w", pady=(4, 0))

    def save() -> None:
        try:
            rule.floors = fields["floors"].get().strip() or "all"
            rule.weight = max(0.0, float(fields["weight"].get()))
            rule.min_per_floor = max(0, int(fields["min"].get()))
            rule.max_per_floor = max(rule.min_per_floor, int(fields["max"].get()))
            rule.hp_percent = max(1.0, float(fields["hp"].get()))
            rule.attack_percent = max(0.0, float(fields["attack"].get()))
            rule.defense_percent = max(0.0, float(fields["defense"].get()))
            rule.name_override = fields["name"].get().strip() or None
            rule.sprite_override = fields["sprite"].get().strip() or None
            rule.resistances = {
                dtype: max(0.0, float(mult.get()))
                for dtype, (enabled, mult) in resistance_vars.items()
                if enabled.get()
            }
            rule.extra_attacks = [attack_ids[i] for i in attack_box.curselection()]
        except Exception as exc:
            messagebox.showerror("Could not save modifiers", str(exc), parent=root)
            return
        saved["ok"] = True
        root.destroy()

    buttons = tk.Frame(outer)
    buttons.pack(fill="x", pady=(14, 0))
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="Save Modifiers", command=save).pack(side="right")
    root.mainloop()
    return bool(saved["ok"])


class ProjectEditor:
    """Project-level authoring shell.

    It provides one project navigation surface for scenes, dungeons, enemies,
    attacks and assets. Specialized scene/dungeon editors temporarily take over
    the same authoring process and return here when closed.
    """

    SECTIONS = ("Game", "Scenes", "Terrain", "Stories", "Pawns", "Characters", "Objects", "Dungeons", "Enemies", "Attacks", "Items", "Localization", "Assets")

    def __init__(self, registry: ProjectRegistry, world_assets, project_root: Path, item_labels: dict[str, str] | None = None) -> None:
        self.registry = registry
        self.world_assets = world_assets
        self.project_root = Path(project_root)
        self.item_labels = dict(item_labels or {})
        self.section = "Dungeons"
        self.selected = 0
        self.screen: pygame.Surface | None = None
        self.font = None
        self.font_small = None
        self.items: list[tuple[str, str]] = []
        self.status = "Ready"
        self.file_menu_open = False

    def _switch_project(self, registry: ProjectRegistry) -> None:
        self.registry = registry
        self.item_labels = registry.item_labels
        self.section = "Game"
        self.selected = 0
        self.file_menu_open = False
        self._refresh()
        pygame.display.set_caption(f"Mystery Engine — {registry.project_name}")
        self.status = f"Opened {registry.project_name}"

    def _new_project_file(self) -> None:
        root = _root("New Game Project", "560x220")
        result: dict[str, str | None] = {"parent": None, "name": None}
        tk.Label(root, text="Create a new Mystery Engine project", font=("TkDefaultFont", 11, "bold")).pack(fill="x", padx=14, pady=(14, 8))
        name_var = tk.StringVar(value="My Game")
        row = tk.Frame(root); row.pack(fill="x", padx=14, pady=6)
        tk.Label(row, text="Project name", width=16, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=name_var).pack(side="left", fill="x", expand=True)

        def choose() -> None:
            parent = filedialog.askdirectory(parent=root, title="Choose parent folder for the new project")
            if not parent:
                return
            result["parent"] = parent
            result["name"] = name_var.get().strip() or "My Game"
            root.destroy()

        buttons = tk.Frame(root); buttons.pack(fill="x", padx=14, pady=16)
        tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
        tk.Button(buttons, text="Choose Folder & Create", command=choose).pack(side="right")
        root.mainloop()
        if not result["parent"]:
            return
        target = Path(result["parent"]) / slugify(result["name"] or "game", "game")
        if target.exists() and any(target.iterdir()):
            messagebox.showerror("Project folder exists", f"{target} already exists and is not empty.")
            return
        try:
            registry = ProjectRegistry.create_project(target, result["name"] or "My Game")
        except Exception as exc:
            messagebox.showerror("Could not create project", str(exc))
            return
        self._switch_project(registry)

    def _open_project_file(self) -> None:
        chosen = filedialog.askdirectory(title="Open Mystery Engine Project")
        if not chosen:
            return
        path = Path(chosen)
        if not (path / "project.json").exists():
            messagebox.showerror("Not a project", "The selected folder does not contain project.json.")
            return
        try:
            registry = ProjectRegistry.load(path)
        except Exception as exc:
            messagebox.showerror("Could not open project", str(exc))
            return
        self._switch_project(registry)

    def _run_project_file(self) -> None:
        runner = self.project_root / "run_game.py"
        if not runner.exists():
            self.status = "Could not find run_game.py"
            return
        try:
            subprocess.Popen([
                sys.executable,
                str(runner),
                "--project",
                str(self.registry.game_root),
            ], cwd=str(self.project_root))
            self.status = f"Running {self.registry.project_name}…"
        except Exception as exc:
            self.status = f"Could not run project: {exc}"

    def _file_action(self, action: str) -> None:
        if action == "new":
            self._new_project_file()
        elif action == "open":
            self._open_project_file()
        elif action == "run":
            self._run_project_file()
        elif action == "export":
            self.status = "Export installers/builds will be added in the packaging pass."
        self.file_menu_open = False

    def _refresh(self) -> None:
        self.registry.reload()
        if self.section == "Game":
            labels = {"settings": self.registry.game_settings.title}
        elif self.section == "Scenes":
            labels = self.registry.scene_labels()
        elif self.section == "Terrain":
            labels = self.registry.terrain_labels
        elif self.section == "Stories":
            labels = self.registry.story_labels()
        elif self.section == "Pawns":
            labels = self.registry.pawn_labels
        elif self.section == "Characters":
            labels = self.registry.character_labels
        elif self.section == "Objects":
            labels = self.registry.object_labels
        elif self.section == "Dungeons":
            labels = self.registry.dungeon_labels()
        elif self.section == "Enemies":
            labels = self.registry.enemy_labels
        elif self.section == "Attacks":
            labels = self.registry.attack_labels
        elif self.section == "Items":
            labels = self.registry.item_labels
        elif self.section == "Localization":
            entries = self.registry.localization_entries()
            labels = {}
            loc = self.registry.localization
            for locale in loc.supported_locales:
                translated, stale, total = loc.coverage(entries, locale)
                if locale == loc.source_locale:
                    suffix = f"Source · {total} strings"
                else:
                    pct = 100 if total == 0 else round((translated / total) * 100)
                    suffix = f"{pct}% · {stale} stale" if stale else f"{pct}%"
                default = " · Default" if locale == loc.default_locale else ""
                labels[locale] = f"{loc.locale_label(locale)} — {suffix}{default}"
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
        file_rect = pygame.Rect(18, 16, 70, 38)
        self._button(file_rect, "File", self.file_menu_open)
        title = self.font.render(self.registry.project_name, True, (247, 241, 222))
        self.screen.blit(title, (100, 22))
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
        if self.file_menu_open:
            menu = pygame.Rect(18, 58, 250, 178)
            pygame.draw.rect(self.screen, (31, 38, 49), menu, border_radius=7)
            pygame.draw.rect(self.screen, (112, 123, 140), menu, 1, border_radius=7)
            entries = [
                ("new", "New Project…"),
                ("open", "Open Project…"),
                ("run", "Run Project"),
                ("export", "Export…  (coming later)"),
            ]
            for index, (_key, label) in enumerate(entries):
                row = pygame.Rect(menu.x + 6, menu.y + 6 + index * 41, menu.w - 12, 36)
                pygame.draw.rect(self.screen, (48, 57, 71), row, border_radius=5)
                self.screen.blit(self.font_small.render(label, True, (240, 239, 232)), (row.x + 10, row.y + 8))

        status = self.font_small.render(self.status, True, (190, 199, 211))
        self.screen.blit(status, (x0, self.screen.get_height()-30))

    def _new(self) -> None:
        if self.section == "Game":
            edit_game_settings_dialog(self.registry)
            self.status = "Game settings updated"
        elif self.section == "Pawns":
            created = edit_pawn_dialog(self.registry)
            self.status = f"Created {created}" if created else "Cancelled"
        elif self.section == "Terrain":
            created = edit_terrain_dialog(self.registry)
            self.status = f"Created {created}" if created else "Cancelled"
        elif self.section == "Stories":
            scene_id = choose_catalog_id("Story room", self.registry.scene_labels())
            if scene_id:
                name = simpledialog.askstring("New story", "Story / scene name:")
                if name:
                    graph, _ = self.registry.create_story(name, scene_id)
                    self.status = f"Created {graph.name or graph.id}"
        elif self.section == "Enemies":
            created = edit_enemy_dialog(self.registry)
            self.status = f"Created {created}" if created else "Cancelled"
        elif self.section == "Attacks":
            created = edit_attack_dialog(self.registry)
            self.status = f"Created {created}" if created else "Cancelled"
        elif self.section == "Characters":
            created = edit_character_dialog(self.registry)
            self.status = f"Created {created}" if created else "Cancelled"
        elif self.section == "Objects":
            created = edit_world_object_dialog(self.registry)
            self.status = f"Created {created}" if created else "Cancelled"
        elif self.section == "Items":
            created = edit_item_dialog(self.registry)
            self.status = f"Created {created}" if created else "Cancelled"
        elif self.section == "Localization":
            created = add_locale_dialog(self.registry)
            self.status = f"Added {created}" if created else "Cancelled"
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
        if self.section == "Game":
            edit_game_settings_dialog(self.registry)
        elif self.section == "Pawns":
            edit_pawn_dialog(self.registry, item_id)
        elif self.section == "Terrain":
            edit_terrain_dialog(self.registry, item_id)
        elif self.section == "Stories":
            graph = self.registry.load_story(item_id)
            if graph.scene_id and graph.scene_id in self.registry.scene_paths():
                from mystery_engine.editor.app import ExplorationSceneEditor
                from mystery_engine.story import load_exploration_scene
                path = self.registry.scene_paths()[graph.scene_id]
                editor = ExplorationSceneEditor(
                    load_exploration_scene(path),
                    path,
                    self.registry.world_asset_catalog(self.world_assets),
                    self.registry.asset_root,
                    project_root=self.project_root,
                    project_registry=self.registry,
                )
                editor.mode = "story"
                editor.story_id = item_id
                editor.run()
            else:
                from mystery_engine.editor.story_graph import StoryGraphEditor
                editor = StoryGraphEditor(
                    graph, self.registry.story_path(item_id),
                    project_root=self.project_root,
                    project_registry=self.registry,
                )
                editor.run()
            self._reinit_display()
        elif self.section == "Enemies":
            edit_enemy_dialog(self.registry, item_id)
        elif self.section == "Attacks":
            edit_attack_dialog(self.registry, item_id)
        elif self.section == "Characters":
            edit_character_dialog(self.registry, item_id)
        elif self.section == "Objects":
            edit_world_object_dialog(self.registry, item_id)
        elif self.section == "Items":
            edit_item_dialog(self.registry, item_id)
        elif self.section == "Localization":
            edit_localization_workspace(self.registry, item_id)
        elif self.section == "Dungeons":
            from mystery_engine.editor.dungeon_builder import DungeonBuilderEditor
            path = self.registry.dungeon_path(item_id)
            definition = self.registry.load_dungeon(item_id)
            editor = DungeonBuilderEditor(
                definition, path, self.registry.asset_root,
                self.registry.enemy_labels, self.registry.item_labels,
                project_root=self.project_root, project_registry=self.registry,
            )
            editor.run()
            self._reinit_display()
        elif self.section == "Scenes":
            from mystery_engine.editor.app import ExplorationSceneEditor
            path = self.registry.scene_paths()[item_id]
            from mystery_engine.story import load_exploration_scene
            editor = ExplorationSceneEditor(
                load_exploration_scene(path), path,
                self.registry.world_asset_catalog(self.world_assets), self.registry.asset_root,
                project_root=self.project_root, project_registry=self.registry,
            )
            editor.run()
            self._reinit_display()
        self._refresh()

    def _reinit_display(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((1500, 900), pygame.RESIZABLE)
        pygame.display.set_caption(f"Mystery Engine — {self.registry.project_name}")
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
                    if pygame.Rect(18, 16, 70, 38).collidepoint(event.pos):
                        self.file_menu_open = not self.file_menu_open
                        continue
                    if self.file_menu_open:
                        menu = pygame.Rect(18, 58, 250, 178)
                        actions = ("new", "open", "run", "export")
                        handled = False
                        for index, action in enumerate(actions):
                            row = pygame.Rect(menu.x + 6, menu.y + 6 + index * 41, menu.w - 12, 36)
                            if row.collidepoint(event.pos):
                                self._file_action(action)
                                handled = True
                                break
                        if handled:
                            continue
                        self.file_menu_open = False
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
                        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                            self._new_project_file()
                        else:
                            self._new()
                    elif event.key == pygame.K_o and pygame.key.get_mods() & pygame.KMOD_CTRL:
                        self._open_project_file()
                    elif event.key == pygame.K_r and pygame.key.get_mods() & pygame.KMOD_CTRL:
                        self._run_project_file()
                    elif event.key == pygame.K_UP:
                        self.selected = max(0, self.selected-1)
                    elif event.key == pygame.K_DOWN:
                        self.selected = min(max(0, len(self.items)-1), self.selected+1)
            self.draw()
            pygame.display.flip()
        pygame.quit()


def run_project_editor(
    game_root: Path,
    world_assets,
    project_root: Path,
    item_labels: dict[str, str] | None = None,
) -> None:
    registry = ProjectRegistry.load(game_root)
    ProjectEditor(registry, world_assets, project_root, registry.item_labels).run()
