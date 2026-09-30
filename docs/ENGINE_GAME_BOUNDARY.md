# Engine / game boundary

The repository begins as a monorepo for ease of refactoring, but the dependency direction is strict:

```text
TEST GAME  ─────►  MYSTERY ENGINE
                  ▲
                  │
          never imports back
```

## Engine-owned concepts

The `mystery_engine` package owns reusable vocabulary and behavior:

- coordinate/direction types;
- characters, stats, resources, skills, typed damage, resistances;
- inventory and defeat-loss primitives;
- dungeon tile grids, floor generation, visibility, discovery memory, pathfinding, turns, and AI;
- continuous exploration maps, collision, actors, and interactions;
- dialogue and scene-command infrastructure;
- input intents and eight-direction keyboard interpretation;
- hierarchical menu infrastructure;
- rendering of exploration, dungeon HUD/minimap, menus, and dialogue;
- stable-ID save serialization;
- the runtime that composes a generic `GameDefinition`.

## Save/load and persistent exploration state

The engine save format stores stable IDs plus mutable runtime state rather than
serializing Python objects directly. Project definitions reconstruct characters,
items, attacks, and other content from those IDs when a save is loaded.

Exploration saves persist:

- party composition, leader, HP, resources, skill charges, and tactics;
- bag/storage contents and capacities;
- carried and stored money;
- story flags and variables;
- the current scene and exact party position/facing;
- per-scene non-party actor position, facing, enabled state, and sprite override;
- per-scene interactable enabled state.

Scene transitions snapshot the mutable state of the room being left, so story
actions such as moving an NPC or disabling an interactable survive later revisits
even before the player saves.

Saving is intentionally limited to exploration mode for now. Dungeon-session
state (generated floor layout, enemies, ground items, discovery/visibility, turn
count, and projectile state) is not yet serialized, so the engine does not create
misleading partial mid-dungeon saves. Loading an exploration save is available
from the system menu and replaces the active runtime state with the reconstructed
save.

The loader accepts the older save shape that predates the `world` block; those
saves resume from the configured starting scene while retaining their saved
party/inventory/story data.

## Game-owned concepts

The `test_game` package owns concrete content and choices:

- Fox and Mara;
- their stats and skills;
- Mosslings and Needle Wisps;
- Field Salves, Throwing Stones, and the Waystone Shard;
- the test clearing and its dialogue;
- dungeon population;
- story flags;
- the three-floor test objective;
- the chosen defeat-loss percentages.

## Extension rule

When a future game needs a mechanic that should not exist in every game, prefer an engine hook or generic primitive plus game-side implementation rather than adding game-specific state to engine classes.

A practical placement test is:

> Could an unrelated game use this code unchanged?

- **Yes** → engine.
- **No, it is specific to this game** → game.
- **Other games may want the capability but not this implementation** → add/extend an engine interface or event, keep the implementation game-side.

## Future repository split

When the API stabilizes, `src/mystery_engine` can become its own separately versioned Python package/repository. `test_game` (or a real game) then depends on a published or editable local engine package. The packaged player build can still ship as one application.
