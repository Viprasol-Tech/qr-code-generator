"""Tests for ASCII, Unicode, and PNG rendering and quiet-zone handling."""

from __future__ import annotations

import struct

import pytest

from qr_code_generator.encoder import encode
from qr_code_generator.render import add_quiet_zone, to_ascii, to_png, to_unicode


def test_quiet_zone_adds_border_on_all_sides() -> None:
    matrix = [[True]]
    padded = add_quiet_zone(matrix, border=4)
    assert len(padded) == 9
    assert all(len(row) == 9 for row in padded)
    assert padded[4][4] is True
    # The border itself is all light.
    assert not any(padded[0])
    assert not any(row[0] for row in padded)


def test_quiet_zone_rejects_negative_border() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        add_quiet_zone([[True]], border=-1)


def test_ascii_dimensions_match_padded_matrix() -> None:
    matrix = encode("VIPRASOL")
    art = to_ascii(matrix, border=4)
    lines = art.splitlines()
    expected_modules = len(matrix) + 8
    assert len(lines) == expected_modules
    assert all(len(line) == expected_modules * 2 for line in lines)


def test_ascii_is_deterministic() -> None:
    matrix = encode("VIPRASOL")
    assert to_ascii(matrix) == to_ascii(matrix)


def test_unicode_uses_half_blocks() -> None:
    matrix = encode("VIPRASOL")
    art = to_unicode(matrix, border=4)
    # Half-block rendering packs two module-rows per line.
    padded_size = len(matrix) + 8
    assert len(art.splitlines()) == (padded_size + 1) // 2


def test_png_has_valid_signature_and_chunks() -> None:
    matrix = encode("VIPRASOL")
    data = to_png(matrix, border=4, scale=4)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert b"IHDR" in data[:33]
    assert data[-8:-4] == b"IEND"
    # IHDR width/height should equal padded modules * scale.
    width, height = struct.unpack(">II", data[16:24])
    expected = (len(matrix) + 8) * 4
    assert width == height == expected


def test_png_rejects_bad_scale() -> None:
    with pytest.raises(ValueError, match="scale"):
        to_png(encode("HI"), scale=0)
