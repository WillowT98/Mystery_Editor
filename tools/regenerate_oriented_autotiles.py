from pathlib import Path
import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageDraw

N, E, S, W = 1, 2, 4, 8
NW, NE, SE, SW = 16, 32, 64, 128


def booleans(mask):
    return bool(mask & N), bool(mask & E), bool(mask & S), bool(mask & W), bool(mask & NW), bool(mask & NE), bool(mask & SE), bool(mask & SW)




def valid_blob_masks() -> tuple[int, ...]:
    """Masks reachable through `_mask_from_same`-style blob autotiling.

    Diagonal bits are only legal when both adjacent cardinal bits are set, so
    only 47 of the 256 bit patterns can ever be requested by path, water, or
    dungeon-floor rendering.
    """
    out = []
    for mask in range(256):
        n, e, s, w, nw, ne, se, sw = booleans(mask)
        if nw and not (n and w):
            continue
        if ne and not (n and e):
            continue
        if se and not (s and e):
            continue
        if sw and not (s and w):
            continue
        out.append(mask)
    return tuple(out)


def make_mask(size: int, margin: int, radius: int, inner_radius: int, mask: int) -> Image.Image:
    n, e, s, w, nw, ne, se, sw = booleans(mask)
    y, x = np.mgrid[0:size, 0:size]
    left = 0 if w else margin
    top = 0 if n else margin
    right = size if e else size - margin
    bottom = size if s else size - margin
    inside = (x >= left) & (x < right) & (y >= top) & (y < bottom)
    r = min(radius, max(1, (right - left) // 2), max(1, (bottom - top) // 2))

    # convex outer corners
    if not n and not w:
        cx, cy = left + r, top + r
        corner = (x < cx) & (y < cy)
        inside &= (~corner) | (((x - cx) ** 2 + (y - cy) ** 2) <= r * r)
    if not n and not e:
        cx, cy = right - r - 1, top + r
        corner = (x > cx) & (y < cy)
        inside &= (~corner) | (((x - cx) ** 2 + (y - cy) ** 2) <= r * r)
    if not s and not e:
        cx, cy = right - r - 1, bottom - r - 1
        corner = (x > cx) & (y > cy)
        inside &= (~corner) | (((x - cx) ** 2 + (y - cy) ** 2) <= r * r)
    if not s and not w:
        cx, cy = left + r, bottom - r - 1
        corner = (x < cx) & (y > cy)
        inside &= (~corner) | (((x - cx) ** 2 + (y - cy) ** 2) <= r * r)

    # concave inner corners: the notch radius must equal the edge inset so the
    # tangent points land exactly on the exposed straight edges.
    ir = inner_radius
    if n and w and not nw:
        inside &= ((x ** 2 + y ** 2) >= ir * ir)
    if n and e and not ne:
        inside &= (((x - (size - 1)) ** 2 + y ** 2) >= ir * ir)
    if s and e and not se:
        inside &= (((x - (size - 1)) ** 2 + (y - (size - 1)) ** 2) >= ir * ir)
    if s and w and not sw:
        inside &= ((x ** 2 + (y - (size - 1)) ** 2) >= ir * ir)

    arr = np.where(inside, 255, 0).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def render_masked(fill: Image.Image, background: Image.Image, mask: Image.Image) -> Image.Image:
    base = background.copy()
    terrain = fill.copy()
    terrain.putalpha(mask)
    base.alpha_composite(terrain)
    return base


def add_shoreline(img: Image.Image, mask: Image.Image, color=(215, 245, 255, 0)) -> Image.Image:
    eroded = mask.filter(ImageFilter.MinFilter(5))
    border = ImageChops.subtract(mask, eroded).filter(ImageFilter.GaussianBlur(0.5))
    line = Image.new("RGBA", img.size, color)
    line.putalpha(border)
    img = img.copy()
    img.alpha_composite(line)
    return img


def add_dungeon_masonry(img: Image.Image, mask: Image.Image, stone_texture: Image.Image) -> Image.Image:
    """Add an explicit textured masonry rim on the wall side of the floor boundary."""
    # A 9px-ish band outside the walkable shape gives the walls visual mass while
    # preserving the same canonical curves as the floor mask.
    dilated = mask.filter(ImageFilter.MaxFilter(19))
    outer_band = ImageChops.subtract(dilated, mask)
    out = img.copy()
    stone = stone_texture.copy()
    stone.putalpha(outer_band)
    out.alpha_composite(stone)

    # Add a narrow contact shadow just inside the floor edge so the masonry rim
    # reads as raised structure rather than a flat white outline.
    eroded = mask.filter(ImageFilter.MinFilter(5))
    inner_band = ImageChops.subtract(mask, eroded).filter(ImageFilter.GaussianBlur(0.35))
    shadow = Image.new("RGBA", img.size, (26, 24, 22, 0))
    shadow.putalpha(inner_band.point(lambda a: int(a * 0.55)))
    out.alpha_composite(shadow)
    return out



def make_exploration_boundary_overlay(mask: Image.Image, cliff_texture: Image.Image, grass_texture: Image.Image) -> Image.Image:
    """Transparent concept-art style cliff border overlay for playable tiles.

    The playable part of the tile remains transparent, while the outside portion
    becomes a substantial rocky boundary face with a grassy lip and contact
    shadow. This is intentionally much thicker than the old thin line overlay.
    """
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    outside = ImageChops.invert(mask)

    rock = cliff_texture.copy()
    rock.putalpha(outside)
    out.alpha_composite(rock)

    eroded_outside = outside.filter(ImageFilter.MinFilter(13))
    void_band = ImageChops.subtract(outside, eroded_outside).filter(ImageFilter.GaussianBlur(0.7))
    void_shadow = Image.new("RGBA", mask.size, (12, 14, 22, 0))
    void_shadow.putalpha(void_band.point(lambda a: int(a * 0.65)))
    out.alpha_composite(void_shadow)

    eroded = mask.filter(ImageFilter.MinFilter(9))
    inner_lip = ImageChops.subtract(mask, eroded)
    grass = grass_texture.copy()
    grass.putalpha(inner_lip)
    out.alpha_composite(grass)

    eroded2 = mask.filter(ImageFilter.MinFilter(15))
    shadow_band = ImageChops.subtract(eroded, eroded2).filter(ImageFilter.GaussianBlur(0.6))
    shadow = Image.new("RGBA", mask.size, (34, 26, 30, 0))
    shadow.putalpha(shadow_band.point(lambda a: int(a * 0.55)))
    out.alpha_composite(shadow)

    lip_highlight = inner_lip.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.4))
    highlight = Image.new("RGBA", mask.size, (210, 224, 128, 0))
    highlight.putalpha(lip_highlight.point(lambda a: int(a * 0.22)))
    out.alpha_composite(highlight)
    return out


