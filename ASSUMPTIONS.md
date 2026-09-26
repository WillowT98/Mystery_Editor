# Implementation assumptions / provisional decisions

These are choices made while implementing the first runnable engine because they had not yet been explicitly specified. They are intentionally easy to revisit.

1. **Logical rendering versus development window**
   - The game always renders to a logical **1920×1080** canvas.
   - The default development window is **1280×720**, resizable, and the logical canvas scales to fit with letterboxing. This makes development practical on screens where a bordered 1920×1080 window would not fit. `F11` toggles fullscreen.
   - A release can default to fullscreen/native 1920×1080 without changing game layout.

2. **World art scale**
   - Dungeon cells are rendered at **64×64 screen pixels**, corresponding to the planned 32 px source art at 2×.
   - Placeholder art is vector/solid-color rendering; there are no committed character art specifications yet.

3. **Dungeon floor size and first generator**
   - Test floors are 38×28 cells, with 6–9 rectangular rooms connected by corridors.
   - Corridors are one cell wide.
   - The generator allows diagonal movement but prevents diagonal movement through a blocked corner.

4. **Dungeon visibility**
   - Visibility currently uses line-of-sight within a radius of 7 cells rather than exact EoS room/corridor visibility behavior.
   - Discovered terrain persists independently of current visibility.

5. **Turn resolution**
   - One player action resolves, then living AI companions act, then living enemies act.
   - Environmental/status ticks have a hook but the test game does not currently include a periodic status effect.
   - A failed movement attempt into a wall does **not** spend a turn. Waiting explicitly does.

6. **Collision and diagonal movement**
   - Characters occupy one dungeon cell.
   - Diagonal movement is allowed only when both adjacent cardinal cells are traversable, preventing corner cutting.
   - Exploration collision uses axis-separated circle-versus-rectangle checks.

7. **Basic attack behavior**
   - The engine provides a universal adjacent basic attack.
   - Attempting to move into a hostile occupied cell performs the basic attack instead of moving.
   - Pressing Space in a dungeon with nothing interactable attacks the hostile cell directly in front of the leader, if occupied; otherwise it waits one turn.

8. **Facing**
   - The most recent non-zero movement direction becomes facing.
   - Skill targeting for player-triggered directional skills follows current facing.

9. **Skill resources**
   - Skills support arbitrary named resource costs and optional per-skill charges.
   - The test skills primarily use charges so the resource abstraction is exercised without inventing a final mana/stamina system.

10. **Damage formula**
    - Prototype damage is `max(1, power + attack - defense + small random variance) × resistance multiplier`.
    - Damage types are string identifiers supplied by game content. Characters need not have a type.
    - This is explicitly placeholder balance logic, not intended as a final RPG formula.

11. **Test-game typed damage**
    - Mara's `Spark` deals `lightning` damage.
    - The ranged test enemy has a modest lightning resistance so type multipliers can be observed.

12. **Companion AI**
    - Mara prioritizes healing a sufficiently injured ally, then ranged attacks, then adjacent attacks, then movement toward threats/leader.
    - Tactics are represented by an engine-side enum, but only a small subset is behaviorally distinct in this prototype.

13. **Enemy AI**
    - Test melee enemies approach the nearest active party member and attack adjacent targets.
    - Test ranged enemies use their ranged skill when they have line of sight/range, otherwise approach.

14. **Defeat**
    - Fox reaching 0 HP causes expedition defeat.
    - Mara reaching 0 HP incapacitates her for the rest of that expedition but does not by itself end the expedition.
    - On defeat, the test game loses **50% of carried money** and independently rolls a **30% loss chance for each droppable bag item**.
    - Protected/key items are supported and cannot be lost.

15. **Dungeon success**
    - The test dungeon has three floors. Taking the stairs on floor 3 is success and returns the party to the exploration map.
    - Success sets a story flag; defeat sets a separate story flag. Mara's exploration dialogue changes accordingly.

16. **Test-game exploration setup**
    - The test game intentionally contains only the two named characters, Fox and Mara.
    - Mara stands near the dungeon entrance in the test clearing and can be spoken to. She becomes Fox's active AI companion on dungeon entry.
    - A simple sign/waystone object is also interactable but is not a character.

17. **Exploration movement**
    - Walk speed is 240 logical px/s and sprint speed is 390 logical px/s.
    - Diagonal velocity is normalized so diagonal travel is not faster.

