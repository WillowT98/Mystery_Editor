# Story Graph / Cutscene Editor

For ordinary room dialogue, the preferred workflow is now **Scenes → open room → 6 Story** in the unified project editor. That view keeps the room, placed pawns, and dialogue together. The graph editor remains the advanced view for branching, conditions, choreography, parallel actions, and other structural work.

Mystery Engine story graphs are data-driven conversations and in-scene cutscenes. They are designed to cover the same broad class of authored scenes as a Mystery Dungeon-style acting script without exposing hundreds of engine opcodes directly.

Open the unified game maker with:

```bash
python run_project_editor.py --project /path/to/project
```

Stories can be opened from the project-level **Stories** section or directly
from a room's Story mode, keeping scene pawns and project content available while
dialogue is authored.

## Editor workflow

The graph canvas supports draggable nodes, visible connections, panning, structural validation, named entry points, and direct F5 playtesting.

Core node types:

- **Dialogue** — one or more lines with a stable pawn reference (or legacy/custom speaker), portrait override, and expression.
- **Choice** — player-facing choices with optional conditions.
- **Condition** — branch on flags or variables.
- **Random** — weighted conditional branches.
- **Effect** — set/toggle flags and edit story variables.
- **Wait** — timed pause.
- **Action** — semantic scene/game action.
- **Parallel** — run multiple graph branches simultaneously and join on all/any.
- **Call** — run another graph/entry and return.
- **End / Return** — finish the graph with an optional result.

Select a node and use **Edit JSON** for its detailed payload. The JSON inspector is intentionally flexible while the node vocabulary is still evolving.

## Story state and conditions

Conditions can read boolean flags or arbitrary story variables and support boolean groups:

```json
{
  "all": [
    {"kind": "flag", "name": "completed_ruins", "op": "==", "value": true},
    {"kind": "variable", "name": "mara_trust", "op": ">=", "value": 3}
  ]
}
```

Effects currently support:

- `set_flag`
- `toggle_flag`
- `set_variable`
- `add_variable`
- `multiply_variable`
- `delete_variable`

## Scene choreography

The exploration scene editor now exposes a **Story marker** asset. Markers are visible in the editor but invisible at runtime. Use their IDs as durable movement/camera destinations instead of putting raw world coordinates into story files.

Engine-native action IDs currently include:

- `move_actor`
- `face_actor` / `turn_actor`
- `teleport_actor` / `place_actor`
- `set_actor_state`
- `set_object_state`
- `camera_pan` / `camera_to`
- `camera_follow`
- `camera_reset`
- `camera_shake`
- `screen_fade` / `screen_flash`
- `banner` / `title_card`
- `play_music` / `stop_music`
- `play_sfx`
- `play_ambience` / `stop_ambience`
- `change_scene`
- `enter_dungeon`
- `message`

Movement is collision-aware and can fall back to teleporting after a timeout so a cutscene cannot be permanently blocked by an awkward actor position.

Action nodes have a `wait` field. When false, the action continues in the background while the graph advances. Background actions continue updating even after the root graph reaches an End node.

## Parallel choreography

Parallel nodes own independent branch cursors:

```json
{
  "type": "parallel",
  "branches": ["move_mara", "turn_fox", "pan_camera"],
  "join": "all",
  "next": "mara_speaks"
}
```

Use `join: "all"` to wait for every branch or `join: "any"` to continue when the first branch completes.

## Extensibility

The action vocabulary is semantic rather than hard-wired to editor classes. A game can register additional actions through `story_actions` or implement `run_story_action(game, action, params)`.

The editor already includes templates for **Animation**, **Effect**, and **Custom** actions. Those IDs intentionally use this extension mechanism until project-specific sprite animation/effect systems are implemented. This means authored graphs do not need to be migrated when those renderers arrive.

## Validation

The editor reports:

- entry points targeting missing nodes
- edges targeting missing nodes
- unreachable nodes

Because graph files are ordinary readable JSON, they also remain straightforward to review and merge in Git.

## Current sample

`src/test_game/stories/mara_meadow.json` replaces the previous Python branching in Mara's meadow interaction. It branches on the existing completion/failure flags and plays the appropriate dialogue through the same graph runtime used by editor-created stories.


## Room and pawn binding

A graph may declare a player-facing `name` and a `scene` ID. When project
context is available, selecting a dialogue node uses the structured dialogue
editor instead of raw JSON and offers pawns from that room.

Dialogue pawn references are stable project IDs. The runtime resolves the
current pawn display name and portrait when the line is played. Free-form
`speaker` remains valid for narration and backwards compatibility.

Scene objects may store `target_story`. This is the generic no-code interaction
link used by the room editor: interacting with that pawn starts the referenced
graph.
