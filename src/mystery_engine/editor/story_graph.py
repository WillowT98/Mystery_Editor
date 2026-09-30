from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import pygame

from mystery_engine.story import StoryGraph


@dataclass
class NodeHit:
    node_id: str
    rect: pygame.Rect


class StoryGraphEditor:
    """Visual editor for dialogue/cutscene graphs.

    The canvas owns graph structure and layout. Detailed node payloads remain
    readable JSON and can be edited in a modal inspector, which keeps the first
    editor version flexible while the node vocabulary is still growing.
    """

    TOP_H = 62
    SIDE_W = 350
    STATUS_H = 32
    NODE_W = 260
    NODE_H = 128

    ACTION_TEMPLATES = {
        "Move": ("action", {"action": "move_actor", "params": {"actor": "actor_id", "target": "marker_id"}, "wait": True}),
        "Face": ("action", {"action": "face_actor", "params": {"actor": "actor_id", "target": "target_actor_id"}, "wait": True}),
        "Teleport": ("action", {"action": "teleport_actor", "params": {"actor": "mara", "target": "marker_id"}, "wait": True}),
        "Actor state": ("action", {"action": "set_actor_state", "params": {"actor": "actor_id", "visible": True}, "wait": True}),
        "Animation": ("action", {"action": "animation", "params": {"actor": "actor_id", "animation": "idle"}, "wait": True}),
        "Effect": ("action", {"action": "effect", "params": {"target": "actor_id", "effect": "surprise"}, "wait": True}),
        "Camera": ("action", {"action": "camera_pan", "params": {"target": "marker_id", "duration": 0.5}, "wait": True}),
        "Camera shake": ("action", {"action": "camera_shake", "params": {"strength": 10, "duration": 0.5}, "wait": True}),
        "Screen": ("action", {"action": "screen_fade", "params": {"color": "black", "duration": 0.4, "alpha": 1.0}, "wait": True}),
        "Banner": ("action", {"action": "banner", "params": {"text": "Location", "duration": 2.0}, "wait": True}),
        "Music": ("action", {"action": "play_music", "params": {"track": "music/track.ogg", "volume": 1.0}, "wait": False}),
        "SFX": ("action", {"action": "play_sfx", "params": {"cue": "ui.confirm"}, "wait": False}),
        "Ambience": ("action", {"action": "play_ambience", "params": {"cue": "ambience.wind", "gain": 1.0}, "wait": False}),
        "Scene": ("action", {"action": "change_scene", "params": {"scene": "scene.json", "marker": "arrival"}, "wait": True}),
        "Dungeon": ("action", {"action": "enter_dungeon", "params": {"floor": 1}, "wait": True}),
        "Custom": ("action", {"action": "custom_action", "params": {}, "wait": True}),
    }


    STRUCTURED_ACTIONS = {
        "move_actor": [
            ("actor", "Actor", "actor"),
            ("target", "Target marker / actor", "target"),
            ("speed", "Speed", "float", 180.0),
            ("tolerance", "Arrival tolerance", "float", 5.0),
            ("timeout", "Timeout (seconds)", "float", 8.0),
            ("teleport_on_fail", "Teleport if blocked", "bool", True),
            ("face_movement", "Face movement direction", "bool", True),
        ],
        "face_actor": [
            ("actor", "Actor", "actor"),
            ("target", "Face toward target", "target"),
            ("direction", "Or direction", "direction", "S"),
        ],
        "turn_actor": [
            ("actor", "Actor", "actor"),
            ("target", "Face toward target", "target"),
            ("direction", "Or direction", "direction", "S"),
        ],
        "teleport_actor": [
            ("actor", "Actor", "actor"),
            ("target", "Target marker / actor", "target"),
            ("x", "Or X coordinate", "optional_float"),
            ("y", "Or Y coordinate", "optional_float"),
        ],
        "place_actor": [
            ("actor", "Actor", "actor"),
            ("target", "Target marker / actor", "target"),
            ("x", "Or X coordinate", "optional_float"),
            ("y", "Or Y coordinate", "optional_float"),
        ],
        "set_actor_state": [
            ("actor", "Actor", "actor"),
            ("enabled", "Enabled / visible", "bool", True),
            ("sprite_key", "Sprite override", "text", ""),
        ],
        "set_object_state": [
            ("object", "Object", "object"),
            ("enabled", "Enabled", "bool", True),
        ],
        "camera_pan": [
            ("target", "Target marker / actor", "target"),
            ("x", "Or X coordinate", "optional_float"),
            ("y", "Or Y coordinate", "optional_float"),
            ("duration", "Duration (seconds)", "float", 0.5),
        ],
        "camera_to": [
            ("target", "Target marker / actor", "target"),
            ("x", "Or X coordinate", "optional_float"),
            ("y", "Or Y coordinate", "optional_float"),
            ("duration", "Duration (seconds)", "float", 0.5),
        ],
        "camera_follow": [("target", "Actor / target", "target")],
        "camera_reset": [],
        "camera_shake": [
            ("strength", "Strength", "float", 10.0),
            ("duration", "Duration (seconds)", "float", 0.5),
        ],
        "screen_fade": [
            ("color", "Color", "text", "black"),
            ("duration", "Duration (seconds)", "float", 0.4),
            ("alpha", "Final alpha (0–1)", "float", 1.0),
            ("hold", "Hold overlay", "bool", True),
        ],
        "screen_flash": [
            ("color", "Color", "text", "white"),
            ("duration", "Duration (seconds)", "float", 0.4),
            ("alpha", "Peak alpha (0–1)", "float", 1.0),
            ("hold", "Hold overlay", "bool", False),
        ],
        "banner": [
            ("text", "Text", "text", ""),
            ("duration", "Duration (seconds)", "float", 2.0),
        ],
        "title_card": [
            ("text", "Text", "text", ""),
            ("duration", "Duration (seconds)", "float", 2.0),
        ],
        "play_music": [
            ("track", "Track", "music"),
            ("volume", "Volume (0–1)", "float", 1.0),
            ("fade_ms", "Fade (ms)", "int", 350),
        ],
        "stop_music": [("fade_ms", "Fade (ms)", "int", 350)],
        "play_sfx": [
            ("cue", "SFX cue", "sfx"),
            ("gain", "Gain (0–1)", "float", 1.0),
        ],
        "play_ambience": [
            ("cue", "Ambience cue", "sfx"),
            ("gain", "Gain (0–1)", "float", 1.0),
        ],
        "stop_ambience": [],
        "change_scene": [
            ("scene", "Destination scene", "scene"),
            ("marker", "Arrival marker / door", "text", ""),
        ],
        "enter_dungeon": [("floor", "Starting floor", "int", 1)],
        "message": [("text", "Message", "text", "")],
    }

    EFFECT_TYPES = {
        "set_flag": ("Flag name", "bool"),
        "toggle_flag": ("Flag name", None),
        "set_variable": ("Variable name", "value"),
        "add_variable": ("Variable name", "number"),
        "multiply_variable": ("Variable name", "number"),
        "delete_variable": ("Variable name", None),
    }

    def __init__(
        self,
        graph: StoryGraph,
        path: Path,
        *,
        project_root: Path | None = None,
        project_registry=None,
        window_size: tuple[int, int] = (1600, 920),
    ) -> None:
        self.graph = graph
        self.path = Path(path)
        self.project_root = Path(project_root) if project_root else None
        self.project_registry = project_registry
        self.window_size = window_size
        self.screen: pygame.Surface | None = None
        self.font: pygame.font.Font | None = None
        self.font_small: pygame.font.Font | None = None
        self.font_large: pygame.font.Font | None = None

        self.selected: str | None = next(iter(graph.nodes), None)
        self.node_hits: list[NodeHit] = []
        self.dragging: str | None = None
        self.drag_offset = (0.0, 0.0)
        self.pan = [0.0, 0.0]
        self.pan_anchor: tuple[int, int] | None = None
        self.pan_start = (0.0, 0.0)
        self.connect_source: str | None = None
        self.status = "Ready"
        self.dirty = False
        self._close_application_requested = False
        self._return_to_project_requested = False
        self._button_hits: list[tuple[pygame.Rect, str, object]] = []

    # ---------- dialogs ----------

    @staticmethod
    def _root():
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return root

    def _ask(self, title: str, prompt: str, initial: str = "") -> str | None:
        from tkinter import simpledialog
        root = self._root()
        try:
            return simpledialog.askstring(title, prompt, initialvalue=initial, parent=root)
        finally:
            root.destroy()

    def _edit_json(self, title: str, payload: dict) -> dict | None:
        import tkinter as tk
        root = self._root()
        result: dict | None = None
        win = tk.Toplevel(root)
        win.title(title)
        win.geometry("760x650")
        text = tk.Text(win, wrap="none", font=("Consolas", 11))
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", json.dumps(payload, indent=2, ensure_ascii=False))
        error = tk.StringVar(value="")
        tk.Label(win, textvariable=error, fg="#aa3333").pack(fill="x", padx=10)

        def save():
            nonlocal result
            try:
                value = json.loads(text.get("1.0", "end"))
                if not isinstance(value, dict):
                    raise ValueError("Node payload must be a JSON object")
            except Exception as exc:
                error.set(str(exc))
                return
            result = value
            win.destroy()

        buttons = tk.Frame(win)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(buttons, text="Save", command=save).pack(side="right", padx=4)
        tk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=4)
        win.transient(root)
        win.grab_set()
        root.wait_window(win)
        root.destroy()
        return result

    def _scene_context(self):
        if self.project_registry is None or not self.graph.scene_id:
            return None
        try:
            from mystery_engine.story import load_exploration_scene
            path = self.project_registry.scene_paths()[self.graph.scene_id]
            return load_exploration_scene(path)
        except (KeyError, OSError, ValueError):
            return None

    def _structured_choices(self, field_type: str) -> list[str]:
        if field_type == "direction":
            return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        scene = self._scene_context()
        if field_type in {"actor", "target", "object"} and scene is not None:
            ids = [obj.id for obj in scene.objects]
            if field_type == "actor":
                ids = [
                    obj.id for obj in scene.objects
                    if self.project_registry is None
                    or self.project_registry.world_asset_catalog({}).get(obj.asset).category == "actor"
                ]
            return ids
        if field_type == "scene" and self.project_registry is not None:
            return sorted(self.project_registry.scene_paths())
        if field_type == "music" and self.project_registry is not None:
            root = Path(self.project_registry.asset_root) / "music"
            if root.exists():
                return sorted(
                    str(path.relative_to(self.project_registry.asset_root)).replace("\\", "/")
                    for path in root.iterdir()
                    if path.suffix.lower() in {".ogg", ".wav", ".mp3", ".flac"}
                )
        if field_type == "sfx" and self.project_registry is not None:
            try:
                from mystery_engine.presentation.sfx import SoundCueCatalog
                catalog = SoundCueCatalog.load(Path(self.project_registry.asset_root) / "sfx_cues.json")
                return [cue.id for cue in catalog.cues.values()]
            except Exception:
                return []
        return []

    @staticmethod
    def _coerce_structured_value(raw: str, field_type: str):
        value = raw.strip()
        if field_type == "optional_float":
            return None if not value else float(value)
        if field_type == "float":
            return float(value)
        if field_type == "int":
            return int(value)
        if field_type == "number":
            number = float(value)
            return int(number) if number.is_integer() else number
        if field_type == "bool":
            return value.lower() in {"1", "true", "yes", "on"}
        if field_type == "value":
            if value.lower() == "true":
                return True
            if value.lower() == "false":
                return False
            if value.lower() == "null":
                return None
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    def _edit_action_structured(self, node: dict) -> dict | None:
        import tkinter as tk
        from tkinter import ttk, messagebox

        root = self._root()
        win = tk.Toplevel(root)
        win.title("Edit choreography action")
        win.geometry("620x720")
        result: dict | None = None

        action_var = tk.StringVar(value=str(node.get("action", "move_actor")))
        wait_var = tk.BooleanVar(value=bool(node.get("wait", True)))
        next_var = tk.StringVar(value=str(node.get("next", "")))
        params = dict(node.get("params") or {})
        field_vars: dict[str, tuple[tk.Variable, str]] = {}

        outer = ttk.Frame(win, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Action").grid(row=0, column=0, sticky="w", pady=4)
        action_box = ttk.Combobox(
            outer,
            textvariable=action_var,
            values=sorted(self.STRUCTURED_ACTIONS),
            state="readonly",
            width=36,
        )
        action_box.grid(row=0, column=1, sticky="ew", pady=4)
        fields_frame = ttk.LabelFrame(outer, text="Parameters", padding=10)
        fields_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 8))
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        def redraw_fields(*_args):
            for child in fields_frame.winfo_children():
                child.destroy()
            field_vars.clear()
            action = action_var.get()
            for row, spec in enumerate(self.STRUCTURED_ACTIONS.get(action, [])):
                key, label, field_type, *default_tail = spec
                default = default_tail[0] if default_tail else ""
                current = params.get(key, default)
                ttk.Label(fields_frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)

                if field_type == "bool":
                    var = tk.BooleanVar(value=bool(current))
                    widget = ttk.Checkbutton(fields_frame, variable=var)
                else:
                    display = "" if current is None else str(current)
                    var = tk.StringVar(value=display)
                    choices = self._structured_choices(field_type)
                    if choices:
                        widget = ttk.Combobox(fields_frame, textvariable=var, values=choices, width=34)
                    else:
                        widget = ttk.Entry(fields_frame, textvariable=var, width=38)
                widget.grid(row=row, column=1, sticky="ew", pady=4)
                field_vars[key] = (var, field_type)
            fields_frame.columnconfigure(1, weight=1)

        action_box.bind("<<ComboboxSelected>>", redraw_fields)
        redraw_fields()

        options = ttk.Frame(outer)
        options.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Checkbutton(options, text="Wait for action to finish", variable=wait_var).pack(side="left")
        ttk.Label(outer, text="Next node").grid(row=3, column=0, sticky="w", pady=4)
        next_values = [""] + sorted(self.graph.nodes)
        ttk.Combobox(outer, textvariable=next_var, values=next_values, width=36).grid(row=3, column=1, sticky="ew", pady=4)

        def save():
            nonlocal result
            try:
                new_params: dict = {}
                for key, (var, field_type) in field_vars.items():
                    raw = str(var.get()) if field_type != "bool" else ("true" if bool(var.get()) else "false")
                    value = self._coerce_structured_value(raw, field_type)
                    if field_type == "optional_float" and value is None:
                        continue
                    if field_type in {"text", "actor", "target", "object", "scene", "music", "sfx", "direction"} and not str(value):
                        continue
                    new_params[key] = value
            except (TypeError, ValueError) as exc:
                messagebox.showerror("Invalid value", str(exc), parent=win)
                return
            result = {
                "type": "action",
                "action": action_var.get(),
                "params": new_params,
                "wait": bool(wait_var.get()),
            }
            if next_var.get().strip():
                result["next"] = next_var.get().strip()
            win.destroy()

        buttons = ttk.Frame(outer)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Advanced JSON…", command=lambda: self._structured_open_json(win, node)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="Save", command=save).pack(side="right", padx=4)
        win.transient(root)
        win.grab_set()
        root.wait_window(win)
        root.destroy()
        return result

    def _structured_open_json(self, parent, node: dict) -> None:
        parent.grab_release()
        edited = self._edit_json("Advanced action JSON", dict(node))
        if edited is not None and self.selected is not None:
            self.graph.nodes[self.selected] = edited
            self.dirty = True
            self.status = f"Updated {self.selected} via advanced JSON"
            parent.destroy()
        else:
            parent.grab_set()

    def _edit_effect_structured(self, node: dict) -> dict | None:
        import tkinter as tk
        from tkinter import ttk, messagebox

        effects = [dict(effect) for effect in node.get("effects", []) if isinstance(effect, dict)]
        if not effects:
            effects = [{"type": "set_flag", "name": "flag_name", "value": True}]

        root = self._root()
        win = tk.Toplevel(root)
        win.title("Edit story-state effects")
        win.geometry("700x560")
        result: dict | None = None

        outer = ttk.Frame(win, padding=12)
        outer.pack(fill="both", expand=True)
        listbox = tk.Listbox(outer, height=10)
        listbox.grid(row=0, column=0, rowspan=6, sticky="nsew", padx=(0, 12))
        type_var = tk.StringVar()
        name_var = tk.StringVar()
        value_var = tk.StringVar()
        next_var = tk.StringVar(value=str(node.get("next", "")))

        ttk.Label(outer, text="Effect type").grid(row=0, column=1, sticky="w")
        type_box = ttk.Combobox(outer, textvariable=type_var, values=list(self.EFFECT_TYPES), state="readonly")
        type_box.grid(row=1, column=1, sticky="ew", pady=(2, 8))
        ttk.Label(outer, text="Flag / variable name").grid(row=2, column=1, sticky="w")
        ttk.Entry(outer, textvariable=name_var).grid(row=3, column=1, sticky="ew", pady=(2, 8))
        ttk.Label(outer, text="Value").grid(row=4, column=1, sticky="w")
        value_entry = ttk.Entry(outer, textvariable=value_var)
        value_entry.grid(row=5, column=1, sticky="ew", pady=(2, 8))

        def label(effect):
            kind = str(effect.get("type", "effect"))
            name = str(effect.get("name", ""))
            if "value" in effect:
                return f"{kind}: {name} = {effect.get('value')!r}"
            return f"{kind}: {name}"

        def refresh(select=None):
            listbox.delete(0, "end")
            for effect in effects:
                listbox.insert("end", label(effect))
            if effects:
                idx = min(select if select is not None else 0, len(effects)-1)
                listbox.selection_set(idx)
                load(idx)

        def load(index=None):
            sel = listbox.curselection()
            idx = int(index if index is not None else (sel[0] if sel else 0))
            if not effects:
                return
            effect = effects[idx]
            kind = str(effect.get("type", "set_flag"))
            type_var.set(kind)
            name_var.set(str(effect.get("name", "")))
            value_var.set("" if "value" not in effect else json.dumps(effect.get("value")) if not isinstance(effect.get("value"), str) else str(effect.get("value")))
            value_entry.configure(state=("disabled" if self.EFFECT_TYPES.get(kind, ("", None))[1] is None else "normal"))

        def apply_current():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            kind = type_var.get()
            effect = {"type": kind, "name": name_var.get().strip()}
            value_type = self.EFFECT_TYPES.get(kind, ("", None))[1]
            if value_type is not None:
                try:
                    effect["value"] = self._coerce_structured_value(value_var.get(), value_type)
                except ValueError as exc:
                    messagebox.showerror("Invalid value", str(exc), parent=win)
                    return
            effects[idx] = effect
            refresh(idx)

        def add_effect():
            effects.append({"type": "set_flag", "name": "flag_name", "value": True})
            refresh(len(effects)-1)

        def remove_effect():
            sel = listbox.curselection()
            if not sel:
                return
            effects.pop(sel[0])
            if not effects:
                effects.append({"type": "set_flag", "name": "flag_name", "value": True})
            refresh(max(0, sel[0]-1))

        listbox.bind("<<ListboxSelect>>", lambda _event: load())
        type_box.bind("<<ComboboxSelected>>", lambda _event: value_entry.configure(
            state=("disabled" if self.EFFECT_TYPES.get(type_var.get(), ("", None))[1] is None else "normal")
        ))

        row = ttk.Frame(outer)
        row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Button(row, text="+ Add", command=add_effect).pack(side="left", padx=3)
        ttk.Button(row, text="Remove", command=remove_effect).pack(side="left", padx=3)
        ttk.Button(row, text="Apply fields", command=apply_current).pack(side="left", padx=3)

        ttk.Label(outer, text="Next node").grid(row=7, column=0, sticky="w", pady=(8, 2))
        ttk.Combobox(outer, textvariable=next_var, values=[""] + sorted(self.graph.nodes)).grid(row=7, column=1, sticky="ew", pady=(8, 2))
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        def save():
            nonlocal result
            apply_current()
            result = {"type": "effect", "effects": effects}
            if next_var.get().strip():
                result["next"] = next_var.get().strip()
            win.destroy()

        buttons = ttk.Frame(outer)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="Save", command=save).pack(side="right", padx=4)
        win.transient(root)
        win.grab_set()
        refresh()
        root.wait_window(win)
        root.destroy()
        return result

    # ---------- graph operations ----------

    def save(self) -> None:
        self.graph.save(self.path)
        self.dirty = False
        self.status = f"Saved {self.path.name}"

    def _new_id(self, prefix: str) -> str:
        base = prefix.lower().replace(" ", "_")
        i = 1
        candidate = base
        while candidate in self.graph.nodes:
            i += 1
            candidate = f"{base}_{i}"
        return candidate

    def add_node(self, kind: str, template: dict | None = None) -> None:
        node_id = self._new_id(kind)
        if template is not None:
            node = json.loads(json.dumps(template))
            node["type"] = kind
        elif kind == "dialogue":
            node = {"type": "dialogue", "lines": [{"id": "line_001", "speaker": "Speaker", "text": "New line.", "expression": "neutral"}], "next": ""}
        elif kind == "choice":
            node = {"type": "choice", "title": "Choose", "choices": [{"id": "choice_001", "text": "Option", "target": ""}]}
        elif kind == "condition":
            node = {"type": "condition", "condition": {"kind": "flag", "name": "flag_name", "op": "==", "value": True}, "true": "", "false": ""}
        elif kind == "random":
            node = {"type": "random", "branches": [{"target": "", "weight": 1.0}]}
        elif kind == "effect":
            node = {"type": "effect", "effects": [{"type": "set_flag", "name": "flag_name", "value": True}], "next": ""}
        elif kind == "wait":
            node = {"type": "wait", "seconds": 0.5, "next": ""}
        elif kind == "parallel":
            node = {"type": "parallel", "branches": [], "join": "all", "next": ""}
        elif kind == "call":
            node = {"type": "call", "graph": "", "entry": "default", "next": ""}
        else:
            node = {"type": kind}
        self.graph.nodes[node_id] = node
        cx = -self.pan[0] + 420 + (len(self.graph.nodes) % 4) * 40
        cy = -self.pan[1] + 180 + (len(self.graph.nodes) % 5) * 42
        self.graph.set_node_position(node_id, cx, cy)
        self.selected = node_id
        self.dirty = True
        self.status = f"Added {kind} node"

    def add_action_template(self, label: str) -> None:
        _kind, template = self.ACTION_TEMPLATES[label]
        self.add_node("action", template)

    def delete_selected(self) -> None:
        if self.selected is None or self.selected not in self.graph.nodes:
            return
        node_id = self.selected
        self.graph.nodes.pop(node_id, None)
        self.graph.editor.setdefault("positions", {}).pop(node_id, None)
        for key, value in list(self.graph.entries.items()):
            if value == node_id:
                self.graph.entries.pop(key)
        self.selected = next(iter(self.graph.nodes), None)
        self.dirty = True
        self.status = f"Deleted {node_id}"

    def edit_selected(self) -> None:
        if self.selected is None:
            return
        current = dict(self.graph.nodes[self.selected])
        if (
            str(current.get("type", "")) == "dialogue"
            and self.project_registry is not None
            and self.graph.scene_id
        ):
            try:
                from mystery_engine.story import load_exploration_scene
                from .project_editor import edit_dialogue_node_dialog
                scene_path = self.project_registry.scene_paths()[self.graph.scene_id]
                scene = load_exploration_scene(scene_path)
                if edit_dialogue_node_dialog(self.project_registry, scene, self.graph, self.selected):
                    self.dirty = True
                    self.status = f"Updated {self.selected}"
                return
            except KeyError:
                self.status = f"Story room not found: {self.graph.scene_id}"
                return
        kind = str(current.get("type", "")).lower()
        action_id = str(current.get("action", "")).lower()
        if kind == "action" and action_id in self.STRUCTURED_ACTIONS:
            edited = self._edit_action_structured(current)
        elif kind == "effect":
            edited = self._edit_effect_structured(current)
        else:
            edited = self._edit_json(f"Edit node: {self.selected}", current)
        if edited is not None:
            if "type" not in edited:
                edited["type"] = current.get("type", "action")
            self.graph.nodes[self.selected] = edited
            self.dirty = True
            self.status = f"Updated {self.selected}"

    def rename_selected(self) -> None:
        if self.selected is None:
            return
        new_id = self._ask("Rename node", "Node ID", self.selected)
        if not new_id:
            return
        new_id = new_id.strip()
        if new_id == self.selected:
            return
        if new_id in self.graph.nodes:
            self.status = f"Node {new_id} already exists"
            return
        old = self.selected
        self.graph.nodes[new_id] = self.graph.nodes.pop(old)
        positions = self.graph.editor.setdefault("positions", {})
        if old in positions:
            positions[new_id] = positions.pop(old)
        for entry, target in list(self.graph.entries.items()):
            if target == old:
                self.graph.entries[entry] = new_id
        for node in self.graph.nodes.values():
            self._replace_target(node, old, new_id)
        self.selected = new_id
        self.dirty = True
        self.status = f"Renamed {old} → {new_id}"

    @classmethod
    def _replace_target(cls, node: dict, old: str, new: str) -> None:
        for key in ("next", "true", "false", "target"):
            if node.get(key) == old:
                node[key] = new
        for raw in node.get("choices", []) or []:
            if isinstance(raw, dict) and raw.get("target") == old:
                raw["target"] = new
        for i, raw in enumerate(node.get("branches", []) or []):
            if raw == old:
                node["branches"][i] = new
            elif isinstance(raw, dict) and raw.get("target") == old:
                raw["target"] = new

    def set_default_entry(self) -> None:
        if self.selected:
            self.graph.entries["default"] = self.selected
            self.dirty = True
            self.status = f"Default entry → {self.selected}"

    def validate(self) -> None:
        issues = self.graph.validation_issues()
        from tkinter import messagebox
        root = self._root()
        try:
            if issues:
                messagebox.showwarning("Story graph validation", "\n".join(issues[:30]), parent=root)
                self.status = f"{len(issues)} validation issue(s)"
            else:
                messagebox.showinfo("Story graph validation", "No structural issues found.", parent=root)
                self.status = "Validation passed"
        finally:
            root.destroy()

    def connect(self, source: str, target: str) -> None:
        node = self.graph.nodes[source]
        kind = str(node.get("type", ""))
        if kind == "condition":
            key = "true" if not node.get("true") else "false"
            node[key] = target
        elif kind == "choice":
            choices = node.setdefault("choices", [])
            empty = next((x for x in choices if isinstance(x, dict) and not x.get("target")), None)
            if empty is not None:
                empty["target"] = target
            else:
                choices.append({"text": f"To {target}", "target": target})
        elif kind in {"random", "parallel"}:
            node.setdefault("branches", []).append({"target": target, "weight": 1.0} if kind == "random" else target)
        elif kind in {"end", "return"}:
            self.status = "End nodes do not have outgoing connections"
            return
        else:
            node["next"] = target
        self.dirty = True
        self.status = f"Connected {source} → {target}"

    # ---------- drawing ----------

    @property
    def canvas(self) -> pygame.Rect:
        assert self.screen
        return pygame.Rect(0, self.TOP_H, self.screen.get_width() - self.SIDE_W, self.screen.get_height() - self.TOP_H - self.STATUS_H)

    @property
    def sidebar(self) -> pygame.Rect:
        assert self.screen
        return pygame.Rect(self.screen.get_width() - self.SIDE_W, self.TOP_H, self.SIDE_W, self.screen.get_height() - self.TOP_H - self.STATUS_H)

    def _screen_pos(self, node_id: str) -> tuple[int, int]:
        x, y = self.graph.node_position(node_id)
        return round(x + self.pan[0]), round(y + self.pan[1] + self.TOP_H)

    def _node_rect(self, node_id: str) -> pygame.Rect:
        x, y = self._screen_pos(node_id)
        return pygame.Rect(x, y, self.NODE_W, self.NODE_H)

    def _button(self, rect: pygame.Rect, label: str, action: str, value=None) -> None:
        assert self.screen and self.font_small
        pygame.draw.rect(self.screen, (52, 62, 78), rect, border_radius=6)
        pygame.draw.rect(self.screen, (91, 105, 126), rect, 1, border_radius=6)
        surf = self.font_small.render(label, True, (242, 240, 231))
        self.screen.blit(surf, surf.get_rect(center=rect.center))
        self._button_hits.append((rect, action, value))

    def _targets(self, node: dict) -> list[tuple[str, str]]:
        return StoryGraph._targets(node)

    def draw(self) -> None:
        assert self.screen and self.font and self.font_small and self.font_large
        self.screen.fill((17, 21, 28))
        self._button_hits.clear()
        self.node_hits.clear()

        pygame.draw.rect(self.screen, (31, 38, 49), (0, 0, self.screen.get_width(), self.TOP_H))
        buttons = [
            ("Dialogue", "add", "dialogue"), ("Choice", "add", "choice"), ("Condition", "add", "condition"),
            ("Random", "add", "random"), ("Effect", "add", "effect"), ("Wait", "add", "wait"),
            ("Parallel", "add", "parallel"), ("Call", "add", "call"), ("End", "add", "end"),
        ]
        x = 10
        for label, action, value in buttons:
            w = 105 if label != "Condition" else 120
            self._button(pygame.Rect(x, 11, w, 38), label, action, value)
            x += w + 6

        pygame.draw.rect(self.screen, (24, 29, 38), self.canvas)
        pygame.draw.rect(self.screen, (28, 35, 46), self.sidebar)

        # Connections first so nodes sit on top.
        for source, node in self.graph.nodes.items():
            src = self._node_rect(source)
            for label, target in self._targets(node):
                if target not in self.graph.nodes:
                    continue
                dst = self._node_rect(target)
                start = (src.right, src.centery)
                end = (dst.left, dst.centery)
                mid = (start[0] + end[0]) // 2
                pygame.draw.line(self.screen, (102, 119, 141), start, (mid, start[1]), 2)
                pygame.draw.line(self.screen, (102, 119, 141), (mid, start[1]), (mid, end[1]), 2)
                pygame.draw.line(self.screen, (102, 119, 141), (mid, end[1]), end, 2)
                if label not in {"next", "target"}:
                    surf = self.font_small.render(label, True, (154, 168, 187))
                    self.screen.blit(surf, (mid + 4, min(start[1], end[1]) + 4))

        for node_id, node in self.graph.nodes.items():
            rect = self._node_rect(node_id)
            if not rect.colliderect(self.canvas):
                continue
            selected = node_id == self.selected
            kind = str(node.get("type", "unknown"))
            fill = (57, 67, 84) if not selected else (91, 77, 47)
            pygame.draw.rect(self.screen, fill, rect, border_radius=9)
            pygame.draw.rect(self.screen, (212, 177, 79) if selected else (112, 126, 148), rect, 2, border_radius=9)
            pygame.draw.rect(self.screen, (38, 45, 57), (rect.x, rect.y, rect.w, 30), border_radius=9)
            title = self.font_small.render(f"{node_id}  [{kind}]", True, (245, 242, 232))
            self.screen.blit(title, (rect.x + 9, rect.y + 7))
            summary = self._summary(node)
            yy = rect.y + 40
            for line in summary[:4]:
                surf = self.font_small.render(line[:36], True, (203, 209, 218))
                self.screen.blit(surf, (rect.x + 10, yy))
                yy += 21
            if node_id in self.graph.entries.values():
                badge = self.font_small.render("ENTRY", True, (226, 194, 94))
                self.screen.blit(badge, (rect.right - badge.get_width() - 8, rect.bottom - 23))
            self.node_hits.append(NodeHit(node_id, rect))

        self._draw_sidebar()
        pygame.draw.rect(self.screen, (31, 38, 49), (0, self.screen.get_height() - self.STATUS_H, self.screen.get_width(), self.STATUS_H))
        suffix = " *" if self.dirty else ""
        self.screen.blit(self.font_small.render(self.status + suffix, True, (214, 218, 224)), (14, self.screen.get_height() - 25))

    def _summary(self, node: dict) -> list[str]:
        kind = str(node.get("type", ""))
        if kind == "dialogue":
            return [f'{x.get("speaker", "")}: {x.get("text", "")}' for x in node.get("lines", []) if isinstance(x, dict)]
        if kind == "choice":
            return [f'› {x.get("text", "")}' for x in node.get("choices", []) if isinstance(x, dict)]
        if kind == "condition":
            cond = node.get("condition", {})
            return [f'if {cond.get("name", "?")} {cond.get("op", "==")} {cond.get("value", True)}']
        if kind == "effect":
            return [f'{x.get("type", "effect")} {x.get("name", "")}' for x in node.get("effects", []) if isinstance(x, dict)]
        if kind == "action":
            return [str(node.get("action", "action")), json.dumps(node.get("params", {}), ensure_ascii=False)]
        if kind == "wait":
            return [f'{node.get("seconds", 0)} seconds']
        if kind == "parallel":
            return [f'{len(node.get("branches", []))} branches', f'join: {node.get("join", "all")}']
        if kind == "call":
            return [f'{node.get("graph", "(this graph)")}::{node.get("entry", "default")}']
        if kind in {"end", "return"}:
            return [str(node.get("result", ""))]
        return [json.dumps(node, ensure_ascii=False)]

    def _draw_sidebar(self) -> None:
        assert self.screen and self.font and self.font_small and self.font_large
        r = self.sidebar
        y = r.y + 16
        title = self.font_large.render("Story Graph", True, (242, 240, 231))
        self.screen.blit(title, (r.x + 16, y)); y += 48
        self.screen.blit(self.font_small.render(self.graph.name or self.graph.id, True, (172, 185, 204)), (r.x + 16, y)); y += 24
        room_label = f"Room: {self.graph.scene_id}" if self.graph.scene_id else "Room: unbound"
        self.screen.blit(self.font_small.render(room_label, True, (150, 164, 184)), (r.x + 16, y)); y += 34

        if self.project_registry is not None:
            self._button(pygame.Rect(r.x + 16, y, r.w - 32, 34), "← Back to Project", "project")
            y += 42
        for label, action in [("Save", "save"), ("Validate", "validate"), ("Playtest", "playtest")]:
            self._button(pygame.Rect(r.x + 16, y, 96, 34), label, action)
            y += 42

        y += 4
        if self.selected:
            self.screen.blit(self.font.render(self.selected, True, (226, 194, 94)), (r.x + 16, y)); y += 38
            selected_kind = str(self.graph.nodes.get(self.selected, {}).get("type", ""))
            selected_node = self.graph.nodes.get(self.selected, {})
            action_id = str(selected_node.get("action", "")).lower()
            if selected_kind == "dialogue" and self.project_registry is not None:
                edit_label = "Edit Dialogue"
            elif selected_kind == "action" and action_id in self.STRUCTURED_ACTIONS:
                edit_label = "Edit Action"
            elif selected_kind == "effect":
                edit_label = "Edit Effects"
            else:
                edit_label = "Edit JSON"
            for label, action in [(edit_label, "edit"), ("Rename", "rename"), ("Set default entry", "entry"), ("Connect…", "connect"), ("Delete", "delete")]:
                self._button(pygame.Rect(r.x + 16, y, r.w - 32, 34), label, action)
                y += 40

        y += 12
        self.screen.blit(self.font.render("Action nodes", True, (242, 240, 231)), (r.x + 16, y)); y += 34
        labels = list(self.ACTION_TEMPLATES)
        gap = 6
        button_w = (r.w - 32 - gap) // 2
        for index, label in enumerate(labels):
            col = index % 2
            row = index // 2
            bx = r.x + 16 + col * (button_w + gap)
            by = y + row * 34
            self._button(pygame.Rect(bx, by, button_w, 30), label, "action_template", label)

    # ---------- input ----------

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            self._close_application_requested = True
            return False
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3 and self.canvas.collidepoint(event.pos):
                self.pan_anchor = event.pos
                self.pan_start = tuple(self.pan)
                return True
            if event.button != 1:
                return True
            for rect, action, value in reversed(self._button_hits):
                if rect.collidepoint(event.pos):
                    self._handle_button(action, value)
                    return not self._return_to_project_requested
            for hit in reversed(self.node_hits):
                if hit.rect.collidepoint(event.pos):
                    if self.connect_source and self.connect_source != hit.node_id:
                        self.connect(self.connect_source, hit.node_id)
                        self.connect_source = None
                    else:
                        self.selected = hit.node_id
                        self.dragging = hit.node_id
                        wx, wy = self.graph.node_position(hit.node_id)
                        sx, sy = self._screen_pos(hit.node_id)
                        self.drag_offset = (event.pos[0] - sx, event.pos[1] - sy)
                    return True
        elif event.type == pygame.MOUSEMOTION:
            if self.pan_anchor is not None:
                self.pan[0] = self.pan_start[0] + event.pos[0] - self.pan_anchor[0]
                self.pan[1] = self.pan_start[1] + event.pos[1] - self.pan_anchor[1]
            elif self.dragging:
                x = event.pos[0] - self.drag_offset[0] - self.pan[0]
                y = event.pos[1] - self.drag_offset[1] - self.pan[1] - self.TOP_H
                self.graph.set_node_position(self.dragging, x, y)
                self.dirty = True
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 3:
                self.pan_anchor = None
            if event.button == 1:
                self.dragging = None
        elif event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            if event.key == pygame.K_ESCAPE:
                if self.connect_source:
                    self.connect_source = None
                    self.status = "Connection cancelled"
                    return True
                return False
            if mods & pygame.KMOD_CTRL and event.key == pygame.K_s:
                self.save()
            elif event.key == pygame.K_DELETE:
                self.delete_selected()
            elif event.key == pygame.K_RETURN and self.selected:
                self.edit_selected()
            elif event.key == pygame.K_F5:
                self.playtest()
        return True

    def _handle_button(self, action: str, value=None) -> None:
        if action == "project":
            self._return_to_project_requested = True
        elif action == "add":
            self.add_node(str(value))
        elif action == "action_template":
            self.add_action_template(str(value))
        elif action == "save":
            self.save()
        elif action == "validate":
            self.validate()
        elif action == "playtest":
            self.playtest()
        elif action == "edit":
            self.edit_selected()
        elif action == "rename":
            self.rename_selected()
        elif action == "entry":
            self.set_default_entry()
        elif action == "delete":
            self.delete_selected()
        elif action == "connect" and self.selected:
            self.connect_source = self.selected
            self.status = f"Click destination for {self.selected}"

    def playtest(self) -> None:
        if self.project_root is None:
            self.status = "Playtest unavailable: no project root"
            return
        self.save()
        env = os.environ.copy()
        env["MYSTERY_STORY_PLAYTEST"] = "1"
        env["MYSTERY_STORY_PATH"] = str(self.path.resolve())
        if self.project_registry is not None and self.graph.scene_id:
            scene_path = self.project_registry.scene_paths().get(self.graph.scene_id)
            if scene_path is not None:
                env["MYSTERY_SCENE_PATH"] = str(scene_path.resolve())
        try:
            subprocess.Popen([sys.executable, str(self.project_root / "run_game.py")], cwd=self.project_root, env=env)
            self.status = "Story playtest launched"
        except OSError as exc:
            self.status = f"Playtest failed: {exc}"

    def run(self) -> bool:
        pygame.init()
        pygame.display.set_caption("Mystery Engine — Story Graph Editor")
        self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        self.font_small = pygame.font.Font(None, 23)
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
        return not self._close_application_requested


def run_story_editor(
    path: Path,
    *,
    project_root: Path | None = None,
    project_registry=None,
) -> None:
    path = Path(path)
    graph = StoryGraph.load(path) if path.exists() else StoryGraph.blank(path.stem)
    StoryGraphEditor(
        graph, path, project_root=project_root, project_registry=project_registry,
    ).run()
