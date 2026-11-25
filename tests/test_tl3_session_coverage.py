"""D3 · Cobertura de sesión con la regla prerregistrada de T7."""

from __future__ import annotations

import pandas as pd

from tradinglab.tl3.data import session_coverage


def _frame(*ranges) -> pd.DataFrame:
    parts = [
        pd.date_range(start, periods=minutes, freq="min", tz="America/New_York")
        for start, minutes in ranges
    ]
    index = parts[0]
    for part in parts[1:]:
        index = index.append(part)
    return pd.DataFrame(
        {"open": 1.0},
        index=index.sort_values().tz_convert("UTC"),
    )


def _base(day: str = "2026-11-24", previous: str = "2026-11-23"):
    return _frame(
        (f"{previous} 09:30", 357),
        (f"{day} 09:30", 357),
        (f"{previous} 18:00", 744),
    )


def test_sesion_valida_sintetica():
    cov = session_coverage(_base(), "2026-11-24")

    assert cov["session_bars"] == 357
    assert cov["previous_bars"] == 357
    assert cov["night_bars"] == 744
    assert cov["valid"] is True


def test_sesion_previa_incompleta():
    frame = _frame(
        ("2026-11-23 09:30", 356),
        ("2026-11-24 09:30", 357),
        ("2026-11-23 18:00", 744),
    )
    cov = session_coverage(frame, "2026-11-24")

    assert cov["previous_bars"] == 356
    assert cov["valid"] is False


def test_sin_comprobar_sesion_previa():
    frame = _frame(
        ("2026-11-24 09:30", 357),
        ("2026-11-23 18:00", 744),
    )
    cov = session_coverage(frame, "2026-11-24", check_previous=False)

    assert cov["previous_bars"] == 0
    assert cov["valid"] is True


def test_sesion_previa_salta_festivo():
    frame = _frame(
        ("2026-11-25 09:30", 357),
        ("2026-11-27 09:30", 357),
        ("2026-11-26 18:00", 744),
    )
    cov = session_coverage(frame, "2026-11-27")

    assert cov["previous_bars"] == 357
    assert cov["valid"] is True


def test_umbral_nocturno():
    frame = _frame(
        ("2026-11-23 09:30", 357),
        ("2026-11-24 09:30", 357),
        ("2026-11-23 18:00", 743),
    )
    cov = session_coverage(frame, "2026-11-24")

    assert cov["night_bars"] == 743
    assert cov["valid"] is False


def test_umbral_sesion():
    frame = _frame(
        ("2026-11-23 09:30", 357),
        ("2026-11-24 09:30", 356),
        ("2026-11-23 18:00", 744),
    )
    cov = session_coverage(frame, "2026-11-24")

    assert cov["session_bars"] == 356
    assert cov["valid"] is False
