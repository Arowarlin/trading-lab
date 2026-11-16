from __future__ import annotations

import pandas as pd
import pytest

from tradinglab import ea_us100
from tradinglab import ea_us100_engine as engine
from tradinglab.ea_registry import get_ea
from tradinglab.nyse_calendar import FULL_HOLIDAYS, is_full_holiday


def test_version_v32():
    assert engine.VERSION == "3.2"


def test_cierre_efectivo_usa_el_calendario():
    assert engine.effective_flat_min(20250703, 1545) == 770
    assert engine.effective_flat_min(20241129, 1545) == 770
    assert engine.effective_flat_min(20260703, 1545) == 945
    assert is_full_holiday(20260703)
    assert engine.effective_flat_min(20250702, 1545) == 945
    assert engine.effective_flat_min(20250703, 1200) == 720
    assert engine.effective_flat_min(20250703, 1545, {}) == 945


def test_entradas_bloqueadas_si_quedan_menos_de_60_min():
    assert engine.entry_allowed(660, 770) is True
    assert engine.entry_allowed(710, 770) is True
    assert engine.entry_allowed(711, 770) is False


@pytest.mark.skipif(
    not ea_us100.CACHE.exists(), reason="cache M5 del EA no disponible"
)
def test_replica_v32_no_cruza_noche_y_no_opera_en_festivos():
    ea = get_ea("us100-ftmo1")
    if ea is None or not ea.setfile.exists():
        pytest.skip("EA o setfile no disponibles")
    frame = pd.read_parquet(ea_us100.CACHE)
    frame.index = pd.DatetimeIndex(frame.index)
    trades = engine.run(
        frame, ea_us100.params_from_set(ea_us100.load_setfile(ea.setfile))
    )

    assert len(trades) > 0
    assert "ent" in trades.columns
    entry_day = pd.to_datetime(trades["t"]).dt.normalize()
    exit_day = pd.to_datetime(trades["t_exit"]).dt.normalize()
    assert (entry_day == exit_day).all()

    days = pd.to_datetime(trades["t"]).dt.strftime("%Y%m%d").astype(int)
    assert not days.isin(FULL_HOLIDAYS).any()
    assert not (days == 20260703).any()

    row = trades[pd.to_datetime(trades["t"]) == pd.Timestamp("2025-07-03 10:00:00")]
    assert len(row) == 1
    assert pd.Timestamp(row.iloc[0]["t_exit"]) == pd.Timestamp(
        "2025-07-03 12:50:00"
    )
