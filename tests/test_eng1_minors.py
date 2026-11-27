"""ENG-1 · hallazgos menores sin efecto en resultados del motor (D-09, D-10)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.discovery import console, jobs


def test_d09_cuenta_informal_trials_y_no_oculta_el_error(tmp_path: Path, monkeypatch) -> None:
    lab = tmp_path / "lab.db"
    con = sqlite3.connect(lab)
    con.executescript(
        """
        CREATE TABLE lesson_tests (id INTEGER PRIMARY KEY);
        CREATE TABLE informal_trials (id INTEGER PRIMARY KEY, n INTEGER);
        INSERT INTO lesson_tests DEFAULT VALUES;
        INSERT INTO informal_trials (n) VALUES (200), (50);
        """
    )
    con.commit()
    con.close()
    counts = console.count_tests_readonly(lab)
    assert counts["informal_trials"] == 250
    assert counts["total"] == 251  # antes 1: faltaban las miradas informales

    def broken(db):
        raise sqlite3.DatabaseError("file is not a database")

    monkeypatch.setattr(console.campaigns, "discovery_tests", broken)
    counts = console.count_tests_readonly(lab, tmp_path / "discovery.db")
    assert counts["discovery"] is None and counts["total"] is None  # antes 0 y 251
    assert counts["discovery_error"].startswith("Sin datos")


def test_d10_slice_bars_no_incluye_la_vela_del_dia_siguiente() -> None:
    index = pd.date_range("2024-06-30 22:00", "2024-07-01 02:00", freq="5min", tz="UTC")
    bars = pd.DataFrame({"close": np.arange(len(index), dtype=float)}, index=index)
    sliced = jobs._slice_bars(bars, None, "2024-06-30")
    assert sliced.index.max() < pd.Timestamp("2024-07-01", tz="UTC")
    assert sliced.index.max() == pd.Timestamp("2024-06-30 23:55", tz="UTC")


def test_c13_vela_invalida_se_nombra_como_ohlc_invalido(tmp_path, monkeypatch) -> None:
    from datetime import date

    import pytest

    from tradinglab.discovery import fetch_dukascopy as duka

    def fake_fetch(client, instrument, day, side, point, **kwargs):
        if day == date(2024, 1, 10) and side == "BID":
            raise duka.DukascopyDataError("1 velas OHLC inválidas en 2024-01-10 (BID)")
        index = pd.date_range(pd.Timestamp(day, tz="UTC"), periods=3, freq="1min")
        frame = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0}, index=index
        )
        if side == "ASK":
            frame.columns = list(duka.ASK_COLUMNS)
        return frame

    monkeypatch.setattr(duka, "_fetch_day", fake_fetch)
    with pytest.raises(duka.DukascopyDataError, match="OHLC inválido en 2024-01") as info:
        duka.download(
            "EURUSD", start="2024-01-01", end="2024-01-31", workers=2,
            rate_per_s=0, root=tmp_path, backoff_s=0,
        )
    assert "sin respuesta" not in str(info.value)  # antes: «1 días sin respuesta»
    assert issubclass(duka.DukascopyDataError, duka.DukascopyError)  # quien capture lo antiguo sigue


def test_c14_load_source_cuenta_los_duplicados_de_la_cache(tmp_path) -> None:
    from tradinglab.discovery import data_sources
    from tradinglab.discovery import fetch_dukascopy as duka

    index = pd.DatetimeIndex(
        ["2024-01-02 00:00", "2024-01-02 00:01", "2024-01-02 00:01", "2024-01-02 00:02"], tz="UTC"
    )
    frame = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0}, index=index
    )
    frame.index.name = "time"
    path = duka.cache_path("EURUSD", root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    loaded = data_sources.load_source("EURUSD", "M1", source="dukascopy", root=tmp_path)
    assert loaded.rows == 3  # el cargador sigue quitándolo (keep="last")
    assert loaded.duplicates == 1  # antes no se sabía
    assert loaded.as_dict()["duplicates"] == 1


def test_c06_un_hueco_largo_cuenta_sus_velas() -> None:
    from tradinglab.discovery import data_quality

    full = pd.date_range("2023-01-01", "2023-12-31 23:00", freq="h", tz="UTC")
    hole = (full >= pd.Timestamp("2023-06-05", tz="UTC")) & (full < pd.Timestamp("2023-06-15", tz="UTC"))

    def report(index):
        frame = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0}, index=index
        )
        return data_quality.check_dataset(frame, "EURUSD", "H1").gap_thresholds

    base, holed = report(full), report(full[~hole])
    extra_gap_pct = holed["gap_pct"] - base["gap_pct"]
    extra_bars = holed["gap_bars_missing"] - base["gap_bars_missing"]
    assert extra_gap_pct < 0.001  # antes solo esto: el hueco de 10 días vale 1 evento
    assert extra_bars >= 8 * 24  # ahora: sus ~240 velas
    assert holed["gap_bars_pct"] - base["gap_bars_pct"] > 0.02
