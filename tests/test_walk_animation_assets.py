from __future__ import annotations

import struct
import zlib
from pathlib import Path


ASSET_DIR = Path(__file__).parents[1] / "src" / "test_game" / "assets" / "characters"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == PNG_SIGNATURE
    return struct.unpack(">II", data[16:24])


def _assert_png_integrity(path: Path) -> None:
    data = path.read_bytes()
    assert data[:8] == PNG_SIGNATURE

    offset = 8
    idat = bytearray()
    saw_iend = False
    while offset < len(data):
        assert offset + 12 <= len(data)
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        crc_end = payload_end + 4
        assert crc_end <= len(data)

        payload = data[payload_start:payload_end]
        stored_crc = struct.unpack(">I", data[payload_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(payload, actual_crc) & 0xFFFFFFFF
        assert stored_crc == actual_crc, f"CRC mismatch in {path.name} {chunk_type!r}"

        if chunk_type == b"IDAT":
            idat.extend(payload)
        elif chunk_type == b"IEND":
            saw_iend = True
            assert crc_end == len(data)
            break

        offset = crc_end

    assert saw_iend
    assert idat
    # libpng's "invalid distance too far back" failure happens while inflating
    # IDAT. Decompressing the complete stream catches that corruption in tests.
    zlib.decompress(bytes(idat))


def test_main_character_walk_atlases_are_directional_8_by_4_sheets() -> None:
    expected_size = (48 * 8, 48 * 4)
    for filename in ("fox_walk.png", "mara_walk.png"):
        path = ASSET_DIR / filename
        assert _png_size(path) == expected_size
        _assert_png_integrity(path)
