"""Remuestreo M1 -> temporalidades: OHLC a mano, corte NY y sin look-ahead."""

from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.discovery.resample import (
    ResampleError,
    resample_session,
    session_labels,
    timeframe_minutes,
)


def _bars(start: str, periods: int, freq: str = "1min") -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    values = pd.Series(range(periods), dtype=float) + 100.0
    return pd.DataFrame(
        {
            "open": values.values,
            "high": values.values + 2.0,
            "low": values.values - 1.0,
            "close": values.values + 0.5,
            "volume": 1.0,
        },
        index=index,
    )


def test_m5_ohcl_calculado_a_mano() -> None:
    frame = _bars("2024-01-08 10:00", 6)
    result = resample_session(frame, "M5")
    assert list(result.index) == [
        pd.Timestamp("2024-01-08 10:00", tz="UTC"),
        pd.Timestamp("2024-01-08 10:05", tz="UTC"),
    ]
    first = result.iloc[0]
    assert first["open"] == pytest.approx(100.0)
    assert first["high"] == pytest.approx(106.0)
    assert first["low"] == pytest.approx(99.0)
    assert first["close"] == pytest.approx(104.5)
    assert first["volume"] == pytest.approx(5.0)
    second = result.iloc[1]
    assert second["open"] == pytest.approx(105.0)
    assert second["high"] == pytest.approx(107.0)
    assert second["low"] == pytest.approx(104.0)
    assert second["close"] == pytest.approx(105.5)


def test_ninguna_vela_usa_minutos_posteriores_a_su_cierre() -> None:
    frame = _bars("2024-01-08 13:57", 30)
    for timeframe in ("M5", "M15", "M30", "H1", "H4", "D1"):
        labels = session_labels(frame.index, timeframe)
        result = resample_session(frame, timeframe)
        duration = pd.Timedelta(minutes=timeframe_minutes(timeframe))
        for label in result.index:
            selected = frame.loc[labels == label]
            assert len(selected) > 0
            assert selected.index.max() < label + duration


def test_hueco_no_fabrica_vela() -> None:
    frame = _bars("2024-01-08 10:00", 15)
    # Vaciar por completo la vela de 10:05-10:09.
    keep = ~(
        (frame.index >= pd.Timestamp("2024-01-08 10:05", tz="UTC"))
        & (frame.index < pd.Timestamp("2024-01-08 10:10", tz="UTC"))
    )
    result = resample_session(frame.loc[keep], "M5")
    assert pd.Timestamp("2024-01-08 10:05", tz="UTC") not in result.index
    assert pd.Timestamp("2024-01-08 10:00", tz="UTC") in result.index
    assert pd.Timestamp("2024-01-08 10:10", tz="UTC") in result.index


def test_h4_y_d1_cortan_a_las_17_ny() -> None:
    index = pd.DatetimeIndex(
        [
            "2024-01-08 13:00",
            "2024-01-08 13:59",
            "2024-01-08 14:00",
            "2024-01-08 21:59",
            "2024-01-08 22:00",
        ],
        tz="UTC",
    )
    values = pd.Series(range(len(index)), dtype=float) + 100.0
    frame = pd.DataFrame(
        {
            "open": values.values,
            "high": values.values + 1.0,
            "low": values.values - 1.0,
            "close": values.values,
        },
        index=index,
    )
    h4 = resample_session(frame, "H4")
    d1 = resample_session(frame, "D1")
    # 13:00-13:59 UTC = 08:00-08:59 NY, dentro de 05:00-09:00 NY.
    assert pd.Timestamp("2024-01-08 10:00", tz="UTC") in h4.index
    # 14:00 UTC = 09:00 NY, inicio del bloque 09:00-13:00 NY.
    assert pd.Timestamp("2024-01-08 14:00", tz="UTC") in h4.index
    # 21:59 UTC = 16:59 NY, todavía en el bloque 13:00-17:00 NY.
    assert pd.Timestamp("2024-01-08 18:00", tz="UTC") in h4.index
    # 22:00 UTC = 17:00 NY: sesión nueva y D1 nueva.
    assert pd.Timestamp("2024-01-08 22:00", tz="UTC") in h4.index
    assert pd.Timestamp("2024-01-08 22:00", tz="UTC") in d1.index
    # Las velas anteriores a las 17:00 NY pertenecen a la sesión del día 7.
    assert pd.Timestamp("2024-01-07 22:00", tz="UTC") in d1.index


def test_pasada_de_hora_no_duplica_etiquetas() -> None:
    frame = _bars("2024-11-03 04:00", 10, freq="30min")
    labels = session_labels(frame.index, "H4")
    assert len(set(labels)) == 2
    result = resample_session(frame, "H4")
    assert len(result) == 2
    assert not result.index.duplicated().any()


def test_columnas_ask_y_volumen() -> None:
    frame = _bars("2024-01-08 10:00", 5)
    frame["ask_open"] = frame["open"] + 0.1
    frame["ask_high"] = frame["high"] + 0.1
    frame["ask_low"] = frame["low"] + 0.1
    frame["ask_close"] = frame["close"] + 0.1
    frame["ask_volume"] = 2.0
    result = resample_session(frame, "M5").iloc[0]
    assert result["ask_open"] == pytest.approx(100.1)
    assert result["ask_high"] == pytest.approx(106.1)
    assert result["ask_low"] == pytest.approx(99.1)
    assert result["ask_close"] == pytest.approx(104.6)
    assert result["ask_volume"] == pytest.approx(10.0)


def test_timeframe_invalido() -> None:
    with pytest.raises(ResampleError, match="no soportado"):
        timeframe_minutes("W1")
