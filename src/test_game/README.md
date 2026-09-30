# Fox & Mara — The Familiar's Bargain

The bundled example project is now a small playable vertical slice of the witch/familiar story used while developing Mystery Engine.

## Playable sequence

1. **The village well** — Mara offers a familiar bond. The player can question the contract, its safeguards, truth clause, and the relationship it creates.
2. **Naming and transformation** — the woman signs with the name Marabeth Vale, rejects it for ordinary use, chooses the provisional name **Fox**, and the bond manifests as spontaneous shapeshifting.
3. **The hidden valley** — Fox arrives at Mara's secluded home and begins experiencing the mutual awareness created by the bond.
4. **Hearthlight Cottage** — the first night, breakfast, concrete magic rules, House rules, and Fox's stewardship amendment.
5. **Ancient Ruins** — after the cottage sequence, the three-floor dungeon opens as Fox and Mara's first expedition.
6. **Homecoming** — success awards a waystone shard and unlocks a final quiet scene at the cottage. Defeat and retreat return to the valley and allow another attempt.

The slice intentionally uses generic project systems rather than game-specific Python: scene triggers, story graphs, choices, flags/variables, gameplay actions, storage objects, dialogue voice cues, dungeon result stories, and persistent save/load state.

## Current visual compromise

There is not yet a separate pre-transformation human sprite for Fox. During the opening negotiation the underlying player actor is hidden; her current Fox sprite is revealed at the transformation beat. The stable runtime character ID remains `fox` throughout so saves and party data do not require a special migration.
