from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import yaml

from tradinglab.config import ROOT
from tradinglab.discovery import indicators_ext as ext
from tradinglab.discovery.compiler import compile
from tradinglab.discovery.dsl import (
    canonical_json,
    count_nodes,
    depth,
    resolved_session_tz,
    strategy_hash,
    validate,
)

TEMPLATES = ROOT / "config" / "discovery" / "templates"


def _bars(periods: int = 240, start: str = "2026-11-16 14:30") -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="5min", tz="UTC")
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 0.2, len(index)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0, 0.2, len(index))
    low = np.minimum(open_, close) - rng.uniform(0, 0.2, len(index))
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tickvol": 100.0,
        },
        index=index,
    )


def _strategy(**overrides) -> dict:
    payload = {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "session": {"start": "09:35", "end": "11:30", "flat_at": "15:45", "or_minutes": 15},
        "long_entry": {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "indicator", "ind": "ema", "src": "close", "n": 20},
        },
        "short_entry": {
            "kind": "lt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "indicator", "ind": "ema", "src": "close", "n": 20},
        },
        "exit": {
            "stop": {"type": "atr", "mult": 1.5, "n": 14},
            "target": {"type": "rr", "rr": 2.0},
            "time_exit_bars": 48,
        },
        "sizing": {"risk_per_trade_r": 1.0},
        "limits": {"max_trades_per_day": 2, "cooldown_bars": 5},
    }
    payload.update(overrides)
    if "long_entry" in overrides and "short_entry" not in overrides:
        # Los tests que solo examinan el largo no arrastran un corto ajeno.
        payload["short_entry"] = None
    return payload


def _errors(**overrides) -> list[str]:
    return validate(_strategy(**overrides))


def test_estrategia_valida() -> None:
    assert validate(_strategy()) == []


def test_hash_canonico_estable() -> None:
    strategy = _strategy()
    assert canonical_json(strategy) == canonical_json(strategy)
    assert strategy_hash(strategy) == strategy_hash(strategy)
    changed = _strategy()
    changed["long_entry"]["right"]["n"] = 21
    assert strategy_hash(strategy) != strategy_hash(changed)


def test_nodos_y_profundidad() -> None:
    strategy = _strategy()
    assert count_nodes(strategy) == 6
    assert depth(strategy) == 2


def test_parametro_fuera_de_rango() -> None:
    errors = _errors(
        long_entry={
            "kind": "gt",
            "left": {"kind": "indicator", "ind": "ema", "src": "close", "n": 1},
            "right": {"kind": "const", "value": 100},
        }
    )
    assert any("n" in error and "fuera de rango" in error for error in errors)


def test_parametro_con_paso_invalido() -> None:
    errors = _errors(
        long_entry={
            "kind": "gt",
            "left": {"kind": "indicator", "ind": "bollinger_pct", "n": 20, "params": {"k": 2.05}},
            "right": {"kind": "const", "value": 1},
        }
    )
    assert any("paso" in error for error in errors)
    valid = _errors(
        long_entry={
            "kind": "gt",
            "left": {"kind": "indicator", "ind": "bollinger_pct", "n": 20, "params": {"k": 2.1}},
            "right": {"kind": "const", "value": 1},
        }
    )
    assert valid == []


def test_parametro_desconocido() -> None:
    errors = _errors(
        long_entry={
            "kind": "gt",
            "left": {"kind": "indicator", "ind": "ema", "src": "close", "n": 20, "params": {"foo": 1}},
            "right": {"kind": "const", "value": 100},
        }
    )
    assert any("desconocido" in error for error in errors)


def test_tipo_de_bloque() -> None:
    boolean_indicator = _errors(
        long_entry={"kind": "indicator", "ind": "bos_up", "params": {"left": 5, "right": 5}},
        short_entry=None,
    )
    assert any("pattern/regime" in error for error in boolean_indicator)
    float_pattern = _errors(
        long_entry={"kind": "pattern", "pattern": "ema", "n": 20},
        short_entry=None,
    )
    assert any("indicator" in error for error in float_pattern)


def test_atr_sin_src_es_valido() -> None:
    errors = _errors(
        long_entry={
            "kind": "gt",
            "left": {"kind": "indicator", "ind": "atr", "n": 14},
            "right": {"kind": "const", "value": 1},
        }
    )
    assert errors == []


