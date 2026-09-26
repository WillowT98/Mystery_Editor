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