18. **Exploration interaction**
    - Space interacts with the nearest enabled interactable within 110 logical pixels. The first prototype does not require strict facing-cone interaction.

19. **Dungeon map panel**
    - The dungeon viewport is exactly 1440×1080 and the sidebar is 480×1080.
    - The map panel uses 432×432 pixels and independently scales its abstract cells to fit the entire dungeon floor rather than using world tile scale.
    - Unknown terrain is not drawn. Known-but-not-currently-visible entities are generally not shown.

20. **Menus**
    - Gameplay menus use `E`; system/pause uses `Esc` when no child UI is open.
    - The prototype supports keyboard navigation only even though mouse support may be added later.
    - Skills selected from Fox's menu target along Fox's current facing. Healing items currently default to Fox; `Give` is not yet a separate targeting flow.

21. **Story scripting**
    - The engine includes a small scene-command runner (`Say`, `SetFlag`, `Wait`, and callable hooks) rather than inventing a custom script language yet.
    - Test content mostly uses dialogue sequences directly.

22. **Content format**
    - Initial content is ordinary Python dataclasses/factories inside `test_game`, not JSON/YAML/TOML.
    - This avoids freezing a content-schema before repeated authoring reveals what the schema should be.

23. **Saving**
    - Generic JSON save/load infrastructure is included, but the first playable test loop does not expose save slots through the UI yet.
    - Serialization intentionally stores stable game IDs and simple state rather than Python objects.

24. **Audio**
    - Hooks/facilities are left for presentation audio, but no test audio assets are bundled yet.

25. **Rescue jobs, progression, equipment, shops, weather, and extensive statuses**
    - These remain outside the first vertical slice. The architecture avoids preventing them, but they are not implemented as finished game systems in v0.1.

26. **Dungeon dash interruption**
    - Shift-repeat currently stops when a previously unseen enemy enters current visibility or when Fox lands on an item.
    - It does not yet auto-stop specifically at corridor intersections; that behavior is left for feel-testing because intersection detection depends on how we ultimately define rooms/corridors and player expectations.

27. **Graphical verification in the generation environment**
    - The source was syntax-compiled; 11 headless engine/content tests were executed successfully; and a composition smoke test instantiated the game, exploration map, and first dungeon floor using a minimal Pygame stand-in.
    - This environment did not have `pygame-ce`, and outbound `pip` installation was unavailable, so the actual windowed renderer/input loop could not be launched here. The project declares `pygame-ce` in `pyproject.toml` and should be smoke-tested locally after installation.

## Visual/rendering decisions added during playtesting

- Temporary character art is now four-direction PMD-scale sprite art plus compact dialogue portraits, not painterly full-resolution illustration.
- Temporary character/item/object sprites use hard opaque/transparent alpha to avoid blotchy semi-transparent extraction artifacts.
- Exploration ground tiles are positioned in world coordinates and transformed through the camera; they are not screen-space wallpaper.
- The exploration camera is rounded to integer pixels for rendering so moving terrain and floating labels do not shimmer.
- Floating world labels use a dark contrast backing rather than anti-aliased text directly over moving terrain.
- Temporary exploration obstacles are intentionally rectangular test collision masses. Their visible border is drawn inside the exact collision rectangle so art and collision agree.
- Current temporary character art has four directions. Diagonal movement uses the horizontal-facing frame when a horizontal component exists; this is provisional until eight-direction art exists.


- Environment rendering was refactored to use semantically placed terrain and separate scenery objects instead of treating all candidate tiles as interchangeable. The outdoor test area now uses a lightweight tilemap (`grass`, `path`, `water`) plus separate tree/boulder/bush scenery, while dungeon walls are rendered with adjacency-aware boundary shading over the base wall texture.


- Environment polish pass: overworld terrain now uses concept-atlas-derived grass, path, water, cliff, tree, bush, boulder, fence, sign, and flower assets. Decorative grass/floor variants are chosen deterministically so maps do not flicker between frames. The outer exploration boundary is now visibly marked with a cliff ring plus perimeter trees. Object alpha is clamped after extraction so trees/rocks/bushes do not contain semi-transparent interior pixels. Dungeon floor/wall/stair textures now come from the dungeon concept atlas, with floor variants selected by tile coordinate.

