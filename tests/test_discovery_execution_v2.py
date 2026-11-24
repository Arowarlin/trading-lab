"""T10 · Modelo de ejecución BID/ASK v2, con resultados calculados a mano."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import fastbt
from tradinglab.discovery.costs import CostBook
from tradinglab.propfund.costs import CostProfile
from tradinglab.propfund.models import Market

WEEK = (0, 1, 2, 3, 4, 5, 6)
P = 10_000.0
SEGMENTS = {
    "is": ["2023-01-02", "2023-04-30"],
    "oos1": ["2023-05-01", "2023-05-31"],
    "oos2": ["2023-06-01", None],
}


def _frame(
    n: int = 40, *, price: float = P, start: str = "2025-01-06 10:00"
) -> pd.DataFrame:
    index = pd.date_range(start, periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price}, index=index
    )


def _signals(
    bars: pd.DataFrame, *, long_at=(), short_at=()
) -> fastbt.Signals:
    long = np.zeros(len(bars), dtype=bool)
    short = np.zeros(len(bars), dtype=bool)
    for position in long_at:
        long[position] = True
    for position in short_at:
        short[position] = True
    return fastbt.Signals(long, short)


def _limits(**kwargs) -> fastbt.RunLimits:
    base = {
        "session_tz": "UTC",
        "session_start": "00:00",
        "session_end": "23:00",
        "weekdays": WEEK,
        "close_at_end": False,
    }
    base.update(kwargs)
    return fastbt.RunLimits(**base)


def _cost(*, spread: float = 2.0, commission: float = 0.0, slip: float = 0.0):
    return fastbt.CfdBpsCosts(
        commission_bps=commission, slippage_bps=slip, spread_bps=spread
    )


def _bps(trade: fastbt.Trade) -> float:
    assert trade.r_cost is not None and trade.risk_price and trade.entry_price
    return trade.r_cost * trade.risk_price / trade.entry_price * 10_000.0


@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("exit_mode", ["tiempo", "senal", "flat", "fin"])
def test_un_solo_spread_en_salidas_que_no_son_objetivo(side, exit_mode):
    long_at, short_at = ([5], []) if side == "long" else ([], [5])
    if exit_mode == "tiempo":
        bars = _frame()
        exit_spec = fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None, time_exit_bars=3)
        limits = _limits()
    elif exit_mode == "senal":
        bars = _frame()
        exit_spec = fastbt.ExitSpec(
            stop="pct", stop_mult=1.0, target=None, opposite_signal=True
        )
        if side == "long":
            short_at = [8]
        else:
            long_at = [8]
        limits = _limits()
    elif exit_mode == "flat":
        bars = _frame(start="2025-01-06 08:00")
        long_at, short_at = ([1], []) if side == "long" else ([], [1])
        exit_spec = fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None)
        limits = _limits(flat_at="12:00")
    else:
        bars = _frame()
        exit_spec = fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None)
        limits = _limits(close_at_end=True)

    result = fastbt.run(
        _signals(bars, long_at=long_at, short_at=short_at),
        bars,
        exit_spec,
        _cost(),
        limits,
        cost_model_version=2,
    )
    trade = result.trades[0]
    assert _bps(trade) == pytest.approx(2.0)
    assert trade.entry_cost_bps + trade.exit_cost_bps == pytest.approx(2.0)


def test_largo_stop_cuesta_un_spread():
    bars = _frame()
    bars.iloc[8, bars.columns.get_loc("low")] = 9_899.0
    result = fastbt.run(
        _signals(bars, long_at=[5]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None),
        _cost(),
        _limits(),
        cost_model_version=2,
    )
    trade = result.trades[0]
    assert trade.reason == "stop" and trade.exit_index == 8
    assert trade.exit_price == 9_900.0
    assert _bps(trade) == pytest.approx(2.0)


def test_corto_stop_dispara_con_el_ask_y_lleva_el_spread_en_el_precio():
    bars = _frame()
    bars.iloc[8, bars.columns.get_loc("high")] = 10_099.0
    result = fastbt.run(
        _signals(bars, short_at=[5]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None, time_exit_bars=10),
        _cost(),
        _limits(),
        cost_model_version=2,
    )
    trade = result.trades[0]
    assert trade.reason == "stop" and trade.exit_index == 8
    # max(stop_p=10100, open_ask=10002) = 10100; el spread ya está en el precio.
    assert trade.exit_price == 10_100.0
    assert trade.entry_cost_bps == trade.exit_cost_bps == 0.0
    assert trade.r_cost == pytest.approx(0.0)
    # Coste económico: el BID equivalente del stop es 10100 - 2 = 10098.
    economic = (
        trade.exit_price - (trade.stop - P * 2.0 / 10_000.0)
    ) / trade.entry_price * 10_000.0
    assert economic == pytest.approx(2.0)

    v1 = fastbt.run(
        _signals(bars, short_at=[5]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None, time_exit_bars=10),
        _cost(),
        _limits(),
        cost_model_version=1,
    )
    assert v1.trades[0].reason == "time_exit"
    assert v1.trades[0].exit_index == 16


def test_objetivo_largo_paga_solo_el_spread_de_entrada():
    bars = _frame()
    bars.iloc[8, bars.columns.get_loc("high")] = 10_060.0
    bars.iloc[8, bars.columns.get_loc("low")] = 9_990.0
    result = fastbt.run(
        _signals(bars, long_at=[5]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target="pct", target_pct=0.5),
        _cost(),
        _limits(),
        cost_model_version=2,
    )
    trade = result.trades[0]
    assert trade.reason == "target" and trade.exit_price == 10_050.0
    assert _bps(trade) == pytest.approx(2.0)


def test_objetivo_corto_sale_al_ask_y_solo_cobra_comision():
    bars = _frame()
    bars.iloc[8, bars.columns.get_loc("high")] = 10_010.0
    bars.iloc[8, bars.columns.get_loc("low")] = 9_940.0
    result = fastbt.run(
        _signals(bars, short_at=[5]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target="pct", target_pct=0.5),
        _cost(commission=1.0),
        _limits(),
        cost_model_version=2,
    )
    trade = result.trades[0]
    assert trade.reason == "target" and trade.exit_price == 9_950.0
    assert trade.entry_cost_bps == trade.exit_cost_bps == 1.0
    assert _bps(trade) == pytest.approx(2.0)  # 1 bps de comisión por lado


def test_spread_variable_usa_la_barra_de_cada_pata():
    bars = _frame(start="2025-01-06 08:00")
    cost = fastbt.CfdBpsCosts(
        commission_bps=0.0,
        slippage_bps=0.0,
        spread_bps_by_hour={10: 2.0, 11: 5.0, 12: 10.0},
    )
    # Señal en 09:00 -> entrada en 10:00 (2 bps); salida temporal en 12:00.
    long_result = fastbt.run(
        _signals(bars, long_at=[1]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None, time_exit_bars=2),
        cost,
        _limits(),
        cost_model_version=2,
    )
    long_trade = long_result.trades[0]
    assert long_trade.entry_cost_bps == pytest.approx(2.0)
    assert long_trade.exit_cost_bps == pytest.approx(0.0)
    assert _bps(long_trade) == pytest.approx(2.0)

    short_result = fastbt.run(
        _signals(bars, short_at=[1]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None, time_exit_bars=2),
        cost,
        _limits(),
        cost_model_version=2,
    )
    short_trade = short_result.trades[0]
    assert short_trade.entry_cost_bps == pytest.approx(0.0)
    assert short_trade.exit_cost_bps == pytest.approx(10.0)
    assert _bps(short_trade) == pytest.approx(10.0)


def test_comision_round_turn_de_cinco_dolares_por_lote():
    profile = CostProfile(
        account="X",
        symbol="EURUSD",
        market=Market.CFD,
        commission_type="per_lot_usd",
        commission_value=5.0,
        commission_side="round_turn",
        spread_price=0.0,
        slippage_price=0.0,
    )
    cost = fastbt.CfdProfileCosts(profile, contract_size=100_000)
    expected = 2.5 / (1.10 * 100_000) * 10_000.0
    assert cost._commission_bps(np.array([1.10]))[0] == pytest.approx(expected)


def test_paridad_v1_con_la_misma_serie():
    bars = _frame()
    bars.iloc[8, bars.columns.get_loc("low")] = 9_899.0
    arguments = (
        _signals(bars, long_at=[5]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target="rr", target_rr=2.0),
        _cost(commission=1.0, slip=1.0),
        _limits(),
    )
    implicit = fastbt.run(*arguments)
    explicit = fastbt.run(*arguments, cost_model_version=1)
    assert implicit.trades == explicit.trades
    assert implicit.metrics == explicit.metrics
    assert implicit.trades[0].spread_r is None


def test_paridad_de_convencion_con_ea_us100_engine():
    """Misma regla que ea_us100_engine.py:134-158, con slippage 0."""

    bars = _frame()
    bars.iloc[8, bars.columns.get_loc("high")] = 10_099.0
    bars.iloc[8, bars.columns.get_loc("low")] = 9_899.0
    spread_bps = np.full(len(bars), 2.0)
    spread_bps[8] = 6.0  # el ASK del stop usa el spread de su propia barra

    class _PanelCost(fastbt.CfdBpsCosts):
        def panel(self, bars: pd.DataFrame) -> fastbt.CostPanel:
            return fastbt.CostPanel(
                spread_bps=spread_bps.copy(),
                slip_bps=np.zeros(len(bars)),
                comm_bps=np.zeros(len(bars)),
            )

    cost = _PanelCost(commission_bps=0.0, slippage_bps=0.0, spread_bps=2.0)

    # Largo: entra al ASK de la barra 6 y sale al BID en el stop de la barra 8.
    long_result = fastbt.run(
        _signals(bars, long_at=[5]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None),
        cost,
        _limits(),
        cost_model_version=2,
    )
    long_trade = long_result.trades[0]
    entry_bid = float(bars["open"].iloc[6])
    engine_long_entry = entry_bid + entry_bid * spread_bps[6] / 10_000.0
    engine_long_exit = min(9_900.0, float(bars["open"].iloc[8]))
    assert long_trade.entry_price + long_trade.entry_price * spread_bps[6] / 10_000.0 == pytest.approx(
        engine_long_entry
    )
    assert long_trade.exit_price == pytest.approx(engine_long_exit)

    # Corto: entra al BID y el stop lo dispara el ASK de la barra 8.
    short_result = fastbt.run(
        _signals(bars, short_at=[5]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None, time_exit_bars=10),
        cost,
        _limits(),
        cost_model_version=2,
    )
    short_trade = short_result.trades[0]
    engine_short_entry = float(bars["open"].iloc[6])
    engine_short_exit = max(
        10_100.0, float(bars["open"].iloc[8]) * (1 + spread_bps[8] / 10_000.0)
    )
    assert short_trade.entry_price == pytest.approx(engine_short_entry)
    assert short_trade.exit_price == pytest.approx(engine_short_exit)


def test_version_por_campana(tmp_path):
    from tradinglab.discovery import campaigns, engine, jobs

    frame = engine.synthetic_frame(years=0.5, seed=17)
    preview = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="v2-default",
        dry_run=True,
        db_path=tmp_path / "discovery.db",
    )
    assert preview["config"]["cost_model_version"] == 2

    old = {
        "id": "vieja",
        "instrument": "US100",
        "timeframe": "M5",
        "config": {"cost": {"account": "CFD-001"}},
    }
    assert jobs.QueueSetup.from_campaign(old).cost_model_version == 1


def test_costbook_aplica_las_mismas_reglas():
    bars = _frame()
    panel = _cost().panel(bars)
    account = SimpleNamespace(
        account="CFD-X",
        instrument="US100",
        panel=lambda bars: panel,
        swap=None,
    )
    book = CostBook(
        [account], mode="target", session_tz="UTC", cost_model_version=2
    )
    result = fastbt.run(
        _signals(bars, long_at=[5]),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=1.0, target=None, time_exit_bars=3),
        book,
        _limits(),
        cost_model_version=2,
    )
    applied = book.apply(result.trades)
    trade = applied.trades[0]
    assert _bps(trade) == pytest.approx(2.0)
    assert trade.spread_r == pytest.approx(2.0 / 10_000.0 * trade.entry_price / trade.risk_price)
    assert trade.slip_r == pytest.approx(0.0)
    assert trade.comm_r == pytest.approx(0.0)
    assert (
        trade.spread_r + trade.slip_r + trade.comm_r - (trade.swap_r or 0.0)
        == pytest.approx(trade.r_cost)
    )
