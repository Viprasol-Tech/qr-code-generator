"""Tests for the QR encoder: matrix structure, determinism, capacity."""

from __future__ import annotations

import pytest

from qr_code_generator.encoder import VERSION_SPECS, encode, smallest_version


def _is_finder(matrix: list[list[bool]], top: int, left: int) -> bool:
    """Check that a 7x7 finder pattern sits at the given top-left corner."""
    expected = [
        [True, True, True, True, True, True, True],
        [True, False, False, False, False, False, True],
        [True, False, True, True, True, False, True],
        [True, False, True, True, True, False, True],
        [True, False, True, True, True, False, True],
        [True, False, False, False, False, False, True],
        [True, True, True, True, True, True, True],
    ]
    for r in range(7):
        for c in range(7):
            if matrix[top + r][left + c] != expected[r][c]:
                return False
    return True


def test_matrix_is_square_and_correct_size() -> None:
    matrix = encode("VIPRASOL")
    assert len(matrix) == 21  # version 1 -> 21x21
    assert all(len(row) == 21 for row in matrix)


def test_version_size_formula() -> None:
    for version, spec in VERSION_SPECS.items():
        assert spec.size == 17 + 4 * version


def test_finder_patterns_in_three_corners() -> None:
    matrix = encode("VIPRASOL")
    size = len(matrix)
    assert _is_finder(matrix, 0, 0)
    assert _is_finder(matrix, 0, size - 7)
    assert _is_finder(matrix, size - 7, 0)
    # The bottom-right corner must NOT be a finder pattern.
    assert not _is_finder(matrix, size - 7, size - 7)


def test_timing_pattern_alternates() -> None:
    matrix = encode("VIPRASOL")
    size = len(matrix)
    # Row 6 timing pattern between the finders alternates dark/light.
    for col in range(8, size - 8):
        assert matrix[6][col] == (col % 2 == 0)


def test_dark_module_always_set() -> None:
    matrix = encode("VIPRASOL")
    size = len(matrix)
    assert matrix[size - 8][8] is True


def test_encoding_is_deterministic() -> None:
    first = encode("VIPRASOL")
    second = encode("VIPRASOL")
    assert first == second


def test_different_input_changes_matrix() -> None:
    assert encode("VIPRASOL") != encode("VIPRASO1")


def test_smallest_version_selection() -> None:
    assert smallest_version(1).version == 1
    assert smallest_version(VERSION_SPECS[1].char_capacity).version == 1
    assert smallest_version(VERSION_SPECS[1].char_capacity + 1).version == 2


def test_explicit_version_override() -> None:
    matrix = encode("HI", version=3)
    assert len(matrix) == VERSION_SPECS[3].size


def test_rejects_non_ascii() -> None:
    with pytest.raises(ValueError, match="ASCII"):
        encode("café")


def test_rejects_overlong_text() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        encode("X" * 1000)


def test_rejects_bad_version() -> None:
    with pytest.raises(ValueError, match="unsupported version"):
        encode("HI", version=9)