- 2026-09-24 tile-rendering correction: path and water no longer select pre-cropped corner pictures by name. They are now composed from a concept-art fill texture using an 8-neighbor blob mask, so inside/outside corners follow map topology. Exploration scenery renders at native asset resolution (no resampling), with transparent padding added to scenery whose opaque pixels touched the source-image bounds. Dungeon walls are now a continuous dark masonry mass; a second pass draws one connected masonry boundary on the walkable side wherever floor meets wall, instead of stamping a complete wall-face image into every wall cell.


- Exploration terrain assembly was revised again after visual review. Path and water now render as full-tile rounded autotiles with exposed-edge contours only, rather than as shrunken center-cross masks. Map boundaries are now drawn as a dedicated continuous cliff ring overlay instead of relying on individual cliff terrain cells to stand alone. Object sprites were lightly defringed and padded to reduce clipped tops and dark fuzzy halos. Dungeon floor variants were softened and reduced so the floor/wall contrast is easier to read.


- After another visual review, path rendering was changed from generated masked fills to explicit concept-derived path edge tiles (`path_00`..`path_22`) so the path no longer reads like a masked square sitting on grass. Dungeon floor-boundary rendering now adds explicit outer-corner caps and concave-corner cleanup. The stairs tile is rendered smaller with padding to avoid edge cropping. Exploration-boundary cliff tiles are composed from a dominant oriented base tile plus a perpendicular corner overlay to keep the perimeter wall continuous. Exploration object sprites were further alpha-cleaned to reduce fuzzy fringes.


- Reworked terrain rendering around explicit visual cases rather than generic tile inference. Path and water now use a full-tile center texture with grass carved back only on exposed sides and corners, eliminating the per-tile center-mask look. Exploration-map perimeter walls are now rendered as continuous overlapping top/bottom/left/right strips with dedicated corner composites rather than isolated per-cell cliff tiles. Dungeon room edges still use the existing edge strips, but convex room corners now receive textured cap compositing from the horizontal and vertical edge art, and concave room corners use a more visible cleanup arc. The stairs asset was also padded and the renderer already draws it inset inside the tile.


- Replaced runtime-generated corner shaping for exploration terrain and dungeon boundaries with explicit corner-tile assets. Path rendering now selects among explicit edge/corner/inner-corner PNGs (`path_00`..`path_22`, `path_corner_*`). Water rendering now selects explicit edge/corner/inner-corner PNGs (`water_top/bottom/left/right`, `water_corner_*`, `water_inner_*`). Exploration-map perimeter walls now use explicit corner tiles (`cliff_corner_*`) instead of compositing boundary seams at draw time. Dungeon room readability now relies on explicit transparent overlay tiles for edges/corners/inner-corners (`dungeon_boundary_*`) rather than line/arc post-processing in the renderer.


- Path and water orientation are now determined by an explicit 8-neighbor topology mask. Every mask value (0-255) has a pre-generated PNG asset for both path and water (`path_auto_000..255`, `water_auto_000..255`). Diagonal bits only count when both adjacent cardinal connections exist, so diagonal-only neighbors do not rotate or distort a tile. The renderer performs no runtime rotation or corner carving for these terrains; it computes the exact mask and loads the matching asset. A pure `core.autotile` helper and five orientation tests were added to lock down horizontal, vertical, outer-corner, inner-corner, and asset-key behavior.

- Path and water oriented autotiles were regenerated from a single canonical geometry mask instead of composing independently painted whole-tile variants. Every `path_auto_###.png` and `water_auto_###.png` now uses the same edge radius, the same concave-corner notch radius, and the same margin, so adjacent tiles meet cleanly at junctions and corners. Water fill now uses the interior texture from `water_center.png` plus a generated shoreline, avoiding full-tile border seams inside connected streams.

- The canonical oriented autotile generator was corrected so the concave inner-corner notch radius equals the straight-edge inset (`inner_radius = margin = 12`). That makes the tangent points of inner corners land exactly on the same x/y offsets as straight exposed edges, eliminating the remaining crescent gaps where a corner tile met an adjacent straight tile.

- Dungeon room/corridor boundaries no longer rely on post-composited edge fragments. Walkable dungeon tiles now use explicit oriented autotile PNGs (`dungeon_auto_000.png` through `dungeon_auto_255.png`) generated from a canonical mask geometry over `dungeon_wall_fill.png`, with `dungeon_floor_0.png` as the walkable fill. Dungeon geometry constants: tile size 64, exposed-edge inset 8, outer-corner radius 10, inner-corner radius 8.

