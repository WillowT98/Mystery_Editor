# Unified Project Authoring

The preferred authoring entry point is now:

```bash
python run_project_editor.py
```

The project editor is the shared navigation surface for **Scenes**, **Dungeons**,
**Enemies**, **Attacks**, and **Assets**. Specialized scene and dungeon editors
open from this project context and return to it when closed.

## Project manifest and content registry

A game project owns a small `project.json` manifest plus individual content
files. The current test game uses:

```text
src/test_game/
  project.json
  content/
    attacks/
    enemies/
  dungeons/
  scenes/
  assets/
```

IDs are stable references. Display names may be edited without breaking dungeon
or enemy references.

Ordinary enemy and attack definitions are JSON-backed rather than Python
factories. Python remains available for game-specific composition and mechanics,
but adding an ordinary enemy or attack no longer requires editing Python.

## Assets are imported by copy

When an editor imports a sprite or projectile from elsewhere on the computer,
the source file is **copied** into the project asset tree. The external source is
never moved or renamed.

Enemy sprites go to `assets/characters/`, projectile sheets go to
`assets/projectiles/`, and per-entrance dungeon art goes to `assets/objects/`.

## Enemy editor

An enemy definition includes:

- stable ID and editable display name
- HP, Attack, and Defense
- sprite
- reusable attacks
- any number of damage-type resistances/vulnerabilities

The resistance value is the damage multiplier used by the engine: `0.5` means
half damage, `1.0` normal damage, and `1.5` one-and-a-half damage.

**Create Attack** can be used from inside the enemy form. Saving that attack
returns it to the shared attack catalog and allows it to be attached immediately.

## Attack editor

Reusable attacks expose the mechanics already understood by the engine:

- target kind
- adjacent / two-tile / line / room / self range pattern
- range
- power or healing
- registered damage type
- accuracy
- charges
- launch/impact SFX cue
- projectile sheet and arc

Projectile sheets can be imported from the attack editor; the source PNG is
copied into the project.

## Dungeon editor

When opened with project context, **Overview → Current dungeon** is a project
selector rather than a filename. The same screen can create a new dungeon and
switch to it.

The **Enemies** tab supports:

- **Add enemy** — choose an existing enemy from the project catalog
- **New enemy** — create an enemy and immediately add it to this dungeon
- spawn floor range, weight, minimum, and maximum
- independent HP / Attack / Defense percentage multipliers
- optional display-name override
- optional imported sprite override
- resistance overrides selected from registered damage types
- additional attacks selected from the shared attack catalog

Dungeon-specific changes remain on the spawn rule; they do not mutate the base
enemy used by other dungeons.

## Exploration → dungeon workflow

The scene asset palette now contains a generic **Dungeon entrance**. Placing one
with project context starts the entrance workflow:

1. enter the player-facing entrance name;
2. choose a PNG for the entrance (or cancel the picker to keep the default);
3. create a new dungeon or choose an existing project dungeon;
4. save the scene link;
5. open that dungeon directly in the dungeon editor.

The scene stores the stable `target_dungeon` ID rather than a Python action
callback. It may also store a per-instance `sprite_override`.

At runtime, a generic dungeon entrance selects that dungeon definition and begins
the expedition. The old hard-coded test entrance remains as a compatibility
asset for existing scenes.

## Compatibility

`run_editor.py` and `run_dungeon_editor.py` still work and now load the same
project registry. The recommended workflow is `run_project_editor.py`.


## Room-first story authoring

Open a room from **Scenes** and choose **6 Story**. The exploration room remains
visible while story content is authored.

The Story sidebar provides:

- a room/scene chooser;
- the project pawn library;
- **New pawn / import art**;
- click-to-place and drag-to-reposition pawns in the visible room;
- stories bound to the current room;
- **New story for this room**;
- structured dialogue nodes;
- **Advanced graph** for branching, conditions, actions, and choreography.

A pawn is a reusable project content resource under `content/pawns/`. It has a
stable ID, editable display name, world sprite, optional dialogue portrait,
interaction radius, and color key.

The pawn editor imports source images by **copying** them into the project:
world art goes under `assets/characters/` and portraits under
`assets/portraits/`. A single PNG is sufficient for a static pawn; compatible
directional or walk sheets can still be supplied using the existing renderer
conventions.

