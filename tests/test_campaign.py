from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from tradinglab.campaign import (
    CAMPAIGN_BARS,
    CampaignError,
    apply_plateau,
    campaign_config,
    campaign_hash,
    common_cutoff,
    compute_n_total,
    correlation_clusters,
    finish_campaign,
    holdout_hash,
    holdout_rows,
    holdout_years,
    init_campaigns,
    load_campaign_frames,
    load_campaign_yaml,
    plan_cells,
    prepare_campaign,
    register_campaign,
    require_live_data,
    required_history,
    run_discovery,
    split_frame,
    trim_for_holdout,
    universe_symbols,
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


def _frame_ending(rows: int, end: str = "2026-01-01") -> pd.DataFrame:
    """Serie diaria que termina en la misma fecha que las demás."""
    index = pd.date_range(end=end, periods=rows, freq="D", tz="UTC")
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


def test_common_cutoff_holdout_at_least_two_years() -> None:
    """El 70 % de la serie más corta deja dos años o más de holdout común."""
    long = _frame_ending(3_653)  # 10 años
    short = _frame_ending(2_922)  # 8 años
    frames = {("AAA", "D1"): long, ("BBB", "D1"): short}

    cutoff = common_cutoff(frames, discovery_pct=0.70)
    years = holdout_years(frames, cutoff)
    assert years is not None and years >= 2.0

    trimmed = trim_for_holdout(frames)
    assert trimmed is not None
    assert trimmed["excluded"] == []
    assert trimmed["holdout_years"] >= 2.0


def test_trim_for_holdout_drops_short_series_iteratively() -> None:
    """Se sacan uno a uno los activos que limitan el holdout, no se acorta."""
    frames = {
        ("SHORT1", "D1"): _frame_ending(1_096),  # 3 años
        ("SHORT2", "D1"): _frame_ending(1_827),  # 5 años
        ("LONG", "D1"): _frame_ending(3_653),  # 10 años
        ("LONG2", "D1"): _frame_ending(4_383),  # 12 años
    }

    trimmed = trim_for_holdout(frames)
    assert trimmed is not None
    assert [item["symbol"] for item in trimmed["excluded"]] == ["SHORT1", "SHORT2"]
    assert all("holdout común" in item["reason"] for item in trimmed["excluded"])
    assert trimmed["holdout_years"] >= 2.0
    assert {symbol for symbol, _ in trimmed["frames"]} == {"LONG", "LONG2"}
    # El corte se recalculó con las series que quedan: al quitar las cortas,
    # el 70 % cae antes y el holdout común se alarga.
    assert trimmed["cutoff"] < common_cutoff(
        {("SHORT1", "D1"): frames[("SHORT1", "D1")]}
    )


def test_trim_for_holdout_stops_with_sin_datos() -> None:
    frames = {("ONLY", "D1"): _frame_ending(1_096)}
    assert trim_for_holdout(frames) is None


def test_correlation_clusters_only_use_pre_cutoff_data() -> None:
    """La meseta entre activos no puede mirar el holdout."""
    index = pd.date_range("2020-01-01", periods=400, freq="D", tz="UTC")
    pattern = np.sin(np.arange(400) / 3.0) * 0.01
    returns_a = pd.Series(pattern, index=index)
    returns_b = pd.Series(np.where(np.arange(400) < 280, pattern, -pattern), index=index)
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    for symbol, returns in (("AAA", returns_a), ("BBB", returns_b)):
        close = 100.0 * (1.0 + returns).cumprod()
        frames[(symbol, "D1")] = pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0,
                "spread": 1.0,
            },
            index=index,
        )

    cutoff = index[280]
    clusters = correlation_clusters(frames, cutoff, threshold=0.6)
    assert clusters["AAA|D1"]["BBB"] > 0.9
    assert clusters["BBB|D1"]["AAA"] > 0.9

    # Con toda la serie la correlación cae por debajo del umbral: si el corte
    # no se respetara, el clúster desaparecería.
    full = frames[("AAA", "D1")]["close"].pct_change().corr(
        frames[("BBB", "D1")]["close"].pct_change()
    )
    assert full < 0.6


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


