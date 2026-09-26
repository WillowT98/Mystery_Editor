from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from mystery_engine.presentation.sfx import SoundCueCatalog


class SoundCueCatalogTests(unittest.TestCase):
    def test_loads_variants_and_categories(self):
        payload = {
            "format": 1,
            "cues": [
                {
                    "id": "ui.confirm",
                    "label": "Confirm",
                    "category": "Ui",
                    "variants": ["sfx/ui/confirm_01.ogg", "sfx/ui/confirm_02.ogg"],
                    "volume": 0.75,
                    "cooldown": 0.03,
                },
                {
                    "id": "ambience.night_field",
                    "label": "Night Field",
                    "category": "Ambience",
                    "variants": ["sfx/ambience/night_field_01.ogg"],
                    "loop": True,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sfx_cues.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            catalog = SoundCueCatalog.load(path)
        self.assertEqual(len(catalog.all()), 2)
        self.assertEqual(catalog.get("ui.confirm").variants[1], "sfx/ui/confirm_02.ogg")
        self.assertTrue(catalog.get("ambience.night_field").loop)
        self.assertEqual([c.id for c in catalog.by_category("ambience")], ["ambience.night_field"])

    def test_missing_catalog_is_empty(self):
        catalog = SoundCueCatalog.load(Path("definitely_missing_sfx_catalog.json"))
        self.assertEqual(catalog.all(), [])
        self.assertIsNone(catalog.get("ui.confirm"))


if __name__ == "__main__":
    unittest.main()
