# Exploration Scene Editor

## Purpose

The exploration scene editor is opened from the unified project editor. It edits the same scene format that the runtime loads. The editor does not place final path, water, or cliff edge tiles; it edits semantic data and lets the renderer derive orientation.

## Data flow

```text
WorldAssetCatalog + scene JSON
             |
             +--> visual editor
             |
             +--> build_exploration_map(...)
                       |
                       +--> ExplorationMap used by the game
```

This keeps the engine independent of any particular authored project.

## Scene JSON

A scene stores:

- ID and tile size
- width/height in tiles
- terrain grid
- elevation grid
- blocked terrain names
- cliff face projection depth
- placed object instances

Placed object instances reference a stable catalog ID. Default sprite, anchor, collider, category, actor metadata, and default interaction ID come from the catalog instead of being duplicated in every scene.

## Modes

### Terrain
Paint `grass`, `path`, `water`, or `void`. The runtime/editor uses the same neighbor-mask rules for path/water visuals.

### Elevation
Paint integer elevation levels. Cliff faces are derived from higher neighboring cells, so authors do not manually place cliff corners.

### Assets
Place game-provided scenery, actors, and interactables at free pixel positions. Placement can optionally snap to 8/16/32/64 px.

### Select
Select, drag, duplicate, delete, and nudge placed objects. Collision and anchor overlays can be toggled for debugging.

### Triggers
Use **7 Triggers** to author automatic story starts without placing invisible interaction objects.

- **Scene-enter trigger** — runs a story after the room has loaded and the party has been positioned.
- **Region trigger** — draw a rectangle directly on the room canvas; the story runs when the leader crosses from outside to inside it.

Each trigger stores a stable ID, story ID, optional story entry point, enabled state, an optional story-state condition, and whether it fires **once** or is **repeatable**. Conditions use the same flag/variable condition JSON as story graph branches. A once trigger records completion in persistent story state, so it remains consumed across scene revisits and save/load.

Repeatable scene-enter triggers fire once per room visit. Repeatable region triggers fire again only after the leader leaves the region and later re-enters it.

## Adding new placeable assets

Add a `WorldAssetDefinition` to the game-side catalog. For example:

```python
"lamp": WorldAssetDefinition(
    id="lamp",
    category="scenery",
    sprite_key="lamp",
    display_name="Lamp",
    size=(72, 120),
    collision=RectObstacle(-14, -24, 28, 24),
)
```

and add the corresponding PNG under the game asset root. The generic editor will discover it automatically.

## Collision-box editing

Placed scenery and interactables can override the collider inherited from their `WorldAssetDefinition`.

1. Switch to **Select** mode and select an object.
2. Click **Edit collision box** in the sidebar or press **B**.
3. The collision rectangle is shown with eight resize handles.
   - drag inside the box to move it;
   - drag a side handle to change one edge;
   - drag a corner handle to resize two edges at once.
4. The first actual edit creates an instance override in the scene JSON.
5. Press **R**, or click **Reset to asset default**, to discard the override and inherit the catalog collider again.

Scene-object collision overrides are stored as `[x, y, width, height]` relative to the object's anchor:

```json
{
  "id": "dungeon_gate",
  "asset": "dungeon_gate",
  "x": 1632,
  "y": 736,
  "collision": [-74, -128, 148, 50]
}
```

Collision editing is currently rectangle-based for scenery/interactables. Actors continue to use their radius-based collision model.

## Invisible scene doors / portals

The editor now includes a **Scene door** asset. It has no runtime sprite: in the game it is an invisible interaction point used to move between exploration scenes. In the editor it is shown as a cyan doorway marker so it can be selected and moved.

### Fast interior workflow

1. Choose **Assets** and place **Scene door** where an entrance should be.
2. Select the door.
3. Click **Open / create linked scene** or press **O**.
4. If the door has no target yet, the editor assigns a sibling JSON file automatically and creates a compact 16×12 scene there.
5. The new scene receives a reciprocal invisible `return_door` that links back to the source door.
6. The editor immediately switches to the linked scene and selects that return door.
7. Use **Alt+Left** or the sidebar Back button to return to the previous scene.

This makes it possible to place a house entrance, press **O**, immediately paint the house interior, and then jump back to the exterior without manually editing paths or action IDs.

### Portal properties

Each scene-door instance can store:

```json
{
  "id": "cottage_door",
  "asset": "scene_door",
  "x": 960,
  "y": 640,
  "target_scene": "cottage_interior.json",
  "target_door": "return_door",
  "portal_facing": "S"
}
```

- `target_scene` — destination scene JSON, normally relative to the current scene file.
- `target_door` — destination portal ID used as the arrival point.
- `portal_facing` — `N`, `E`, `S`, or `W`; controls which side of the destination portal the party appears on.

In Selection mode:

- **O** — open/create linked scene
- **T** — edit target scene path
- **D** — edit target door ID
- **Q** — cycle arrival facing
- **Alt+Left** — return to previous editor scene

### Runtime behavior

The scene door is invisible during play. Pressing the normal interaction key near it loads the linked exploration scene. The active party is preserved between scene files, so editor-created interiors do not need to contain duplicate Fox/Mara objects. When a `target_door` is supplied, the party appears beside that portal using its arrival-facing direction.

## Scene music

The editor has a fifth **Audio** mode (`5`) for assigning looping background music to an exploration scene.

### Importing a track

- Click **Import audio file…** and choose an `.ogg`, `.wav`, `.mp3`, or `.flac` file; or
- drag one of those files directly onto the editor window.

Imported files are copied into the game-side `assets/music/` directory and the scene stores a relative path such as:

```json
{
  "music": "music/opening_meadow.ogg",
  "music_volume": 0.8
}
```

The Audio sidebar lists every supported track currently in `assets/music/`. Clicking one assigns it to the current scene. **Preview current track** loops it inside the editor, and the scene-gain buttons adjust that scene's relative mix without changing the player's global volume.

Scene music starts automatically when the scene loads. Moving through an invisible scene door changes to the destination scene's track; if two linked scenes use the same track, the runtime keeps it playing rather than restarting it. Entering the dungeon currently fades exploration music out, and returning to exploration restores the scene track.

### In-game music volume

Press **Esc → Audio → Music volume** to choose a global volume from 0% to 100% in 10% increments. The same submenu is also available under the exploration command menu's **System → Audio** branch.

The final playback volume is:

```text
player music volume × scene music gain
```

The player setting is persisted per game under the user's `.mystery_engine/<game_id>/settings.json` directory so editor playtests keep the same volume between runs.
