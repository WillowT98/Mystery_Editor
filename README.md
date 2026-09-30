# Willow Mystery Engine — prototype 0.1

A PC-first, reusable framework for story RPGs with:

- continuous 8-direction exploration maps;
- portrait/dialogue interactions and simple scripted scenes;
- procedural, grid-based, turn-based dungeons;
- autonomous party members;
- directional attacks and skills with typed damage;
- limited visibility plus persistent map discovery;
- a dedicated 480 px dungeon HUD/minimap region at the 1920×1080 design resolution;
- EoS-inspired hierarchical/contextual command menus;
- slot-based expedition inventory and defeat penalties;
- strict engine/game dependency separation.

The included `test_game` has **Fox** as party leader and **Mara** as the AI companion.

## Setup

Python 3.11+ is recommended.

```bash
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate

python -m pip install -e .
python run_game.py
```

For tests (the bundled suite uses only the standard library):

```bash
python run_tests.py
```

`pytest` is also listed as an optional development dependency if you prefer it.

## Current patch notes

- Companion tactics now use a proper tactic-selection submenu instead of blind cycling.
- The test-game balance has been softened: fewer enemies, more healing, and lower enemy damage.
- Fox/Mara/enemy/item/object art has been upgraded from simple placeholders to more polished temporary assets.
- The game now opens at the full 1920×1080 logical resolution by default to avoid non-integer tile scaling seams.

## Controls

### Global

- **WASD** — move / menu navigation
- **Shift** — sprint in exploration; fast repeated movement in dungeons
- **Space** — interact / confirm / advance dialogue
- **E** — gameplay command menu
- **Esc** — back; when no gameplay menu/dialogue is open, opens the system menu

### 8-direction movement

Diagonals use WASD chords: `W+A`, `W+D`, `S+A`, `S+D`.
Dungeon controls include a short diagonal grace window so a near-simultaneous two-key press becomes one diagonal turn rather than two cardinal turns.

## Architectural rule

`mystery_engine` never imports `test_game`. The game configures and extends the engine; the engine does not know game-specific names, story flags, maps, skills, or characters.

See `ASSUMPTIONS.md` for choices that were inferred while implementing this first playable version.


## Engine/game separation

See `docs/ENGINE_GAME_BOUNDARY.md` for the dependency rule and eventual publishing split.

## PyCharm `src` layout

This project uses the standard Python `src/` package layout. If PyCharm underlines imports such as `test_game` or `mystery_engine` as unresolved even though `run_game.py` runs, mark the `src` directory as a source root:

1. Right-click `src` in the Project pane.
2. Choose **Mark Directory as → Sources Root**.

Also make sure PyCharm is using the same interpreter/virtual environment where you ran `python -m pip install -e .`.

## pygame-ce key-repeat compatibility

Keyboard event handling intentionally uses `getattr(event, "repeat", False)` rather than assuming every `KEYDOWN` event has a `repeat` attribute. Some pygame-ce/platform event objects omit that optional attribute.


## Smarter environment placement

The test area no longer draws arbitrary decorative atlas fragments as if every square were interchangeable.
Instead, it now uses:

- a small semantic exploration tilemap (`grass`, `path`, `water`)
- separate scenery objects (`tree`, `boulder`, `bush`) for large environmental features
- adjacency-aware dungeon wall rendering so boundaries appear where open floor actually neighbors a wall

This keeps corners, paths, and environmental objects in sensible places.


## Environment polish pass

The current test build now uses the recent concept-art tilesets much more directly:

- seamless grass base with occasional decorative variants
- semantic path tiles and water texture
- visible cliff boundary around the exploration map
- deliberate trees, bushes, boulders, flowers, fences, and signposts as scenery objects
- opaque-interior scenery sprites (no blotchy semi-transparency)
- dungeon floor crack/moss variants, wall variants, and stairs from the dungeon concept atlas

Terrain topology still comes from map data; decorative variants are deterministic and do not affect collision.

## Tile topology/rendering fix

This build replaces the earlier approximate terrain placement with topology-driven rendering:

