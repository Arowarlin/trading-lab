"""T1 · Manifiesto de datos y cargador."""

from __future__ import annotations

import json

import pytest

from tradinglab.tl3 import data


@pytest.fixture(scope="module")
def manifest():
    # Leer, no reconstruir: build_manifest() reescribe data/tl3/manifest.json.
    return json.loads(data.MANIFEST.read_text(encoding="utf-8"))


def test_manifest_clasifica_cfd_y_futuros(manifest):
    ea = next(
        item for item in manifest["files"] if "US100_CASH_M5_NY" in item["path"]
    )
    future = next(
        item for item in manifest["files"] if "databento/US100_M1" in item["path"]
    )

    assert ea["instrument_class"] == "cfd"
    assert ea["instrument_real"] == "US100.cash"
    assert future["instrument_class"] == "future"
    assert future["instrument_real"] == "NQ.c.0"


@pytest.mark.requires_local("data/cache/ea/US100_CASH_M5_NY.parquet")
def test_load_m5_2018_falla_por_granularidad(manifest):
    with pytest.raises(data.TL3DataError, match="granularidad"):
        data.load(
            "data/cache/ea/US100_CASH_M5_NY.parquet",
            "M5",
            "2018-01-01",
            "2018-12-31",
            "cfd",
        )


def test_load_databento_como_cfd_falla(manifest):
    with pytest.raises(data.TL3DataError, match="future"):
        data.load(
            "data/cache/databento/US100_M1.parquet",
            "M1",
            "2018-01-01",
            "2018-12-31",
            "cfd",
        )


def test_dukascopy_sin_ask(manifest):
    duka = next(
        item for item in manifest["files"] if "dukascopy/US100_M1" in item["path"]
    )
    assert duka["has_ask"] == 0.0


@pytest.mark.requires_local("data/cache/ea/US100_CASH_M5_NY.parquet")
def test_load_m5_2022_ok(manifest):
    frame = data.load(
        "data/cache/ea/US100_CASH_M5_NY.parquet",
        "M5",
        "2022-01-03",
        "2022-12-30",
        "cfd",
    )
    assert not frame.empty
    assert data.dominant_step(frame.index) == 300.0
