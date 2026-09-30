from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT / "src" / "mystery_engine"
EXAMPLE_ROOT = ROOT / "src" / "test_game"


def test_engine_never_imports_example_project():
    violations: list[str] = []
    for path in ENGINE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "test_game" or name.startswith("test_game.") for name in names):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_example_project_has_no_custom_python_runtime():
    obsolete = {
        "content.py",
        "game_definition.py",
        "world_assets.py",
    }
    present = {path.name for path in EXAMPLE_ROOT.glob("*.py")}
    assert obsolete.isdisjoint(present)


def test_only_unified_editor_launcher_is_shipped():
    assert (ROOT / "run_project_editor.py").exists()
    for obsolete in ("run_editor.py", "run_dungeon_editor.py", "run_story_editor.py"):
        assert not (ROOT / obsolete).exists()
