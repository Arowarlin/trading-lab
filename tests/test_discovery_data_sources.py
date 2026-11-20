from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from tradinglab.discovery.config import SourceConfig, load_engine_config
from tradinglab.discovery.data_sources import DataSourceError, load_source


def _ny_frame() -> pd.DataFrame:
    stamps = pd.DatetimeIndex(
        [
            "2024-03-10 01:55",
            "2024-03-10 02:30",
            "2024-03-10 03:00",
            "2024-11-03 00:55",
            "2024-11-03 01:00",
            "2024-11-03 01:30",
            "2024-11-03 01:55",
            "2024-11-03 02:00",
        ]
    )
    close = pd.Series(range(len(stamps)), dtype=float) + 100.0
    return pd.DataFrame(
        {
            "open": close.values,
            "high": close.values + 0.5,
            "low": close.values - 0.5,
            "close": close.values,
        },
        index=stamps,
    )


def test_carga_ny_a_utc_sin_escribir(tmp_path: Path) -> None:
    path = tmp_path / "us100.parquet"
    _ny_frame().to_parquet(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    config = load_engine_config().data_quality.model_copy(
        update={
            "sources": {
                "default": SourceConfig(
                    path=str(path), timezone="America/New_York", calendar=None
                )
            }
        }
    )
    loaded = load_source("TEST", "M5", config=config, root=tmp_path)
    assert loaded.frame.index.tz is not None
    assert str(loaded.frame.index.tz) == "UTC"
    assert loaded.rows_raw == 8
    assert loaded.dropped == 1
    assert loaded.adjusted == 3
    assert loaded.rows == 7
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_fuente_por_defecto_mt5() -> None:
    config = load_engine_config().data_quality
    source = config.source_for("EURUSD")
    assert source.path == "data/cache/mt5/{symbol}_{tf}.parquet"
    assert source.timezone == "UTC"
    us100 = config.source_for("US100.cash")
    assert us100.path == "data/cache/ea/US100_CASH_M5_NY.parquet"
    assert us100.timezone == "America/New_York"
    assert us100.calendar == "nyse"


def test_fuente_desconocida_sin_archivo(tmp_path: Path) -> None:
    config = load_engine_config().data_quality.model_copy(
        update={
            "sources": {
                "default": SourceConfig(
                    path=str(tmp_path / "no_existe.parquet"),
                    timezone="UTC",
                    calendar=None,
                )
            }
        }
    )
    with pytest.raises(DataSourceError, match="Sin datos"):
        load_source("TEST", "M5", config=config, root=tmp_path)
