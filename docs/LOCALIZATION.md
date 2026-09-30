# Localization

Mystery Engine projects keep source-language text in the normal content files and
store target-language translations separately under `locales/`.

This lets authors keep writing dialogue, item descriptions, names, and other
text in the editors where that content belongs while translators work from a
project-wide translation view or external localization tools.

## Project setup

Each project declares:

- a **source locale** (for example `en-US`);
- a **default locale** used when the game starts;
- zero or more additional supported locales;
- optional human-readable locale names.

New projects ask for the source locale. Existing projects default to
`en-US` until changed.

Source locale changes are allowed only before target translations exist. This
prevents a project from silently relabeling an existing English source corpus as
another language after translation work has started.

Example:

```json
"localization": {
  "source_locale": "en-US",
  "default_locale": "en-US",
  "supported_locales": ["en-US", "fr-FR", "ja-JP"],
  "locale_names": {
    "en-US": "English (US)",
    "fr-FR": "Français",
    "ja-JP": "日本語"
  }
}
```

## Stable string IDs

Game logic never uses translated text as identity.

Reusable resources derive localization keys from their stable project IDs:

```text
pawn.mara.name
item.field_salve.name
item.field_salve.description
attack.mara_spark.name
dungeon.ancient_ruins.name
```

Dialogue and choice entries also receive stable IDs inside their story nodes:

```json
{
  "id": "line_003",
  "pawn": "mara",
  "text": "Don't touch that.",
  "expression": "neutral"
}
```

which produces a localization key such as:

```text
story.first_meeting.dialogue_2.line_003.text
```

Existing story files are assigned line/choice IDs automatically the first time
the localization index is built. Reordering a line afterward therefore does not
change its translation key.

## Source text and stale translations

Locale files contain the translated text plus a short hash of the source text
that translation was based on.

Example target locale entry:

```json
"story.first_meeting.dialogue_2.line_003.text": {
  "text": "Ne touche pas à ça.",
  "source_hash": "..."
}
```

If the English source changes later, the French text is retained but shown as
**STALE** in the editor. This lets a translator decide whether the old
translation is still appropriate.

Runtime behavior is intentionally forgiving:

1. current translation, if available;
2. stale translation, if available;
3. source-language text otherwise.

A partially translated project therefore remains playable.

## Localization workspace

The project editor has a **Localization** section.

Each language shows translation coverage and stale counts. Open a target
language to see a searchable translation workspace with:

- stable key;
- translator context;
- source text;
- target translation;
- **OK**, **MISSING**, or **STALE** status;
- project-wide coverage.

Dialogue context includes the story/node, speaker, and neighboring lines where
available.

The source-language row is read-only in this workspace because source text
should be edited in its normal content editor. This avoids maintaining two
competing copies of the source manuscript.

## Import and export

Each target locale can be exchanged as either:

### CSV

UTF-8 CSV contains:

```text
key
context
source
source_hash
translation
status
```

This is suitable for spreadsheet-based translation.

### XLIFF 1.2

XLIFF export includes stable IDs, source/target text, source hashes, and context.
This is intended for CAT/localization tools such as memoQ, Trados, Lokalise,
Crowdin, Weblate, and similar workflows.

When a translated CSV/XLIFF is imported, the exported source hash is preserved.
If the game's source text changed while the file was with the translator, those
rows immediately appear as stale instead of being accepted as silently current.

## Runtime language selection

The generic project runtime starts in the project's default locale.

A locale can also be requested explicitly during development:

```bash
python run_game.py --project /path/to/game --locale ja-JP
```

If a game has more than one supported language, the runtime system menu includes
**Language**.

Changing language refreshes already-created:

- party names;
- attack names/descriptions;
- inventory item names/descriptions;

and subsequently loaded enemies, dungeon names, objects, scenes, and stories
use the selected locale.

## Variables

Localized story text may use project story variables:

```text
You found {count} apples.
```

A translator may move the placeholder anywhere required by the target language:

```text
Vous avez trouvé {count} pommes.
```

Formatting occurs after translation selection. Unknown placeholders are left
visible rather than crashing the story.

This first implementation deliberately does not invent a proprietary plural
syntax. Rich plural/grammatical selection should be layered on later using an
established message-format system.

## Currently extracted project text

The localization index includes:

- game title;
- Pawn/character names;
- enemy names;
- attack names and descriptions;
- item names and descriptions;
- reusable object names and interaction labels;
- per-scene placed-object labels;
- terrain names;
- dungeon names;
- story names;
- dialogue;
- custom/narrator speaker names;
- choice titles, option text, and option details.

## Future layers

This localization foundation is intentionally separated from several later
features:

- locale-specific font stacks and glyph coverage;
- localized images/audio;
- richer plural and grammatical selectors;
- right-to-left editor/runtime layout;
- localization of the Mystery Engine Maker UI itself.

The Maker UI language and a project's game languages are separate concepts. A
French editor interface must still be able to author an English game with
Japanese and German translations.
