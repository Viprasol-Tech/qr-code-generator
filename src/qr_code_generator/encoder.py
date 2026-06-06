"""Byte-mode QR encoder producing a boolean module matrix.

This is a genuine QR encoder following ISO/IEC 18004, not a wrapper around an
external library. It implements the full small-version pipeline:

1. Byte-mode data encoding (mode indicator, char count, payload, padding).
2. Reed-Solomon error-correction codewords over GF(256) (see :mod:`galois`).
3. Function-pattern placement (finders, separators, timing, dark module,
   format information).
4. Symbol-character (data) placement using the standard upward/downward
   zig-zag, skipping function modules.
5. Data masking with the eight standard mask patterns and penalty-based
   mask selection.

Supported: versions 1-3 at error-correction level M (single error-correction
block, which keeps interleaving trivial and the implementation auditable).
The capacity per version is documented in :data:`VERSION_SPECS`.

Part of QR Code Generator by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from dataclasses import dataclass

from qr_code_generator.galois import reed_solomon

# Byte mode indicator (0100) per ISO/IEC 18004 Table 2.
_MODE_BYTE = 0b0100

# Pad codewords alternated after the data terminator (Section 8.4.9).
_PAD_BYTES = (0b11101100, 0b00010001)


@dataclass(frozen=True)
class VersionSpec:
    """Fixed parameters for a single QR version at error-correction level M.

    Only single-block versions are modelled, so ``data_codewords`` and
    ``ec_codewords`` describe the whole symbol.
    """

    version: int
    data_codewords: int
    ec_codewords: int
    alignment_centers: tuple[int, ...]

    @property
    def size(self) -> int:
        """Side length of the module matrix in modules."""
        return 17 + 4 * self.version

    @property
    def char_capacity(self) -> int:
        """Maximum number of byte-mode characters this version can hold.

        Mode indicator (4 bits) + 8-bit char count + payload + 4-bit
        terminator must fit in ``data_codewords`` codewords.
        """
        return self.data_codewords - 2


# Error-correction level M, single block. Values from ISO/IEC 18004 Annex tables.
VERSION_SPECS: dict[int, VersionSpec] = {
    1: VersionSpec(version=1, data_codewords=16, ec_codewords=10, alignment_centers=()),
    2: VersionSpec(version=2, data_codewords=28, ec_codewords=16, alignment_centers=(6, 18)),
    3: VersionSpec(version=3, data_codewords=44, ec_codewords=26, alignment_centers=(6, 22)),
}

# Error-correction level M is encoded as bits 00 in the format information.
_EC_LEVEL_M_BITS = 0b00

# BCH(15,5) generator and the standard format mask (Section 8.9).
_FORMAT_GENERATOR = 0b10100110111
_FORMAT_MASK = 0b101010000010010


def smallest_version(length: int) -> VersionSpec:
    """Return the smallest supported version that fits ``length`` characters.

    Raises:
        ValueError: If the text is too long for any supported version.
    """
    for version in sorted(VERSION_SPECS):
        spec = VERSION_SPECS[version]
        if length <= spec.char_capacity:
            return spec
    biggest = VERSION_SPECS[max(VERSION_SPECS)]
    raise ValueError(
        f"text of {length} bytes exceeds capacity {biggest.char_capacity} "
        f"of supported version {biggest.version} (level M)"
    )


class _BitBuffer:
    """Append-only bit buffer that packs into 8-bit codewords."""

    def __init__(self) -> None:
        self._bits: list[int] = []

    def append(self, value: int, length: int) -> None:
        """Append the low ``length`` bits of ``value``, most-significant first."""
        for i in range(length - 1, -1, -1):
            self._bits.append((value >> i) & 1)

    def __len__(self) -> int:
        return len(self._bits)

    def to_codewords(self) -> list[int]:
        """Pack the buffered bits into a list of byte codewords."""
        codewords: list[int] = []
        for i in range(0, len(self._bits), 8):
            chunk = self._bits[i : i + 8]
            byte = 0
            for bit in chunk:
                byte = (byte << 1) | bit
            byte <<= 8 - len(chunk)  # left-align a trailing partial byte
            codewords.append(byte)
        return codewords


def _encode_data(text: str, spec: VersionSpec) -> list[int]:
    """Encode ``text`` into the full set of data codewords for ``spec``."""
    payload = text.encode("ascii")
    buffer = _BitBuffer()
    buffer.append(_MODE_BYTE, 4)
    buffer.append(len(payload), 8)  # 8-bit char count for versions 1-9, byte mode
    for byte in payload:
        buffer.append(byte, 8)

    capacity_bits = spec.data_codewords * 8
    # Terminator: up to four 0 bits.
    terminator = min(4, capacity_bits - len(buffer))
    buffer.append(0, terminator)

    codewords = buffer.to_codewords()
    # Alternate pad bytes until the data region is full.
    for i in range(spec.data_codewords - len(codewords)):
        codewords.append(_PAD_BYTES[i % 2])
    return codewords


def _format_bits(mask: int) -> list[int]:
    """Compute the 15-bit BCH-protected, masked format information."""
    data = (_EC_LEVEL_M_BITS << 3) | mask
    # BCH(15,5) remainder via polynomial long division over GF(2).
    rem = data << 10
    while rem.bit_length() > 10:
        rem ^= _FORMAT_GENERATOR << (rem.bit_length() - 11)
    combined = ((data << 10) | rem) ^ _FORMAT_MASK
    return [(combined >> i) & 1 for i in range(14, -1, -1)]


class _Matrix:
    """Mutable module matrix tracking which modules are function patterns."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.modules: list[list[bool]] = [[False] * size for _ in range(size)]
        self.reserved: list[list[bool]] = [[False] * size for _ in range(size)]

    def set(self, row: int, col: int, value: bool, *, reserved: bool = True) -> None:
        self.modules[row][col] = value
        if reserved:
            self.reserved[row][col] = True

    def is_reserved(self, row: int, col: int) -> bool:
        return self.reserved[row][col]


