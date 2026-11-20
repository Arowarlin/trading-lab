from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import tradinglab.journal as journal_mod
from tradinglab import web
from tradinglab.backtest import run as run_backtest
from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.journal import build_journal
from tradinglab.orchestrator import BotSpec
from tradinglab.prop.rules import ftmo
from tradinglab.prop.simulator import multiverse_by_trade


def test_multiverse_reproducible_y_curvas() -> None:
    rules = ftmo(100_000, "challenge")
    pnls = [1_000.0, -500.0, 300.0, 800.0, -200.0, 400.0]
    first = multiverse_by_trade(rules, pnls, n_paths=1_000, seed=42)
    second = multiverse_by_trade(rules, pnls, n_paths=1_000, seed=42)
    assert first["curves"] == second["curves"]
    assert first["prob_breach_any"] == second["prob_breach_any"]
    assert first["seed"] == 42
    assert first["paths"] == 1_000
    assert len(first["curves"]["p5"]) == len(first["steps"])
    for low, mid, high in zip(
        first["curves"]["p5"], first["curves"]["p50"], first["curves"]["p95"]
    ):
        assert low <= mid <= high
    assert first["prob_breach_daily"] == pytest.approx(0.0)
    assert first["prob_breach_max"] == pytest.approx(0.0)
    assert first["expected_max_drawdown"] <= 0
    assert first["final_equity_median"] > first["capital"]


def test_multiverse_breach_diario_y_bloques_por_dia() -> None:
    rules = ftmo(100_000, "challenge")
    single = multiverse_by_trade(
        rules, [-3_000.0, -3_000.0, -3_000.0, -3_000.0], n_paths=500, seed=7
    )
    assert single["daily_basis"] == "por_operacion"
    assert single["prob_breach_daily"] == pytest.approx(0.0)

    blocks = multiverse_by_trade(
        rules,
        [-3_000.0, -3_000.0, -3_000.0, -3_000.0],
        n_paths=500,
        seed=7,
        day_sizes=[2, 2],
    )
    assert blocks["daily_basis"] == "bloques_por_dia"
    assert blocks["prob_breach_daily"] == pytest.approx(1.0)
    assert blocks["day_sizes"] == [2, 2]


def test_multiverse_max_loss() -> None:
    rules = ftmo(100_000, "challenge")
    result = multiverse_by_trade(
        rules, [-10_000.0, 100.0], n_paths=200, seed=42
    )
    assert result["prob_breach_max"] == pytest.approx(1.0)
    assert result["prob_breach_any"] == pytest.approx(1.0)


def test_backtest_expone_operaciones_para_sidecar() -> None:
    rng = np.random.default_rng(7)
    n = 260
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    idx = pd.bdate_range("2020-01-01", periods=n)
    frame = pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.001, n)),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        },
        index=idx,
    )
    target = pd.Series(0.0, index=idx)
    target.iloc[50:120] = 1.0
    target.iloc[150:200] = 1.0
    result = run_backtest(frame, target, starting_cash=100_000)
    assert len(result.trade_pnls) >= 2
    assert len(result.trade_pnls) == len(result.trade_days)
    assert result.metrics["num_trades"] == len(result.trade_pnls)


def test_journal_incluye_multiverse_por_cuenta(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        for day, buy, sell in (
            ("2026-01-05", 100.0, 110.0),
            ("2026-01-06", 110.0, 105.0),
        ):
            cur = con.execute(
                "INSERT INTO orders(ts, ticker, side, qty, order_type, status, bot, reason) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (f"{day}T15:00:00+00:00", "SPY", "buy", 1, "market", "filled", "trend-spy", "test"),
            )
            order_id = int(cur.lastrowid)
            con.execute(
                "INSERT INTO fills(order_id, ts, qty, price, commission) VALUES(?,?,?,?,?)",
                (order_id, f"{day}T15:00:00+00:00", 1, buy, 0),
            )
            cur = con.execute(
                "INSERT INTO orders(ts, ticker, side, qty, order_type, status, bot, reason) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (f"{day}T16:00:00+00:00", "SPY", "sell", 1, "market", "filled", "trend-spy", "test"),
            )
            order_id = int(cur.lastrowid)
            con.execute(
                "INSERT INTO fills(order_id, ts, qty, price, commission) VALUES(?,?,?,?,?)",
                (order_id, f"{day}T16:00:00+00:00", 1, sell, 0),
            )
    specs = [
        BotSpec(
            id="trend-spy",
            type="deterministic",
            strategy="trend",
            universe=["SPY"],
            enabled=True,
            profile="intraday_fx",
            account="ftmo_demo",
        )
    ]
    monkeypatch.setattr(journal_mod, "load_bots", lambda: specs)
    payload = build_journal(db, tz="UTC")
    rows = {row["account"]: row for row in payload["multiverse"]}
    assert "ftmo_demo" in rows
    assert rows["ftmo_demo"]["paths"] == 1_000
    assert rows["ftmo_demo"]["seed"] == 42
    assert rows["ftmo_demo"]["trades"] == 2
    assert rows["ftmo_demo"]["daily_basis"] == "bloques_por_dia"
    assert 0.0 <= rows["ftmo_demo"]["prob_breach_any"] <= 1.0


def test_research_detail_lee_sidecar_de_operaciones(tmp_path: Path) -> None:
    research = tmp_path / "reports" / "research"
    artifacts = research / "artifacts"
    artifacts.mkdir(parents=True)
    idx = pd.bdate_range("2026-01-01", periods=4)
    pd.DataFrame(
        {"equity": [100, 101, 100, 102], "buy_hold": [100, 100, 101, 102]},
        index=idx,
    ).to_parquet(artifacts / "test.parquet")
    pd.DataFrame(
        {"pnl": [500.0, -200.0, 300.0, -100.0], "day": ["2026-01-02", "2026-01-02", "2026-01-03", "2026-01-03"]}
    ).to_parquet(artifacts / "test.trades.parquet")
    (research / "latest.json").write_text(
        json.dumps({"rules_meta": {"firm": "FTMO", "phase": "challenge", "account_size": 100000.0}}),
        encoding="utf-8",
    )
    data = web.LabData(
        Settings(), root=tmp_path, db_path=tmp_path / "missing.db", external=False
    )
    detail = data.research_detail("artifacts/test.parquet")
    assert detail["artifact_trades"] == 4
    assert detail["multiverse"]["paths"] == 1_000
    assert detail["multiverse"]["seed"] == 42
    assert detail["multiverse"]["day_sizes"] == [2, 2]
    assert detail["multiverse_reason"] is None


def test_research_detail_sin_sidecar_no_inventa(tmp_path: Path) -> None:
    research = tmp_path / "reports" / "research"
    artifacts = research / "artifacts"
    artifacts.mkdir(parents=True)
    idx = pd.bdate_range("2026-01-01", periods=2)
    pd.DataFrame(
        {"equity": [100, 101], "buy_hold": [100, 100]}, index=idx
    ).to_parquet(artifacts / "test.parquet")
    data = web.LabData(
        Settings(), root=tmp_path, db_path=tmp_path / "missing.db", external=False
    )
    detail = data.research_detail("artifacts/test.parquet")
    assert detail["multiverse"] is None
    assert "Sin datos" in detail["multiverse_reason"]
