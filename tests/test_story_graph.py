from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mystery_engine.core.game_state import StoryState
from mystery_engine.story import (
    DialogueController,
    ImmediateAction,
    StoryGraph,
    StoryGraphRunner,
    StoryRuntimeContext,
    TimedAction,
    evaluate_condition,
)


def _context(story=None):
    story = story or StoryState()
    dialogue = DialogueController()
    choices = []
    actions = []

    def choose(title, options, callback):
        choices.append((title, options, callback))

    def run_action(name, params):
        actions.append((name, params))
        return ImmediateAction()

    return StoryRuntimeContext(story, dialogue, choose, run_action), choices, actions


def test_condition_language_handles_flags_variables_and_boolean_groups():
    story = StoryState(flags={"done": True}, variables={"trust": 3})
    assert evaluate_condition({"kind": "flag", "name": "done", "op": "==", "value": True}, story)
    assert evaluate_condition({"kind": "variable", "name": "trust", "op": ">=", "value": 2}, story)
    assert evaluate_condition({"all": [
        {"kind": "flag", "name": "done"},
        {"kind": "variable", "name": "trust", "op": "<", "value": 5},
    ]}, story)
    assert not evaluate_condition({"not": {"kind": "flag", "name": "done"}}, story)


def test_graph_effect_and_condition_flow():
    graph = StoryGraph.from_dict({
        "id": "test",
        "entries": {"default": "set"},
        "nodes": {
            "set": {"type": "effect", "effects": [{"type": "set_flag", "name": "ready", "value": True}], "next": "branch"},
            "branch": {
                "type": "condition",
                "condition": {"kind": "flag", "name": "ready"},
                "true": "good",
                "false": "bad",
            },
            "good": {"type": "end", "result": "good"},
            "bad": {"type": "end", "result": "bad"},
        },
    })
    ctx, _, _ = _context()
    runner = StoryGraphRunner(ctx)
    runner.start(graph)
    runner.update(0.016)
    assert not runner.active
    assert runner.result == "good"
    assert ctx.story.flag("ready")


def test_dialogue_node_waits_until_dialogue_finishes():
    graph = StoryGraph.from_dict({
        "id": "dialogue",
        "entries": {"default": "talk"},
        "nodes": {
            "talk": {
                "type": "dialogue",
                "lines": [{"speaker": "Mara", "text": "Hello."}],
                "next": "end",
            },
            "end": {"type": "end"},
        },
    })
    ctx, _, _ = _context()
    runner = StoryGraphRunner(ctx)
    runner.start(graph)
    runner.update(0.016)
    assert runner.active
    assert ctx.dialogue.active
    ctx.dialogue.advance()
    runner.update(0.016)
    assert not runner.active


def test_choice_node_exposes_filtered_options_and_resumes():
    graph = StoryGraph.from_dict({
        "id": "choice",
        "entries": {"default": "choose"},
        "nodes": {
            "choose": {
                "type": "choice",
                "choices": [
                    {"text": "Visible", "target": "yes"},
                    {
                        "text": "Hidden",
                        "target": "no",
                        "condition": {"kind": "flag", "name": "secret"},
                        "condition_mode": "hidden",
                    },
                ],
            },
            "yes": {"type": "end", "result": "yes"},
            "no": {"type": "end", "result": "no"},
        },
    })
    ctx, choices, _ = _context()
    runner = StoryGraphRunner(ctx)
    runner.start(graph)
    runner.update(0.016)
    assert len(choices) == 1
    title, options, callback = choices[0]
    assert [o.text for o in options] == ["Visible"]
    callback(options[0].target)
    runner.update(0.016)
    assert runner.result == "yes"


def test_nonblocking_action_continues_in_background():
    story = StoryState()
    dialogue = DialogueController()
    handle = TimedAction(1.0)
    seen = []

    ctx = StoryRuntimeContext(
        story=story,
        dialogue=dialogue,
        choose=lambda *_: None,
        run_action=lambda name, params: (seen.append(name) or handle),
    )
    graph = StoryGraph.from_dict({
        "id": "async",
        "entries": {"default": "action"},
        "nodes": {
            "action": {"type": "action", "action": "move_actor", "params": {}, "wait": False, "next": "end"},
            "end": {"type": "end"},
        },
    })
    runner = StoryGraphRunner(ctx)
    runner.start(graph)
    runner.update(0.1)
    assert not runner.active
    assert seen == ["move_actor"]
    assert len(runner.background) == 1


def test_graph_validation_reports_missing_and_unreachable_nodes():
    graph = StoryGraph.from_dict({
        "id": "bad",
        "entries": {"default": "start"},
        "nodes": {
            "start": {"type": "dialogue", "lines": [], "next": "missing"},
            "orphan": {"type": "end"},
        },
    })
    issues = graph.validation_issues()
    assert any("missing" in issue for issue in issues)
    assert any("orphan" in issue and "unreachable" in issue for issue in issues)


def test_sample_story_is_packaged_and_valid():
    path = SRC / "test_game" / "stories" / "mara_meadow.json"
    graph = StoryGraph.load(path)
    assert graph.id == "mara_meadow"
    assert graph.validation_issues() == []


def test_background_action_keeps_updating_after_graph_end():
    story = StoryState()
    dialogue = DialogueController()
    handle = TimedAction(0.2)
    ctx = StoryRuntimeContext(
        story=story,
        dialogue=dialogue,
        choose=lambda *_: None,
        run_action=lambda _name, _params: handle,
    )
    graph = StoryGraph.from_dict({
        "id": "async_finish",
        "entries": {"default": "action"},
        "nodes": {
            "action": {"type": "action", "action": "move_actor", "params": {}, "wait": False, "next": "end"},
            "end": {"type": "end"},
        },
    })
    runner = StoryGraphRunner(ctx)
    runner.start(graph)
    runner.update(0.05)
    assert not runner.active
    assert len(runner.background) == 1
    runner.update(0.20)
    assert runner.background == []
