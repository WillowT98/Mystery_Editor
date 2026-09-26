from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from random import Random
from typing import Any, Callable, Protocol

from mystery_engine.core.game_state import StoryState
from .dialogue import DialogueController, DialogueLine, DialogueSequence


@dataclass(frozen=True)
class ChoiceOption:
    text: str
    target: str
    enabled: bool = True
    detail: str = ""


class StoryActionHandle(Protocol):
    def update(self, dt: float) -> bool:
        """Return True when the action has completed."""
        ...

    def cancel(self) -> None: ...


@dataclass
class ImmediateAction:
    def update(self, dt: float) -> bool:
        return True

    def cancel(self) -> None:
        pass


@dataclass
class TimedAction:
    duration: float
    elapsed: float = 0.0
    on_update: Callable[[float], None] | None = None
    on_finish: Callable[[], None] | None = None

    def update(self, dt: float) -> bool:
        self.elapsed += max(0.0, dt)
        progress = 1.0 if self.duration <= 0 else min(1.0, self.elapsed / self.duration)
        if self.on_update:
            self.on_update(progress)
        if self.elapsed >= self.duration:
            if self.on_finish:
                callback, self.on_finish = self.on_finish, None
                callback()
            return True
        return False

    def cancel(self) -> None:
        self.on_finish = None


