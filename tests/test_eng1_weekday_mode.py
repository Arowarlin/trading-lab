"""ENG-1 A-01 (entradas): ``weekday_mode`` opcional; por defecto nada cambia."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import dsl, genetic
from tradinglab.discovery.fastbt import ExitSpec, RunLimits, Signals, cfd_costs_from_bps, run

NY = "America/New_York"
ZERO = cfd_costs_from_bps(commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0)


def _d1_bars() -> pd.DataFrame:
    sessions = pd.bdate_range("2024-03-04", "2024-03-15")
    index = pd.DatetimeIndex(
        [(day - pd.Timedelta(days=1)).replace(hour=17).tz_localize(NY) for day in sessions]
    ).tz_convert("UTC")
    return pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}, index=index)


def _entry_index(mode: str) -> int:
    bars = _d1_bars()
    longs = np.zeros(len(bars), dtype=bool)
    longs[4] = True  # sesión del viernes 8
    limits = RunLimits(
        session_tz=NY, session_start="00:00", session_end="23:59", flat_at="23:59",
        allow_next_day_entry=True, close_at_end=True, weekday_mode=mode,
    )
    spec = ExitSpec(stop="pct", stop_mult=2.0, target="pct", target_pct=50.0)
    result = run(Signals(longs, np.zeros(len(bars), dtype=bool), 0), bars, spec, ZERO, limits)
    return result.trades[0].entry_index


def test_label_por_defecto_entra_el_martes():
    assert _entry_index("label") == 6  # la sesión del lunes (etiqueta domingo) se salta


def test_session_entra_el_lunes():
    assert _entry_index("session") == 5


def test_el_hash_de_las_estrategias_no_cambia():
    strategy = genetic.template_strategy("trend_pullback_mtf")
    before = dsl.canonical_json(strategy)
    model = dsl.Strategy.model_validate(strategy)
    assert model.session.weekday_mode == "label"
    assert "weekday_mode" not in before


def test_export_rechaza_session():
    from tradinglab.discovery import export_mql5

    strategy = genetic.template_strategy("ny_open_vol_filter")
    strategy["session"]["weekday_mode"] = "session"
    model = dsl.Strategy.model_validate(strategy)
    with pytest.raises(ValueError, match="weekday_mode"):
        export_mql5.export_strategy(model, account_id="CFD-001")
