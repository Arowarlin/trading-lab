"""Caché LRU de indicadores: hits, límite y paridad de señales."""

from __future__ import annotations

import copy
import random

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import compiler, dsl, genetic
from tradinglab.discovery.indicator_cache import IndicatorCache


def _bars(bars: int = 400, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-08 00:00", periods=bars, freq="5min", tz="UTC")
    close = 20000.0 + np.cumsum(rng.normal(0.0, 4.0, bars))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(1.0, 5.0, bars)
    low = np.minimum(open_, close) - rng.uniform(1.0, 5.0, bars)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )


def _strategy(threshold: float = 0.5) -> dict:
    return {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "session": {"start": "09:35", "end": "11:30", "flat_at": "15:45"},
        "long_entry": {
            "kind": "and",
            "args": [
                {
                    "kind": "gt",
                    "left": {"kind": "indicator", "ind": "ema", "src": "close", "n": 20},
                    "right": {"kind": "indicator", "ind": "ema", "src": "close", "n": 50},
                },
                {
                    "kind": "regime",
                    "regime": "vol_high",
                    "n": 14,
                    "lookback": 100,
                    "params": {"pct": threshold},
                },
            ],
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "atr", "mult": 2.0, "n": 14},
            "target": {"type": "rr", "rr": 2.0},
        },
        "limits": {"max_trades_per_day": 2, "cooldown_bars": 0},
    }


def test_cache_hits_and_matches_no_cache() -> None:
    bars = _bars()
    strategy = _strategy()
    assert dsl.validate(strategy) == []
    plain = compiler.compile(strategy, bars)
    cache = IndicatorCache(64 * 1024 * 1024, dataset_token=id(bars))
    first = compiler.compile(strategy, bars, cache=cache)
    second_strategy = copy.deepcopy(strategy)
    second_strategy["long_entry"]["args"][1]["params"]["pct"] = 0.9
    second = compiler.compile(second_strategy, bars, cache=cache)
    assert np.array_equal(plain.long_entry, first.long_entry)
    plain_second = compiler.compile(second_strategy, bars)
    assert np.array_equal(plain_second.long_entry, second.long_entry)
    assert cache.stats()["hits"] > 0


def test_cache_disabled_and_tiny_limit() -> None:
    bars = _bars()
    strategy = _strategy()
    zero = IndicatorCache(0, dataset_token=id(bars))
    compiler.compile(strategy, bars, cache=zero)
    assert zero.stats()["hits"] == 0
    assert zero.stats()["entries"] == 0

    tiny = IndicatorCache(256, dataset_token=id(bars))
    compiler.compile(strategy, bars, cache=tiny)
    assert tiny.stats()["entries"] == 0


def test_cache_rejects_other_dataset() -> None:
    first = _bars(seed=4)
    second = _bars(seed=5)
    cache = IndicatorCache(1024 * 1024, dataset_token=id(first))
    compiler.compile(_strategy(), first, cache=cache)
    with pytest.raises(dsl.DslError, match="otro dataset"):
        compiler.compile(_strategy(), second, cache=cache)


def test_random_strategy_compiles_with_cache() -> None:
    bars = _bars()
    strategy = genetic.random_strategy(random.Random(1), "ny_open_vol_filter")
    assert strategy is not None
    cache = IndicatorCache(16 * 1024 * 1024, dataset_token=id(bars))
    signals = compiler.compile(strategy, bars, cache=cache)
    assert len(signals.long_entry) == len(bars)
