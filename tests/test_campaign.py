from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from tradinglab.campaign import (
    CAMPAIGN_BARS,
    CampaignError,
    campaign_hash,
    common_cutoff,
    compute_n_total,
    holdout_hash,
    holdout_rows,
    init_campaigns,
    plan_cells,
    register_campaign,
    required_history,
    split_frame,
)
from tradinglab.db import connect, init_db
from tradinglab.learning import count_tests


def _frame(rows: int, start: str = "2015-01-01", freq: str = "D") -> pd.DataFrame:
    index = pd.date_range(start, periods=rows, freq=freq, tz="UTC")
    close = pd.Series(range(100, 100 + rows), index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "tick_volume": 1_000,
            "spread": 1,
        },
        index=index,
    )


def _universe(*, eligible_d1: list[str], symbols: list[dict]) -> dict:
    return {
        "symbols": symbols,
        "eligible_by_timeframe": {"H1": [], "H4": [], "D1": eligible_d1},
    }


# ------------------------------------------------------------------- costes


def test_commission_verified_convertible_and_not() -> None:
    from tradinglab.campaign import _commission_side_bps

    frame = _frame(50)
    eurusd = _commission_side_bps("EURUSD", frame)
    assert eurusd["verified"] is True
    assert eurusd["convertible"] is True
    assert eurusd["commission_side_bps"] is not None
    assert eurusd["commission_side_bps"] > 0

    # Cruce sin USD: la tabla lo verifica, pero pasar a bps exigiría un tipo
    # de cambio que no se inventa.
    audcad = _commission_side_bps("AUDCAD", frame)
    assert audcad["verified"] is True
    assert audcad["convertible"] is False
    assert audcad["commission_side_bps"] is None

    # Cripto fuera de la tabla: Sin datos, no se supone comisión.
    crypto = _commission_side_bps("BTCUSD", frame)
    assert crypto["verified"] is False
    assert crypto["convertible"] is False
    assert crypto["commission_side_bps"] is None


def test_n_total_counts_families_and_variants() -> None:
    symbols = [
        {"symbol": "EURUSD", "asset_class": "forex"},
        {"symbol": "XAUUSD", "asset_class": "metals"},
        {"symbol": "US100.CASH", "asset_class": "indices"},
    ]
    universe = _universe(
        eligible_d1=["EURUSD", "XAUUSD", "US100.CASH"], symbols=symbols
    )
    totals = compute_n_total(universe)
    # forex y metales: 3 familias x 4 variantes = 12; índices: + calendar = 16.
    assert totals["per_timeframe"] == {"H1": 0, "H4": 0, "D1": 40}
    assert totals["n_total"] == 40
    assert totals["variants_per_family"]["calendar"] == 4


# ---------------------------------------------------------- corte común


def test_common_cutoff_uses_shortest_series() -> None:
    long = _frame(5_000, start="2010-01-01")
    short = _frame(200, start="2020-01-01")
    frames = {("AAA", "D1"): long, ("BBB", "D1"): short}

    cutoff = common_cutoff(frames, discovery_pct=0.70)
    assert cutoff is not None
    # 70 % de la serie más corta (200 barras -> posición 140).
    assert cutoff == short.index[140]

    discovery, sealed = split_frame(long, cutoff)
    assert len(discovery) + len(sealed) == len(long)
    assert discovery.index.max() < cutoff
    assert sealed.index.min() >= cutoff
    # La serie corta conserva su 30 % final.
    _, short_sealed = split_frame(short, cutoff)
    assert len(short_sealed) == len(short) - 140


def test_holdout_hash_is_deterministic_and_cutoff_sensitive() -> None:
    frames = {("AAA", "D1"): _frame(300)}
    cutoff = common_cutoff(frames)
    rows = holdout_rows(frames, cutoff)
    first = holdout_hash(rows, cutoff)
    assert first == holdout_hash(rows, cutoff)
    assert first != holdout_hash(rows, frames[("AAA", "D1")].index[-1])
    # Cambiar el corte cambia el trozo sellado y la huella.
    later = pd.Timestamp(frames[("AAA", "D1")].index[250])
    assert holdout_hash(holdout_rows(frames, later), later) != first


# ------------------------------------------------------- celdas y registro


def test_plan_cells_excludes_insufficient_history() -> None:
    symbols = [
        {"symbol": "AAA", "asset_class": "forex"},
        {"symbol": "BBB", "asset_class": "forex"},
        {"symbol": "SHORT", "asset_class": "forex"},
    ]
    universe = _universe(eligible_d1=["AAA", "BBB", "SHORT"], symbols=symbols)
    frames = {
        # Serie más corta: fija el corte en 2015-03. Tiene 70 barras de
        # descubrimiento, así que algunas variantes largas no caben.
        ("SHORT", "D1"): _frame(100, start="2015-01-01"),
        # Serie larga que termina antes del corte: descubrimiento completo.
        ("AAA", "D1"): _frame(600, start="2013-01-01"),
        # Serie con más barras que la corta pero que empieza después del
        # corte: no le queda descubrimiento.
        ("BBB", "D1"): _frame(120, start="2026-01-01"),
    }
    cutoff = common_cutoff(frames)
    plan = plan_cells(universe, frames, cutoff)

    assert plan["n_total"] == len(plan["runnable"])
    assert plan["n_total"] > 0
    assert "AAA" in {cell["symbol"] for cell in plan["runnable"]}
    excluded_bbb = [cell for cell in plan["excluded"] if cell["symbol"] == "BBB"]
    assert len(excluded_bbb) == 12
    assert all("historia insuficiente" in cell["reason"] for cell in excluded_bbb)
    assert plan["cutoff_utc"] is not None


