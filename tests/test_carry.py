from __future__ import annotations

from datetime import date, time

import pandas as pd
import pytest

from tradinglab.backtest import run
from tradinglab.carry import CostModel, cost_model_from_asset
from tradinglab.intraday import run_event_backtest
from tradinglab.intraday_costs import asset_costs


def _daily_bars(closes: list[float]) -> pd.DataFrame:
    index = pd.bdate_range("2026-11-09", periods=len(closes), tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
        },
        index=index,
    )


def test_tres_noches_con_miercoles_pagan_cinco_veces_el_swap_diario():
    model = CostModel(
        swap_long=-3.65,
        swap_short=-1.0,
        swap_unit="percent_annual",
    )
    notional = 100_000.0
    daily = model.daily_cash(
        "long", notional=notional, shares=1.0, day=date(2026, 11, 9)
    )
    total = model.carry_for_nights(
        "long",
        notional=notional,
        shares=1.0,
        start_day=date(2026, 11, 9),
        end_day=date(2026, 11, 12),
    )
    assert daily < 0
    assert total == pytest.approx(5.0 * daily)


def test_costs_yaml_no_inventa_swap_si_falta_mt5(tmp_path):
    path = tmp_path / "costs.yaml"
    path.write_text(
        "assets:\n"
        "  US100.CASH:\n"
        "    verified: true\n"
        "    commission_type: zero\n"
        "swap:\n"
        "  defaults:\n"
        "    long: null\n"
        "    short: null\n",
        encoding="utf-8",
    )
    asset = asset_costs("US100.CASH", path)
    assert asset.swap_long is None
    assert asset.swap_short is None
    assert asset.swap_provisional is True
    model = cost_model_from_asset(asset)
    assert model.provisional is True
    assert model.status == "costes provisionales"


def test_us100_semana_completa_triple_viernes():
    model = CostModel(
        swap_long=-676.55,
        swap_short=1.75,
        swap_unit="points",
        triple_weekday=4,  # viernes
        point=0.01,
        contract_size=1.0,
    )
    monday = date(2026, 11, 9)
    assert model.daily_cash(
        "long", notional=0.0, shares=1.0, day=monday
    ) == pytest.approx(-6.7655)
    total = model.carry_for_nights(
        "long",
        notional=0.0,
        shares=1.0,
        start_day=monday,
        end_day=date(2026, 11, 16),
    )
    assert total == pytest.approx(7.0 * -6.7655)


def test_fin_de_semana_no_cobra_y_triple_solo_en_su_dia():
    model = CostModel(
        swap_long=-8.59,
        swap_short=0.33,
        swap_unit="percent_annual",
        triple_weekday=2,  # miércoles
    )
    friday = date(2026, 11, 13)
    assert model.carry_for_nights(
        "long",
        notional=100_000.0,
        shares=1.0,
        start_day=friday,
        end_day=date(2026, 11, 16),
    ) == pytest.approx(model.daily_cash(
        "long", notional=100_000.0, shares=1.0, day=friday
    ))

    tuesday = date(2026, 11, 10)
    assert model.carry_for_nights(
        "long",
        notional=100_000.0,
        shares=1.0,
        start_day=tuesday,
        end_day=date(2026, 11, 12),
    ) == pytest.approx(4.0 * model.daily_cash(
        "long", notional=100_000.0, shares=1.0, day=tuesday
    ))

    assert model.carry_for_nights(
        "long",
        notional=100_000.0,
        shares=1.0,
        start_day=tuesday,
        end_day=tuesday,
    ) == 0.0


def test_sin_swap_queda_provisional_y_no_cobra():
    model = CostModel()
    assert model.provisional is True
    assert model.status == "costes provisionales"
    assert model.daily_cash(
        "long", notional=100_000.0, shares=1.0, day=date(2026, 11, 11)
    ) == 0.0


def test_backtest_aplica_carry_y_marca_estado():
    bars = _daily_bars([100.0] * 5)
    target = pd.Series(1.0, index=bars.index)
    model = CostModel(
        swap_long=-3.65,
        swap_short=-1.0,
        swap_unit="percent_annual",
    )
    with_carry = run(
        bars,
        target,
        starting_cash=100_000.0,
        commission_bps=0.0,
        slippage_bps=0.0,
        carry=model,
    )
    without = run(
        bars,
        target,
        starting_cash=100_000.0,
        commission_bps=0.0,
        slippage_bps=0.0,
    )
    assert with_carry.costs_status == "swap incluido"
    assert without.costs_status.startswith("Sin datos")
    assert with_carry.metrics["costs_status"] == "swap incluido"
    assert with_carry.equity.iloc[-1] < without.equity.iloc[-1]
    assert without.equity.iloc[-1] - with_carry.equity.iloc[-1] == pytest.approx(
        50.0, abs=0.5
    )
    assert with_carry.metrics["carry_paid"] < 0
    assert with_carry.metrics["time_in_market"] > 0
    assert without.metrics["carry_paid"] == 0.0


def test_event_backtest_cobra_carry_al_cruzar_noches():
    bars = _daily_bars([100.0, 100.0, 100.0, 100.0])
    bars.loc[bars.index[-1], "low"] = 80.0
    order = {
        "side": "buy",
        "type": "market",
        "stop": 90.0,
        "target": None,
        "created_at": "2026-11-08T00:00:00Z",
        "expires_at": "2026-11-13T00:00:00Z",
    }
    model = CostModel(
        swap_long=-3.65,
        swap_short=-1.0,
        swap_unit="percent_annual",
    )
    result = run_event_backtest(
        bars,
        [order],
        point=0.01,
        commission_bps=0.0,
        spread_bps=0.0,
        slippage_bps=0.0,
        force_exit_time=None,
        symbol="US100.cash",
        session_window=(time(0, 0), time(0, 0)),
        session_tz="UTC",
        session_weekdays=(0, 1, 2, 3, 4),
        carry=model,
    )
    assert result["costs_status"] == "swap incluido"
    assert result["trades"]
    trade = result["trades"][0]
    daily_pct = -3.65 / 100.0 / 365.0
    assert trade["carry_pct"] == pytest.approx(5.0 * daily_pct)
