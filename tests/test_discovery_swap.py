"""Swap de financiación en el coste del Discovery Lab (R9c)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import fastbt
from tradinglab.discovery.config import load_engine_config
from tradinglab.discovery.costs import AccountCost, CostBook, LocalSpread
from tradinglab.propfund.costs import CostProfile, SwapSpec, estimate_cfd, load_profile, rollover_units
from tradinglab.propfund.models import Market

NY = "America/New_York"


def _profile(swap_long: float, swap_short: float, *, mode: int = 1) -> CostProfile:
    return CostProfile(
        account="TEST",
        symbol="XAUUSD",
        market=Market.CFD,
        spread_price=0.4,
        spread_p75_price=0.4,
        slippage_price=0.15,
        commission_type="zero",
        commission_value=0.0,
        swap_long=swap_long,
        swap_short=swap_short,
        swap_mode=mode,
        swap_rollover3days=3,
        swap_rollover_hour="17:00",
        swap_rollover_tz=NY,
        point=0.01,
    )


def _bars(n: int = 20) -> pd.DataFrame:
    index = pd.date_range("2026-11-02 17:00", periods=n, freq="D", tz=NY)
    close = 2000.0 + np.arange(n) * 0.5
    return pd.DataFrame(
        {"open": close, "high": close + 2, "low": close - 2, "close": close},
        index=index,
    )


def _signals(bars: pd.DataFrame, position: int = 15) -> fastbt.Signals:
    long = np.zeros(len(bars), dtype=bool)
    long[position] = True
    return fastbt.Signals(long, np.zeros(len(bars), dtype=bool), 0)


def _limits() -> fastbt.RunLimits:
    return fastbt.RunLimits(
        session_tz=NY,
        session_start="00:00",
        session_end="23:59",
        flat_at="23:59",
        weekdays=(0, 1, 2, 3, 4),
        allow_next_day_entry=True,
    )


def test_noches_cero_una_y_triple() -> None:
    monday = pd.Timestamp("2026-11-23 17:00", tz=NY)
    tuesday = pd.Timestamp("2026-11-24 17:00", tz=NY)
    thursday = pd.Timestamp("2026-11-26 17:00", tz=NY)
    assert rollover_units(monday, monday, triple_day=3) == 0
    assert rollover_units(monday, tuesday, triple_day=5) == 1
    # 00:00 del miércoles del servidor = martes 17:00 NY: triple FX.
    assert rollover_units(monday, tuesday, triple_day=3) == 3
    assert rollover_units(monday, thursday, triple_day=3) == 5


def test_swap_points_largo_corto_y_positivo() -> None:
    spec = SwapSpec(
        long=-54.46,
        short=25.0,
        mode=1,
        triple_day=3,
        point=0.01,
    )
    assert spec.per_night_r(
        side="long", entry_price=2000.0, risk_price=10.0
    ) == pytest.approx(-0.05446)
    assert spec.per_night_r(
        side="short", entry_price=2000.0, risk_price=10.0
    ) == pytest.approx(0.025)
    monday = pd.Timestamp("2026-11-23 17:00", tz=NY)
    tuesday = pd.Timestamp("2026-11-24 17:00", tz=NY)
    assert spec.r(
        side="long",
        entry_price=2000.0,
        risk_price=10.0,
        entry_time=monday,
        exit_time=tuesday,
    ) == pytest.approx(-0.05446 * 3)
    one_night = SwapSpec(
        long=-54.46,
        short=25.0,
        mode=1,
        triple_day=5,
        point=0.01,
    )
    assert one_night.r(
        side="long",
        entry_price=2000.0,
        risk_price=10.0,
        entry_time=monday,
        exit_time=tuesday,
    ) == pytest.approx(-0.05446)


def test_swap_interest_current() -> None:
    spec = SwapSpec(
        long=-7.33,
        short=-1.33,
        mode=5,
        triple_day=5,
        point=0.01,
    )
    expected = 20000.0 * (-7.33 / 100.0 / 360.0) / 100.0
    assert spec.per_night_r(
        side="long", entry_price=20000.0, risk_price=100.0
    ) == pytest.approx(expected)
    assert expected < 0.0


def test_fastbt_cobra_swap_y_lo_expone() -> None:
    bars = _bars()
    cost = fastbt.cost_from_profile(_profile(-54.46, -15.0))
    limits = _limits()
    prepared = fastbt.prepare(bars, cost, atr_windows=(14,), sessions=(limits,))
    result = fastbt.run(
        _signals(bars),
        bars,
        fastbt.ExitSpec(stop="atr", stop_mult=10.0, target=None, time_exit_bars=2),
        cost,
        limits,
        prepared=prepared,
    )
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.swap_r is not None
    assert trade.swap_r < 0.0
    expected = -54.46 * 0.01 / float(trade.risk_price) * 2
    assert trade.swap_r == pytest.approx(expected)
    assert trade.r_cost == pytest.approx(
        (trade.entry_cost_bps + trade.exit_cost_bps)
        / 10_000.0
        * trade.entry_price
        / float(trade.risk_price)
        - trade.swap_r
    )


def test_estimate_cfd_incluye_swap() -> None:
    profile = _profile(-54.46, -15.0)
    estimate = estimate_cfd(
        profile,
        lots=1.0,
        price=2000.0,
        contract_size=100.0,
        nights=3,
        side="long",
    )
    assert estimate.complete, estimate.missing
    assert estimate.components["swap"] == pytest.approx(
        -54.46 * 0.01 * 100.0 * 1.0 * 3
    )


def _account(name: str, swap_long: float) -> AccountCost:
    profile = _profile(swap_long, swap_long)
    profile = CostProfile(**{**profile.__dict__, "account": name})
    cost = fastbt.CfdProfileCosts(profile, contract_size=100.0)
    spread = LocalSpread(
        account=name,
        instrument="XAUUSD",
        broker_symbol="XAUUSD",
        source="test",
        p75_bps={},
        days_by_hour={},
        from_ts_by_hour={},
        to_ts_by_hour={},
        missing_hours=(),
        issues=(),
    )
    return AccountCost(
        account=name,
        instrument="XAUUSD",
        profile=profile,
        spread=spread,
        cost=cost,
        assumed_slippage=0.15,
        slippage_source="test",
    )


def test_cost_book_best_worst_incluye_swap() -> None:
    bars = _bars()
    signals = _signals(bars)
    limits = _limits()
    base = fastbt.run(
        signals,
        bars,
        fastbt.ExitSpec(stop="atr", stop_mult=10.0, target=None, time_exit_bars=2),
        fastbt.cfd_costs_from_bps(
            commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0
        ),
        limits,
    )
    assert len(base.trades) == 1
    accounts = [_account("A", -100.0), _account("B", -1.0)]
    worst = CostBook(accounts, mode="worst", session_tz=NY)
    worst.panel(bars)
    applied = worst.apply(base.trades, session_tz=NY)
    assert applied.selected_account == "A"
    assert applied.trades[0].swap_r == pytest.approx(
        -100.0 * 0.01 / float(applied.trades[0].risk_price) * 2
    )
    best = CostBook(accounts, mode="best", session_tz=NY)
    best.panel(bars)
    chosen = best.apply(base.trades, session_tz=NY)
    assert chosen.selected_account == "B"

def _us100_bars() -> pd.DataFrame:
    index = pd.date_range("2026-11-02 17:00", periods=20, freq="D", tz=NY)
    close = 20000.0 + np.arange(20) * 5.0
    return pd.DataFrame(
        {"open": close, "high": close + 4, "low": close - 4, "close": close},
        index=index,
    )


def _us100_result(side: str):
    bars = _us100_bars()
    profile = load_profile("CFD-001", "US100", firm="ftmo")
    cost = fastbt.cost_from_profile(profile)
    limits = _limits()
    prepared = fastbt.prepare(bars, cost, atr_windows=(14,), sessions=(limits,))
    long = np.zeros(len(bars), dtype=bool)
    short = np.zeros(len(bars), dtype=bool)
    if side == "long":
        long[15] = True
    else:
        short[15] = True
    result = fastbt.run(
        fastbt.Signals(long, short, 0),
        bars,
        fastbt.ExitSpec(stop="atr", stop_mult=10.0, target=None, time_exit_bars=2),
        cost,
        limits,
        prepared=prepared,
    )
    assert len(result.trades) == 1
    return result.trades[0]


def test_config_swap_credit_false_por_defecto() -> None:
    assert load_engine_config().discovery.swap_credit is False


def test_largo_us100_ftmo_no_cuenta_credito() -> None:
    trade = _us100_result("long")
    assert trade.swap_r == 0.0
    expected = (
        (trade.entry_cost_bps + trade.exit_cost_bps)
        / 10_000.0
        * trade.entry_price
        / float(trade.risk_price)
    )
    assert trade.r_cost == pytest.approx(expected)


def test_corto_us100_ftmo_cobra_coste() -> None:
    trade = _us100_result("short")
    assert trade.swap_r is not None and trade.swap_r < 0.0


def test_largo_us100_cfd006_cobra_coste() -> None:
    from dataclasses import replace as dataclass_replace

    profile = load_profile("CFD-006", "US100", firm="fundingpips")
    profile = dataclass_replace(profile, slippage_price=0.01)
    bars = _us100_bars()
    cost = fastbt.cost_from_profile(profile)
    limits = _limits()
    prepared = fastbt.prepare(bars, cost, atr_windows=(14,), sessions=(limits,))
    long = np.zeros(len(bars), dtype=bool)
    long[15] = True
    result = fastbt.run(
        fastbt.Signals(long, np.zeros(len(bars), dtype=bool), 0),
        bars,
        fastbt.ExitSpec(stop="atr", stop_mult=10.0, target=None, time_exit_bars=2),
        cost,
        limits,
        prepared=prepared,
    )
    assert len(result.trades) == 1
    assert result.trades[0].swap_r < 0.0

def test_cost_book_descarta_credito_en_discovery() -> None:
    bars = _bars()
    base = fastbt.run(
        _signals(bars),
        bars,
        fastbt.ExitSpec(stop="atr", stop_mult=10.0, target=None, time_exit_bars=2),
        fastbt.cfd_costs_from_bps(
            commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0
        ),
        _limits(),
    )
    account = _account("CREDIT", 100.0)
    book = CostBook([account], mode="target", session_tz=NY)
    book.panel(bars)
    applied = book.apply(base.trades, session_tz=NY)
    assert applied.trades[0].swap_r == 0.0
