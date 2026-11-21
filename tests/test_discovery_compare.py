"""Comparación Dukascopy vs bróker: correlación, nivel, lag y veredicto."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery.compare import compare_all, compare_symbol
from tradinglab.discovery.resample import resample_session


def _m1() -> pd.DataFrame:
    index = pd.date_range(
        "2024-01-08 00:00", "2024-01-09 23:59", freq="1min", tz="UTC"
    )
    rng = np.random.default_rng(4)
    close = 1.1000 + np.cumsum(rng.normal(0.0, 0.00002, len(index)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.00003
    low = np.minimum(open_, close) - 0.00003
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1.0,
        },
        index=index,
    )


def _write(root: Path, m1: pd.DataFrame, *, shift: int = 0) -> pd.DataFrame:
    duka = root / "data" / "cache" / "dukascopy" / "EURUSD_M1.parquet"
    duka.parent.mkdir(parents=True)
    m1.to_parquet(duka)
    m5 = resample_session(m1, "M5")
    broker = m5.copy()
    broker[["open", "high", "low", "close"]] = (
        broker[["open", "high", "low", "close"]] + 0.00008
    )
    if shift:
        broker.index = broker.index + pd.Timedelta(minutes=5 * shift)
    path = root / "data" / "cache" / "discovery" / "EURUSD_M5.parquet"
    path.parent.mkdir(parents=True)
    broker.to_parquet(path)
    return broker


def test_comparacion_apta(tmp_path: Path) -> None:
    _write(tmp_path, _m1())
    row = compare_symbol(
        "EURUSD",
        start="2024-01-08",
        end="2024-01-09",
        root=tmp_path,
    )
    assert row["rows"] > 500
    assert row["correlation"] >= 0.95
    assert row["lag"] == 0
    assert row["match_pct"] == pytest.approx(100.0)
    assert row["verdict"] == "apta"
    assert row["mean_diff"] == pytest.approx(0.00008, abs=1e-9)


def test_desfase_horario_no_apta(tmp_path: Path) -> None:
    _write(tmp_path, _m1(), shift=1)
    row = compare_symbol(
        "EURUSD",
        start="2024-01-08",
        end="2024-01-09",
        root=tmp_path,
    )
    assert row["lag"] != 0
    assert row["verdict"] == "no apta"
    assert "lag" in row["reason"]


def test_sin_broker_no_apta(tmp_path: Path) -> None:
    duka = tmp_path / "data" / "cache" / "dukascopy" / "EURUSD_M1.parquet"
    duka.parent.mkdir(parents=True)
    _m1().to_parquet(duka)
    row = compare_all(["EURUSD"], start="2024-01-08", root=tmp_path)[0]
    assert row["verdict"] == "no apta"
    assert "Sin datos" in row["reason"]