- path and water use 8-neighbor blob autotiling, including inner-corner logic
- the test stream is cardinally continuous (no diagonal-only water joins)
- scenery such as trees, rocks, bushes, fences and signs is rendered at native asset size
- scenery art has transparent safety padding so canopies/rocks are not clipped at asset bounds
- dungeon wall cells form one dark masonry mass and rooms/corridors receive a continuous connected stone boundary on the floor side

The result is intended to fix the specific wrong-corner, repeated-water-corner, blurry-scaled-sprite, clipped-scenery and disconnected-dungeon-wall problems visible in the previous running-game screenshots.


## Tile-topology polish follow-up

This pass specifically addresses the visual issues seen in the running game screenshots:

- path and water now use full-tile rounded autotiles
- only exposed edges are outlined, eliminating the path-grid effect
- the exploration-map border is drawn as a continuous cliff ring overlay with proper corners
- scenery objects were padded and lightly defringed to reduce clipped tops and fuzzy dark borders
- dungeon floor variants were simplified/softened for better readability against the wall mass

Automated tests remain green (`14/14`).


## Visual topology cleanup follow-up

This pass targets the remaining issues called out from the latest screenshots:

- path tiles now use the explicit concept-art path edge set (`path_00`..`path_22`)
- the exploration-map wall/perimeter composition was tightened so corners stay connected
- dungeon room boundaries now include explicit exterior corner caps and concave-corner cleanup
- the stairs tile is drawn with padding so it no longer appears cropped
- exploration scenery received another alpha/fringe cleanup pass

Automated tests still pass (`14/14`).


## Explicit visual-case terrain pass

This follow-up stops trying to fix the screenshots with broad heuristic tweaks and instead targets the exact remaining cases:

- exploration paths now start from a full path tile and only carve grass back on exposed sides/corners
- water uses the same full-tile approach, so it should occupy the whole tile again
- the exploration boundary is now drawn as continuous overlapping wall strips with dedicated corner composites
- dungeon room corners now get explicit textured convex-corner caps and stronger concave-corner cleanup
- the stairs asset was padded further and still renders inset in the dungeon cell

Automated tests still pass (`14/14`).


## Explicit corner-tile pass

This pass addresses the user's request that corners stop being faked in the renderer and instead be represented by explicit tile assets. Specifically:

- path tiles now use dedicated edge/corner/inner-corner assets
- water tiles now use dedicated edge/corner/inner-corner assets
- exploration-map boundary walls now use dedicated corner tiles
- dungeon floor/wall boundaries now use dedicated transparent overlay tiles for sides, convex corners, and concave corners

Automated tests still pass (`14/14`).


## Orientation-aware autotiles

Path and water now use an explicit orientation system rather than choosing a generic edge/corner image. For each terrain tile, the engine computes an 8-neighbor bitmask (N/E/S/W plus valid diagonals) and loads the corresponding pre-generated asset:

- `path_auto_000.png` … `path_auto_255.png`
- `water_auto_000.png` … `water_auto_255.png`

This means horizontal middle tiles, vertical middle tiles, 90-degree bends, outer corners, inner corners, T-junctions, and fully surrounded center tiles all have distinct oriented assets. The renderer does not rotate or reshape these tiles at runtime. The source generator is included at `tools/build_autotiles.py`. Five new tests verify the orientation mask logic.

## Canonical oriented autotile regeneration

This patch replaces the previous pre-generated path/water autotile atlas with a new atlas generated from a single shared mask geometry. The important change is not the neighbor-mask selection logic (that was already present), but the art-generation rule:

- every path tile now uses the same canonical margin/radius geometry
- every water tile now uses the same canonical margin/radius geometry
- concave inner corners are carved with a consistent notch radius
- connected water no longer inherits a full-tile border on every tile; instead the border is generated only on the exposed shoreline

A helper script was added at `tools/regenerate_oriented_autotiles.py` so these 256 explicit path tiles and 256 explicit water tiles can be regenerated deterministically later.

Tests: `19/19` passing.

## Canonical inner-corner geometry correction

The previous oriented autotile atlas still had a geometric mismatch: straight exposed edges were inset by 12 px, but concave inner corners were carved with an 18 px radius. That caused near-miss joins and visible crescents where a corner met a straight edge.