def test_between_usa_left() -> None:
    valid = _errors(
        long_entry={
            "kind": "between",
            "left": {"kind": "indicator", "ind": "rsi", "n": 14},
            "low": 30,
            "high": 70,
        }
    )
    assert valid == []
    invalid = _errors(
        long_entry={"kind": "between", "low": 30, "high": 70},
    )
    assert any("between" in error for error in invalid)


def test_zona_de_sesion_del_instrumento() -> None:
    assert resolved_session_tz(_strategy()) == "America/New_York"
    assert resolved_session_tz(_strategy(instrument="EURUSD")) == "Europe/London"
    mismatch = _errors(
        session={"tz": "Europe/London", "start": "09:35", "end": "11:30", "flat_at": "15:45"}
    )
    assert any("session_tz" in error for error in mismatch)


def test_sesion_que_cruza_medianoche() -> None:
    strategy = _strategy(
        session={"start": "18:00", "end": "03:00", "flat_at": "02:45", "or_minutes": 15},
        long_entry={"kind": "time_between", "start": "18:00", "end": "03:00"},
        short_entry=None,
    )
    assert validate(strategy) == []


def test_plantillas_cargan_y_validan() -> None:
    paths = sorted(TEMPLATES.glob("*.yaml"))
    assert len(paths) == 19
    names = set()
    for path in paths:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        names.add(payload["name"])
        assert validate(payload["strategy"]) == [], path.name
    assert names == {
        "ny_open_vol_filter",
        "asia_range_reversion",
        "session_breakout_htf",
        "intraday_momentum_close",
        "intraday_momentum_close_v2",
        "intraday_momentum_close_v3",
        "session_breakout_htf_v3",
        "st_reversal_idx_v3",
        "ts_momentum_d1",
        "donchian_vol_h4",
        "d1_extension_reversion",
        "turn_of_month",
        "fix_reversal",
        "london_breakout",
        "st_reversal_idx",
        "trend_pullback_mtf",
        "vol_squeeze_breakout",
        "h1_sma50_session_long",
        "h1_sma50_session_long_v2",
    }


def test_compile_es_determinista() -> None:
    strategy = _strategy()
    frame = _bars()
    first = compile(strategy, frame)
    second = compile(strategy, frame)
    assert np.array_equal(first.long_entry, second.long_entry)
    assert np.array_equal(first.short_entry, second.short_entry)
    assert first.valid_from == second.valid_from
    assert first.valid_from > 0
    assert first.long_entry.dtype == bool


def test_compile_rechaza_indice_sin_zona() -> None:
    frame = _bars()
    frame.index = frame.index.tz_localize(None)
    with pytest.raises(ValueError, match="zona horaria"):
        compile(_strategy(), frame)


def test_vwap_rechaza_indice_sin_zona() -> None:
    frame = _bars()
    frame.index = frame.index.tz_localize(None)
    with pytest.raises(ValueError, match="zona horaria"):
        ext.vwap_session(frame, tz="America/New_York", start="09:35", end="16:00")
    for indicator in (
        ext.adx,
        ext.stochastic,
        ext.cci,
        ext.donchian,
        ext.keltner,
        ext.atr_pct_rank,
        ext.range_compression,
        ext.swing_high,
    ):
        with pytest.raises(ValueError, match="zona horaria"):
            indicator(frame)
    with pytest.raises(ValueError, match="zona horaria"):
        ext.macd(frame["close"])
    with pytest.raises(ValueError, match="zona horaria"):
        ext.bollinger(frame["close"])
    with pytest.raises(ValueError, match="zona horaria"):
        ext.realized_vol(frame["close"])


def test_validate_rechaza_corto_misma_direccion_258() -> None:
    payload = json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "discovery_regla_anomala_258.json"
        ).read_text(encoding="utf-8")
    )
    errors = validate(payload["dsl"])
    assert any("misma dirección" in error for error in errors)


def test_validate_acepta_corto_espejo() -> None:
    from tradinglab.discovery import genetic

    strategy = genetic.template_strategy("ny_open_vol_filter")
    assert validate(strategy) == []
    mirrored = genetic.mirror_expr(strategy["long_entry"])
    assert mirrored == strategy["short_entry"]

