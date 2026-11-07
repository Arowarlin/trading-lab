from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_fase8_cierra_sin_nautilus() -> None:
    text = (ROOT / "docs" / "fase8_nautilus.md").read_text(encoding="utf-8")
    assert "No se adopta NautilusTrader" in text
    assert "backtester propio" in text
    assert "Gate para reabrir" in text


def test_sin_dependencias_de_motor_de_eventos() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for forbidden in ("nautilus", "databento", "ib_async", "ibapi"):
        assert forbidden not in pyproject
