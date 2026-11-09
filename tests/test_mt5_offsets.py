from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from tradinglab.execution.mt5 import MT5Broker
from tradinglab.execution.mt5_offsets import (
    infer_bar_offsets,
    offset_periods,
    session_bounds,
)


def _server_index(values: list[str]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp(value, tz="UTC") for value in values])


def test_bordes_semanales_siguen_horario_de_eeuu() -> None:
    # 2025-03-09: EE. UU. pasa a EDT (UTC-4); la apertura dominical pasa de
    # 22:00 a 21:00 UTC. El servidor sigue el cambio: +2 -> +3.
    winter_open, winter_close = session_bounds(date(2025, 3, 3))
    summer_open, summer_close = session_bounds(date(2025, 3, 10))
    assert winter_open.hour == 22 and winter_close.hour == 22
    assert summer_open.hour == 21 and summer_close.hour == 21


def test_offset_por_periodo_cambia_en_dst_eeuu() -> None:
    index = _server_index(
        [
            "2025-03-03 00:00",  # lunes servidor, aún GMT+2
            "2025-03-10 00:00",  # lunes servidor, ya GMT+3
            "2025-10-27 00:00",  # lunes servidor, aún GMT+3
            "2025-11-03 00:00",  # lunes servidor, ya GMT+2
        ]
    )
    offsets = infer_bar_offsets(index, "M15")
    assert offsets.tolist() == pytest.approx([2.0, 3.0, 3.0, 2.0])


def test_misma_apertura_utc_antes_y_despues_del_cambio() -> None:
    # La sesión de las 08:00 UTC se etiqueta 10:00 en servidor (+2) y 11:00
    # en servidor (+3). Con offset por barra, ambas vuelven a 08:00 UTC.
    index = _server_index(
        [
            "2025-03-03 00:00",
            "2025-03-05 10:00",
            "2025-03-10 00:00",
            "2025-03-12 11:00",
        ]
    )
    offsets = infer_bar_offsets(index, "H1")
    utc = (index - pd.to_timedelta(offsets.to_numpy(), unit="h")).to_list()
    assert utc[1] == pd.Timestamp("2025-03-05 08:00", tz="UTC")
    assert utc[3] == pd.Timestamp("2025-03-12 08:00", tz="UTC")


def test_offset_periods_resume_tramos() -> None:
    index = _server_index(["2025-03-03 00:00", "2025-03-10 00:00"])
    offsets = infer_bar_offsets(index, "M15")
    periods = offset_periods(index, offsets)
    assert [row["offset"] for row in periods] == [2.0, 3.0]
    assert periods[0]["start"].startswith("2025-03-02T22:00")
    assert periods[1]["start"].startswith("2025-03-09T21:00")


def test_rates_aplica_offset_por_barra(monkeypatch) -> None:
    stamps = [
        pd.Timestamp("2025-03-03 00:00", tz="UTC").timestamp(),
        pd.Timestamp("2025-03-05 10:00", tz="UTC").timestamp(),
        pd.Timestamp("2025-03-10 00:00", tz="UTC").timestamp(),
        pd.Timestamp("2025-03-12 11:00", tz="UTC").timestamp(),
    ]
    dtype = [
        ("time", "i8"),
        ("open", "f8"),
        ("high", "f8"),
        ("low", "f8"),
        ("close", "f8"),
        ("tick_volume", "f8"),
        ("spread", "f8"),
    ]
    raw = np.array(
        [(stamp, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0) for stamp in stamps],
        dtype=dtype,
    )

    class FakeMT5:
        TIMEFRAME_M1 = 1
        TIMEFRAME_M5 = 5
        TIMEFRAME_M15 = 15
        TIMEFRAME_M30 = 30
        TIMEFRAME_H1 = 60
        TIMEFRAME_H4 = 240
        TIMEFRAME_D1 = 1440
        TIMEFRAME_W1 = 10080

        @staticmethod
        def copy_rates_from_pos(symbol, timeframe, start, count):
            return raw

        @staticmethod
        def last_error():
            return (0, "ok")

    broker = MT5Broker(server_utc_offset_hours=2, dry_run=True)
    broker._connected = True
    fake = FakeMT5()
    monkeypatch.setattr(broker, "_require", lambda: fake)
    monkeypatch.setattr(broker, "symbol_spec", lambda symbol: {})

    frame = broker.rates("EURUSD", "M15", count=4)
    assert frame.index[1] == pd.Timestamp("2025-03-05 08:00", tz="UTC")
    assert frame.index[3] == pd.Timestamp("2025-03-12 08:00", tz="UTC")
    assert [row["offset"] for row in broker.rate_offset_periods] == [2.0, 3.0]