def test_required_history_scales_with_timeframe() -> None:
    daily = _frame(50, freq="D")
    hourly = _frame(50, freq="h")
    params = {"lookback_days": 60.0, "vol_days": 20.0}
    d1 = required_history(daily, "D1", "tsmom", params)
    h1 = required_history(hourly, "H1", "tsmom", params)
    # El mismo lookback en días exige muchas más barras en H1 que en D1.
    assert h1 > d1 > 0


def test_campaign_hash_includes_cutoff() -> None:
    base = {
        "id": "TEST-A",
        "universe": ["EURUSD"],
        "timeframes": ["H1", "H4", "D1"],
        "families": ["tsmom"],
        "discovery_pct": 0.70,
        "n_total": 4,
        "cutoff_utc": "2020-02-28 00:00:00+00:00",
    }
    moved = {**base, "cutoff_utc": "2021-01-01 00:00:00+00:00"}
    assert campaign_hash(base) != campaign_hash(moved)


def _config(n_total: int, *, campaign: str = "TEST-A") -> dict:
    return {
        "id": campaign,
        "universe": ["EURUSD"],
        "timeframes": ["H1", "H4", "D1"],
        "families": ["tsmom"],
        "discovery_pct": 0.70,
        "cutoff_utc": "2020-02-28 00:00:00+00:00",
        "n_total": n_total,
        "holdout_hash": "abc123",
    }


def test_second_registration_is_refused(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_campaigns(db)
    record = register_campaign(db, _config(5))
    assert record["n_total"] == 5
    assert record["holdout_hash"] == "abc123"
    with pytest.raises(CampaignError):
        register_campaign(db, _config(5))


# --------------------------------------------------- migración del contador


def _old_db(path: Path, rows: int = 3) -> None:
    """Base anterior a `counted`: strategy_trials sin la columna."""
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE strategy_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            family TEXT NOT NULL,
            hypothesis TEXT NOT NULL,
            symbol TEXT NOT NULL,
            params TEXT NOT NULL,
            window_start TEXT,
            window_end TEXT,
            result TEXT,
            outcome TEXT NOT NULL DEFAULT 'failed',
            reason TEXT,
            source TEXT NOT NULL DEFAULT 'humano',
            run_id TEXT,
            lesson_id INTEGER,
            fingerprint TEXT
        )
        """
    )
    for index in range(rows):
        con.execute(
            "INSERT INTO strategy_trials"
            "(ts, family, hypothesis, symbol, params) VALUES(?,?,?,?,?)",
            ("2026-01-01T00:00:00+00:00", "tsmom", "h", f"S{index}", "{}"),
        )
    con.commit()
    con.close()


def test_migration_sets_counted_and_keeps_count(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    _old_db(db, rows=3)

    raw = sqlite3.connect(db)
    baseline = raw.execute("SELECT COUNT(*) FROM strategy_trials").fetchone()[0]
    raw.close()
    assert baseline == 3

    init_db(db)
    with connect(db) as con:
        columns = [
            row["name"] for row in con.execute("PRAGMA table_info(strategy_trials)")
        ]
        assert "counted" in columns
        counted = con.execute(
            "SELECT counted, COUNT(*) AS n FROM strategy_trials GROUP BY counted"
        ).fetchall()
    assert [(row["counted"], row["n"]) for row in counted] == [(1, 3)]

    before = count_tests(db)
    assert before == baseline

    register_campaign(db, _config(7))
    assert count_tests(db) == before + 7


def test_migration_does_not_overwrite_campaign_cells(tmp_path: Path) -> None:
    """Las celdas con counted=0 no se cuentan dos veces al reiniciar."""
    db = tmp_path / "lab.db"
    init_campaigns(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO strategy_trials"
            "(ts, family, hypothesis, symbol, params, counted) VALUES(?,?,?,?,?,0)",
            ("2026-01-01T00:00:00+00:00", "tsmom", "h", "EURUSD", "{}"),
        )
        con.commit()

    init_db(db)
    with connect(db) as con:
        row = con.execute(
            "SELECT counted FROM strategy_trials WHERE symbol='EURUSD'"
        ).fetchone()
    assert row["counted"] == 0


def test_campaign_sizes_are_positive() -> None:
    assert CAMPAIGN_BARS["H1"] > 0
    assert CAMPAIGN_BARS["H4"] > 0