This patch corrects the generator so:

- tile size = 64 px
- straight-edge inset = 12 px
- outer-corner radius = 20 px
- inner-corner radius = 12 px

All `path_auto_###.png` and `water_auto_###.png` files were regenerated from that corrected canonical geometry, and the helper script at `tools/regenerate_oriented_autotiles.py` now preserves that rule.

Tests: `19/19` passing.

## Dungeon explicit autotiles

The dungeon renderer now uses the same general strategy as the overworld path/water system: explicit mask-driven autotile assets instead of runtime edge-fragment composition.

### What changed
- Added `dungeon_walkable_mask(...)` to compute 8-neighbor connectivity for walkable dungeon tiles.
- Extended `autotile_asset(...)` to support `"dungeon_floor"`, producing `tiles/dungeon_auto_###.png`.
- Regenerated a 256-tile dungeon autotile atlas with a canonical geometry:
  - tile size `64`
  - straight-edge inset `8`
  - outer-corner radius `10`
  - inner-corner radius `8`
- Updated the renderer to draw `dungeon_auto_###.png` for every walkable tile and retire the old boundary-overlay pass.

This makes the dungeon use explicit oriented corner/edge tiles just like the overworld system, instead of trying to synthesize them in post during rendering.

Tests: `21/21` passing.

## Dungeon autotile import hotfix

Fixed a runtime `NameError` where `renderer.py` used `dungeon_walkable_mask(...)` without importing it. A regression test now checks that the renderer imports the helper it calls.

## Exploration collision + textured dungeon boundary pass

Exploration movement now checks the world objects that are actually drawn instead of relying only on the old hand-maintained obstacle rectangles.

- `water` and `cliff` terrain block movement
- enabled exploration actors block one another (so Fox cannot walk through Mara)
- trees collide at their trunks, not their canopies
- boulders, bushes, flower bushes, fences, and signposts have local scenery footprints
- the waystone has a small collision radius
- scenery collision footprints live with the scenery definitions rather than in an unrelated obstacle list

The dungeon autotile generator was also adjusted so the explicit curved dungeon tiles use a **textured masonry rim** baked into each generated tile. The corrected corner geometry remains intact; this only restores visual material/detail to the boundary instead of drawing it as a simple light outline.

Tests: `26/26` passing.

## Experimental wall-void dungeon mode

This patch tries the visual approach we discussed for dungeon walls:

- walkable dungeon tiles still use the explicit oriented autotile system (`dungeon_auto_###.png`)
- `TileKind.WALL` cells still exist logically for collision, generation, pathfinding, and line-of-sight blocking
- but on the **main dungeon view**, wall cells now render as **void/darkness** instead of as textured masonry cells
- the visible wall is therefore represented only once: by the boundary baked into the adjacent walkable autotile

This removes the dim/bright outer wall-cell halo around rooms and corridors, so the visual transition becomes:

`floor -> masonry boundary -> darkness`

Tests: `26/26` passing.

## Exploration depth, prop art, and boundary pass

This pass unifies how world props behave when approached from different directions and brings the exploration border closer to the dungeon wall model.

### Depth and collision
- Physical scenery, actors, and interactables now participate in one Y-sorted world pass.
- Fences are no longer permanently drawn behind actors; Fox appears behind them from the north and in front from the south.
- The waystone uses a bottom-center anchor and a rectangular collider around its stone base rather than a circular collider through the whole sprite.
- Interactables can now define local rectangular collision footprints just like scenery.

### Art
- Replaced `objects/waystone.png` with a painterly rune-stone asset matching the newer environment art.
- Replaced `objects/dungeon_gate.png` with a mossy stone cave entrance in the same visual language.
- The older exploration concept sheet is intentionally omitted from the slim package because it is documentation-only and not used by the engine or asset generator.

