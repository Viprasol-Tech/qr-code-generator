"""Tests for GF(256) arithmetic and Reed-Solomon codeword generation."""

from __future__ import annotations

from qr_code_generator.galois import gf_mul, gf_pow, reed_solomon


def test_gf_mul_identity_and_zero() -> None:
    assert gf_mul(0, 5) == 0
    assert gf_mul(7, 0) == 0
    assert gf_mul(1, 123) == 123


def test_gf_mul_known_values() -> None:
    # In GF(256) with primitive 0x11D, alpha=2 so 2*alpha^7 wraps via the field.
    assert gf_mul(2, 2) == 4
    assert gf_mul(2, 128) == 0x1D  # 256 reduces by 0x11D -> 0x1D


def test_gf_pow_matches_repeated_mul() -> None:
    acc = 1
    for power in range(8):
        assert gf_pow(2, power) == acc
        acc = gf_mul(acc, 2)


def test_reed_solomon_known_version1_M_vector() -> None:
    # Standard worked example (ISO/IEC 18004 / Thonky tutorial): encoding the
    # data "HELLO WORLD" at version 1-M yields these 10 EC codewords.
    data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
    expected = [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]
    assert reed_solomon(data, 10) == expected


def test_reed_solomon_length() -> None:
    assert len(reed_solomon([1, 2, 3, 4], 16)) == 16