def _tile_texture(tex: Image.Image, size: tuple[int, int]) -> Image.Image:
    if tex.size == size:
        return tex.copy()
    return tex.resize(size, Image.Resampling.LANCZOS)


def _solid_rgba(size: tuple[int, int], color: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", size, color)


def _compose_with_mask(base: Image.Image, top: Image.Image, mask: Image.Image) -> None:
    layer = top.copy()
    layer.putalpha(mask)
    base.alpha_composite(layer)


def _generate_edge_band_masks(width: int, height: int, orientation: str) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Return masks for lower grass, rock face, and upper grass strip.

    These are larger-than-cell sprites intended to span both the blocking cliff
    cell and the adjacent visible interior cell, so the result reads as a real
    cliff rather than a decorative border.
    """
    hi = 4
    W, H = width * hi, height * hi
    import math
    from PIL import Image
    lower = Image.new('L', (W, H), 0)
    rock = Image.new('L', (W, H), 0)
    upper = Image.new('L', (W, H), 0)
    lp = lower.load(); rp = rock.load(); up = upper.load()

    if orientation in ('n', 's'):
        # from outer side inward: void -> upper grass -> rock face -> lower grass
        void_band = 10 * hi
        upper_band = 22 * hi
        rock_band = 42 * hi

        for x in range(W):
            wob = int(round(6 * hi * math.sin(x / 27.0) + 3 * hi * math.sin(x / 11.0)))
            if orientation == 'n':
                b0 = void_band + wob // 5
                b1 = b0 + upper_band + wob // 8
                b2 = b1 + rock_band + wob // 10
                for y in range(H):
                    if y < b0:
                        continue
                    elif y < b1:
                        up[x, y] = 255
                    elif y < b2:
                        rp[x, y] = 255
                    else:
                        lp[x, y] = 255
            else:  # south, reversed vertically
                b0 = H - void_band + wob // 5
                b1 = b0 - upper_band + wob // 8
                b2 = b1 - rock_band + wob // 10
                for y in range(H):
                    if y >= b0:
                        continue
                    elif y >= b1:
                        up[x, y] = 255
                    elif y >= b2:
                        rp[x, y] = 255
                    else:
                        lp[x, y] = 255
    else:
        void_band = 10 * hi
        upper_band = 22 * hi
        rock_band = 42 * hi
        for y in range(H):
            wob = int(round(6 * hi * math.sin(y / 27.0) + 3 * hi * math.sin(y / 11.0)))
            if orientation == 'w':
                b0 = void_band + wob // 5
                b1 = b0 + upper_band + wob // 8
                b2 = b1 + rock_band + wob // 10
                for x in range(W):
                    if x < b0:
                        continue
                    elif x < b1:
                        up[x, y] = 255
                    elif x < b2:
                        rp[x, y] = 255
                    else:
                        lp[x, y] = 255
            else:  # east
                b0 = W - void_band + wob // 5
                b1 = b0 - upper_band + wob // 8
                b2 = b1 - rock_band + wob // 10
                for x in range(W):
                    if x >= b0:
                        continue
                    elif x >= b1:
                        up[x, y] = 255
                    elif x >= b2:
                        rp[x, y] = 255
                    else:
                        lp[x, y] = 255

    return (lower.resize((width, height), Image.Resampling.LANCZOS),
            rock.resize((width, height), Image.Resampling.LANCZOS),
            upper.resize((width, height), Image.Resampling.LANCZOS))


def _generate_corner_band_masks(size: int, corner: str) -> tuple[Image.Image, Image.Image, Image.Image]:
    hi = 4
    S = size * hi
    import math
    from PIL import Image
    lower = Image.new('L', (S, S), 0)
    rock = Image.new('L', (S, S), 0)
    upper = Image.new('L', (S, S), 0)
    lp = lower.load(); rp = rock.load(); up = upper.load()
    centers = {
        'nw': (0, 0),
        'ne': (S - 1, 0),
        'sw': (0, S - 1),
        'se': (S - 1, S - 1),
    }
    cx, cy = centers[corner]
    r_void = 10 * hi
    r_upper = r_void + 22 * hi
    r_rock = r_upper + 42 * hi
    for y in range(S):
        for x in range(S):
            dx = x - cx
            dy = y - cy
            d = math.hypot(dx, dy)
            wob = 5 * hi * math.sin((x + y) / 31.0) + 2 * hi * math.sin((x - y) / 13.0)
            d2 = d + wob
            if d2 < r_void:
                continue
            elif d2 < r_upper:
                up[x, y] = 255
            elif d2 < r_rock:
                rp[x, y] = 255
            else:
                lp[x, y] = 255
    return (lower.resize((size, size), Image.Resampling.LANCZOS),
            rock.resize((size, size), Image.Resampling.LANCZOS),
            upper.resize((size, size), Image.Resampling.LANCZOS))


def _render_multi_depth_cliff(size: tuple[int, int], grass_tex: Image.Image, rock_tex: Image.Image, lower_mask: Image.Image, rock_mask: Image.Image, upper_mask: Image.Image) -> Image.Image:
    out = _solid_rgba(size, (5, 7, 14, 255))
    # Upper plateau strip (higher elevation)
    _compose_with_mask(out, grass_tex, upper_mask)
    # Rock face
    _compose_with_mask(out, rock_tex, rock_mask)
    # Lower playable grass
    _compose_with_mask(out, grass_tex, lower_mask)

    # Shadow under upper grass lip, to show overhang above the cliff face.
    up_inner = upper_mask.filter(ImageFilter.MinFilter(13))
    up_edge = ImageChops.subtract(upper_mask, up_inner).filter(ImageFilter.GaussianBlur(1.0))
    shadow = _solid_rgba(size, (46, 34, 28, 0))
    shadow.putalpha(up_edge.point(lambda a: int(a * 0.82)))
    out.alpha_composite(shadow)

    # Highlight on the top of the raised strip.
    highlight = _solid_rgba(size, (216, 236, 144, 0))
    highlight.putalpha(up_edge.point(lambda a: int(a * 0.26)))
    out.alpha_composite(highlight)

    # Slight darkening at the base of the rock face where it meets lower grass.
    rock_inner = rock_mask.filter(ImageFilter.MinFilter(13))
    rock_edge = ImageChops.subtract(rock_mask, rock_inner).filter(ImageFilter.GaussianBlur(0.9))
    base = _solid_rgba(size, (24, 24, 22, 0))
    base.putalpha(rock_edge.point(lambda a: int(a * 0.30)))
    out.alpha_composite(base)

    # Deepen the void outside the raised strip.
    upper_outer = upper_mask.filter(ImageFilter.MaxFilter(17))
    void_band = ImageChops.subtract(upper_outer, upper_mask).filter(ImageFilter.GaussianBlur(1.3))
    vshade = _solid_rgba(size, (0, 0, 0, 0))
    vshade.putalpha(void_band.point(lambda a: int(a * 0.48)))
    out.alpha_composite(vshade)
    return out


def regenerate_exploration_cliff_tiles(asset_dir: Path) -> None:
    """Regenerate all 256 elevation-cliff masks with orientation-aware painted art.

    Topology/endpoints still come from the existing smoothed 8-neighbor SDF. The
    painted cliff reference is sampled in a *local cliff coordinate frame*, so
    straight edges, inside corners, outside corners, and diagonal endpoints do
    not all reuse the same left-right picture.
    """
    from scipy.ndimage import gaussian_filter, distance_transform_edt

    size = 64
    face_depth = 44.0
    lip_outset = 4.0
    foot_depth = 8.0
    canvas = size * 3

    bit_for = {
        (-1, -1): NW, (0, -1): N, (1, -1): NE,
        (-1, 0): W,                  (1, 0): E,
        (-1, 1): SW,  (0, 1): S,   (1, 1): SE,
    }

    ref_path = asset_dir / 'cliff_style_reference.png'
    ref = Image.open(ref_path if ref_path.exists() else asset_dir / 'cliff_face_texture.png').convert('RGBA')

    def make_style_strip(box: tuple[int, int, int, int]) -> Image.Image:
        crop = ref.crop(box)
        half = crop.resize((32, size), Image.Resampling.LANCZOS)
        strip = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        strip.alpha_composite(half, (0, 0))
        strip.alpha_composite(half.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (32, 0))
        return strip

    if ref.width >= 1000 and ref.height >= 1100:
        style_a = make_style_strip((340, 300, 570, 1200))
        style_b = make_style_strip((690, 300, 920, 1200))
    else:
        style_a = make_style_strip((0, 0, ref.width, ref.height))
        style_b = style_a.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    style_a_arr = np.asarray(style_a, dtype=np.uint8)
    style_b_arr = np.asarray(style_b, dtype=np.uint8)
    fallback_arr = np.asarray(Image.open(asset_dir / 'cliff_face_texture.png').convert('RGBA').resize((size, size), Image.Resampling.LANCZOS), dtype=np.uint8)

    TOP_Y0, TOP_Y1 = 0, 17
    ROCK_Y0, ROCK_Y1 = 10, 56
    FOOT_Y0, FOOT_Y1 = 50, 63
    yy, xx = np.mgrid[0:size, 0:size]

    def sample_rows(style_arr: np.ndarray, u_idx: np.ndarray, v_norm: np.ndarray, y0: int, y1: int) -> np.ndarray:
        v_idx = np.rint(y0 + np.clip(v_norm, 0.0, 1.0) * (y1 - y0)).astype(np.int16)
        v_idx = np.clip(v_idx, 0, size - 1)
        return style_arr[v_idx, u_idx]

    for mask in range(256):
        blank = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        if mask == 0:
            blank.save(asset_dir / f'elevation_cliff_auto_{mask:03d}.png')
            continue

        lower = np.zeros((canvas, canvas), dtype=np.float32)
        for gy in range(3):
            for gx in range(3):
                dx, dy = gx - 1, gy - 1
                is_lower = (dx == 0 and dy == 0) or not (mask & bit_for.get((dx, dy), 0))
                if is_lower:
                    lower[gy*size:(gy+1)*size, gx*size:(gx+1)*size] = 1.0

        blurred = gaussian_filter(lower, sigma=8.0, mode='nearest')
        lower_shape = blurred >= 0.5
        signed = distance_transform_edt(lower_shape) - distance_transform_edt(~lower_shape)
        d = signed[size:2*size, size:2*size].astype(np.float32)

        gy_field, gx_field = np.gradient(d)
        mag = np.sqrt(gx_field * gx_field + gy_field * gy_field)
        mag = np.maximum(mag, 1e-5)
        nx = gx_field / mag
        ny = gy_field / mag
        tx = -ny
        ty = nx
        # Tangent coordinate: the source texture flows along the contour instead
        # of remaining fixed left-right in every topology.
        u_idx = np.mod(np.rint(xx * tx + yy * ty).astype(np.int16), size)

        style_arr = style_a_arr if ((mask * 1103515245 + 12345) & 1) == 0 else style_b_arr
        out = np.zeros((size, size, 4), dtype=np.uint8)

        top_m = (d >= -lip_outset) & (d <= 7.0)
        rock_m = (d > 7.0) & (d <= face_depth - foot_depth)
        foot_m = (d > face_depth - foot_depth) & (d <= face_depth + 2.5)

        if np.any(top_m):
            samp = sample_rows(style_arr, u_idx, (d + lip_outset) / (7.0 + lip_outset), TOP_Y0, TOP_Y1)
            out[top_m] = samp[top_m]
        if np.any(rock_m):
            samp = sample_rows(style_arr, u_idx, (d - 5.0) / max(1.0, face_depth - foot_depth - 5.0), ROCK_Y0, ROCK_Y1)
            selected = samp.copy()
            low_alpha = selected[..., 3] < 96
            selected[low_alpha] = fallback_arr[low_alpha]
            out[rock_m] = selected[rock_m]
        if np.any(foot_m):
            samp = sample_rows(style_arr, u_idx, (d - (face_depth - foot_depth)) / (foot_depth + 2.5), FOOT_Y0, FOOT_Y1)
            out[foot_m] = samp[foot_m]

        # Fade only at the true contour limits, never at tile borders.
        neg = top_m & (d < 0)
        if np.any(neg):
            fade = np.clip((d + lip_outset) / lip_outset, 0.0, 1.0)
            out[..., 3][neg] = (out[..., 3][neg].astype(np.float32) * fade[neg]).astype(np.uint8)
        far = foot_m & (d > face_depth)
        if np.any(far):
            fade = np.clip((face_depth + 2.5 - d) / 2.5, 0.0, 1.0)
            out[..., 3][far] = (out[..., 3][far].astype(np.float32) * fade[far]).astype(np.uint8)

        out_img = Image.fromarray(out, mode='RGBA')
        face_mask = Image.fromarray(np.where((d >= 0.0) & (d <= face_depth), 255, 0).astype(np.uint8), mode='L')
        edge = ImageChops.subtract(face_mask, face_mask.filter(ImageFilter.MinFilter(5)))
        shade = Image.new('RGBA', (size, size), (28, 20, 24, 0))
        shade.putalpha(edge.point(lambda a: int(a * 0.15)))
        out_img.alpha_composite(shade)
        out_img.save(asset_dir / f'elevation_cliff_auto_{mask:03d}.png')


def regenerate(asset_dir: Path) -> None:
    size = 64
    regenerate_exploration_cliff_tiles(asset_dir)

    # Overworld geometry.
    ow_margin = 12
    ow_radius = 20
    ow_inner = ow_margin
    path_tex = Image.open(asset_dir / "path_center.png").convert("RGBA")
    grass = Image.open(asset_dir / "grass_0.png").convert("RGBA")
    water_center = Image.open(asset_dir / "water_center.png").convert("RGBA")
    wfill = water_center.crop((8, 8, 56, 56)).resize((size, size), Image.Resampling.LANCZOS)

    for kind, fill in (("path", path_tex), ("water", wfill)):
        for mask in valid_blob_masks():
            m = make_mask(size, ow_margin, ow_radius, ow_inner, mask)
            img = render_masked(fill, grass, m)
            if kind == "water":
                img = add_shoreline(img, m)
            img.save(asset_dir / f"{kind}_auto_{mask:03d}.png")

    # Dungeon geometry: same explicit-mask idea, but with a tighter inset and a
    # less bubbly radius so rooms/corridors stay crisp and readable.
    dg_margin = 8
    dg_radius = 10
    dg_inner = dg_margin
    floor_fill = Image.open(asset_dir / "dungeon_floor_0.png").convert("RGBA")
    wall_fill = Image.open(asset_dir / "dungeon_wall_fill.png").convert("RGBA")
    stone_texture = Image.open(asset_dir / "wall.png").convert("RGBA")

    for mask in valid_blob_masks():
        m = make_mask(size, dg_margin, dg_radius, dg_inner, mask)
        img = render_masked(floor_fill, wall_fill, m)
        img = add_dungeon_masonry(img, m, stone_texture)
        img.save(asset_dir / f"dungeon_auto_{mask:03d}.png")


if __name__ == "__main__":
    regenerate(Path(__file__).resolve().parents[1] / "src" / "test_game" / "assets" / "tiles")
