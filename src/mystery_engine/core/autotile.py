from __future__ import annotations

N, E, S, W = 1, 2, 4, 8
NW, NE, SE, SW = 16, 32, 64, 128


def _mask_from_same(same) -> int:
    """Build an 8-neighbor connectivity mask from a predicate on relative offsets."""
    n = same(0, -1)
    e = same(1, 0)
    s = same(0, 1)
    w = same(-1, 0)

    mask = 0
    if n:
        mask |= N
    if e:
        mask |= E
    if s:
        mask |= S
    if w:
        mask |= W

    if n and w and same(-1, -1):
        mask |= NW
    if n and e and same(1, -1):
        mask |= NE
    if s and e and same(1, 1):
        mask |= SE
    if s and w and same(-1, 1):
        mask |= SW
    return mask


def oriented_neighbor_mask(terrain, tx: int, ty: int, kind: str) -> int:
    """Return an 8-neighbor mask for an exploration autotile at (tx, ty)."""
    return _mask_from_same(lambda dx, dy: terrain.terrain_at(tx + dx, ty + dy) == kind)



def elevation_higher_mask(terrain, tx: int, ty: int) -> int:
    """Return the raw 8-neighbor mask of cells higher than the current cell.

    Unlike ordinary blob autotiling, diagonal bits are *not* suppressed when a
    cardinal neighbor is missing. Those diagonal relationships are exactly what
    distinguish convex and concave elevation corners in the SDF-generated atlas.
    """
    current = terrain.elevation_at(tx, ty)
    mask = 0
    checks = (
        (N, 0, -1), (E, 1, 0), (S, 0, 1), (W, -1, 0),
        (NW, -1, -1), (NE, 1, -1), (SE, 1, 1), (SW, -1, 1),
    )
    for bit, dx, dy in checks:
        if terrain.elevation_at(tx + dx, ty + dy) > current:
            mask |= bit
    return mask


def elevation_cliff_asset(terrain, tx: int, ty: int) -> str | None:
    """Return the main rock-face overlay for a lower cell."""
    mask = elevation_higher_mask(terrain, tx, ty)
    if mask == 0:
        return None
    return f"tiles/elevation_cliff_auto_{mask:03d}.png"


def elevation_cliff_assets(terrain, tx: int, ty: int) -> tuple[str, ...]:
    """Return the cliff overlay stack for a lower cell.

    The current orientation-aware cliff art bakes the grassy lip and foot
    vegetation into the main asset, so only one runtime PNG is needed per mask.
    """
    asset = elevation_cliff_asset(terrain, tx, ty)
    return () if asset is None else (asset,)


def dungeon_walkable_mask(floor, x: int, y: int) -> int:
    """Return an 8-neighbor mask for walkable dungeon connectivity."""
    from mystery_engine.dungeon.tiles import TileKind
    from mystery_engine.core.types import GridPos

    def walkable(dx: int, dy: int) -> bool:
        p = GridPos(x + dx, y + dy)
        return floor.in_bounds(p) and floor.tile(p).kind is not TileKind.WALL

    return _mask_from_same(walkable)


def autotile_asset(kind: str, mask: int) -> str:
    if kind not in {"path", "water", "dungeon_floor"}:
        raise ValueError(f"Unsupported oriented autotile kind: {kind}")
    prefix = {'dungeon_floor': 'dungeon_auto'}.get(kind, f'{kind}_auto')
    return f"tiles/{prefix}_{mask:03d}.png"