# ------------------------------------------------- fetch de todos los candidatos


class _RatesBroker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def symbol_spec(self, name: str) -> dict:
        return {"tick_size": 0.01}

    def rates(self, name: str, timeframe: str, count: int) -> pd.DataFrame:
        self.calls.append((name, timeframe, int(count)))
        freq = "h" if timeframe == "H1" else "4h"
        frame = _frame(400, start="2024-01-01", freq=freq)
        return frame.rename(columns={"tick_volume": "volume"})


def test_universe_symbols_includes_all_measured_candidates() -> None:
    universe = {
        "symbols": [
            {"symbol": "AAA", "asset_class": "forex"},
            {"symbol": "BBB", "asset_class": "metals"},
            {"symbol": "CCC", "asset_class": "indices"},
            {"symbol": "OIL", "asset_class": "energy"},
        ]
    }
    # La energía queda fuera por diseño, como en el resto del universo.
    assert universe_symbols(universe) == ["AAA", "BBB", "CCC"]


def test_load_campaign_frames_downloads_h1_h4_for_all_candidates(
    tmp_path: Path,
) -> None:
    universe = {
        "symbols": [
            {"symbol": "AAA", "asset_class": "forex"},
            {"symbol": "BBB", "asset_class": "metals"},
            {"symbol": "CCC", "asset_class": "indices"},
        ]
    }
    symbols = universe_symbols(universe)
    broker = _RatesBroker()
    frames, _ = load_campaign_frames(
        broker,
        symbols,
        names={"AAA": "aaa.cash"},
        cache_dir=tmp_path,
        save=False,
    )

    assert ("aaa.cash", "H1", CAMPAIGN_BARS["H1"]) in broker.calls
    assert ("aaa.cash", "H4", CAMPAIGN_BARS["H4"]) in broker.calls
    assert ("BBB", "H1", CAMPAIGN_BARS["H1"]) in broker.calls
    assert ("CCC", "H4", CAMPAIGN_BARS["H4"]) in broker.calls
    assert {symbol for symbol, _ in frames} == {"AAA", "BBB", "CCC"}
    assert ("AAA", "D1") in frames


class _TickBroker:
    def __init__(self, age_minutes: float, *, offset_known: bool = True) -> None:
        self.age = age_minutes
        self.offset_known = offset_known

    def health(self) -> dict:
        return {
            "offset_known": self.offset_known,
            "server_utc_offset_hours": 2.0,
            "offset_source": "detectado" if self.offset_known else "unknown",
        }

    def tick(self, name: str) -> dict:
        return {"time": datetime.now(timezone.utc) - timedelta(minutes=self.age)}


def test_require_live_data_needs_fresh_tick_and_known_offset() -> None:
    access = require_live_data(_TickBroker(1.0))
    assert access["symbol"] == "EURUSD"
    assert access["age_minutes"] < 15.0

    with pytest.raises(CampaignError, match="mercado cerrado"):
        require_live_data(_TickBroker(120.0))
    with pytest.raises(CampaignError, match="offset"):
        require_live_data(_TickBroker(1.0, offset_known=False))


# ------------------------------------------- plan final, N_total y yaml


