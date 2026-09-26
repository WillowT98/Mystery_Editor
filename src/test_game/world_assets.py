from __future__ import annotations

from mystery_engine.story import RectObstacle, WorldAssetCatalog, WorldAssetDefinition


WORLD_ASSETS = WorldAssetCatalog(
    assets={
        "tree": WorldAssetDefinition(
            id="tree", category="scenery", sprite_key="tree", display_name="Tree",
            size=(196, 230), collision=RectObstacle(-27, -58, 54, 58),
        ),
        "boulder": WorldAssetDefinition(
            id="boulder", category="scenery", sprite_key="boulder", display_name="Boulder",
            size=(146, 120), collision=RectObstacle(-62, -72, 124, 68),
        ),
        "flower_bush": WorldAssetDefinition(
            id="flower_bush", category="scenery", sprite_key="flower_bush", display_name="Flower bush",
            size=(121, 105), draw_behind_actors=True, collision=RectObstacle(-48, -34, 96, 34),
        ),
        "bush": WorldAssetDefinition(
            id="bush", category="scenery", sprite_key="bush", display_name="Bush",
            size=(126, 100), draw_behind_actors=True, collision=RectObstacle(-38, -30, 76, 30),
        ),
        "fence": WorldAssetDefinition(
            id="fence", category="scenery", sprite_key="fence", display_name="Fence",
            size=(206, 100), collision=RectObstacle(-99, -34, 198, 28),
        ),
        "signpost": WorldAssetDefinition(
            id="signpost", category="scenery", sprite_key="signpost", display_name="Signpost",
            size=(106, 110), collision=RectObstacle(-22, -42, 44, 42),
        ),
        "waystone": WorldAssetDefinition(
            id="waystone", category="interactable", sprite_key="waystone", display_name="Waystone",
            size=(112, 132), collision=RectObstacle(-40, -27, 80, 27),
            label="Waystone", action_id="inspect_waystone",
        ),
        "dungeon_gate": WorldAssetDefinition(
            id="dungeon_gate", category="interactable", sprite_key="dungeon_gate", display_name="Dungeon entrance",
            size=(192, 150),
            # Only the rear/back wall of the entrance is solid. The opening and
            # foreground path remain approachable from the south so the player
            # can still walk up to the doorway and interact with it, while the
            # collider prevents walking behind the cave sprite from the north.
            collision=RectObstacle(-88, -136, 176, 58),
            label="Dungeon entrance", action_id="enter_test_dungeon",
        ),
        "scene_door": WorldAssetDefinition(
            id="scene_door", category="portal", sprite_key=None, display_name="Scene door",
            # Scene doors are editor-visible markers only. At runtime they are
            # invisible interactables that transition to another exploration scene.
            size=(72, 56), collision=None, label="Door", runtime_visible=False,
        ),
        "fox": WorldAssetDefinition(
            id="fox", category="actor", sprite_key="fox", display_name="Fox",
            actor_name="Fox", color_key="fox", radius=28.0,
        ),
        "mara": WorldAssetDefinition(
            id="mara", category="actor", sprite_key="mara", display_name="Mara",
            actor_name="Mara", color_key="mara", radius=28.0, action_id="talk_mara",
        ),
    }
)
