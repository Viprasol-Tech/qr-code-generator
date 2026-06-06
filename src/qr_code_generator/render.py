"""Render a QR module matrix to ASCII art or a minimal PNG.

The PNG writer is pure standard library (``zlib`` + ``struct``): it emits a
valid 1-bit-per-pixel-equivalent greyscale PNG with no third-party imaging
dependency. The ASCII renderer uses half-block characters so the output stays
roughly square in a terminal.

Part of QR Code Generator by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

import struct
import zlib

Matrix = list[list[bool]]


def add_quiet_zone(matrix: Matrix, border: int = 4) -> Matrix:
    """Return ``matrix`` surrounded by a ``border``-module light quiet zone."""
    if border < 0:
        raise ValueError("border must be non-negative")
    size = len(matrix)
    padded_size = size + 2 * border
    out: Matrix = [[False] * padded_size for _ in range(padded_size)]
    for r, row in enumerate(matrix):
        for c, value in enumerate(row):
            out[r + border][c + border] = value
    return out


def to_ascii(matrix: Matrix, *, border: int = 4, dark: str = "##", light: str = "  ") -> str:
    """Render the matrix as an ASCII-art string.

    Args:
        matrix: The boolean module matrix.
        border: Quiet-zone width in modules.
        dark: Two-character glyph for a dark module.
        light: Two-character glyph for a light module.

    Returns:
        A multi-line string; each module is rendered two characters wide so the
        result is approximately square in a monospace terminal.
    """
    padded = add_quiet_zone(matrix, border)
    lines = ["".join(dark if cell else light for cell in row) for row in padded]
    return "\n".join(lines)


def to_unicode(matrix: Matrix, *, border: int = 4) -> str:
    """Render the matrix using Unicode half-block characters (two rows/line)."""
    padded = add_quiet_zone(matrix, border)
    size = len(padded)
    lines: list[str] = []
    for r in range(0, size, 2):
        top = padded[r]
        bottom = padded[r + 1] if r + 1 < size else [False] * size
        chars: list[str] = []
        for c in range(size):
            up, down = top[c], bottom[c]
            if up and down:
                chars.append("█")  # full block
            elif up:
                chars.append("▀")  # upper half
            elif down:
                chars.append("▄")  # lower half
            else:
                chars.append(" ")
        lines.append("".join(chars))
    return "\n".join(lines)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    """Build a single length-prefixed, CRC-suffixed PNG chunk."""
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def to_png(matrix: Matrix, *, border: int = 4, scale: int = 8) -> bytes:
    """Render the matrix to PNG bytes using only the standard library.

    Args:
        matrix: The boolean module matrix.
        border: Quiet-zone width in modules.
        scale: Pixel size of each module (must be >= 1).

    Returns:
        The encoded PNG file as bytes.
    """
    if scale < 1:
        raise ValueError("scale must be >= 1")
    padded = add_quiet_zone(matrix, border)
    modules = len(padded)
    width = modules * scale
    # Build greyscale (8-bit) raw image: 0x00 dark, 0xFF light, with filter byte.
    raw = bytearray()
    for row in padded:
        raw.append(0)  # filter type 0 (None) for this scanline
        pixel_row = bytearray()
        for cell in row:
            pixel_row.extend(bytes([0x00 if cell else 0xFF]) * scale)
        for _ in range(scale):
            raw.extend(pixel_row)
            if _ < scale - 1:
                raw.append(0)  # filter byte for each repeated scanline

    header = struct.pack(">IIBBBBB", width, width, 8, 0, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", header)
    png += _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _png_chunk(b"IEND", b"")
    return png
