from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog

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
        "Move": ("action", {"action": "move_actor", "params": {"actor": "mara", "target": "marker_id"}, "wait": True}),
        "Face": ("action", {"action": "face_actor", "params": {"actor": "mara", "target": "fox"}, "wait": True}),
        "Teleport": ("action", {"action": "teleport_actor", "params": {"actor": "mara", "target": "marker_id"}, "wait": True}),
        "Actor state": ("action", {"action": "set_actor_state", "params": {"actor": "mara", "visible": True}, "wait": True}),
        "Animation": ("action", {"action": "animation", "params": {"actor": "mara", "animation": "idle"}, "wait": True}),
        "Effect": ("action", {"action": "effect", "params": {"target": "mara", "effect": "surprise"}, "wait": True}),
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

    def __init__(
        self,
        graph: StoryGraph,
        path: Path,
        *,
        project_root: Path | None = None,
        window_size: tuple[int, int] = (1600, 920),
    ) -> None:
        self.graph = graph
        self.path = Path(path)
        self.project_root = Path(project_root) if project_root else None
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
        self._button_hits: list[tuple[pygame.Rect, str, object]] = []

    # ---------- dialogs ----------

    @staticmethod
    def _root():
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return root

    def _ask(self, title: str, prompt: str, initial: str = "") -> str | None:
        root = self._root()
        try:
            return simpledialog.askstring(title, prompt, initialvalue=initial, parent=root)
        finally:
            root.destroy()

    def _edit_json(self, title: str, payload: dict) -> dict | None:
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
            node = {"type": "dialogue", "lines": [{"speaker": "Mara", "text": "New line.", "expression": "neutral"}], "next": ""}
        elif kind == "choice":
            node = {"type": "choice", "title": "Choose", "choices": [{"text": "Option", "target": ""}]}
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
            ("Effect", "add", "effect"), ("Wait", "add", "wait"), ("Parallel", "add", "parallel"),
            ("Call", "add", "call"), ("End", "add", "end"),
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
        self.screen.blit(self.font_small.render(self.graph.id, True, (172, 185, 204)), (r.x + 16, y)); y += 38

        for label, action in [("Save", "save"), ("Validate", "validate"), ("Playtest", "playtest")]:
            self._button(pygame.Rect(r.x + 16, y, 96, 34), label, action)
            y += 42

        y += 4
        if self.selected:
            self.screen.blit(self.font.render(self.selected, True, (226, 194, 94)), (r.x + 16, y)); y += 38
            for label, action in [("Edit JSON", "edit"), ("Rename", "rename"), ("Set default entry", "entry"), ("Connect…", "connect"), ("Delete", "delete")]:
                self._button(pygame.Rect(r.x + 16, y, r.w - 32, 34), label, action)
                y += 40

        y += 12
        self.screen.blit(self.font.render("Action nodes", True, (242, 240, 231)), (r.x + 16, y)); y += 34
        for label in self.ACTION_TEMPLATES:
            self._button(pygame.Rect(r.x + 16, y, r.w - 32, 30), label, "action_template", label)
            y += 34
            if y > r.bottom - 36:
                break

    # ---------- input ----------

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
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
                    return True
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
        if action == "add":
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
        try:
            subprocess.Popen([sys.executable, str(self.project_root / "run_game.py")], cwd=self.project_root, env=env)
            self.status = "Story playtest launched"
        except OSError as exc:
            self.status = f"Playtest failed: {exc}"

    def run(self) -> None:
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


def run_story_editor(path: Path, *, project_root: Path | None = None) -> None:
    path = Path(path)
    graph = StoryGraph.load(path) if path.exists() else StoryGraph.blank(path.stem)
    StoryGraphEditor(graph, path, project_root=project_root).run()
