"""Module entry point so ``python -m qr_code_generator`` runs the CLI.

Part of QR Code Generator by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from qr_code_generator.cli import app

if __name__ == "__main__":
    app()