Dialogue lines can reference a stable pawn ID:

```json
{
  "pawn": "mara",
  "text": "The ruins are east of here.",
  "expression": "neutral"
}
```

At runtime, the project registry resolves that pawn ID to its current display
name and portrait. Renaming a pawn therefore does not require editing every line
of dialogue.

The structured dialogue editor draws its pawn choices from the pawns placed in
the current room. Legacy free-form `speaker` lines remain supported for
narrators and older content.

A placed pawn can also be assigned the current story with **Make pawn start
current story**. This writes a generic `target_story` reference onto the scene
object. Interacting with that pawn launches the story graph without a
game-specific Python callback.

Story graphs can now include `name` and `scene` metadata. The scene binding
lets the advanced graph editor playtest in the correct room and lets the room
editor discover the stories relevant to the visible scene.


## Game setup without Python

The project editor now also owns the high-level setup that previously lived in
`game_definition.py`.

### Game

The **Game** section edits project-wide settings stored in `project.json`:

- title and game version;
- starting exploration scene and optional marker;
- default dungeon;
- bag and storage capacity;
- starting carried/stored money;
- defeat money/item-loss percentages;
- starting party and leader;
- starting inventory;
- starting story flags.

The runtime reads these values when constructing a new game state.

### Playable characters

The **Characters** section turns a reusable Pawn into a playable/combat
character. A character definition contains:

- stable character ID and referenced pawn;
- HP, Attack, and Defense;
- reusable attacks;
- damage resistances/vulnerabilities;
- companion AI tactic.

Game Settings chooses which character IDs form the starting party and which one
is the leader. The pawn continues to own the visible name, exploration sprite,
and dialogue portrait, so changing presentation does not duplicate combat data.

### Items

The **Items** section is now backed by `content/items/*.json`. Ordinary items
no longer need to be added to `content.py`.

The item editor supports:

- name and description;
- healing amount;
- throwable damage and damage type;
- droppable/key-item behavior;
- ground sprite import;
- projectile sheet and arc;
- use/impact SFX cues.

Imported item/projectile art is copied into the project, just like other
authoring assets.

Dungeon item pools use the same project item registry. The dungeon editor can
choose an existing item or create a new one directly from the Items tab.

### Runtime boundary

The test game's runtime now constructs its starting party, inventory, wallet,
story flags, default dungeon, and starting room from project data. Python remains
available for genuinely custom engine/game mechanics and legacy bespoke
interactions, but ordinary game setup no longer requires editing it.


## Custom world objects

The **Objects** section creates reusable exploration props under
`content/objects/*.json`. Ordinary scenery and interactable props no longer
need a `WorldAssetDefinition(...)` added in Python.

A custom object can define:

- stable ID and editable display name;
- **Scenery** or **Interactable** category;
- an imported PNG sprite (copied into `assets/objects/`);
- authored display width/height and anchor;
- draw-behind-actors behavior;
- runtime visibility;
- default interaction label / legacy action ID / interaction SFX;
- a default collider and collision radius.

The Object editor can create a rectangular default collider numerically. Once an
object is placed in a room, the exploration editor's existing visual collider
tools can resize it or convert that individual placement to a polygon.

### Per-instance collider toggle

Collider **state** is separate from collider **shape**. In **Select** mode, a
placed scenery/interactable object now shows an explicit **Collider ON/OFF**
control. Click **Enable/Disable collider** or press **K**.

This is a per-placement override:

- inherited/default: use the reusable object's collider;
- OFF: ignore the collider for this placement;
- ON: explicitly enable collision (and create a sensible default box if the
  object definition has no collider);
- **Reset to asset default** clears both the shape override and the ON/OFF
  override.

Turning a collider off does not delete its authored geometry, so it can be
turned back on without reconstructing the object definition.

### No-code interactable objects

An object created as **Interactable** can be linked to a Story from the room
editor. The placed object stores `target_story`; interacting with it launches
that story through the same generic runtime path used by story-linked pawns.
The legacy Action ID field remains available for game-specific callbacks, but
ordinary dialogue/inspection objects can now be authored without Python.

The existing Tree, Boulder, Flower Bush, Bush, Fence, Signpost, and Waystone are
also present as project object definitions, so the shipped test project exercises
the same data-backed path used by newly created objects.
