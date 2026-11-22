"""Calidad por fuente y temporalidad: matriz de 7 TF y días sin datos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.discovery.config import load_engine_config
from tradinglab.discovery.resample import resample_session
from tradinglab.discovery.source_quality import (
    quality_config,
    quality_for_source,
    quality_matrix,
)

SEGMENTS = {
    "is": ("2024-01-08", "2024-01-09"),
    "oos1": ("2024-01-10", "2024-01-11"),
    "oos2": ("2024-01-12", None),
}


def _m1() -> pd.DataFrame:
    index = pd.date_range(
        "2024-01-08 00:00", "2024-01-12 23:59", freq="1min", tz="UTC"
    )
    values = np.arange(len(index), dtype=float) + 100.0
    return pd.DataFrame(
        {
            "open": values,
            "high": values + 0.5,
            "low": values - 0.5,
            "close": values + 0.2,
            "volume": 1.0,
        },
        index=index,
    )


def _write_m1(root: Path, frame: pd.DataFrame) -> None:
    path = root / "data" / "cache" / "dukascopy" / "EURUSD_M1.parquet"
    path.parent.mkdir(parents=True)
    frame.to_parquet(path)


def test_calidad_dukascopy_por_tf(tmp_path: Path) -> None:
    m1 = _m1()
    _write_m1(tmp_path, m1)
    data = quality_for_source(
        "EURUSD",
        "M5",
        source="dukascopy",
        root=tmp_path,
        segments=SEGMENTS,
    )
    assert data["status"] in {"ok", "warn"}
    assert data["rows"] == 5 * 288
    assert data["source_name"] == "dukascopy"
    assert data["source"]["derived_from"] == "M1"
    assert data["granularity"]["useful_start"]
    assert data["missing_weekdays"] == 0
    assert data["segments"]["is"]["rows"] > 0

    matrix = quality_matrix(
        "EURUSD",
        source="dukascopy",
        root=tmp_path,
        segments=SEGMENTS,
    )
    assert [row["timeframe"] for row in matrix] == [
        "M1",
        "M5",
        "M15",
        "M30",
        "H1",
        "H4",
        "D1",
    ]
    assert all(row["rows"] > 0 for row in matrix)
    assert matrix[-1]["rows"] == 6  # sesiones del 7 al 12 (domingo a viernes)


def test_calidad_dukascopy_sin_datos(tmp_path: Path) -> None:
    data = quality_for_source(
        "EURUSD",
        "M5",
        source="dukascopy",
        root=tmp_path,
    )
    assert data["status"] == "fail"
    assert any("Sin datos" in issue for issue in data["issues"])


def test_umbrales_por_timeframe() -> None:
    base = load_engine_config().data_quality
    assert quality_config(base, "EURUSD", "M5", "dukascopy").max_gap_hours == 4.0
    assert quality_config(base, "EURUSD", "D1", "dukascopy").max_gap_hours == 72.0
    assert quality_config(base, "EURUSD", "H4", "dukascopy").gap_factor == 1.5
    assert quality_config(base, "US100", "M5", "dukascopy").source_for("US100").calendar == "nyse"


def test_remuestreo_broker_tambien_carga(tmp_path: Path) -> None:
    m1 = _m1()
    m5 = resample_session(m1, "M5")
    path = tmp_path / "data" / "cache" / "discovery" / "EURUSD_M5.parquet"
    path.parent.mkdir(parents=True)
    m5.to_parquet(path)
    data = quality_for_source(
        "EURUSD",
        "M5",
        source="broker",
        root=tmp_path,
        segments=SEGMENTS,
    )
    assert data["source_name"] == "broker"
    assert data["rows"] == len(m5)