def _place_finder(matrix: _Matrix, top: int, left: int) -> None:
    """Place one 7x7 finder pattern with its surrounding separator."""
    for r in range(-1, 8):
        for c in range(-1, 8):
            row, col = top + r, left + c
            if not (0 <= row < matrix.size and 0 <= col < matrix.size):
                continue
            in_outer = 0 <= r <= 6 and 0 <= c <= 6
            is_ring = r in (0, 6) or c in (0, 6)
            is_core = 2 <= r <= 4 and 2 <= c <= 4
            dark = in_outer and (is_ring or is_core)
            matrix.set(row, col, dark)


def _place_alignment(matrix: _Matrix, spec: VersionSpec) -> None:
    """Place 5x5 alignment patterns at the version's centre coordinates."""
    centers = spec.alignment_centers
    for cr in centers:
        for cc in centers:
            # Skip centres that collide with finder patterns.
            if (cr, cc) in {(6, 6), (6, centers[-1]), (centers[-1], 6)}:
                continue
            if matrix.is_reserved(cr, cc):
                continue
            for r in range(-2, 3):
                for c in range(-2, 3):
                    is_ring = max(abs(r), abs(c)) in (0, 2)
                    matrix.set(cr + r, cc + c, is_ring)


def _place_timing(matrix: _Matrix) -> None:
    """Place the horizontal and vertical timing patterns on row/col 6."""
    for i in range(8, matrix.size - 8):
        dark = i % 2 == 0
        if not matrix.is_reserved(6, i):
            matrix.set(6, i, dark)
        if not matrix.is_reserved(i, 6):
            matrix.set(i, 6, dark)


def _reserve_format_areas(matrix: _Matrix) -> None:
    """Reserve the format-information modules and place the dark module."""
    size = matrix.size
    for i in range(9):
        if not matrix.is_reserved(8, i):
            matrix.set(8, i, False)
        if not matrix.is_reserved(i, 8):
            matrix.set(i, 8, False)
    for i in range(8):
        matrix.set(8, size - 1 - i, False)
        matrix.set(size - 1 - i, 8, False)
    # Dark module, always set (Section 8.9).
    matrix.set(size - 8, 8, True)


def _place_function_patterns(spec: VersionSpec) -> _Matrix:
    """Build a matrix with every function pattern placed."""
    matrix = _Matrix(spec.size)
    size = spec.size
    _place_finder(matrix, 0, 0)
    _place_finder(matrix, 0, size - 7)
    _place_finder(matrix, size - 7, 0)
    _place_timing(matrix)
    _place_alignment(matrix, spec)
    _reserve_format_areas(matrix)
    return matrix