### Exploration border
- Logical `cliff` cells now render as void/darkness, like dungeon wall cells.
- The playable tile adjacent to the cliff owns the visible cliff boundary.
- Added 256 explicit `exploration_boundary_auto_###.png` overlays generated from the same canonical mask geometry idea used for dungeon walls.
- The overlays use a continuous cliff-face texture plus a grassy lip/contact shadow, rather than stitching the old directional cliff tiles at runtime.

Tests: `30/30` passing.

## Full-cell exploration cliff border

The previous exploration boundary system produced only a thin visible strip because the cliff art was generated as a 9px overlay on the first playable tile. The logical cliff-ring tile itself was still being rendered as void.

This pass changes that model:

- the blocked `cliff` cells now own the visible wall face
- top/bottom/left/right edge cells use explicit 64x64 cliff tiles
- all four map corners use explicit rounded corner tiles
- each tile contains a substantial rock face with an 18px grassy interior lip
- the old adjacent-playable-tile boundary overlay is disabled
- collision needs no special inset because the visual wall now occupies the same cell that is already non-walkable

A reusable `cliff_face_texture.png` was added and `tools/regenerate_oriented_autotiles.py` now regenerates the perimeter cliff assets deterministically.

Tests: `31/31` passing.

## Concept-art exploration border pass

This pass replaces the square full-cell exploration border with a concept-art style perimeter:

- logical `cliff` cells still exist and block movement
- those cliff cells render as off-map void/darkness
- the first playable tile adjacent to the cliff ring receives an explicit `exploration_boundary_auto_###.png` overlay
- those overlays are full-size 64x64 pieces with a thick rocky wall band, rounded corners, a grassy inner lip, and contact shadow

The result is intended to match the rounded border style shown in the earlier concept art rather than appearing as a strip or a row of square wall tiles.

## Actual cliff-face exploration boundary

The exploration perimeter now uses explicit full cliff-face tiles instead of lines, masks, or square blocked filler tiles.

### Presentation model
- the logical one-tile `cliff` ring still defines map bounds and collision
- each cliff cell renders one of eight explicit art assets:
  - `cliff_n.png`, `cliff_s.png`, `cliff_e.png`, `cliff_w.png`
  - `cliff_corner_nw.png`, `cliff_corner_ne.png`, `cliff_corner_sw.png`, `cliff_corner_se.png`
- those assets contain:
  - an irregular grassy cliff top on the playable side
  - a substantial exposed rock face
  - shading into the off-map void
- the exploration boundary overlay pass is now a no-op

This is meant to match the original concept-art intent: an actual raised cliff-face boundary around the exploration zone.

## Cliff-top cap exploration border pass

The exploration map perimeter now uses explicit cliff tiles whose composition matches the approved concept art:

- **lower playable grass** on the map interior side
- **vertical cliff face** in the middle
- **raised upper grass strip / cliff cap** beyond the face
- **off-map void** outside the upper strip

This is implemented by regenerating the 8 perimeter tiles:

- `cliff_n.png`, `cliff_s.png`, `cliff_e.png`, `cliff_w.png`
- `cliff_corner_nw.png`, `cliff_corner_ne.png`, `cliff_corner_sw.png`, `cliff_corner_se.png`

No additional overlay line or mask is drawn over interior tiles.

## Multi-depth exploration cliff boundary

The exploration border now uses **oversized perimeter cliff sprites** instead of single-cell border graphics.

### Visual structure
Each perimeter segment is drawn as:
- lower playable grass
- vertical cliff face
- raised upper grass strip / plateau lip
- outer void

### Asset sizes
- `cliff_n.png`, `cliff_s.png`: **64x128**
- `cliff_w.png`, `cliff_e.png`: **128x64**
- `cliff_corner_nw/ne/sw/se.png`: **128x128**

### Renderer behavior
- base terrain still draws the logical map cells
- cliff cells are skipped in the base pass
- a dedicated exploration-boundary pass draws the oversized cliff sprite for each logical `cliff` cell
- south/east assets are offset inward by one extra tile so they overlap the adjacent playable edge and preserve the sense of depth

This is intended to match the concept more closely than the earlier single-cell decorative border approach.

## Exploration elevation / cliff architecture

The exploration border now uses a real elevation system rather than encoding the entire landform into a border sprite.

