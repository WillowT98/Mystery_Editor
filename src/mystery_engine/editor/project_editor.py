from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import pygame

from mystery_engine.project import AttackDefinitionData, EnemyDefinitionData, PawnDefinitionData, ProjectRegistry, slugify


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
            line = {
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

    SECTIONS = ("Scenes", "Stories", "Pawns", "Dungeons", "Enemies", "Attacks", "Assets")

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

    def _refresh(self) -> None:
        self.registry.reload()
        if self.section == "Scenes":
            labels = self.registry.scene_labels()
        elif self.section == "Stories":
            labels = self.registry.story_labels()
        elif self.section == "Pawns":
            labels = self.registry.pawn_labels
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
        if self.section == "Pawns":
            created = edit_pawn_dialog(self.registry)
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
        if self.section == "Pawns":
            edit_pawn_dialog(self.registry, item_id)
        elif self.section == "Stories":
            from mystery_engine.editor.story_graph import StoryGraphEditor
            graph = self.registry.load_story(item_id)
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
        elif self.section == "Dungeons":
            from mystery_engine.editor.dungeon_builder import DungeonBuilderEditor
            path = self.registry.dungeon_path(item_id)
            definition = self.registry.load_dungeon(item_id)
            editor = DungeonBuilderEditor(
                definition, path, self.registry.asset_root,
                self.registry.enemy_labels, self.item_labels,
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


def run_project_editor(
    game_root: Path,
    world_assets,
    project_root: Path,
    item_labels: dict[str, str] | None = None,
) -> None:
    ProjectEditor(ProjectRegistry.load(game_root), world_assets, project_root, item_labels).run()
