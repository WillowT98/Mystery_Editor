# Dungeon Builder

Mystery Engine dungeons are authored as JSON definitions rather than hard-coded floor construction.

Launch the current test dungeon with:

```bash
python run_dungeon_editor.py
```

Open or create another dungeon with:

```bash
python run_dungeon_editor.py --dungeon src/test_game/dungeons/my_dungeon.json
```

## Builder tabs

- **Overview** — dungeon ID, display name, floor count, and tileset key.
- **Generation** — base generator type and dimensions/room parameters.
- **Profiles** — weighted PMD-style floor tendencies, assignable by floor range.
- **Enemies** — enemy pool entries with floor selectors, weights, and per-floor min/max counts.
- **Items** — item pool entries with the same floor-range model.
- **Audio** — default dungeon music and gain.
- **Preview** — deterministic generated-floor preview, floor navigation, reseeding, and direct playtest.

Press **Ctrl+S** to save, **R** to regenerate with a new seed, and **F5** to save and launch a playtest directly into the selected floor.

## Floor selectors

Spawn rules and floor-specific overrides accept:

- `all` or `*`
- a single floor: `7`
- a range: `3-8`
- an open-ended range: `10+`
- combinations: `1-3,8,12+`

## Generation

The engine currently includes:

- `rooms_and_corridors` — the original Mystery Engine procedural layout.
- `open_room` — one large arena/tutorial room.

Generators are selected by ID in the dungeon definition. More generator implementations can be added without changing game-specific content.

## Generation profiles

Generation profiles are reusable floor tendencies layered over the dungeon's base **Generation** settings. The built-in profiles are:

- **Dungeon Default** — keep the base generation settings unchanged.
- **Compact** — smaller overall dimensions with a normal room count.
- **Many Small Rooms** — room-dense floors made from numerous small chambers.
- **Sprawling** — substantially larger dimensions and longer travel distances.
- **Sparse Large Rooms** — a handful of broad rooms on a large map.
- **Tight Labyrinth** — compact dimensions packed with tiny chambers and short corridors.
- **Open Hall** — a single large room using the open-room generator.

The **Profiles** editor tab stores a weighted pool of profile rules. Each rule has a floor selector and a relative weight. When a floor is generated, all matching positive-weight rules form a pool and one profile is rolled. If no profile rule matches, the floor uses **Dungeon Default**.

For example:

```json
"generation_profile_rules": [
  {"profile": "default", "floors": "1-10", "weight": 5},
  {"profile": "many_small_rooms", "floors": "1-10", "weight": 2},
  {"profile": "compact", "floors": "1-4", "weight": 2},
  {"profile": "sprawling", "floors": "7-10", "weight": 1}
]
```

On floors 1-4 this gives Default a 5/9 chance, Many Small Rooms a 2/9 chance, and Compact a 2/9 chance. On floors 7-10 the matching pool becomes Default 5, Many Small Rooms 2, and Sprawling 1.

The preview uses the current seed, so **New seed** rerolls both the selected profile and the generated layout. The preview title shows which profile was selected.

## Floor overrides

`floor_rules` can override generation settings, tileset, music, enemy counts, or item counts for a floor range. This makes it possible to create sections such as early/deep ruins and special final floors without authoring every floor separately.

Example:

```json
{
  "floors": "8-10",
  "tileset": "deep_ruins",
  "generation": {
    "room_count_min": 4,
    "room_count_max": 6
  },
  "music": {
    "track": "music/deep_ruins.ogg",
    "volume": 0.7
  }
}
```

## Tilesets

A dungeon's `tileset` is a semantic key. The renderer first looks for:

`assets/tiles/<tileset>_auto_###.png`

using the same connectivity masks as the existing dungeon autotiles. Missing custom variants fall back to the standard `dungeon_auto_###.png` art, so definitions remain playable before a complete art set exists.

## Content catalogs

The engine does not import Foxglove-specific enemies or items. The game supplies catalogs/factories to the dungeon definition runtime and editor. The current test game exposes Mossling and Needle Wisp enemy factories plus its existing item definitions.
