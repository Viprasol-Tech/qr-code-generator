"""Command-line interface for QR Code Generator.

``qr-code-generator demo`` encodes ``VIPRASOL`` and prints the module matrix as
ASCII art — no network, no API keys, fully deterministic.

Part of QR Code Generator by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from qr_code_generator import __version__
from qr_code_generator.encoder import VERSION_SPECS, encode
from qr_code_generator.render import to_ascii, to_png, to_unicode

app = typer.Typer(add_completion=False, help="QR Code Generator — by Viprasol Tech.")
console = Console()


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"qr-code-generator [bold cyan]{__version__}[/] — by Viprasol Tech")


@app.command()
def encode_text(
    text: str = typer.Argument(..., help="ASCII text to encode."),
    qr_version: int | None = typer.Option(None, "--qr-version", help="Force version 1-3."),
    unicode: bool = typer.Option(False, "--unicode", help="Use half-block glyphs."),
    png: Path | None = typer.Option(None, "--png", help="Also write a PNG to this path."),
) -> None:
    """Encode ``text`` and print the resulting QR matrix."""
    matrix = encode(text, version=qr_version)
    art = to_unicode(matrix) if unicode else to_ascii(matrix)
    console.print(art, highlight=False, soft_wrap=True)
    console.print(f"Size: [bold]{len(matrix)}x{len(matrix)}[/] modules")
    if png is not None:
        png.write_bytes(to_png(matrix))
        console.print(f"Wrote PNG: [bold green]{png}[/]")


@app.command()
def demo() -> None:
    """Encode ``VIPRASOL`` and print the QR matrix (offline, deterministic)."""
    text = "VIPRASOL"
    matrix = encode(text)
    spec = VERSION_SPECS[(len(matrix) - 17) // 4]
    console.print(to_ascii(matrix), highlight=False, soft_wrap=True)
    console.print(f"Encoded:  [bold]{text!r}[/] in byte mode")
    size = len(matrix)
    console.print(f"Version:  [bold]{spec.version}[/] (level M), {size}x{size} modules")
    console.print(f"Capacity: up to [bold]{spec.char_capacity}[/] ASCII chars")


if __name__ == "__main__":
    app()
