"""ENG-1 E-01: la mutación de sesión del GA no se limita a 09:30-15:00.

Antes, en plantillas de Asia, Londres o cualquier sesión fuera de la regular de
NY, toda mutación de horario se descartaba (0/200): el GA nunca exploró el
horario fuera de NY. La regla de NY no cambia (mismos hijos con la misma semilla).
"""

from __future__ import annotations

import random

from tradinglab.discovery import genetic


def _mutations(name: str, n: int = 200):
    strategy = genetic.template_strategy(name)
    sym = genetic.template_symmetric(name)
    return strategy, [genetic.mutate_session(strategy, random.Random(i), symmetric=sym) for i in range(n)]


def _minutes(text: str) -> int:
    h, m = (int(part) for part in text.split(":"))
    return h * 60 + m


def test_asia_y_londres_mutan_y_conservan_la_forma():
    for name in ("asia_range_reversion", "london_breakout"):
        original, children = _mutations(name)
        valid = [c for c in children if c is not None]
        assert len(valid) > 100, name
        crosses = _minutes(original["session"]["start"]) > _minutes(original["session"]["end"])
        for child in valid:
            start, end = _minutes(child["session"]["start"]), _minutes(child["session"]["end"])
            assert (start > end) == crosses
            flat = child["session"].get("flat_at")
            if flat:
                duration = (end - start) % 1440
                assert 0 < (_minutes(flat) - start) % 1440 <= duration


def test_ny_sigue_dentro_de_la_sesion_regular():
    _original, children = _mutations("ny_open_vol_filter")
    valid = [c for c in children if c is not None]
    assert len(valid) == 147  # el mismo número que antes del cambio
    for child in valid:
        assert 9 * 60 + 30 <= _minutes(child["session"]["start"]) < _minutes(child["session"]["end"]) <= 15 * 60


def test_sesiones_de_24h_no_mutan():
    _original, children = _mutations("trend_pullback_mtf")
    assert all(child is None for child in children)
