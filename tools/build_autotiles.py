from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
TILES = ROOT / 'src' / 'test_game' / 'assets' / 'tiles'
SCALE = 4

N, E, S, W = 1, 2, 4, 8
NW, NE, SE, SW = 16, 32, 64, 128


def load(name: str) -> Image.Image:
    return Image.open(TILES / name).convert('RGBA')


def has(mask: int, bit: int) -> bool:
    return bool(mask & bit)




def valid_blob_masks() -> tuple[int, ...]:
    out = []
    for mask in range(256):
        n, e, s, w = (has(mask, b) for b in (N, E, S, W))
        if has(mask, NW) and not (n and w):
            continue
        if has(mask, NE) and not (n and e):
            continue
        if has(mask, SE) and not (s and e):
            continue
        if has(mask, SW) and not (s and w):
            continue
        out.append(mask)
    return tuple(out)


def shape_mask(mask: int, size: int, *, inset: int, radius: int) -> Image.Image:
    """Build a high-resolution binary/AA shape for one explicit 8-neighbor autotile.

    The center belongs to the terrain. Cardinal neighbors extend the terrain to
    the relevant tile edge. A diagonal fills its corner only when both adjacent
    cardinal connections also exist, so concave corners remain explicit.
    """
    hs = size * SCALE
    im = Image.new('L', (hs, hs), 0)
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    m = inset * SCALE
    r = radius * SCALE
    half = hs // 2

    # Rounded center body.
    d.rounded_rectangle((m, m, hs - m, hs - m), radius=r, fill=255)

    n, e, s, w = (has(mask, b) for b in (N, E, S, W))
    nw, ne, se, sw = (has(mask, b) for b in (NW, NE, SE, SW))

    # Cardinal arms to tile edges.
    if n:
        d.rectangle((m, 0, hs - m, half + m), fill=255)
    if s:
        d.rectangle((m, half - m, hs - m, hs), fill=255)
    if w:
        d.rectangle((0, m, half + m, hs - m), fill=255)
    if e:
        d.rectangle((half - m, m, hs, hs - m), fill=255)

    cardinal_count = sum((n, e, s, w))

    # A simple 90-degree bend needs its inside quadrant filled even when there is
    # no diagonal terrain cell. For broader T/cross/blob shapes, a missing
    # diagonal is instead a genuine concave corner and remains grass.
    def fills_corner(a: bool, b: bool, diagonal: bool) -> bool:
        return a and b and (diagonal or cardinal_count <= 2)

    if fills_corner(n, w, nw):
        d.rectangle((0, 0, half + m, half + m), fill=255)
    if fills_corner(n, e, ne):
        d.rectangle((half - m, 0, hs, half + m), fill=255)
    if fills_corner(s, e, se):
        d.rectangle((half - m, half - m, hs, hs), fill=255)
    if fills_corner(s, w, sw):
        d.rectangle((0, half - m, half + m, hs), fill=255)

    # Explicit concave corners only for broad blob/T/cross situations.
    cut = (radius + inset) * SCALE
    if cardinal_count >= 3 and n and w and not nw:
        d.ellipse((-cut, -cut, cut, cut), fill=0)
    if cardinal_count >= 3 and n and e and not ne:
        d.ellipse((hs - cut, -cut, hs + cut, cut), fill=0)
    if cardinal_count >= 3 and s and e and not se:
        d.ellipse((hs - cut, hs - cut, hs + cut, hs + cut), fill=0)
    if cardinal_count >= 3 and s and w and not sw:
        d.ellipse((-cut, hs - cut, cut, hs + cut), fill=0)

    return im.resize((size, size), Image.Resampling.LANCZOS)


def build_one(kind: str, mask: int) -> Image.Image:
    grass = load('grass_0.png' if (TILES / 'grass_0.png').exists() else 'grass.png')
    material = load('path_center.png' if kind == 'path' else 'water_center.png')
    size = material.width

    if kind == 'path':
        inset, radius = 9, 12
        edge_rgba = (84, 124, 66, 150)
        edge_width = 2
    else:
        inset, radius = 7, 12
        edge_rgba = (211, 242, 251, 190)
        edge_width = 2

    mask_img = shape_mask(mask, size, inset=inset, radius=radius)
    out = Image.composite(material, grass, mask_img)

    # Explicit shoreline/grass lip, pre-baked into the tile. This is generated
    # once as an asset; the renderer does no post-hoc shape adjustment.
    # Edge ring = dilated terrain mask minus terrain mask.
    dilated = mask_img.filter(ImageFilter.MaxFilter(edge_width * 2 + 1))
    ring = ImageChops.subtract(dilated, mask_img)
    edge = Image.new('RGBA', (size, size), edge_rgba)
    out.alpha_composite(Image.composite(edge, Image.new('RGBA', (size, size), (0, 0, 0, 0)), ring))
    return out


def main() -> None:
    for kind in ('path', 'water'):
        for mask in valid_blob_masks():
            img = build_one(kind, mask)
            img.save(TILES / f'{kind}_auto_{mask:03d}.png')
    print(f'Wrote {2 * len(valid_blob_masks())} reachable oriented autotiles to {TILES}')


if __name__ == '__main__':
    main()
