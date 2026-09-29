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
    description="Send a bolt of lightning down a straight line.",
    target=TargetKind.ENEMY,
    range=10,
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
    description="Restore 11 HP to all allies in the room.",
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
    description="Fire a piercing needle down a straight line.",
    target=TargetKind.ENEMY,
    range=10,
    power=2,
    damage_type="piercing",
    max_charges=None,
    sfx_cue="magic.bolt_launch",
    impact_sfx_cue="magic.bolt_impact",
    projectile_key="needle",
    range_pattern=RangePattern.LINE,
)

LOST_LANTERN_GLOW_SHOT = SkillDefinition(
    id="lost_lantern_glow_shot",
    name="Glow Shot",
    description="Launch a slow-burning mote down a straight line.",
    target=TargetKind.ENEMY,
    range=6,
    power=4,
    damage_type="spirit",
    max_charges=8,
    sfx_cue="magic.bolt_launch",
    impact_sfx_cue="magic.bolt_impact",
    range_pattern=RangePattern.LINE,
)

LOST_LANTERN_FLARE = SkillDefinition(
    id="lost_lantern_flare",
    name="Lantern Flare",
    description="Flood the current room with a brief pulse of ghost-light.",
    target=TargetKind.ENEMY,
    range=4,
    power=2,
    damage_type="spirit",
    max_charges=2,
    sfx_cue="magic.arcane_cast",
    impact_sfx_cue="magic.bolt_impact",
    range_pattern=RangePattern.ROOM,
)

MIRROR_SHADE_SHARD_VOLLEY = SkillDefinition(
    id="mirror_shade_shard_volley",
    name="Shard Volley",
    description="Fire a reflected shard down a straight line.",
    target=TargetKind.ENEMY,
    range=7,
    power=4,
    damage_type="piercing",
    max_charges=7,
    accuracy=0.90,
    sfx_cue="magic.bolt_launch",
    impact_sfx_cue="magic.bolt_impact",
    range_pattern=RangePattern.LINE,
)

MIRROR_SHADE_REFLECTED_LUNGE = SkillDefinition(
    id="mirror_shade_reflected_lunge",
    name="Reflected Lunge",
    description="Snap forward through a reflected angle to strike up to two cells away.",
    target=TargetKind.ENEMY,
    range=2,
    power=5,
    damage_type="shadow",
    max_charges=5,
    sfx_cue="combat.light_hit",
    range_pattern=RangePattern.TWO_TILES,
)

WEAVING_WISP_WAVE_BURST = SkillDefinition(
    id="weaving_wisp_wave_burst",
    name="Wave Burst",
    description="Send a wavering pulse of memory-light down a straight line.",
    target=TargetKind.ENEMY,
    range=5,
    power=3,
    damage_type="arcane",
    max_charges=8,
    sfx_cue="magic.bolt_launch",
    impact_sfx_cue="magic.bolt_impact",
    range_pattern=RangePattern.LINE,
)

WEAVING_WISP_MEMORY_RIPPLE = SkillDefinition(
    id="weaving_wisp_memory_ripple",
    name="Memory Ripple",
    description="Disturb every foe in the room with an unstable recollection.",
    target=TargetKind.ENEMY,
    range=4,
    power=2,
    damage_type="arcane",
    max_charges=2,
    sfx_cue="magic.arcane_cast",
    range_pattern=RangePattern.ROOM,
)

CLOCKWORK_SENTINEL_PENDULUM_SWEEP = SkillDefinition(
    id="clockwork_sentinel_pendulum_sweep",
    name="Pendulum Sweep",
    description="Sweep a heavy arm through a target up to two cells away.",
    target=TargetKind.ENEMY,
    range=2,
    power=5,
    damage_type="physical",
    max_charges=6,
    sfx_cue="combat.heavy_hit",
    range_pattern=RangePattern.TWO_TILES,
)

CLOCKWORK_SENTINEL_TIME_PULSE = SkillDefinition(
    id="clockwork_sentinel_time_pulse",
    name="Time Pulse",
    description="Release a short clockwork pulse through the entire room.",
    target=TargetKind.ENEMY,
    range=4,
    power=3,
    damage_type="arcane",
    max_charges=2,
    sfx_cue="magic.arcane_cast",
    impact_sfx_cue="magic.bolt_impact",
    range_pattern=RangePattern.ROOM,
)

FORGOTTEN_HOUND_POUNCE = SkillDefinition(
    id="forgotten_hound_pounce",
    name="Pounce",
    description="Leap at a target up to two cells away.",
    target=TargetKind.ENEMY,
    range=2,
    power=5,
    damage_type="physical",
    max_charges=5,
    sfx_cue="combat.heavy_hit",
    range_pattern=RangePattern.TWO_TILES,
)

FORGOTTEN_HOUND_SHADOW_REND = SkillDefinition(
    id="forgotten_hound_shadow_rend",
    name="Shadow Rend",
    description="Tear at an adjacent target with lingering shadow.",
    target=TargetKind.ENEMY,
    range=1,
    power=4,
    damage_type="shadow",
    max_charges=None,
    sfx_cue="combat.light_hit",
    range_pattern=RangePattern.ADJACENT,
)

