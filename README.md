# Mystery Engine

Mystery Engine is a PC-first dungeon-crawler engine and visual game maker built
with Python and pygame-ce. The intended authoring workflow is data-driven:
ordinary games should be creatable, editable, and runnable without writing
Python.

The repository also contains `src/test_game`, a bundled example project built
with the same project format exposed by the editor.

## Current capabilities

- continuous 8-direction exploration scenes;
- visual scene editing with terrain, elevation, backgrounds, objects, pawns,
  colliders, doors, dungeon entrances, audio, and story links;
- procedural turn-based dungeons with weighted generation profiles;
- reusable attacks, items, enemies, pawns, playable characters, objects, and
  terrain definitions;
- dungeon-specific enemy stat/resistance/attack/sprite/name overrides;
- dialogue and branching story graphs authored from the editor;
- project-local localization with stable string IDs, stale-translation
  detection, CSV/XLIFF exchange, and runtime language selection;
- project-owned asset import by copy;
- generic runtime for editor-authored projects;
- project-level **File → New/Open/Run** workflow.

Cross-platform export is intentionally reserved for a later packaging pass.

## Setup

Python 3.11+ is required.

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

python -m pip install -e ".[dev]"
```

## Open the game maker

```bash
python run_project_editor.py
```

That opens the bundled example project. To open another project directly:

```bash
python run_project_editor.py --project /path/to/project
```

The unified project editor is the supported authoring entry point. Scene,
dungeon, and story editors are opened from that project window so they share
the same registry, assets, and project context.

## Run a game

```bash
python run_game.py
```

With no arguments, this runs the bundled example project through the same
generic runtime used by user-created projects.

Run another project with:

```bash
python run_game.py --project /path/to/project
```

For localization testing:

```bash
python run_game.py --project /path/to/project --locale ja-JP
```

## Tests

```bash
python run_tests.py
```

or directly:

```bash
python -m pytest -q
```

## Project structure

A normal authored project is self-contained and looks roughly like:

```text
my_game/
├── project.json
├── assets/
├── content/
│   ├── attacks/
│   ├── characters/
│   ├── enemies/
│   ├── items/
│   ├── objects/
│   ├── pawns/
│   └── terrain/
├── dungeons/
├── locales/
├── scenes/
└── stories/
```

Routine content belongs in those project files. Python remains available for
engine development and genuinely custom mechanics, but it is not the normal
content-authoring path.

## Architecture

The core dependency rule is:

```text
project data
    ↓
mystery_engine.project.ProjectRegistry
    ↓
mystery_engine.project_runtime.ProjectGameDefinition
    ↓
mystery_engine core/runtime/presentation
```

`mystery_engine` does not import the bundled example project. The example is
data consumed by the generic runtime, just like a newly-created project.

Stable IDs are used for cross-content references. Display names can change
without breaking those references.

## Controls

### Exploration

- **WASD** — move
- **Shift** — sprint
- **Space** — interact / confirm / advance dialogue
- **E** — gameplay menu
- **Esc** — back / system menu

Diagonal movement uses simultaneous WASD chords.

### Dungeon

Dungeon movement is grid-based and turn-based. The same movement keys apply;
Shift enables repeated movement, and menus expose skills, items, party tactics,
ground actions, dungeon information, waiting, and giving up.

## Documentation

- `docs/PROJECT_EDITOR.md` — unified project authoring workflow
- `docs/SCENE_EDITOR.md` — exploration scene authoring
- `docs/DUNGEON_BUILDER.md` — dungeon definitions and generation profiles
- `docs/STORY_GRAPH_EDITOR.md` — dialogue/cutscene graph authoring
- `docs/LOCALIZATION.md` — localization model and translator workflow
- `docs/SFX.md` — sound-cue system
- `docs/ENGINE_GAME_BOUNDARY.md` — engine/project ownership boundary

## Asset-generation tools

The `tools/` directory contains development-time helpers for regenerating
oriented autotile assets. Their optional NumPy/Pillow/SciPy dependencies can be
installed with:

```bash
python -m pip install -e ".[art]"
```

Those dependencies are not required by the game runtime.