### Terrain model
- `TerrainTileMap` now stores an `elevations` grid separately from terrain type.
- Lower meadow cells are elevation `0`.
- The perimeter shelf is ordinary `upper_grass` terrain at elevation `1`.
- The outermost ring is `void`.
- Because the upper shelf is real terrain, it can later become walkable without changing the rendering model.

### Cliff rendering
The renderer derives cliff faces from positive height differences between adjacent terrain cells. Explicit assets are selected for straight faces and inner corners:

- `elevation_cliff_n/s/e/w.png`
- `elevation_cliff_corner_nw/ne/sw/se.png`

The cliff sprites contain only the vertical face, a small grassy overhang from the higher tile, and base shading. The upper plateau itself is rendered by the ordinary grass terrain system.

### Collision
Characters cannot cross between different elevations unless a future traversal feature explicitly allows it. The test meadow also sets `elevation_face_depth=44`, so collision stops at the visible foot of the cliff face instead of allowing the character to walk through the wall sprite.

Tests: `32/32` passing.

## SDF elevation-cliff autotiles

Elevation cliff rendering now uses a single 256-variant atlas generated from a signed-distance-field workflow rather than separate straight-edge and corner formulas.

- each lower cell computes an 8-neighbor mask of **higher** elevation cells
- diagonal relationships are preserved
- the atlas generator constructs a local 3x3 elevation occupancy field
- that field is smoothed into one coherent contour
- the cliff face is the distance band inside the lower terrain
- convex and concave corners therefore use the same geometry and meet continuously

The actual game runtime only loads the generated PNG assets and still requires pygame only. Regenerating the art atlas uses NumPy, Pillow, and SciPy.

## Crisp cliff grass tufts pass

The previous fringe experiment used soft alpha bands and read as blur. This pass replaces those with explicit pixel-art grass blade clusters generated from the same SDF contour as the cliff face.

For every elevation-cliff mask the generator now emits:

- `elevation_cliff_auto_XXX.png` — rock face
- `elevation_cliff_bottom_auto_XXX.png` — small weeds/grass at the cliff foot
- `elevation_cliff_top_auto_XXX.png` — distinct overhanging grass blades at the cliff lip

The grass tufts are drawn as crisp blade strokes and small leafy wedges; no Gaussian blur is used on the blade silhouettes. Collision is unchanged.
## Orientation-aware painted cliff pass

This pass fixes the previous restyle mistake where one horizontal cliff painting was merely clipped into every topology mask.

The existing 256-mask elevation topology is unchanged. For each generated cliff tile, the renderer art generator now computes the local SDF gradient and uses it as the cliff normal. The painted grassy-cliff reference is sampled in local cliff coordinates:

- **distance from the boundary** selects upper grass overhang -> rock face -> bottom vegetation
- **local tangent direction** selects where to sample along the painted cliff

As a result, north/south/east/west faces and corner/end configurations use differently oriented artwork while keeping exactly the same connectivity endpoints as the prior SDF system. The painted grass overhang and base vegetation are baked into the main cliff asset; the legacy top/bottom companion overlay files remain transparent compatibility files.

A generated irregular-shape preview and orientation contact sheet were used to verify the actual output before packaging. Test result: **33 passed**.
## Asset/package cleanup

The project was audited after the orientation-aware cliff pass. The slim package removes generated and historical files that the current engine cannot request or no longer uses.

- Path, water, and dungeon autotiles now emit only the **47 reachable blob masks** rather than all 256 bit patterns. Their runtime mask builders cannot produce a diagonal bit unless both adjacent cardinal bits are present, so the other 209 files in each family were duplicates/unreachable.
- Cliff art still keeps all **256 elevation masks**, because elevation diagonals are intentionally independent and every raw 8-neighbor mask can be meaningful.
- The former `elevation_cliff_top_auto_*` and `elevation_cliff_bottom_auto_*` families were removed. Their decoration is already baked into `elevation_cliff_auto_*`.
- Superseded explicit path/water edge tiles, old dungeon boundary fragments, old cliff aliases, caches, `.bak` files, packaging previews, and the documentation-only 3 MB concept sheet were removed.
- `cliff_style_reference.png` remains because the current cliff generator actually uses it to regenerate the orientation-aware cliff atlas.