VEIL_BLOOM_SPORE_BURST = SkillDefinition(
    id="veil_bloom_spore_burst",
    name="Spore Burst",
    description="Scatter luminous spores through the current room.",
    target=TargetKind.ENEMY,
    range=4,
    power=2,
    damage_type="plant",
    max_charges=3,
    sfx_cue="magic.arcane_cast",
    impact_sfx_cue="magic.bolt_impact",
    range_pattern=RangePattern.ROOM,
)

VEIL_BLOOM_ROOT_LASH = SkillDefinition(
    id="veil_bloom_root_lash",
    name="Root Lash",
    description="Whip a root at a target up to two cells away.",
    target=TargetKind.ENEMY,
    range=2,
    power=4,
    damage_type="physical",
    max_charges=6,
    sfx_cue="combat.light_hit",
    range_pattern=RangePattern.TWO_TILES,
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


def make_lost_lantern(identifier: str) -> Character:
    return Character(
        id=identifier,
        name="Lost Lantern",
        stats=Stats(max_hp=15, attack=3, defense=1),
        skills=[
            SkillRuntime.from_definition(LOST_LANTERN_GLOW_SHOT),
            SkillRuntime.from_definition(LOST_LANTERN_FLARE),
        ],
        resistances={"physical": 0.75, "lightning": 1.2},
        hostile=True,
        metadata={"sprite_key": "lost_lantern"},
    )


def make_mirror_shade(identifier: str) -> Character:
    return Character(
        id=identifier,
        name="Mirror Shade",
        stats=Stats(max_hp=18, attack=4, defense=2),
        skills=[
            SkillRuntime.from_definition(MIRROR_SHADE_SHARD_VOLLEY),
            SkillRuntime.from_definition(MIRROR_SHADE_REFLECTED_LUNGE),
        ],
        resistances={"physical": 0.7, "arcane": 1.3},
        hostile=True,
        metadata={"sprite_key": "mirror_shade"},
    )


def make_weaving_wisp(identifier: str) -> Character:
    return Character(
        id=identifier,
        name="Weaving Wisp",
        stats=Stats(max_hp=13, attack=3, defense=1),
        skills=[
            SkillRuntime.from_definition(WEAVING_WISP_WAVE_BURST),
            SkillRuntime.from_definition(WEAVING_WISP_MEMORY_RIPPLE),
        ],
        resistances={"lightning": 0.6},
        hostile=True,
        metadata={"sprite_key": "weaving_wisp"},
    )


def make_clockwork_sentinel(identifier: str) -> Character:
    return Character(
        id=identifier,
        name="Clockwork Sentinel",
        stats=Stats(max_hp=28, attack=5, defense=5),
        skills=[
            SkillRuntime.from_definition(CLOCKWORK_SENTINEL_TIME_PULSE),
            SkillRuntime.from_definition(CLOCKWORK_SENTINEL_PENDULUM_SWEEP),
        ],
        resistances={"physical": 0.85, "lightning": 1.25},
        hostile=True,
        metadata={"sprite_key": "clockwork_sentinel"},
    )


def make_forgotten_hound(identifier: str) -> Character:
    return Character(
        id=identifier,
        name="Forgotten Hound",
        stats=Stats(max_hp=24, attack=6, defense=3),
        skills=[
            SkillRuntime.from_definition(FORGOTTEN_HOUND_POUNCE),
            SkillRuntime.from_definition(FORGOTTEN_HOUND_SHADOW_REND),
        ],
        resistances={"shadow": 0.7},
        hostile=True,
        metadata={"sprite_key": "forgotten_hound"},
    )


def make_veil_bloom(identifier: str) -> Character:
    return Character(
        id=identifier,
        name="Veil Bloom",
        stats=Stats(max_hp=20, attack=4, defense=3),
        skills=[
            SkillRuntime.from_definition(VEIL_BLOOM_SPORE_BURST),
            SkillRuntime.from_definition(VEIL_BLOOM_ROOT_LASH),
        ],
        resistances={"piercing": 0.85, "lightning": 1.2},
        hostile=True,
        metadata={"sprite_key": "veil_bloom"},
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
    "lost_lantern": make_lost_lantern,
    "mirror_shade": make_mirror_shade,
    "weaving_wisp": make_weaving_wisp,
    "clockwork_sentinel": make_clockwork_sentinel,
    "forgotten_hound": make_forgotten_hound,
    "veil_bloom": make_veil_bloom,
}

ENEMY_LABELS = {
    "mossling": "Mossling",
    "needle_wisp": "Needle Wisp",
    "lost_lantern": "Lost Lantern",
    "mirror_shade": "Mirror Shade",
    "weaving_wisp": "Weaving Wisp",
    "clockwork_sentinel": "Clockwork Sentinel",
    "forgotten_hound": "Forgotten Hound",
    "veil_bloom": "Veil Bloom",
}

ITEM_CATALOG = {
    FIELD_SALVE.id: FIELD_SALVE,
    THROWING_STONE.id: THROWING_STONE,
    WAYSTONE_SHARD.id: WAYSTONE_SHARD,
}

ITEM_LABELS = {item_id: item.name for item_id, item in ITEM_CATALOG.items()}