@dataclass
class StoryGraph:
    id: str
    entries: dict[str, str]
    nodes: dict[str, dict[str, Any]]
    editor: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None

    @classmethod
    def blank(cls, graph_id: str = "new_story") -> "StoryGraph":
        return cls(
            id=graph_id,
            entries={"default": "start"},
            nodes={
                "start": {
                    "type": "dialogue",
                    "lines": [{"speaker": "Mara", "text": "New dialogue.", "expression": "neutral"}],
                    "next": "end",
                },
                "end": {"type": "end"},
            },
            editor={"positions": {"start": [140, 180], "end": [520, 180]}},
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source_path: Path | None = None) -> "StoryGraph":
        nodes = {
            str(node_id): dict(payload)
            for node_id, payload in dict(data.get("nodes", {})).items()
            if isinstance(payload, dict)
        }
        entries = {str(k): str(v) for k, v in dict(data.get("entries", {"default": next(iter(nodes), "")})).items()}
        return cls(
            id=str(data.get("id") or (source_path.stem if source_path else "story")),
            entries=entries,
            nodes=nodes,
            editor=dict(data.get("editor") or {}),
            source_path=source_path,
        )

    @classmethod
    def load(cls, path: Path) -> "StoryGraph":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Story graph root must be a JSON object")
        return cls.from_dict(data, source_path=path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": 1,
            "id": self.id,
            "entries": dict(self.entries),
            "nodes": self.nodes,
            "editor": self.editor,
        }

    def save(self, path: Path | None = None) -> Path:
        target = Path(path or self.source_path or f"{self.id}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.source_path = target
        return target

    def node_position(self, node_id: str) -> tuple[float, float]:
        raw = dict(self.editor.get("positions", {})).get(node_id, [100, 100])
        try:
            return float(raw[0]), float(raw[1])
        except (TypeError, ValueError, IndexError):
            return 100.0, 100.0

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        positions = self.editor.setdefault("positions", {})
        positions[node_id] = [round(float(x), 2), round(float(y), 2)]

    def validation_issues(self) -> list[str]:
        issues: list[str] = []
        if not self.nodes:
            return ["Graph has no nodes."]
        for entry, target in self.entries.items():
            if target not in self.nodes:
                issues.append(f'Entry "{entry}" points to missing node "{target}".')

        for node_id, node in self.nodes.items():
            node_type = str(node.get("type", ""))
            if not node_type:
                issues.append(f'Node "{node_id}" has no type.')
            for label, target in self._targets(node):
                if target and target not in self.nodes:
                    issues.append(f'Node "{node_id}" {label} points to missing node "{target}".')

        roots = [v for v in self.entries.values() if v in self.nodes]
        reachable: set[str] = set()
        stack = roots[:]
        while stack:
            node_id = stack.pop()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            for _label, target in self._targets(self.nodes[node_id]):
                if target in self.nodes and target not in reachable:
                    stack.append(target)
        for node_id in self.nodes:
            if node_id not in reachable:
                issues.append(f'Node "{node_id}" is unreachable from every entry.')
        return issues

    @staticmethod
    def _targets(node: dict[str, Any]) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for key in ("next", "true", "false", "target"):
            value = node.get(key)
            if isinstance(value, str) and value:
                result.append((key, value))
        for i, choice in enumerate(node.get("choices", []) or []):
            if isinstance(choice, dict) and isinstance(choice.get("target"), str):
                result.append((f"choice {i}", str(choice["target"])))
        for i, branch in enumerate(node.get("branches", []) or []):
            if isinstance(branch, str):
                result.append((f"branch {i}", branch))
            elif isinstance(branch, dict) and isinstance(branch.get("target"), str):
                result.append((f"branch {i}", str(branch["target"])))
        return result


def evaluate_condition(condition: object, story: StoryState) -> bool:
    if condition is None:
        return True
    if isinstance(condition, bool):
        return condition
    if not isinstance(condition, dict):
        return bool(condition)

    if "all" in condition:
        return all(evaluate_condition(v, story) for v in condition.get("all", []))
    if "any" in condition:
        return any(evaluate_condition(v, story) for v in condition.get("any", []))
    if "not" in condition:
        return not evaluate_condition(condition.get("not"), story)

    kind = str(condition.get("kind", "flag"))
    name = str(condition.get("name", ""))
    op = str(condition.get("op", "==")).lower()
    expected = condition.get("value", True)

    if kind == "flag":
        actual: Any = story.flag(name)
    elif kind == "variable":
        actual = story.variables.get(name)
    elif kind == "literal":
        actual = condition.get("actual")
    else:
        actual = story.variables.get(name)

    try:
        if op in {"=", "==", "is"}:
            return actual == expected
        if op in {"!=", "is_not"}:
            return actual != expected
        if op == ">":
            return actual > expected
        if op == ">=":
            return actual >= expected
        if op == "<":
            return actual < expected
        if op == "<=":
            return actual <= expected
        if op == "in":
            return actual in expected
        if op == "contains":
            return expected in actual
        if op == "truthy":
            return bool(actual)
        if op == "falsy":
            return not bool(actual)
    except (TypeError, ValueError):
        return False
    return False


def apply_effect(effect: dict[str, Any], story: StoryState) -> None:
    kind = str(effect.get("type", "set_flag"))
    name = str(effect.get("name", ""))
    value = effect.get("value", True)
    if kind == "set_flag":
        story.set_flag(name, bool(value))
    elif kind == "toggle_flag":
        story.set_flag(name, not story.flag(name))
    elif kind == "set_variable":
        story.variables[name] = value
    elif kind == "add_variable":
        current = story.variables.get(name, 0)
        story.variables[name] = current + value
    elif kind == "multiply_variable":
        current = story.variables.get(name, 0)
        story.variables[name] = current * value
    elif kind == "delete_variable":
        story.variables.pop(name, None)


@dataclass
class StoryRuntimeContext:
    story: StoryState
    dialogue: DialogueController
    choose: Callable[[str, list[ChoiceOption], Callable[[str], None]], None]
    run_action: Callable[[str, dict[str, Any]], StoryActionHandle | None]
    load_graph: Callable[[str], StoryGraph] | None = None
    on_finish: Callable[[str | None], None] | None = None
    rng: Random = field(default_factory=Random)


@dataclass
class _Cursor:
    node_id: str | None
    state: dict[str, Any] = field(default_factory=dict)
    done: bool = False


class StoryGraphRunner:
    """Executes a data-driven conversation/cutscene graph.

    Blocking nodes retain state on their cursor. Non-blocking actions are kept as
    background handles, so walking/camera/effects can continue while dialogue or
    later graph steps run. Parallel branches use independent cursors and join at
    the parent node's `next` edge.
    """

    def __init__(self, context: StoryRuntimeContext) -> None:
        self.context = context
        self.graph: StoryGraph | None = None
        self.cursor = _Cursor(None)
        self.active = False
        self.result: str | None = None
        self.background: list[StoryActionHandle] = []
        self._step_budget = 128

    def start(self, graph: StoryGraph, entry: str = "default") -> None:
        try:
            node_id = graph.entries[entry]
        except KeyError as exc:
            raise KeyError(f'Unknown story entry "{entry}" in {graph.id}') from exc
        if node_id not in graph.nodes:
            raise KeyError(f'Entry "{entry}" points to missing node "{node_id}"')
        self.graph = graph
        self.cursor = _Cursor(node_id)
        self.active = True
        self.result = None

    def cancel(self) -> None:
        for handle in self.background:
            handle.cancel()
        self.background.clear()
        self.active = False
        self.cursor = _Cursor(None)

    def update(self, dt: float) -> None:
        # Background actions deliberately outlive the main cursor. This is what
        # lets a non-blocking walk, camera pan, or effect continue after a graph
        # reaches its end node.
        self.background = [h for h in self.background if not h.update(dt)]
        if not self.active or self.graph is None:
            return
        self._advance_cursor(self.cursor, dt, root=True)
        if self.cursor.done:
            self.active = False
            if self.context.on_finish:
                self.context.on_finish(self.result)

    def _advance_cursor(self, cursor: _Cursor, dt: float, *, root: bool) -> None:
        if cursor.done or self.graph is None:
            return

        steps = 0
        while not cursor.done and cursor.node_id is not None and steps < self._step_budget:
            steps += 1
            node = self.graph.nodes.get(cursor.node_id)
            if node is None:
                cursor.done = True
                return
            node_type = str(node.get("type", "end")).lower()

            if node_type == "dialogue":
                if not cursor.state.get("started"):
                    lines = [
                        DialogueLine(
                            speaker=str(line.get("speaker", "")),
                            text=str(line.get("text", "")),
                            portrait_key=(str(line["portrait_key"]) if line.get("portrait_key") else None),
                            expression=str(line.get("expression", "neutral")),
                        )
                        for line in node.get("lines", [])
                        if isinstance(line, dict)
                    ]
                    self.context.dialogue.start(DialogueSequence(lines))
                    cursor.state["started"] = True
                    return
                if self.context.dialogue.active:
                    return
                self._goto(cursor, node.get("next"))
                continue

            if node_type == "choice":
                selected = cursor.state.pop("selected", None)
                if selected is not None:
                    cursor.state.clear()
                    cursor.node_id = str(selected)
                    continue
                if not cursor.state.get("pending"):
                    options: list[ChoiceOption] = []
                    for raw in node.get("choices", []) or []:
                        if not isinstance(raw, dict) or not raw.get("target"):
                            continue
                        condition = raw.get("condition")
                        mode = str(raw.get("condition_mode", "hidden"))
                        allowed = evaluate_condition(condition, self.context.story)
                        if not allowed and mode == "hidden":
                            continue
                        options.append(ChoiceOption(
                            str(raw.get("text", "...")),
                            str(raw["target"]),
                            enabled=allowed,
                            detail=str(raw.get("detail", "")),
                        ))
                    if not options:
                        self._goto(cursor, node.get("next"))
                        continue

                    def choose(target: str, c=cursor) -> None:
                        c.state["selected"] = target
                        c.state["pending"] = False

                    cursor.state["pending"] = True
                    self.context.choose(str(node.get("title", "Choose")), options, choose)
                return

            if node_type == "condition":
                result = evaluate_condition(node.get("condition"), self.context.story)
                self._goto(cursor, node.get("true") if result else node.get("false"))
                continue

            if node_type == "random":
                candidates: list[tuple[str, float]] = []
                for raw in node.get("branches", []) or []:
                    if isinstance(raw, str):
                        candidates.append((raw, 1.0))
                    elif isinstance(raw, dict) and raw.get("target") and evaluate_condition(raw.get("condition"), self.context.story):
                        candidates.append((str(raw["target"]), max(0.0, float(raw.get("weight", 1.0)))))
                if not candidates or sum(weight for _target, weight in candidates) <= 0:
                    self._goto(cursor, node.get("next"))
                    continue
                target = self.context.rng.choices(
                    [target for target, _weight in candidates],
                    weights=[weight for _target, weight in candidates],
                    k=1,
                )[0]
                cursor.node_id = target
                cursor.state.clear()
                continue

            if node_type == "effect":
                for effect in node.get("effects", []) or []:
                    if isinstance(effect, dict):
                        apply_effect(effect, self.context.story)
                self._goto(cursor, node.get("next"))
                continue

            if node_type == "action":
                if "handle" not in cursor.state:
                    handle = self.context.run_action(str(node.get("action", "custom")), dict(node.get("params") or {}))
                    handle = handle or ImmediateAction()
                    if bool(node.get("wait", True)):
                        cursor.state["handle"] = handle
                    else:
                        self.background.append(handle)
                        self._goto(cursor, node.get("next"))
                        continue
                handle = cursor.state["handle"]
                if handle.update(dt):
                    self._goto(cursor, node.get("next"))
                    continue
                return

            if node_type == "wait":
                cursor.state["elapsed"] = float(cursor.state.get("elapsed", 0.0)) + max(0.0, dt)
                if cursor.state["elapsed"] >= max(0.0, float(node.get("seconds", 0.0))):
                    self._goto(cursor, node.get("next"))
                    continue
                return

            if node_type == "parallel":
                branches = cursor.state.get("branches")
                if branches is None:
                    branches = [_Cursor(str(v["target"] if isinstance(v, dict) else v)) for v in node.get("branches", []) if v]
                    cursor.state["branches"] = branches
                for branch in branches:
                    if not branch.done:
                        self._advance_cursor(branch, dt, root=False)
                mode = str(node.get("join", "all")).lower()
                completed = any(b.done for b in branches) if mode == "any" else all(b.done for b in branches)
                if completed:
                    if mode == "any":
                        for branch in branches:
                            branch.done = True
                    self._goto(cursor, node.get("next"))
                    continue
                return

            if node_type == "call":
                child = cursor.state.get("child")
                if child is None:
                    graph_name = str(node.get("graph", "")).strip()
                    child_graph = self.graph
                    if graph_name:
                        if self.context.load_graph is None:
                            self._goto(cursor, node.get("next"))
                            continue
                        child_graph = self.context.load_graph(graph_name)
                    entry = str(node.get("entry", "default"))
                    child_context = StoryRuntimeContext(
                        story=self.context.story,
                        dialogue=self.context.dialogue,
                        choose=self.context.choose,
                        run_action=self.context.run_action,
                        load_graph=self.context.load_graph,
                        rng=self.context.rng,
                    )
                    child = StoryGraphRunner(child_context)
                    child.start(child_graph, entry)
                    cursor.state["child"] = child
                child.update(dt)
                if child.active:
                    return
                self.background.extend(child.background)
                self._goto(cursor, node.get("next"))
                continue

            if node_type in {"goto", "jump"}:
                self._goto(cursor, node.get("target"))
                continue

            if node_type == "join":
                cursor.done = not root
                if root:
                    self._goto(cursor, node.get("next"))
                return

            if node_type in {"end", "return"}:
                if root:
                    self.result = str(node.get("result")) if node.get("result") is not None else None
                cursor.done = True
                cursor.node_id = None
                return

            # Unknown node types intentionally degrade into an engine action. This
            # keeps old graphs usable when a project registers a custom node/action.
            handle = self.context.run_action(node_type, dict(node.get("params") or node))
            if handle and not handle.update(dt):
                cursor.state["handle"] = handle
                return
            self._goto(cursor, node.get("next"))

        if steps >= self._step_budget:
            # A graph consisting only of immediate cyclic nodes would otherwise
            # hang the frame. Leave it active and try again next frame.
            return

    @staticmethod
    def _goto(cursor: _Cursor, target: object) -> None:
        cursor.state.clear()
        if isinstance(target, str) and target:
            cursor.node_id = target
        else:
            cursor.node_id = None
            cursor.done = True
