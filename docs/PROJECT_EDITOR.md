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
