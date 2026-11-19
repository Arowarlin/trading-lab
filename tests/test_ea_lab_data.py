from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from tradinglab.ea_lab.data import (
    DataError,
    apply_spread_floor,
    load_m5_us500,
    measured_spread,
    validate_bars,
)


def _frame(*, start: str = "2026-11-19 09:30", periods: int = 20) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="5min")
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "tickvol": 10.0,
            "spread": 40.0,
        },
        index=index,
    )


class _FakeBroker:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.calls: list[str] = []

    def symbol_spec(self, symbol: str) -> dict:
        self.calls.append(f"symbol_spec:{symbol}")
        return {"point": 0.01, "digits": 2, "tick_size": 0.01, "contract_size": 1.0}

    def rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        self.calls.append(f"rates:{symbol}:{timeframe}:{count}")
        return self.frame.copy()


def test_carga_desde_broker_y_cache_propia(tmp_path):
    frame = _frame()
    cache = tmp_path / "us500_m5.parquet"
    broker = _FakeBroker(frame)
    bundle = load_m5_us500(refresh=True, cache_path=cache, broker=broker)
    assert bundle.source == "mt5-attach-only"
    assert cache.exists()
    assert bundle.spec["point"] == 0.01
    assert broker.calls == ["symbol_spec:US500.cash", "rates:US500.cash:M5:400000"]

    cached = load_m5_us500(cache_path=cache)
    assert cached.source == "mt5-attach-only"
    assert cached.downloaded_at
    assert cached.spec["digits"] == 2
    assert list(cached.frame.columns) == ["open", "high", "low", "close", "tickvol", "spread"]


def test_validacion_detecta_duplicados_invalidas_y_sesion():
    frame = _frame(periods=20)
    duplicated = pd.concat([frame, frame.iloc[[3]]])
    duplicated.loc[duplicated.index[0], "high"] = 90.0  # high < low
    report = validate_bars(
        duplicated,
        {"point": 0.01, "digits": 2},
        start="2026-11-19",
        end="2026-11-19",
    )
    assert report["duplicates"] == 1
    assert report["invalid_bars"] == 1
    assert report["first_rth_time"].startswith("09:30")
    assert report["spec"]["point_ok"] is True
    assert report["coverage_ok"] is False
    assert report["missing_rth_bars"] > 0


def test_punto_distinto_de_0_01_no_pasa():
    report = validate_bars(
        _frame(periods=20),
        {"point": 0.1, "digits": 1},
        start="2026-11-19",
        end="2026-11-19",
    )
    assert report["spec"]["point_ok"] is False


def test_spread_medido_como_suelo(monkeypatch):
    rows = pd.DataFrame(
        {
            "symbol": ["US500.cash"],
            "hour_utc": [14],
            "median_bps": [1.0],
            "p75_bps": [1.2],
            "n_ticks": [100],
            "from_ts": ["2026-11-19T14:00:00+00:00"],
            "to_ts": ["2026-11-19T14:59:59+00:00"],
            "source": ["broker"],
        }
    )
    monkeypatch.setattr("tradinglab.ea_lab.data.load_spreads", lambda *a, **k: rows)
    measured = measured_spread(now=datetime(2026, 11, 19, 16, tzinfo=UTC))
    assert measured["median_bps"] == pytest.approx(1.0)
    assert measured["age_hours"] == pytest.approx(1.0, abs=0.01)

    frame = _frame(start="2026-11-19 09:30", periods=1)
    frame.loc[frame.index[0], "spread"] = 0.0
    floored, info = apply_spread_floor(frame, measured, spread_rows=rows)
    # 100 × 1 bp / 10 000 = 0,01 precio = 1 punto con point=0,01.
    assert floored["spread"].iloc[0] == pytest.approx(1.0)
    assert info["hours_covered"] == [14]
    assert info["bars_total"] == 1


def test_spread_medido_ausente_pide_el_comando(monkeypatch):
    monkeypatch.setattr(
        "tradinglab.ea_lab.data.load_spreads",
        lambda *a, **k: pd.DataFrame(),
    )
    with pytest.raises(DataError, match="lab ticks broker-spread US500.cash --days 7"):
        measured_spread()


def test_spread_caducado_no_se_usa(monkeypatch):
    rows = pd.DataFrame(
        {
            "symbol": ["US500.cash"],
            "hour_utc": [14],
            "median_bps": [1.0],
            "p75_bps": [1.2],
            "n_ticks": [100],
            "from_ts": ["2026-10-01T14:00:00+00:00"],
            "to_ts": ["2026-10-01T14:59:59+00:00"],
            "source": ["broker"],
        }
    )
    monkeypatch.setattr("tradinglab.ea_lab.data.load_spreads", lambda *a, **k: rows)
    with pytest.raises(DataError, match="medición"):
        measured_spread(now=datetime(2026, 11, 19, 16, tzinfo=UTC))
