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

For ordinary dialogue, choreography actions, and story-state effects, selecting a node now opens a structured editor instead of raw JSON. The structured action editor provides labeled controls for actor/target selection, movement, camera, screen, audio, scene-transition, dungeon-entry, and message parameters, plus the node's wait behavior and next edge. Effect nodes expose editable effect rows for flags and variables.

Known project context is used where possible: actor/target IDs come from the bound room, scene destinations come from the project scene registry, music comes from project assets, and sound-cue fields list registered SFX cues.

**Advanced JSON…** remains available for structured nodes, and unknown/custom action types continue to use the JSON editor directly. This keeps the editor extensible without making routine cutscene authoring depend on JSON.

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


Gameplay-aware conditions are also available. These are resolved by the engine against the active persistent game state, so they work in Condition nodes, conditional choices/random branches, and scene triggers:

- `has_item` / `item_count` — compare item quantities in the bag, storage, or both;
- `has_money` — compare carried, stored, or total money;
- `party_contains` — test whether a character is currently in the party;
- `party_hp` — compare current HP, missing HP, or HP percentage for a party member;
- `skill_charges` — compare remaining charges for a specific party member's skill.

These conditions support the ordinary comparison operators (`==`, `!=`, `>`, `>=`, `<`, `<=`) and may be nested inside `all`, `any`, and `not` groups.

## Scene choreography

The exploration scene editor now exposes a **Story marker** asset. Markers are visible in the editor but invisible at runtime. Use their IDs as durable movement/camera destinations instead of putting raw world coordinates into story files.

Engine-native gameplay actions also include:

- `give_item` / `remove_item` — move authored quantities into or out of the bag or storage;
- `give_money` / `remove_money` — change carried or stored money;
- `heal_party` — heal one party member or the whole party by an amount or to full HP;
- `restore_skill_charges` — restore one skill or all skills for one member or the whole party;
- `restore_party` — fully restore HP and skill charges for one member or the whole party.

All of these use the existing persistent inventory/wallet/party state, so their results participate in normal save/load automatically.

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


### Structured choreography editing

The structured editor also covers the generic gameplay actions above. Item fields use project item IDs, character fields use project character IDs, and condition nodes now have a structured **Edit Condition** form for gameplay checks as well as flags/variables.

The structured action editor currently covers:

- actor movement, facing, teleportation/placement, and actor visibility/sprite state;
- enabling/disabling scene interactables;
- camera pan/to, follow, reset, and shake;
- screen fade/flash and banners/title cards;
- play/stop music, SFX, and ambience;
- scene changes and arrival markers;
- dungeon entry;
- ordinary runtime messages.

The action selector can also switch a node between supported built-in actions without replacing the node or rewiring its graph connections. Quick-add templates in the sidebar include the common variants (such as Object state, Camera follow/reset, Stop music, Stop ambience, and Message).

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

## Automatic scene triggers

Exploration scenes may also launch story graphs automatically through scene triggers. The scene editor's **7 Triggers** mode supports:

- `on_scene_enter` — after scene loading, persistent-state restoration, and party placement;
- `on_region_enter` — when the leader crosses into an authored rectangular trigger region.

Triggers can specify a named story entry point, the same flag/variable condition objects used elsewhere in story graphs, and `once` or repeatable behavior. Once-trigger completion is stored in story state and therefore participates in normal save/load automatically.
