"""Motor multi-temporalidad: minutos, plantillas, HTF y hash de campaña."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import (
    campaigns,
    compiler,
    dsl,
    genetic,
    resample,
    specs,
)
from tradinglab.discovery import (
    indicators_ext as ext,
)
from tradinglab.discovery.timeframes import (
    TIMEFRAMES,
    bars_in_window,
    higher_timeframes,
    minutes_to_bars,
    normalize_timeframe,
    timeframe_minutes,
)


def _bars(n: int = 240, freq: str = "5min", start: str = "2024-01-10 09:30") -> pd.DataFrame:
    index = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = 100.0 + np.arange(n, dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 0.5,
            "low": close - 1.0,
            "close": close,
        },
        index=index,
    )


def test_timeframes_canonicas_y_conversion() -> None:
    assert TIMEFRAMES == ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
    assert normalize_timeframe("30m") == "M30"
    assert normalize_timeframe("4h") == "H4"
    assert timeframe_minutes("M30") == 30
    assert minutes_to_bars(90, "M15") == 6
    assert minutes_to_bars(90, "H1") == 2
    assert minutes_to_bars(90, "D1") == 1
    assert minutes_to_bars(0, "M5") == 0
    assert bars_in_window("18:00", "03:00", "H4") == 3
    assert higher_timeframes("M30") == ("H1", "H4", "D1")


def test_plantillas_declaran_timeframes_compatibles() -> None:
    assert genetic.template_timeframes("ny_open_vol_filter") == ("M1", "M5", "M15")
    assert genetic.template_timeframes("session_breakout_htf") == ("M5", "M15", "M30")
    assert genetic.template_timeframes("asia_range_reversion")[-2:] == ("H4", "D1")


def test_minutos_a_velas_en_specs() -> None:
    strategy = {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M15",
        "session": {"start": "09:35", "end": "11:30", "flat_at": "15:45"},
        "long_entry": {"kind": "gt", "left": {"kind": "price", "price": "close"}, "right": {"kind": "const", "value": 0.0}},
        "short_entry": None,
        "exit": {"stop": {"type": "atr", "mult": 1.5, "n": 14}, "target": {"type": "rr", "rr": 2.0}, "time_exit_minutes": 90},
        "limits": {"max_trades_per_day": 2, "cooldown_minutes": 30},
    }
    model = dsl.Strategy.model_validate(strategy)
    assert specs.time_exit_bars(model) == 6
    assert specs.cooldown_bars(model) == 2


def test_time_exit_bars_y_minutos_no_se_mezclan() -> None:
    payload = {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "long_entry": {"kind": "gt", "left": {"kind": "price", "price": "close"}, "right": {"kind": "const", "value": 0.0}},
        "exit": {"time_exit_bars": 6, "time_exit_minutes": 30},
    }
    errors = dsl.validate(payload)
    assert any("time_exit" in error for error in errors)


def test_warmup_minutes_se_convierte_a_velas() -> None:
    strategy = {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "warmup_minutes": 60,
        "session": {"start": "09:30", "end": "16:00", "flat_at": "16:00"},
        "long_entry": {"kind": "gt", "left": {"kind": "price", "price": "close"}, "right": {"kind": "const", "value": 0.0}},
        "short_entry": None,
    }
    signals = compiler.compile(strategy, _bars(n=200))
    assert signals.valid_from == 12


def _campaign_frame() -> pd.DataFrame:
    return _bars(n=12 * 24 * 45, start="2023-01-02 00:00")


def _benign_quality(*_args, **_kwargs):
    return (
        SimpleNamespace(
            status="ok",
            issues=[],
            granularity={"useful_start": "2023-01-01"},
            segments={},
        ),
        "2023-01-01",
    )


def test_timeframe_entra_en_config_hash(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(campaigns, "_quality", _benign_quality)
    frame = _campaign_frame()
    segments = {
        "is": ["2023-01-02", "2023-01-20"],
        "oos1": ["2023-01-21", "2023-01-25"],
        "oos2": ["2023-01-26", None],
    }
    one = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        frame=frame,
        segments=segments,
        dry_run=True,
        db_path=tmp_path / "discovery.db",
    )
    two = campaigns.register(
        "US100",
        "M15",
        "ny_open_vol_filter",
        frame=frame,
        segments=segments,
        dry_run=True,
        db_path=tmp_path / "discovery.db",
    )
    assert one["config"]["timeframe"] == "M5"
    assert two["config"]["timeframe"] == "M15"
    assert one["config_hash"] != two["config_hash"]


def test_h4_d1_exigen_dukascopy(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(campaigns, "_quality", _benign_quality)
    frame = _campaign_frame()
    segments = {
        "is": ["2023-01-02", "2023-01-20"],
        "oos1": ["2023-01-21", "2023-01-25"],
        "oos2": ["2023-01-26", None],
    }
    with pytest.raises(campaigns.CampaignError, match="Dukascopy"):
        campaigns.register(
            "US100",
            "H4",
            "asia_range_reversion",
            frame=frame,
            segments=segments,
            data_source="broker",
            dry_run=True,
            db_path=tmp_path / "discovery.db",
        )
    preview = campaigns.register(
        "US100",
        "H4",
        "asia_range_reversion",
        frame=frame,
        segments=segments,
        data_source="dukascopy",
        dry_run=True,
        db_path=tmp_path / "discovery.db",
    )
    assert preview["config"]["data_source"] == "dukascopy"


def test_plantilla_no_compatible_se_rechaza(tmp_path) -> None:
    with pytest.raises(campaigns.CampaignError, match="no declara M30"):
        campaigns.register(
            "US100",
            "M30",
            "ny_open_vol_filter",
            frame=_campaign_frame(),
            dry_run=True,
            db_path=tmp_path / "discovery.db",
        )


def _htf_fixture(base: str, higher: str) -> tuple[pd.DataFrame, np.ndarray]:
    htf_minutes = timeframe_minutes(higher)
    base_minutes = timeframe_minutes(base)
    if htf_minutes % base_minutes:
        raise AssertionError("TF no divisible")
    bars_per_period = htf_minutes // base_minutes
    periods = 3
    n = periods * bars_per_period
    # La rejilla HTF arranca en la sesión 17:00 NY (22:00 UTC en invierno).
    index = pd.date_range(
        "2024-01-01 22:00", periods=n, freq=f"{base_minutes}min", tz="UTC"
    )
    period_ids = pd.factorize(resample.session_labels(index, higher))[0]
    close = np.empty(n, dtype=float)
    for period in range(periods):
        mask = period_ids == period
        positions = np.arange(mask.sum(), dtype=float)
        direction = 1.0 if period % 2 == 0 else -1.0
        close[mask] = 100.0 + period * 10.0 + direction * positions
    open_ = close - 0.5
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + 0.1,
            "low": np.minimum(open_, close) - 0.1,
            "close": close,
        },
        index=index,
    )
    expected = np.zeros(n, dtype=bool)
    for period in range(1, periods):
        expected[period_ids == period] = period % 2 == 1
    return frame, expected


def test_htf_usa_solo_la_vela_cerrada_en_cada_par() -> None:
    failures: list[str] = []
    for base in TIMEFRAMES:
        for higher in higher_timeframes(base):
            frame, expected = _htf_fixture(base, higher)
            strategy = {
                "dsl_version": "1",
                "instrument": "US100",
                "market": "cfd",
                "timeframe": base,
                "session": {
                    "start": "00:00",
                    "end": "23:59",
                    "flat_at": "23:59",
                    "or_minutes": 15,
                },
                "long_entry": {
                    "kind": "htf",
                    "tf": higher,
                    "expr": {
                        "kind": "gt",
                        "left": {"kind": "price", "price": "close"},
                        "right": {"kind": "price", "price": "open"},
                    },
                },
                "short_entry": None,
            }
            signals = compiler.compile(strategy, frame)
            _local, session_mask = ext._session_mask(
                frame.index, "America/New_York", "00:00", "23:59"
            )
            expected = expected & session_mask.to_numpy(dtype=bool)
            if not np.array_equal(signals.long_entry, expected):
                failures.append(f"{base}->{higher}")
    assert failures == []


def test_htf_inferior_o_igual_se_rechaza() -> None:
    strategy = {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "H1",
        "long_entry": {
            "kind": "htf",
            "tf": "M30",
            "expr": {
                "kind": "gt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "const", "value": 0.0},
            },
        },
        "short_entry": None,
    }
    errors = dsl.validate(strategy)
    assert any("superior" in error for error in errors)
