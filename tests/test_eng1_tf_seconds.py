"""ENG-1: duración de la vela con índices de pandas 3 (unidad 'us').

``fastbt`` calculaba la duración con ``asi8 // 1e9``, que supone nanosegundos.
En pandas 3 los índices son de microsegundos por defecto (también al leer
parquet): la duración salía 1000 veces menor. Con ``flat_mode='no_overnight'``
la vela que contiene ``flat_at`` no se marcaba y, con datos de 24 h, el cierre
caía en la última vela del día.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from tradinglab.discovery import fastbt

NY = "America/New_York"


def _m15_24h() -> pd.DataFrame:
    index = pd.date_range("2024-03-05 00:00", "2024-03-07 23:45", freq="15min", tz=NY).tz_convert("UTC")
    assert index.unit == "us"
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=index)


def test_no_overnight_marca_la_vela_que_contiene_flat_at_con_datos_24h():
    bars = _m15_24h()
    limits = fastbt.RunLimits(
        session_tz=NY, session_start="09:30", session_end="15:55", flat_at="15:55",
        flat_mode="no_overnight",
    )
    mask = fastbt.session_mask(bars, limits)
    local = bars.index.tz_convert(NY)
    marked = sorted({ts.strftime("%H:%M") for ts, flag in zip(local, mask.flat_flag) if flag})
    assert marked == ["15:45"]


def test_la_misma_respuesta_con_indice_en_nanosegundos():
    bars = _m15_24h()
    ns = bars.copy()
    ns.index = ns.index.as_unit("ns")
    limits = fastbt.RunLimits(
        session_tz=NY, session_start="09:30", session_end="15:55", flat_at="15:55",
        flat_mode="no_overnight",
    )
    a = fastbt.session_mask(bars, limits).flat_flag
    b = fastbt.session_mask(ns, limits).flat_flag
    assert np.array_equal(a, b)
