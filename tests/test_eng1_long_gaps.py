"""ENG-1 C-01: en M1-M30 los huecos largos dentro de sesión también se ven.

Antes ``_gap_analysis`` descartaba sin clasificar todo hueco >= ``max_gap_hours``
en marcos de menos de 60 min: con los mismos minutos ausentes, M15/M30 daban
``ok`` y H1/H4 los contaban. Serie sintética 24/5 estilo índice CFD.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.discovery.config import load_engine_config
from tradinglab.discovery.data_quality import check_dataset
from tradinglab.discovery.resample import resample_session
from tradinglab.discovery.source_quality import quality_config

NY = "America/New_York"
SEGMENTS = {"is": ("2024-01-08", "2024-01-31"), "oos1": ("2024-02-01", "2024-02-20"), "oos2": ("2024-02-21", None)}


def _m1(holes: bool) -> pd.DataFrame:
    idx = pd.date_range("2024-01-07 18:00", "2024-03-01 16:14", freq="1min", tz=NY)
    keep = idx.day_of_week != 5
    keep &= ~((idx.day_of_week == 4) & (idx.hour * 60 + idx.minute >= 16 * 60 + 15))
    keep &= ~((idx.day_of_week == 6) & (idx.hour < 18))
    keep &= ~(idx.hour == 17)
    idx = idx[keep]
    if holes:
        hole1 = (idx >= pd.Timestamp("2024-01-17 00:00", tz=NY)) & (idx < pd.Timestamp("2024-01-17 12:00", tz=NY))
        hole2 = (idx >= pd.Timestamp("2024-02-07 17:00", tz=NY)) & (idx < pd.Timestamp("2024-02-08 17:00", tz=NY))
        idx = idx[~(hole1 | hole2)]
    px = 17000.0
    return pd.DataFrame(
        {"open": px, "high": px + 1, "low": px - 1, "close": px, "volume": 1.0}, index=idx.tz_convert("UTC")
    )


def _report(m1: pd.DataFrame, tf: str):
    cfg = quality_config(load_engine_config().data_quality, "US100", tf, "dukascopy")
    frame = resample_session(m1, tf)
    return check_dataset(frame, "US100", tf, segments=SEGMENTS, config=cfg, data_source="dukascopy")


@pytest.mark.parametrize("tf", ["M15", "M30"])
def test_huecos_largos_en_m15_m30_se_cuentan(tf):
    assert _report(_m1(holes=True), tf).non_scheduled_gaps >= 2


@pytest.mark.parametrize("tf", ["M15", "M30", "H1"])
def test_fines_de_semana_y_pausas_no_cuentan(tf):
    assert _report(_m1(holes=False), tf).non_scheduled_gaps == 0