The cleanup does not change runtime rendering or collision behavior. The full test suite passes after regenerating assets.

## Unified project editor

The editor can now create, open, and run self-contained projects from its **File**
menu. Ordinary projects do not need their own Python package. Custom exploration
terrain, painted/tiled scene backgrounds, reusable objects, stories, pawns,
characters, items, attacks, enemies, and dungeons are all project data. The
**Export** File-menu entry is intentionally reserved for the later cross-platform
packaging pass.

The preferred authoring workflow is the project-level editor:

```bash
python run_project_editor.py
```

It provides one navigation surface for scenes, dungeons, enemies, reusable attacks,
and imported assets. Enemy/attack definitions are data-backed, dungeon enemy entries
support per-dungeon stat/resistance/attack/name/sprite modifiers, and generic dungeon
entrances can create or select a dungeon directly from the exploration editor.
Imported files are copied into the project rather than moved. See
`docs/PROJECT_EDITOR.md` for the current workflow and data layout.

## Exploration scene editor

The exploration editor remains available directly for data-driven exploration scenes.

Launch the current test clearing with:

```bash
python run_editor.py
```

Open or create another scene with:

```bash
python run_editor.py --scene src/test_game/scenes/my_scene.json --width 40 --height 24
```

If the file does not exist, the editor starts with a blank grass map and saves it there on `Ctrl+S`.

### Editor controls

- **1 / 2 / 3 / 4** — terrain / elevation / asset / selection modes
- **Left drag** — paint terrain/elevation
- **Shift + left drag** — fill a rectangle of terrain/elevation
- **F** — flood fill from the hovered tile
- **Right drag** — pan the map
- **Mouse wheel** — zoom the canvas; over the sidebar it scrolls the asset palette
- **WASD** — pan
- **G** — grid overlay
- **C** — collision overlay
- **V** — elevation overlay
- **[ / ]** — decrease/increase object snap (off, 8, 16, 32, 64 px)
- **Delete** — delete selected object
- **Ctrl+D** — duplicate selected object
- **Arrow keys** — nudge selection 1 px; Shift+arrow nudges 16 px
- **Ctrl+Z / Ctrl+Y** — undo / redo
- **Ctrl+S** — save scene JSON
- **F5** — save and launch a playtest using the currently edited scene

### Scene architecture

Exploration scenes are stored as JSON under `src/test_game/scenes/`. Terrain, elevation, and placed world objects are data rather than hardcoded Python coordinates. `test_clearing.json` now drives the existing meadow.

The generic editor and scene loader live in `mystery_engine`; the game-specific world asset catalog lives in `test_game/world_assets.py`. Adding a new asset definition there automatically makes it available in the editor palette without adding game names to engine code.

Terrain is semantic (`grass`, `path`, `water`, `void`). Path/water orientation is still chosen automatically by the engine. Elevation is a separate integer grid, and the cliff renderer derives the current orientation-aware cliff faces from differences between adjacent elevation cells.

## Invisible linked scene doors

The exploration editor now supports an editor-only **Scene door** marker for quickly linking exterior/interior scenes. Scene doors are invisible during normal gameplay. Select one and choose **Open / create linked scene** (or press **O**) to jump to its target. If no target exists yet, the editor creates a 16×12 scene automatically, adds a reciprocal `return_door`, links both ends, saves them, and opens the new scene. **Alt+Left** returns to the previous editor scene.

Portal metadata is serialized as `target_scene`, `target_door`, and `portal_facing`; scene transitions are no longer faked by reusing the dungeon-entrance sprite/action. At runtime, interacting near a portal loads the target scene while preserving the current party and placing it beside the destination door.

## Scene music

Exploration scenes can now carry looping background music. Open the scene editor, choose **5 Audio**, and either import an audio file or select one already under `src/test_game/assets/music/`. The editor can preview the assigned track and set a per-scene gain.

At runtime, use **Esc → Audio → Music volume** to change the global music level. Scene gain and player volume are multiplied together.
