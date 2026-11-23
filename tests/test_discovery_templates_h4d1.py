"""Plantillas H4/D1: validación, simetría y sesgo de anticipación.

No hay bloques DSL nuevos: las tres plantillas se componen con bloques ya
probados. Este test cubre lo que sí es nuevo: que la plantilla completa no
mira el futuro y que el modo rejilla respeta el lado declarado.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import compiler, dsl, fastbt, genetic, grid, specs

CASES = [
    ("ts_momentum_d1", "D1", "XAUUSD"),
    ("donchian_vol_h4", "H4", "XAUUSD"),
    ("d1_extension_reversion", "D1", "XAUUSD"),
]


def _bars(name: str, timeframe: str, n: int = 420, seed: int = 7) -> pd.DataFrame:
    freq = "1D" if timeframe == "D1" else "4h"
    index = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    rng = np.random.default_rng(seed)
    if name == "ts_momentum_d1":
        # Varios ciclos para que SMA(50) cruce SMA(200) en ambos sentidos.
        position = np.arange(n)
        close = (
            100.0
            + 30.0 * np.sin(2.0 * np.pi * position / 120.0)
            + 0.08 * position
            + np.cumsum(rng.normal(0.0, 0.4, n))
        )
    else:
        # Tendencia alcista con caídas puntuales: alimenta Donchian y la
        # reversión tras extensión sin sacar el cierre de SMA(200).
        close = 100.0 + np.linspace(0.0, 140.0, n) + np.cumsum(
            rng.normal(0.0, 0.8, n)
        )
        for position in range(230, n, 30):
            close[position] -= 10.0
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0.1, 1.2, n)
    low = np.minimum(open_, close) - rng.uniform(0.1, 1.2, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=index,
    )


def _alter_future(frame: pd.DataFrame, cutoff: int, seed: int) -> pd.DataFrame:
    altered = frame.copy()
    future = altered.index > altered.index[cutoff]
    count = int(future.sum())
    rng = np.random.default_rng(seed)
    last = float(altered["close"].iloc[cutoff])
    close = last + np.cumsum(rng.normal(0.0, 2.5, count))
    open_ = np.r_[last, close[:-1]]
    altered.loc[future, "open"] = open_
    altered.loc[future, "close"] = close
    altered.loc[future, "high"] = np.maximum(open_, close) + rng.uniform(0.1, 2.0, count)
    altered.loc[future, "low"] = np.minimum(open_, close) - rng.uniform(0.1, 2.0, count)
    return altered


@pytest.mark.parametrize(("name", "timeframe", "instrument"), CASES)
def test_plantilla_h4d1_valida_y_declara_su_tf(
    name: str, timeframe: str, instrument: str
) -> None:
    assert genetic.template_timeframes(name) == (timeframe,)
    base = genetic.configured_template(
        name, instrument=instrument, timeframe=timeframe
    )
    assert dsl.validate(base) == []
    assert dsl.count_nodes(base) <= 12
    expected_symmetric = name != "d1_extension_reversion"
    assert genetic.template_symmetric(name) is expected_symmetric
    if expected_symmetric:
        assert base["short_entry"] == genetic.mirror_expr(base["long_entry"])
    else:
        assert base["short_entry"] is None


@pytest.mark.parametrize(("name", "timeframe", "instrument"), CASES)
def test_plantilla_h4d1_sin_lookahead(
    name: str, timeframe: str, instrument: str
) -> None:
    frame = _bars(name, timeframe)
    cutoff = 300
    strategy = genetic.configured_template(
        name, instrument=instrument, timeframe=timeframe
    )
    left = compiler.compile(strategy, frame)
    altered = _alter_future(frame, cutoff, seed=91)
    right = compiler.compile(strategy, altered)

    assert left.valid_from == right.valid_from
    assert left.valid_from <= cutoff + 1
    np.testing.assert_array_equal(left.long_entry[: cutoff + 1], right.long_entry[: cutoff + 1])
    np.testing.assert_array_equal(left.short_entry[: cutoff + 1], right.short_entry[: cutoff + 1])
    # Las señales existen: no es un test vacío de todo False.
    assert left.long_entry.any() or left.short_entry.any()


@pytest.mark.parametrize(("name", "timeframe", "instrument"), CASES)
def test_rejilla_h4d1_respeta_simetria_y_valida(
    name: str, timeframe: str, instrument: str
) -> None:
    strategies = grid.grid_strategies(
        name, instrument=instrument, timeframe=timeframe
    )
    assert len(strategies) == 27
    assert len({dsl.strategy_hash(item) for item in strategies}) == 27
    symmetric = genetic.template_symmetric(name)
    for item in strategies:
        assert dsl.validate(item) == []
        if symmetric:
            assert item["short_entry"] == genetic.mirror_expr(item["long_entry"])
        else:
            assert item["short_entry"] is None


@pytest.mark.parametrize(("name", "timeframe", "instrument"), CASES)
def test_salidas_de_plantilla_identicas_en_python_y_numba(
    name: str, timeframe: str, instrument: str
) -> None:
    if not fastbt.HAVE_NUMBA:
        pytest.skip("numba no está instalado")
    bars = _bars(name, timeframe)
    model = dsl.Strategy.model_validate(
        genetic.configured_template(name, instrument=instrument, timeframe=timeframe)
    )
    signals = compiler.compile(model, bars)
    cost = fastbt.cfd_costs_from_bps(
        commission_bps=1.0, slippage_bps=1.0, spread_bps=2.0
    )
    limits = fastbt.RunLimits(
        session_tz="UTC",
        session_start="00:00",
        session_end="23:59",
        flat_at="23:59",
        weekdays=(0, 1, 2, 3, 4),
        max_trades_per_day=model.limits.max_trades_per_day,
        cooldown_bars=specs.cooldown_bars(model),
        allow_next_day_entry=model.timeframe == "D1",
    )
    exit_spec = specs.exit_spec_from_strategy(model)
    fastbt.set_backend("python")
    python_result = fastbt.run(signals, bars, exit_spec, cost, limits)
    fastbt.set_backend("numba")
    numba_result = fastbt.run(signals, bars, exit_spec, cost, limits)
    assert len(python_result.trades) == len(numba_result.trades) > 0
    for left, right in zip(python_result.trades, numba_result.trades):
        assert left.reason == right.reason
        assert left.entry_price == pytest.approx(right.entry_price)
        assert left.exit_price == pytest.approx(right.exit_price)
    assert python_result.daily_r.equals(numba_result.daily_r)
