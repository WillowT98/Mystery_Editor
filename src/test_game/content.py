from __future__ import annotations

from mystery_engine.core import (
    AITactic,
    Character,
    Inventory,
    ItemDefinition,
    RangePattern,
    SkillDefinition,
    SkillRuntime,
    Stats,
    TargetKind,
    Wallet,
)


# ---------- items ----------

FIELD_SALVE = ItemDefinition(
    id="field_salve",
    name="Field Salve",
    description="A small jar of salve. Restores 14 HP to the user.",
    heal=14,
)

THROWING_STONE = ItemDefinition(
    id="throwing_stone",
    name="Throwing Stone",
    description="A smooth, palm-sized stone. Can be thrown in a straight line for 10 physical damage.",
    throwable_damage=10,
    damage_type="physical",
    projectile_key="stone",
    projectile_arc_px=24.0,
)

WAYSTONE_SHARD = ItemDefinition(
    id="waystone_shard",
    name="Waystone Shard",
    description="A test key item used to verify that protected items survive defeat.",
    droppable=False,
    key_item=True,
)


# ---------- skills ----------

FOX_LUNGE = SkillDefinition(
    id="fox_lunge",
    name="Lunge",
    description="Strike a target up to two cells away in the facing direction.",
    target=TargetKind.ENEMY,
    range=2,
    power=7,
    damage_type="physical",
    max_charges=8,
    sfx_cue="combat.light_hit",
    range_pattern=RangePattern.TWO_TILES,
)

MARA_SPARK = SkillDefinition(
    id="mara_spark",
    name="Spark",
    description="A ranged bolt of lightning.",
    target=TargetKind.ENEMY,
    range=5,
    power=5,
    damage_type="lightning",
    max_charges=10,
    sfx_cue="magic.bolt_launch",
    impact_sfx_cue="magic.bolt_impact",
    projectile_key="spark",
    range_pattern=RangePattern.LINE,
)

MARA_MEND = SkillDefinition(
    id="mara_mend",
    name="Mend",
    description="Restore 11 HP to an ally.",
    target=TargetKind.ALLY,
    range=4,
    heal=11,
    max_charges=6,
    sfx_cue="magic.heal",
    range_pattern=RangePattern.ROOM,
)

WISP_BOLT = SkillDefinition(
    id="wisp_bolt",
    name="Needle Bolt",
    description="A simple ranged enemy attack.",
    target=TargetKind.ENEMY,
    range=4,
    power=2,
    damage_type="piercing",
    max_charges=None,
    sfx_cue="magic.bolt_launch",
    impact_sfx_cue="magic.bolt_impact",
    projectile_key="needle",
    range_pattern=RangePattern.LINE,
)


# ---------- characters ----------


def make_fox() -> Character:
    return Character(
        id="fox",
        name="Fox",
        stats=Stats(max_hp=46, attack=8, defense=5),
        skills=[SkillRuntime.from_definition(FOX_LUNGE)],
        party_member=True,
        leader=True,
        metadata={"sprite_key": "fox", "portrait_key": "fox"},
    )


def make_mara() -> Character:
    return Character(
        id="mara",
        name="Mara",
        stats=Stats(max_hp=38, attack=6, defense=4),
        skills=[SkillRuntime.from_definition(MARA_SPARK), SkillRuntime.from_definition(MARA_MEND)],
        party_member=True,
        ai_tactic=AITactic.PROTECT,
        metadata={"sprite_key": "mara", "portrait_key": "mara"},
    )


def make_mossling(identifier: str) -> Character:
    return Character(
        id=identifier,
        name="Mossling",
        stats=Stats(max_hp=16, attack=3, defense=2),
        hostile=True,
        metadata={"sprite_key": "mossling", "portrait_key": "mossling"},
    )


def make_needle_wisp(identifier: str) -> Character:
    return Character(
        id=identifier,
        name="Needle Wisp",
        stats=Stats(max_hp=14, attack=2, defense=1),
        skills=[SkillRuntime.from_definition(WISP_BOLT)],
        resistances={"lightning": 0.6},
        hostile=True,
        metadata={"sprite_key": "needle_wisp", "portrait_key": "needle_wisp"},
    )


def make_starting_bag() -> Inventory:
    bag = Inventory(capacity=12)
    bag.add(FIELD_SALVE, 4)
    bag.add(THROWING_STONE, 3)
    bag.add(WAYSTONE_SHARD, 1)
    return bag


# ---------- editor/runtime content catalogs ----------

ENEMY_FACTORIES = {
    "mossling": make_mossling,
    "needle_wisp": make_needle_wisp,
}

ENEMY_LABELS = {
    "mossling": "Mossling",
    "needle_wisp": "Needle Wisp",
}

ITEM_CATALOG = {
    FIELD_SALVE.id: FIELD_SALVE,
    THROWING_STONE.id: THROWING_STONE,
    WAYSTONE_SHARD.id: WAYSTONE_SHARD,
}

ITEM_LABELS = {item_id: item.name for item_id, item in ITEM_CATALOG.items()}