def _bitstream(codewords: list[int]) -> list[int]:
    """Expand codewords to a flat list of bits, most-significant first."""
    bits: list[int] = []
    for byte in codewords:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _place_data(matrix: _Matrix, bits: list[int]) -> None:
    """Place data bits using the standard right-to-left upward zig-zag."""
    size = matrix.size
    bit_index = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:  # skip the vertical timing column
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in (col, col - 1):
                if matrix.is_reserved(row, c):
                    continue
                bit = bits[bit_index] if bit_index < len(bits) else 0
                matrix.set(row, c, bit == 1, reserved=False)
                bit_index += 1
        upward = not upward
        col -= 2


def _mask_condition(mask: int, row: int, col: int) -> bool:
    """Return whether mask pattern ``mask`` flips the module at (row, col)."""
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _apply_mask(matrix: _Matrix, mask: int) -> _Matrix:
    """Return a copy of ``matrix`` with ``mask`` applied to data modules."""
    out = _Matrix(matrix.size)
    out.reserved = [row[:] for row in matrix.reserved]
    for r in range(matrix.size):
        for c in range(matrix.size):
            value = matrix.modules[r][c]
            if not matrix.reserved[r][c] and _mask_condition(mask, r, c):
                value = not value
            out.modules[r][c] = value
    return out


def _write_format(matrix: _Matrix, mask: int) -> None:
    """Write the masked, BCH-protected format information for ``mask``."""
    bits = _format_bits(mask)
    size = matrix.size
    # Around the top-left finder.
    coords_a = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]  # fmt: skip
    for (r, c), bit in zip(coords_a, bits, strict=True):
        matrix.set(r, c, bit == 1)
    # Split copy along the right and bottom edges.
    for i in range(7):
        matrix.set(size - 1 - i, 8, bits[i] == 1)
    for i in range(8):
        matrix.set(8, size - 8 + i, bits[7 + i] == 1)


def _penalty(matrix: _Matrix) -> int:
    """Compute the total mask penalty score (lower is better)."""
    size = matrix.size
    score = 0
    mods = matrix.modules
    # Rule 1: runs of >= 5 same-coloured modules in rows and columns.
    for line in (mods, [list(col) for col in zip(*mods, strict=True)]):
        for row in line:
            run = 1
            for i in range(1, size):
                if row[i] == row[i - 1]:
                    run += 1
                else:
                    if run >= 5:
                        score += 3 + (run - 5)
                    run = 1
            if run >= 5:
                score += 3 + (run - 5)
    # Rule 2: 2x2 blocks of the same colour.
    for r in range(size - 1):
        for c in range(size - 1):
            if mods[r][c] == mods[r][c + 1] == mods[r + 1][c] == mods[r + 1][c + 1]:
                score += 3
    # Rule 4: proportion of dark modules.
    dark = sum(cell for row in mods for cell in row)
    ratio = dark * 100 // (size * size)
    score += min(abs(ratio - 50) // 5, abs((ratio + 5) - 50) // 5) * 10
    return score


def encode(text: str, *, version: int | None = None) -> list[list[bool]]:
    """Encode ASCII ``text`` into a QR module matrix (no quiet zone).

    Args:
        text: ASCII text to encode. Must fit a supported version at level M.
        version: Optional explicit version (1-3). If omitted, the smallest
            version that fits is chosen automatically.

    Returns:
        A square list of boolean rows; ``True`` means a dark module.

    Raises:
        ValueError: If the text is non-ASCII or too long, or the version is
            unsupported or too small for the text.
    """
    try:
        text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("only ASCII text is supported in byte mode") from exc

    if version is None:
        spec = smallest_version(len(text))
    else:
        if version not in VERSION_SPECS:
            raise ValueError(f"unsupported version {version}; supported: 1-3")
        spec = VERSION_SPECS[version]
        if len(text) > spec.char_capacity:
            raise ValueError(
                f"text of {len(text)} chars exceeds version {version} "
                f"capacity {spec.char_capacity} (level M)"
            )

    data = _encode_data(text, spec)
    ec = reed_solomon(data, spec.ec_codewords)
    bits = _bitstream(data + ec)

    base = _place_function_patterns(spec)
    _place_data(base, bits)

    best: _Matrix | None = None
    best_score = -1
    for mask in range(8):
        candidate = _apply_mask(base, mask)
        _write_format(candidate, mask)
        score = _penalty(candidate)
        if best is None or score < best_score:
            best, best_score = candidate, score

    assert best is not None
    return best.modules
