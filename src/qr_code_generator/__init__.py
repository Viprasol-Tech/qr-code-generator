"""QR Code Generator — real byte-mode QR encoding by Viprasol Tech.

Part of QR Code Generator by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from qr_code_generator.encoder import VERSION_SPECS, VersionSpec, encode
from qr_code_generator.render import to_ascii, to_png, to_unicode

__version__ = "0.1.0"

__all__ = [
    "VERSION_SPECS",
    "VersionSpec",
    "__version__",
    "encode",
    "to_ascii",
    "to_png",
    "to_unicode",
]
