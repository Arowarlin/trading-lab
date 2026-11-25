from __future__ import annotations

import pandas as pd

from tradinglab.ea_lab.session_data import (
    build_session_data_report,
    load_m5_us100_own,
    session_atr,
    session_spread,
)
from tradinglab.ea_lab.sessions import ASIA_ANCHORS, LONDON_ANCHORS, NYSE_ANCHORS


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


def _session_frame() -> pd.DataFrame:
    rows = []
    index = []
    price = 20000.0
    for day in range(5):
        base = pd.Timestamp("2025-11-16") + pd.Timedelta(days=day)
        # 03:05 NY = 08:05 Londres; 09:35 NY = NY; 19:05 NY = 09:05 Tokio.
        for hour, minute, spread in ((3, 5, 100.0), (9, 35, 50.0), (19, 5, 200.0)):
            stamp = base + pd.Timedelta(hours=hour, minutes=minute)
            rows.append(
                {
                    "open": price,
                    "high": price + 2,
                    "low": price - 2,
                    "close": price + 1,
                    "tickvol": 1000.0,
                    "spread": spread,
                }
            )
            index.append(stamp)
            price += 1
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index))


def _spread_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["US100.CASH"] * 24,
            "hour_utc": list(range(24)),
            "median_bps": [0.0] * 24,
            "p75_bps": [0.0] * 24,
            "n_ticks": [10] * 24,
            "from_ts": ["2026-11-19T00:00:00+00:00"] * 24,
            "to_ts": ["2026-11-19T23:59:59+00:00"] * 24,
            "source": ["broker"] * 24,
        }
    )


def test_cache_propia_de_us100(tmp_path):
    frame = _session_frame()
    cache = tmp_path / "us100_m5.parquet"
    broker = _FakeBroker(frame)
    bundle = load_m5_us100_own(refresh=True, cache_path=cache, broker=broker)
    assert bundle.source == "mt5-attach-only"
    assert cache.exists()
    assert bundle.spec["point"] == 0.01
    assert broker.calls == ["symbol_spec:US100.cash", "rates:US100.cash:M5:400000"]

    cached = load_m5_us100_own(cache_path=cache)
    assert cached.source == "mt5-attach-only"
    assert list(cached.frame.columns) == ["open", "high", "low", "close", "tickvol", "spread"]


def test_spread_por_ventana_y_comparacion_con_ny():
    frame = _session_frame()
    rows = _spread_rows()
    measured = {"symbol": "US100.CASH", "median_bps": 0.0}
    ny = session_spread(frame, measured, NYSE_ANCHORS, "Nueva York", spread_rows=rows)
    london = session_spread(frame, measured, LONDON_ANCHORS, "Londres", spread_rows=rows)
    asia = session_spread(frame, measured, ASIA_ANCHORS, "Asia", spread_rows=rows)

    assert ny["median_points"] == 50.0
    assert london["median_points"] == 100.0
    assert asia["median_points"] == 200.0
    assert london["bars"] == 5
    assert asia["bars"] == 5
    assert ny["bars"] == 5
    assert london["window"] == "08:05–10:00"
    assert asia["window"] == "09:05–11:00"
    assert ny["window"] == "09:35–11:30"
    assert london["hourly"][0]["hour_local"] == 8
    assert asia["hourly"][0]["hour_local"] == 9


def test_atr_en_ventana_de_londres():
    index = pd.date_range("2025-11-17 03:00", periods=120, freq="5min")
    frame = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "tickvol": 1000.0,
            "spread": 100.0,
        },
        index=index,
    )
    result = session_atr(frame, LONDON_ANCHORS)
    assert result["atr_len"] == 14
    assert result["bars"] > 0
    assert result["median_atr"] == 2.0


def test_informe_de_datos_de_sesion(tmp_path):
    frame = _session_frame()
    rows = _spread_rows()
    measured = {"symbol": "US100.CASH", "median_bps": 0.0}
    ny = session_spread(frame, measured, NYSE_ANCHORS, "Nueva York", spread_rows=rows)
    london = session_spread(frame, measured, LONDON_ANCHORS, "Londres", spread_rows=rows)
    bundle = load_m5_us100_own(
        refresh=True, cache_path=tmp_path / "us100_m5.parquet", broker=_FakeBroker(frame)
    )
    payload = build_session_data_report(
        bundle,
        measured,
        candidate="us100-london",
        anchors=LONDON_ANCHORS,
        session_stats=london,
        ny_stats=ny,
        atr_stats={"median_atr": 2.0, "bars": 10},
        ny_atr={"median_atr": 4.0, "bars": 10},
    )
    assert payload["candidate"] == "us100-london"
    assert payload["spread"]["comparison"]["ratio_vs_ny"] == 2.0
    assert payload["viability"]["session"]["spread_over_atr"] == 0.5
    assert payload["viability"]["ny"]["spread_over_atr"] == 0.125
    assert payload["viability"]["ratio_vs_ny"] == 4.0
    assert payload["data_ok"] is False  # los datos sintéticos no cubren la ventana