- Fixed a packaging/runtime regression in the dungeon autotile patch: `renderer.py` called `dungeon_walkable_mask(...)` but had not imported it from `mystery_engine.core.autotile`. A regression test now verifies the renderer namespace contains that helper.

- Exploration collision is now data-driven. `ExplorationScenery` may carry a local `RectObstacle` footprint relative to its rendered anchor; `ExplorationMap` checks those footprints, blocked terrain classes, enabled actors, and interactable collision radii during movement. The test clearing marks `water` and `cliff` as blocked, gives trees/boulders/bushes/fences/signposts local colliders, makes Mara and other enabled exploration actors solid, and gives the waystone a small collision radius. Large tree canopies remain non-colliding because only the trunk footprint is solid.
- Dungeon explicit autotiles retain the corrected canonical curve geometry, but their boundary band is now textured masonry generated into the tile asset itself rather than a pale runtime outline.

- Added an experimental dungeon presentation mode where wall grid cells render as pure void/darkness on the main dungeon view. Walls still exist as `TileKind.WALL` cells for generation, collision, pathfinding, and visibility blocking, but the visible masonry is represented only by the explicit boundary baked into adjacent walkable autotiles. Discovered/visible state no longer changes the appearance of wall cells themselves in this mode.

- Exploration presentation now uses a shared Y-depth pass for physical scenery, interactables, and actors. Scenery/interactable positions are bottom-center anchors, while actor depth uses the actor center plus collision radius (their effective feet line). Fences were moved out of the always-behind decoration layer so they occlude correctly from north/south approaches. The waystone now uses a rectangular base collider instead of a center-radius collider, matching its visible plinth. The dungeon entrance remains non-solid at its opening so interaction can trigger naturally.
- Waystone and dungeon-entrance art were replaced with new concept-matched painterly pixel-art assets. Their runtime sprites are pre-sized assets, so the renderer does not scale them dynamically.
- Exploration-map cliff-ring cells now render as void, mirroring dungeon wall presentation. Adjacent playable tiles receive one pre-generated `exploration_boundary_auto_###.png` transparent cliff overlay selected by an 8-neighbor mask, giving continuous straight edges and canonical convex/concave corners.

