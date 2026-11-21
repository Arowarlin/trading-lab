"""Campañas: la fuente entra en config_hash y los segmentos salen del snapshot."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import campaigns, jobs
from tradinglab.discovery.data_sources import DataSourceError, load_source

SEGMENTS = {
    "is": ["2024-01-08", "2024-01-20"],
    "oos1": ["2024-01-21", "2024-02-05"],
    "oos2": ["2024-02-06", None],
}


def _frame(bars: int = 20_000, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-08 00:00", periods=bars, freq="5min", tz="UTC")
    close = 20_000.0 + np.cumsum(rng.normal(0.0, 4.0, bars))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(1.0, 5.0, bars)
    low = np.minimum(open_, close) - rng.uniform(1.0, 5.0, bars)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )


def test_source_entra_en_config_hash(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    broker = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="broker",
        data_source="broker",
        db_path=db,
    )
    dukascopy = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="dukascopy",
        data_source="dukascopy",
        db_path=db,
    )
    assert broker["config"]["data_source"] == "broker"
    assert dukascopy["config"]["data_source"] == "dukascopy"
    assert broker["config_hash"] != dukascopy["config_hash"]
    assert broker["dataset_hash"] == dukascopy["dataset_hash"]


def test_source_invalida_rechazada(tmp_path: Path) -> None:
    with pytest.raises(campaigns.CampaignError, match="fuente no soportada"):
        campaigns.register(
            "US100",
            "M5",
            "ny_open_vol_filter",
            "small",
            segments=SEGMENTS,
            frame=_frame(),
            data_source="mixta",
            db_path=tmp_path / "discovery.db",
        )


def test_segmentos_leen_el_snapshot_de_una_sola_fuente(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    campaign = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="c1",
        data_source="dukascopy",
        db_path=db,
    )
    campaigns.approve("c1", db_path=db, verify=False)
    is_frame = campaigns.load_segment("c1", "is", db_path=db)
    assert not is_frame.empty
    assert is_frame.index.min() >= pd.Timestamp(campaign["is_start"], tz="UTC")
    assert campaigns.campaign_data_source(campaign) == "dukascopy"


def test_queue_setup_hereda_la_fuente(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    campaign = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=_frame(),
        campaign_id="c1",
        data_source="dukascopy",
        db_path=db,
    )
    setup = jobs.QueueSetup.from_campaign(campaign)
    assert setup.data_source == "dukascopy"


def test_load_source_dukascopy_remuestrea_en_memoria(tmp_path: Path) -> None:
    index = pd.date_range("2024-01-08 10:00", periods=60, freq="1min", tz="UTC")
    values = np.arange(len(index), dtype=float) + 100.0
    m1 = pd.DataFrame(
        {
            "open": values,
            "high": values + 0.5,
            "low": values - 0.5,
            "close": values + 0.2,
            "volume": 1.0,
        },
        index=index,
    )
    path = tmp_path / "data" / "cache" / "dukascopy" / "EURUSD_M1.parquet"
    path.parent.mkdir(parents=True)
    m1.to_parquet(path)
    loaded = load_source("EURUSD", "M5", source="dukascopy", root=tmp_path)
    assert loaded.source == "dukascopy"
    assert loaded.derived_from == "M1"
    assert loaded.rows == 12
    assert len(loaded.frame) == 12
    assert loaded.frame.index.tz is not None
    assert not (tmp_path / "data" / "cache" / "discovery").exists()


def test_load_source_dukascopy_sin_datos(tmp_path: Path) -> None:
    with pytest.raises(DataSourceError, match="Sin datos"):
        load_source("EURUSD", "M5", source="dukascopy", root=tmp_path)
