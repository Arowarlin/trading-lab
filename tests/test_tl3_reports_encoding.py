"""D1 · Los informes TL3 deben ser UTF-8 limpio."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_informes_utf8_sin_mojibake():
    for path in sorted((ROOT / "TL3_REPORTS").glob("*.md")):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM en {path.name}"
        text = raw.decode("utf-8")
        assert not re.search(r"\?\d", text), f"? delante de dígito en {path.name}"
        for mark in ("Ã", "â€", "┬", "├"):
            assert mark not in text, f"mojibake {mark} en {path.name}"