def test_prepare_campaign_n_total_and_yaml_match(tmp_path: Path) -> None:
    names = ("AAA", "BBB", "CCC")
    universe = {
        "campaign": "TEST-A",
        "symbols": [
            {"symbol": name, "asset_class": "forex", "mt5_name": name}
            for name in names
        ],
        "eligible_by_timeframe": {"H1": [], "H4": [], "D1": list(names)},
        "counts": {},
    }
    frames = {
        (name, "D1"): _frame(3_653, start="2016-01-01") for name in names
    }

    prepared = prepare_campaign(universe, frames, reassess=False)
    plan = prepared["plan"]
    assert prepared["holdout_years"] >= 2.0
    assert plan["excluded"] == []
    assert plan["n_total"] == 36

    config = campaign_config(prepared, "TEST-A")
    assert config["n_total"] == plan["n_total"] == 36
    assert config["n_total_detail"] == {"H1": 0, "H4": 0, "D1": 36}
    assert config["n_total_theoretical"] == compute_n_total(prepared)["n_total"]
    assert config["cutoff_utc"] == plan["cutoff_utc"]
    assert config["holdout_hash"] == plan["holdout_hash"]
    assert config["config_hash"] == campaign_hash(config)

    path = tmp_path / "TEST-A.yaml"
    path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    stored = load_campaign_yaml(path)
    assert stored["n_total"] == config["n_total"]
    assert stored["n_total_detail"] == config["n_total_detail"]
    assert stored["cutoff_utc"] == config["cutoff_utc"]
    assert stored["holdout_hash"] == config["holdout_hash"]
    assert campaign_hash(stored) == config["config_hash"]


def test_run_discovery_only_passes_pre_cutoff_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "lab.db"
    init_campaigns(db)
    config = _config(4)
    register_campaign(db, config)
    frames = {("EURUSD", "D1"): _frame(800, start="2018-01-01")}
    cutoff = pd.Timestamp(config["cutoff_utc"])
    seen: list[pd.Timestamp] = []

    def fake_backtest(symbol, timeframe, frame, family, params, **kwargs):
        seen.append(pd.Timestamp(frame.index.max()))
        index = frame.index
        returns = pd.Series(0.0, index=index)
        if len(index):
            returns.iloc[-1] = 0.01
        return {
            "metrics": {
                "sharpe": 1.0,
                "num_trades": 40,
                "max_drawdown": -0.01,
                "total_return": 0.02,
                "bars": len(frame),
            },
            "returns": returns,
        }

    monkeypatch.setattr("tradinglab.campaign.backtest_variant", fake_backtest)
    result = run_discovery(db, config, frames, persist=False)
    assert result["n_cells"] == 4
    assert seen and all(stamp < cutoff for stamp in seen)


def test_resume_only_after_a_partial_run(tmp_path: Path) -> None:
    """Reanudar exige un run empezado y sin terminar: nunca reejecuta."""
    db = tmp_path / "lab.db"
    init_campaigns(db)
    register_campaign(db, _config(5))
    with pytest.raises(CampaignError):
        run_discovery(db, _config(5), {}, resume=True)

    finish_campaign(db, "TEST-A")
    with pytest.raises(CampaignError):
        run_discovery(db, _config(5), {}, resume=True)


def test_finish_campaign_runs_once(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_campaigns(db)
    register_campaign(db, _config(5))
    record = finish_campaign(db, "TEST-A")
    assert record["finished_at"]
    with pytest.raises(CampaignError):
        finish_campaign(db, "TEST-A")


def test_plateau_exencion_c_si_adyacente_vacio() -> None:
    cells = [
        {
            "symbol": "AAA", "timeframe": "D1", "family": "tsmom",
            "variant": variant, "sharpe": 1.0, "trades": 40,
        }
        for variant in ("lb20", "lb60", "lb120", "lb250")
    ]
    cells.append({
        "symbol": "BBB", "timeframe": "D1", "family": "tsmom",
        "variant": "lb20", "sharpe": 1.0, "trades": 40,
    })
    clusters = {"AAA|D1": {"BBB": 1.0}}
    without = apply_plateau([dict(cell) for cell in cells], clusters)
    target = next(
        cell for cell in without
        if cell["symbol"] == "AAA" and cell["variant"] == "lb20"
    )
    assert target["adjacent_ok"] is False
    assert any(item.startswith("c:") for item in target["failed"])

    with_exemption = apply_plateau(
        [dict(cell) for cell in cells], clusters,
        skip_adjacent_if_empty=True,
    )
    target = next(
        cell for cell in with_exemption
        if cell["symbol"] == "AAA" and cell["variant"] == "lb20"
    )
    assert target["adjacent_exempt"] is True
    assert target["adjacent_ok"] is True
    assert target["plateau"] is True
    assert not any(item.startswith("c:") for item in target["failed"])
