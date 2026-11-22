"""Calendarios R2j y clasificación de huecos por sesión derivada."""

from __future__ import annotations

import pandas as pd

from tradinglab.discovery import calendars
from tradinglab.discovery.config import SessionSegment
from tradinglab.discovery.data_quality import _calendar_gap_session
from tradinglab.discovery.sessions import derive_year
from tradinglab.nyse_calendar import EARLY_CLOSES, FULL_HOLIDAYS

NY = "America/New_York"


def test_nyse_2021_2027_exacto() -> None:
    assert calendars.nyse_holidays(2021, 2027) == FULL_HOLIDAYS
    assert calendars.nyse_early_closes(2021, 2027) == EARLY_CLOSES


def test_cierres_especiales() -> None:
    for key in (20040611, 20070102, 20121029, 20121030, 20181205, 20250109):
        day = pd.Timestamp(str(key)).date()
        assert calendars.is_holiday(calendars.NYSE, day)
    assert calendars.is_holiday(
        calendars.NYSE, pd.Timestamp("2016-03-25").date()
    )


def test_fx_metal_viernes_santo_y_navidad() -> None:
    assert calendars.is_holiday(
        calendars.FX_METAL, pd.Timestamp("2024-03-29").date()
    )
    assert calendars.is_holiday(
        calendars.FX_METAL, pd.Timestamp("2024-12-25").date()
    )
    assert not calendars.is_holiday(
        calendars.FX_METAL, pd.Timestamp("2024-03-28").date()
    )


def _session(**kwargs) -> SessionSegment:
    values = {
        "friday_close": "17:00",
        "sunday_open": "17:00",
    }
    values.update(kwargs)
    return SessionSegment(**values)


def test_viernes_indices_cierra_1615_no_cuenta() -> None:
    session = _session(friday_close="16:15", sunday_open="17:00")
    real, reason = _calendar_gap_session(
        pd.Timestamp("2024-01-12 16:15", tz=NY),
        pd.Timestamp("2024-01-14 17:00", tz=NY),
        1440,
        36 * 60,
        calendars.NYSE,
        session,
        NY,
    )
    assert real is False
    assert "fin de semana" in reason or "horario" in reason


def test_falta_miercoles_en_d1_cuenta() -> None:
    session = _session(friday_close="16:15", sunday_open="17:00")
    real, reason = _calendar_gap_session(
        pd.Timestamp("2024-01-09 17:00", tz=NY),
        pd.Timestamp("2024-01-10 17:00", tz=NY),
        1440,
        36 * 60,
        calendars.NYSE,
        session,
        NY,
    )
    assert real is True
    assert "sin datos" in reason


def test_viernes_santo_oro_no_cuenta() -> None:
    session = _session(friday_close="17:00", sunday_open="17:00")
    real, reason = _calendar_gap_session(
        pd.Timestamp("2024-03-29 00:00", tz=NY),
        pd.Timestamp("2024-03-31 17:00", tz=NY),
        1440,
        36 * 60,
        calendars.FX_METAL,
        session,
        NY,
    )
    assert real is False
    assert "festivo" in reason


def test_festivo_nyse_2016_en_us100_no_cuenta() -> None:
    session = _session(friday_close="16:15", sunday_open="17:00")
    real, reason = _calendar_gap_session(
        pd.Timestamp("2016-03-25 00:00", tz=NY),
        pd.Timestamp("2016-03-27 17:00", tz=NY),
        1440,
        36 * 60,
        calendars.NYSE,
        session,
        NY,
    )
    assert real is False
    assert "festivo" in reason


def test_falta_una_hora_a_mitad_de_sesion_cuenta() -> None:
    session = _session(friday_close="16:15", sunday_open="17:00")
    real, reason = _calendar_gap_session(
        pd.Timestamp("2024-01-10 09:00", tz=NY),
        pd.Timestamp("2024-01-10 11:00", tz=NY),
        60,
        90,
        calendars.NYSE,
        session,
        NY,
    )
    assert real is True
    assert "2024-01-10" in reason


def test_cierre_temprano_solo_excusa_despues_de_1300() -> None:
    session = _session(friday_close="16:15", sunday_open="17:00")
    # Mañana del 24-dic (índice): falta 09:00-13:00, cuenta.
    real, _reason = _calendar_gap_session(
        pd.Timestamp("2024-12-24 09:00", tz=NY),
        pd.Timestamp("2024-12-24 13:30", tz=NY),
        60,
        90,
        calendars.NYSE,
        session,
        NY,
    )
    assert real is True
    # Solo después de las 13:00: programado.
    real, _reason = _calendar_gap_session(
        pd.Timestamp("2024-12-24 13:30", tz=NY),
        pd.Timestamp("2024-12-24 15:00", tz=NY),
        60,
        90,
        calendars.NYSE,
        session,
        NY,
    )
    assert real is False


def test_sesion_corta_forex_solo_excusa_despues_del_cierre_derivado() -> None:
    session = _session(
        friday_close="17:00",
        sunday_open="17:00",
        short_close="13:00",
    )
    real, _reason = _calendar_gap_session(
        pd.Timestamp("2024-12-24 09:00", tz=NY),
        pd.Timestamp("2024-12-24 13:30", tz=NY),
        60,
        90,
        calendars.FX_METAL,
        session,
        NY,
    )
    assert real is True
    real, _reason = _calendar_gap_session(
        pd.Timestamp("2024-12-24 13:30", tz=NY),
        pd.Timestamp("2024-12-24 15:00", tz=NY),
        60,
        90,
        calendars.FX_METAL,
        session,
        NY,
    )
    assert real is False


def test_sin_sesion_comportamiento_legacy() -> None:
    # Sin SessionSegment, _calendar_gap_session cae al clasificador antiguo.
    real, _reason = _calendar_gap_session(
        pd.Timestamp("2024-01-12 17:00", tz=NY),
        pd.Timestamp("2024-01-14 17:00", tz=NY),
        1440,
        36 * 60,
        calendars.NYSE,
        None,
        NY,
    )
    assert real is False


def _synthetic_week(start: str) -> pd.DataFrame:
    begin = pd.Timestamp(f"{start} 17:00", tz=NY)
    end = begin + pd.Timedelta(days=5)
    index = pd.date_range(begin, end, freq="5min", inclusive="left")
    # Pausa diaria 12:00-13:00.
    index = index[index.hour != 15]
    close = pd.Series(range(len(index)), dtype=float) + 100.0
    return pd.DataFrame(
        {"open": close, "high": close + 0.1, "low": close - 0.1, "close": close},
        index=index,
    )


def test_derive_sessions_ignora_miercoles_y_viernes_faltantes() -> None:
    frame = pd.concat(
        [_synthetic_week("2024-01-07"), _synthetic_week("2024-01-14"), _synthetic_week("2024-01-21")]
    ).sort_index()
    # Quitar un miércoles completo y el cierre de un viernes.
    wednesday = frame.index.date == pd.Timestamp("2024-01-10").date()
    frame = frame.loc[~wednesday]
    friday = (frame.index.date == pd.Timestamp("2024-01-19").date()) & (
        frame.index.hour >= 16
    )
    frame = frame.loc[~friday]
    result = derive_year(frame, 2024, 5)
    assert result.friday_close == "17:00"
    assert result.sunday_open == "17:00"
    assert result.pause_start == "15:00"
    assert result.pause_end == "16:00"
    assert result.stable is True
