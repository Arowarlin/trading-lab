"""COLA-MOTOR-FLAT · M1: comportamiento ``legacy`` documentado e identidad.

Estos tests reproducen el fallo y fijan la identidad del modo por defecto antes
de tocar el motor. Deben pasar antes y después de M2.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from tradinglab.discovery import fastbt
from tradinglab.discovery.export_samples import build_samples
from tradinglab.discovery.fastbt import RunLimits, _session_mask
from tradinglab.discovery.timeframes import timeframe_minutes

NY = "America/New_York"
FIXTURES = Path(__file__).parent / "fixtures" / "motor_flat"
TEMPLATES = Path(__file__).parents[1] / "config" / "discovery" / "templates"
TFS = ("M5", "M15", "M30", "H1", "H4")


def _session_bars(
    timeframe: str,
    start: str,
    end: str,
    *,
    days: int = 2,
    first_day: str = "2024-07-01",
    drop_last: bool = False,
) -> pd.DataFrame:
    """Barras sintéticas alineadas a la rejilla del TF, en zona NY."""

    step = timeframe_minutes(timeframe)
    begin_h, begin_m = (int(part) for part in start.split(":"))
    end_h, end_m = (int(part) for part in end.split(":"))
    rows: list[pd.Timestamp] = []
    base = pd.Timestamp(first_day, tz=NY).normalize()
    for offset in range(days):
        current = base + pd.Timedelta(days=offset)
        begin = current + pd.Timedelta(hours=begin_h, minutes=begin_m)
        finish = current + pd.Timedelta(hours=end_h, minutes=end_m)
        if finish <= begin:
            finish += pd.Timedelta(days=1)
        stamps = list(pd.date_range(begin, finish, freq=f"{step}min", inclusive="both"))
        if drop_last and stamps:
            stamps = stamps[:-1]
        rows.extend(stamps)
    index = pd.DatetimeIndex(rows).tz_convert("UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        index=index,
    )


def _continuous_bars(timeframe: str, *, days: int = 60) -> pd.DataFrame:
    minutes = timeframe_minutes(timeframe)
    index = pd.date_range(
        "2024-01-01",
        periods=(days * 24 * 60) // minutes,
        freq=f"{minutes}min",
        tz=NY,
    ).tz_convert("UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        index=index,
    )


def _limits(**kwargs) -> RunLimits:
    return RunLimits(
        session_tz=NY,
        weekdays=(0, 1, 2, 3, 4, 5, 6),
        **kwargs,
    )


def _flag_at(mask, bars: pd.DataFrame, stamp: str) -> bool:
    target = pd.Timestamp(stamp, tz=NY).tz_convert("UTC")
    position = bars.index.get_loc(target)
    return bool(mask.flat_flag[position])


@pytest.mark.parametrize("first_day", ["2024-07-01", "2024-01-08"])
def test_legacy_1555_no_dispara_en_m15_m30_h1(first_day: str) -> None:
    """Sesión 09:30-15:55 con flat 15:55: solo M5 marca la vela de las 15:55."""

    cases = {
        "M5": True,
        "M15": False,
        "M30": False,
        "H1": False,
    }
    for timeframe, expected in cases.items():
        bars = _session_bars(
            timeframe, "09:30", "15:55", days=3, first_day=first_day
        )
        mask = _session_mask(
            bars,
            _limits(session_start="09:30", session_end="15:55", flat_at="15:55"),
        )
        marked = np.flatnonzero(mask.flat_flag)
        if expected:
            assert marked.size > 0
            for position in marked:
                local = bars.index[position].tz_convert(NY)
                assert (local.hour, local.minute) == (15, 55)
        else:
            assert marked.size == 0, f"{timeframe} no debería marcar ninguna vela"


def test_legacy_overnight_h1_marca_las_0300() -> None:
    """Sesión 18:00-03:00 con flat 02:45: H1 marca la vela de las 03:00."""

    bars = _session_bars("H1", "18:00", "03:00", days=3, first_day="2024-07-01")
    mask = _session_mask(
        bars,
        _limits(session_start="18:00", session_end="03:00", flat_at="02:45"),
    )
    marked = [bars.index[i].tz_convert(NY) for i in np.flatnonzero(mask.flat_flag)]
    assert marked
    assert all((stamp.hour, stamp.minute) == (3, 0) for stamp in marked)


def test_legacy_24h_h1_no_marca_ninguna_vela() -> None:
    """Sesión 24 h con flat 23:55: H1 no marca ninguna vela."""

    bars = _session_bars("H1", "00:00", "23:00", days=3, first_day="2024-07-01")
    mask = _session_mask(
        bars,
        _limits(session_start="00:00", session_end="23:59", flat_at="23:55"),
    )
    assert not mask.flat_flag.any()


def _template_session(name: str) -> dict:
    payload = yaml.safe_load(
        (TEMPLATES / f"{name}.yaml").read_text(encoding="utf-8")
    ) or {}
    return (payload.get("strategy") or {}).get("session") or {}


def test_legacy_flat_flag_identico_a_motor_flat_pre() -> None:
    """Los arrays legacy de 60 días coinciden con la foto previa al cambio."""

    fixture = np.load(FIXTURES / "legacy_flags.npz")
    assert fixture.files
    for key in fixture.files:
        template, timeframe = key.split("|")
        session = _template_session(template)
        bars = _continuous_bars(timeframe)
        mask = _session_mask(
            bars,
            _limits(
                session_start=str(session.get("start")),
                session_end=str(session.get("end")),
                flat_at=str(session.get("flat_at")),
            ),
        )
        np.testing.assert_array_equal(
            mask.flat_flag,
            fixture[key],
            err_msg=f"legacy cambió en {key}",
        )


def _normalize_mq5(source: str) -> str:
    lines = source.replace("\r\n", "\n").split("\n")
    return "\n".join(
        line
        for line in lines
        if not line.startswith("//| Exportador:")
        and not line.startswith("const int FLAT_MODE")
    )


def test_export_legacy_identico_salvo_version_y_flat_mode(tmp_path: Path) -> None:
    """El .mq5 legacy solo puede cambiar en la versión y en ``FLAT_MODE``."""

    result = build_samples(tmp_path)["synthetic_trend"]
    current = result.mq5_path.read_text(encoding="utf-8")
    previous = (FIXTURES / "legacy_synthetic_trend.mq5").read_text(encoding="utf-8")
    assert _normalize_mq5(current) == _normalize_mq5(previous)


def test_flat_mode_legacy_es_el_defecto() -> None:
    """Sin declarar ``flat_mode``, el motor usa ``legacy``."""

    limits = _limits(session_start="09:30", session_end="15:55", flat_at="15:55")
    assert getattr(limits, "flat_mode", "legacy") == "legacy"
    assert fastbt is not None
