from __future__ import annotations

import json

from mystery_engine.localization import LocalizationEntry, ProjectLocalization, source_hash
from mystery_engine.project import (
    AttackDefinitionData,
    ItemDefinitionData,
    PawnDefinitionData,
    PlayableCharacterDefinitionData,
    ProjectRegistry,
)
from mystery_engine.story import ExplorationSceneData, StoryGraph, save_exploration_scene


def test_translation_falls_back_and_marks_stale(tmp_path):
    loc = ProjectLocalization(
        tmp_path / "locales",
        source_locale="en-US",
        default_locale="en-US",
        supported_locales=["en-US", "fr-FR"],
    )
    entry = LocalizationEntry("item.herb.name", "Healing Herb", "Item name")
    assert loc.translate(entry.key, entry.source, locale="fr-FR") == "Healing Herb"
    assert loc.status(entry, "fr-FR") == "missing"

    loc.set_translation("fr-FR", entry, "Herbe de soin")
    assert loc.translate(entry.key, entry.source, locale="fr-FR") == "Herbe de soin"
    assert loc.status(entry, "fr-FR") == "translated"

    changed = LocalizationEntry(entry.key, "Greater Healing Herb", entry.context)
    assert loc.translate(changed.key, changed.source, locale="fr-FR") == "Herbe de soin"
    assert loc.status(changed, "fr-FR") == "stale"


def test_csv_round_trip_preserves_exported_source_hash(tmp_path):
    source = LocalizationEntry("story.intro.line.text", "Hello.", "Dialogue")
    loc = ProjectLocalization(
        tmp_path / "locales",
        source_locale="en-US",
        supported_locales=["en-US", "ja-JP"],
    )
    path = tmp_path / "ja.csv"
    loc.export_csv(path, "ja-JP", [source])

    text = path.read_text(encoding="utf-8-sig")
    text = text.replace(",Hello.,", ",Hello.,")
    rows = text.splitlines()
    header = rows[0]
    values = rows[1].split(",")
    # Translation is the fifth field in our simple no-comma test fixture.
    values[4] = "こんにちは。"
    path.write_text(header + "\n" + ",".join(values) + "\n", encoding="utf-8-sig")

    imported, skipped = loc.import_csv(path, "ja-JP", [source])
    assert imported == 1
    assert skipped == 0
    assert loc.translate(source.key, source.source, locale="ja-JP") == "こんにちは。"
    assert loc.load_locale("ja-JP")[source.key].source_hash == source.hash


def test_xliff_round_trip(tmp_path):
    entry = LocalizationEntry("pawn.mara.name", "Mara", "Pawn name")
    loc = ProjectLocalization(
        tmp_path / "locales",
        source_locale="en-US",
        supported_locales=["en-US", "de-DE"],
    )
    loc.set_translation("de-DE", entry, "Mara")
    path = tmp_path / "de.xlf"
    loc.export_xliff(path, "de-DE", [entry])

    other = ProjectLocalization(
        tmp_path / "other_locales",
        source_locale="en-US",
        supported_locales=["en-US", "de-DE"],
    )
    imported, skipped = other.import_xliff(path, "de-DE", [entry])
    assert imported == 1
    assert skipped == 0
    assert other.translate(entry.key, entry.source, locale="de-DE") == "Mara"


def test_registry_collects_content_and_assigns_stable_story_line_ids(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Localized Game")
    registry.save_item(ItemDefinitionData(
        id="salve",
        name="Field Salve",
        description="Restores HP.",
        heal=10,
    ))
    graph = StoryGraph.from_dict({
        "id": "intro",
        "name": "Introduction",
        "scene": "start",
        "entries": {"default": "talk"},
        "nodes": {
            "talk": {
                "type": "dialogue",
                "lines": [{"speaker": "Guide", "text": "Welcome."}],
                "next": "end",
            },
            "end": {"type": "end"},
        },
    })
    graph.save(registry.story_dir / "intro.json")

    entries = {entry.key: entry for entry in registry.localization_entries()}
    assert entries["game.title"].source == "Localized Game"
    assert entries["item.salve.name"].source == "Field Salve"
    assert entries["item.salve.description"].source == "Restores HP."
    assert entries["story.intro.talk.line_001.text"].source == "Welcome."
    assert entries["story.intro.talk.line_001.speaker"].source == "Guide"

    saved = json.loads((registry.story_dir / "intro.json").read_text(encoding="utf-8"))
    assert saved["nodes"]["talk"]["lines"][0]["id"] == "line_001"


def test_registry_localizes_runtime_content_and_story(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Localized Game")
    registry.save_pawn(PawnDefinitionData(
        id="hero_pawn",
        name="Hero",
        sprite_key="hero",
    ))
    registry.save_attack(AttackDefinitionData(
        id="spark",
        name="Spark",
        description="A tiny bolt.",
        power=3,
        damage_type="physical",
    ))
    registry.save_character(PlayableCharacterDefinitionData(
        id="hero",
        pawn_id="hero_pawn",
        max_hp=20,
        attack=4,
        defense=2,
        attacks=("spark",),
    ))
    registry.save_item(ItemDefinitionData(
        id="salve",
        name="Salve",
        description="Restores HP.",
        heal=5,
    ))

    registry.add_locale("fr-FR", "Français")
    entries = {
        entry.key: entry
        for entry in registry.localization_entries()
    }
    # Newly-created resources are visible to localization after reload.
    registry.localization.set_translation(
        "fr-FR",
        LocalizationEntry("pawn.hero_pawn.name", "Hero", "Pawn name"),
        "Héroïne",
    )
    registry.localization.set_translation(
        "fr-FR",
        LocalizationEntry("attack.spark.name", "Spark", "Attack name"),
        "Étincelle",
    )
    registry.localization.set_translation(
        "fr-FR",
        LocalizationEntry("item.salve.name", "Salve", "Item name"),
        "Baume",
    )
    registry.set_active_locale("fr-FR")

    hero = registry.make_character("hero", leader=True)
    assert hero.name == "Héroïne"
    assert hero.skills[0].definition.name == "Étincelle"
    assert registry.item("salve").name == "Baume"


def test_story_localization_and_variable_formatting_keys_remain_stable(tmp_path):
    registry = ProjectRegistry.create_project(tmp_path / "game", "Localized Game")
    graph = StoryGraph.from_dict({
        "id": "counting",
        "entries": {"default": "talk"},
        "nodes": {
            "talk": {
                "type": "dialogue",
                "lines": [{
                    "id": "line_apples",
                    "speaker": "Guide",
                    "text": "You found {count} apples.",
                }],
                "next": "end",
            },
            "end": {"type": "end"},
        },
    })
    registry.add_locale("fr-FR", "Français")
    source_entry = LocalizationEntry(
        "story.counting.talk.line_apples.text",
        "You found {count} apples.",
        "Dialogue",
    )
    registry.localization.set_translation(
        "fr-FR",
        source_entry,
        "Vous avez trouvé {count} pommes.",
    )
    registry.set_active_locale("fr-FR")
    localized = registry.localize_story(graph)
    assert localized.nodes["talk"]["lines"][0]["text"] == "Vous avez trouvé {count} pommes."
    assert source_hash("You found {count} apples.") == source_entry.hash