- Exploration perimeter cliffs now render on the blocked `cliff` ring cells themselves rather than as a narrow transparent overlay on the adjacent playable cells. The previous overlay used a 9px inset, which is why it appeared as a thin line in the running game. The new border uses full 64x64 explicit edge/corner cliff tiles with a substantial rock face and an 18px grass lip, while collision remains naturally correct because the visual wall occupies the already-blocked cliff cells.
- Reworked the exploration-map perimeter to use full-size concept-art style boundary overlays on the first playable tile adjacent to the logical cliff ring. Cliff cells now render as void/darkness again, while `exploration_boundary_auto_###.png` supplies a thick rocky wall band with rounded corners, grassy lip, and contact shadow so the border resembles the original concept art rather than square blocked tiles.
- Replaced the exploration border placeholder/overlay approach with explicit concept-art cliff-face perimeter tiles. The one-tile logical cliff ring now renders `cliff_n/s/e/w.png` and `cliff_corner_*.png`, each containing a grassy cliff top on the playable side and a substantial rock face toward the off-map void. The separate exploration-boundary overlay pass is now disabled.
- Reworked exploration perimeter cliff art to match the approved zoomed-in concept: each cliff boundary tile now depicts, in order from playable side outward, lower playable grass, a vertical rock cliff face, a raised upper grass strip/cap, and finally off-map void. The renderer still uses the one-tile logical cliff ring; only the explicit cliff tile art was changed.
- Replaced the exploration boundary again with multi-depth cliff sprites that visually match the approved concept more closely. Straight cliff assets are now larger than a single cell (north/south: 64x128, east/west: 128x64) and corners are 128x128. Each asset depicts, in order from playable side outward: lower playable grass, a substantial vertical rock cliff face, a raised upper grass strip, and then off-map void. The renderer now draws cliff tiles in a dedicated pass with inward offsets so the art can extend over the adjacent playable-edge row/column instead of being squeezed inside a 64x64 boundary cell.
- Exploration cliffs now use a true elevation model. `TerrainTileMap` stores elevation separately from terrain type; the meadow perimeter is elevation-1 `upper_grass`, surrounded by `void`, while the interior meadow remains elevation 0. Cliff faces are derived from adjacent height differences and drawn as overlays on the lower cell. Movement blocks untraversable elevation changes, and collision also accounts for the projected 44 px cliff-face depth so actors stop at the visible wall foot.
- Elevation cliff corners now use a 256-variant SDF-generated autotile atlas (`elevation_cliff_auto_000.png` through `elevation_cliff_auto_255.png`). The renderer derives a raw 8-neighbor higher-elevation mask for each lower cell; diagonals are preserved, so convex and concave corners are generated from the same smoothed local contour instead of separate edge/corner formulas. Runtime remains pygame-only; the offline asset regeneration script uses NumPy, Pillow, and SciPy.
- Cliff grass decoration should read as explicit pixel-art blades/tufts rather than a soft alpha halo. Decorative top/bottom cliff layers remain collision-free and derive their roots/orientation from the same SDF contour as the rock face.
- The grassy cliff style proof is now used as a **material/style reference**, not pasted wholesale into every cliff tile. The 256-mask SDF topology remains authoritative for endpoints and corner geometry. Each generated cliff pixel samples the painted reference in a local coordinate frame derived from the SDF gradient: distance from the cliff lip controls vertical sampling through grass/rock/foot vegetation, while the local tangent controls sampling along the cliff. This intentionally makes N/E/S/W edges and corners visually oriented instead of clipping the same left-right image into every mask.
- The old separate top/bottom grass overlay contract remains for compatibility, but those generated files are transparent because top grass and bottom vegetation are now baked into each orientation-aware `elevation_cliff_auto_XXX.png`.
- Package cleanup: only the 47 reachable blob masks are now retained/generated for path, water, and dungeon-floor autotiles; the 209 other mask files per family were unreachable duplicates. The elevation-cliff atlas retains all 256 masks because its raw diagonal bits are meaningful. Transparent top/bottom cliff overlay families and superseded legacy tile fragments were removed; grassy lip and foot decoration remain baked into the main orientation-aware cliff asset. Historical previews, caches, backups, and the documentation-only exploration concept sheet are omitted from the slim package.
- Exploration authoring now uses JSON scene files plus a generic visual editor. Terrain and elevation remain separate semantic grids; the editor paints those values rather than rendered autotile images.
- Game-specific placeable assets are described by `WorldAssetDefinition` entries in a game-side `WorldAssetCatalog`. Scene instances normally store only asset ID, stable instance ID, position, and optional interaction/label overrides.
- The initial editor defaults to a 40×24 scene at 64 px/tile when creating a new file. Object placement defaults to 16 px snapping, with off/8/16/32/64 px options.
- Interaction callbacks are never serialized as Python code. Scene JSON stores string action IDs and the game definition resolves those IDs to callbacks when building the runtime exploration map.
- The first editor intentionally covers exploration terrain, elevation, scenery, actors, and interactables. Dialogue/quest scripting and dungeon-layout editing remain separate future tools.
- F5 playtesting passes the edited scene path to the test game through `MYSTERY_SCENE_PATH`, keeping the editor generic while allowing arbitrary scene files to be previewed in the current game.

## Scene editor collision + scene-portal pass
- Collision-box customization is stored per scene-object instance rather than mutating the global asset definition.
- An absent instance collision means “inherit the asset catalog collision.”
- Collision editing is rectangle-based for scenery and ordinary interactables; actor collision remains radius-based.
- The old visible generic Door/transition placeholder has been replaced by an **invisible scene portal** (`scene_door`).
- Scene portals are visible only in the editor through a generated cyan marker; they have no runtime sprite and no default collision box.
- Portal instances store `target_scene`, optional `target_door`, and `portal_facing` directly in scene JSON instead of encoding scene transitions as named Python action IDs.
- Opening an unlinked portal in the editor creates a 16×12 target scene and a reciprocal return portal automatically.
- The active party is preserved by the runtime when changing exploration scenes, so linked interior scenes do not need to duplicate party actors in their JSON.

## Scene-audio pass
- Exploration scenes may specify one looping background-music track using a path relative to the game asset root plus a per-scene gain from 0.0–1.0.
- The editor supports OGG, WAV, MP3, and FLAC imports and copies them into `assets/music/`; MIDI is intentionally excluded because pygame/SDL MIDI playback is platform-dependent.
- The engine has a separate player music-volume setting, defaulting to 70%, that multiplies the scene gain and is persisted per game in the user's home directory.
- Scene portals switch music automatically. Reusing the same track across linked scenes does not restart it.
- Dungeon entry currently fades exploration music out; the current exploration scene's music resumes after leaving the dungeon.
