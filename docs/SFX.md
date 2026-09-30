# Sound effects and ambience

Mystery Engine uses **semantic sound cues** rather than wiring gameplay directly to
individual OGG filenames. The cue catalog for the test game lives at
`src/test_game/assets/sfx_cues.json`. Game-ready files are expected below
`src/test_game/assets/sfx/`.

The current cue catalog mirrors **Foxglove SFX v0.1** (203 generated effects):

- UI: cursor, confirm/cancel, menu open/close, error/warning, item get, save,
  text advance, quest accept/complete.
- Combat: light/heavy/critical hit, block, evade, stun, defeat.
- Magic: arcane cast/charge, bolt launch/impact, heal, buff/debuff, shields,
  portal open/close, teleport, transformation.
- Dialogue reactions: surprise, confusion, realization, happy, sad, worried,
  afraid, angry, embarrassed, affection, relief, determined, disappointed,
  exasperated, shock.
- Ambience: night field, arcane room, magical cave, dream space, memory haze,
  portal idle, magical storm, ancient engine.

Each cue can contain several interchangeable variants. Runtime systems select a
variant automatically. Scene JSON and gameplay definitions store the cue ID
(e.g. `magic.heal`) rather than a specific file.

## Defaults currently wired

The test game automatically uses existing cues for:

- menu open/close, cursor movement, confirm/cancel/error;
- dialogue advance;
- item pickup and saving;
- ordinary combat impacts and defeat;
- Fox's Lunge;
- Mara's Spark launch/impact;
- Mara's Mend;
- Needle Wisp bolt launch/impact;
- dialogue reactions when a `DialogueLine.expression` matches a reaction cue.

Scene ambience is selected in the editor's **Audio** tab. Interactable, actor,
and scene-door interaction sounds can be overridden per placed object in
**Select** mode. These per-instance overrides inherit from the asset definition
when unset.

## Installing Foxglove SFX v0.1

Copy the game-ready category folders from the SFX bundle into:

```
src/test_game/assets/sfx/
    ambience/
    combat/
    magic/
    reactions/
    ui/
```

The `masters_wav/`, audition previews, build script, and QA files are not
required at runtime.

## Pertinent gaps for the next SFX pass

These are intentionally **not** mapped to a vaguely similar existing sound.
Purpose-built cues would improve the game substantially:

1. **Movement / terrain footsteps** — grass, dirt/path, stone, wood, shallow
   water, plus optional sprint variants. This is the largest current gap.
2. **Physical attack motion** — light swing/whoosh and Fox Lunge movement,
   separate from the impact sound.
3. **Thrown objects** — throw/release plus stone impact/bounce for Throwing
   Stone.
4. **Ordinary doors and mechanisms** — wooden door open/close, heavy stone
   door/gate, latch, lever/button. Generic scene doors are often mundane, so
   magical portal sounds should not be their default.
5. **Mundane environment loops** — daytime meadow/forest, ordinary cave room
   tone, running water, fireplace, wind, rain. The current ambience library is
   deliberately magic-heavy plus one night-field family.
6. **Dungeon navigation** — stairs/descend, floor arrival, dungeon entry and
   dungeon clear/return.
7. **Nonmagical item use** — salve/consume, inventory rustle, coin/money pickup.
8. **Creature identity sounds** — Mossling movement/hurt/defeat and Needle Wisp
   idle/hurt, if stronger creature personality is desired.
9. **Dialogue texture** — optional character-specific text blips / voice ticks;
   `ui.text_advance` currently covers page advancement only.
10. **World-object feedback** — waystone/chime, chest/container, sign/inspect,
    foliage rustle, splash, breakable object, and similar exploration feedback.

The engine should keep these as semantic cue IDs so new audio files can be added
without changing scene code.

## Dialogue text voices

Dialogue now reveals with a typewriter effect instead of drawing the whole line at
once. Each Pawn can choose a semantic **Dialogue voice cue** from the project's
`sfx_cues.json` catalog. While that pawn's text reveals, the runtime plays the
cue every few visible characters; the cue's own variant/randomization and cooldown
rules still apply.

This lets different speakers have different nonverbal tones without recording
spoken dialogue. For example, a project could register cues such as
`dialogue.fox`, `dialogue.mara`, or `dialogue.wisp`, each backed by its own
short family of blips.

Resolution order is:

1. a dialogue line's optional `voice_cue` override;
2. the speaking Pawn's `voice_cue`;
3. the project event cue `dialogue_blip`, if configured;
4. silence.

The dialogue editor exposes the per-line override, while the Pawn editor exposes
the normal per-speaker setting. Space reveals the rest of a partially displayed
line immediately; pressing Space again advances to the next line.

