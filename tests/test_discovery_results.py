"""Comando de lectura `discovery results`: solo IS, sin tocar OOS-2."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from tradinglab import cli as cli_mod
from tradinglab.discovery import databank, results


def _strategy(threshold: float = 25.0) -> dict:
    return {
        "dsl_version": "1",
        "instrument": "USDJPY",
        "market": "cfd",
        "timeframe": "H1",
        "session": {"start": "18:00", "end": "03:00", "flat_at": "02:45"},
        "long_entry": {
            "kind": "and",
            "args": [
                {
                    "kind": "gt",
                    "left": {"kind": "price", "price": "close"},
                    "right": {"kind": "const", "value": 0.0},
                },
                {
                    "kind": "regime",
                    "regime": "ranging",
                    "n": 14,
                    "params": {"threshold": threshold},
                },
            ],
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "atr", "mult": 2.5},
            "target": {"type": "rr", "rr": 2.5},
        },
        "limits": {"max_trades_per_day": 2, "cooldown_bars": 0},
    }


def _campaign(db: Path) -> int:
    databank.add_campaign(
        "camp",
        {
            "instrument": "USDJPY",
            "timeframe": "H1",
            "template": "asia_range_reversion",
            "grid": {
                "dimensions": [
                    {
                        "name": "threshold",
                        "kind": "path",
                        "path": "long_entry.args[1].params.threshold",
                        "values": [15, 20, 25],
                    },
                    {
                        "name": "stop",
                        "kind": "path",
                        "path": "exit.stop.mult",
                        "values": [1.5, 2.0, 2.5],
                    },
                    {
                        "name": "target_rr",
                        "kind": "path",
                        "path": "exit.target.rr",
                        "values": [1.5, 2.0, 2.5],
                    },
                ]
            },
        },
        instrument="USDJPY",
        timeframe="H1",
        template="asia_range_reversion",
        status="done",
        n_total=1,
        db_path=db,
    )
    databank.set_campaign_counts("camp", n_evaluated=1, db_path=db)
    strategy_id = databank.add_strategy(
        "camp", _strategy(), level=1, status="evaluated", db_path=db
    )
    databank.add_evaluation(
        strategy_id,
        segment="fitness_is",
        cost_profile="best:CFD-001+CFD-006:USDJPY",
        metrics={
            "is": {
                "expectancy_r": -0.0755,
                "gross_expectancy_r": -0.0291,
                "trades": 2274,
                "profit_factor": 0.7620,
                "cost_by_account": {"CFD-001": 0.0506, "CFD-006": 0.0422},
            },
            "folds": [
                {"expectancy_r": -0.0550},
                {"expectancy_r": -0.0423},
                {"expectancy_r": -0.0847},
                {"expectancy_r": 0.0100},
            ],
        },
        trades_count=2274,
        returns=[-0.0755],
        db_path=db,
    )
    databank.add_lineage(
        strategy_id,
        parent_a=None,
        parent_b=None,
        operator=None,
        rank=0,
        db_path=db,
    )
    databank.set_strategy_selection(
        strategy_id,
        "discarded",
        "descartado: IS completa -0.07546851553502852 <= 0",
        db_path=db,
    )
    return strategy_id


def test_campaign_results_lee_solo_is(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    strategy_id = _campaign(db)

    report = results.campaign_results("camp", db_path=db)

    assert report["read_only"] is True
    assert report["campaign"]["n_evaluated"] == 1
    row = report["rows"][0]
    assert row["id"] == strategy_id
    assert row["params"] == {"threshold": 25.0, "stop": 2.5, "target_rr": 2.5}
    assert row["verdict"] == "DESCARTADO"
    assert row["verdict_source"] == "selection"
    assert row["gross_r"] == -0.0291
    assert row["net_r"] == -0.0755
    assert row["positive_folds"] == 1
    assert row["reason"].startswith("descartado: IS completa")

    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM disc_holdout_reads").fetchone()[0] == 0
    finally:
        con.close()


def test_slip_eq_solo_en_campana_aprobada(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    strategy_id = _campaign(db)
    report = results.campaign_results("camp", db_path=db)
    assert report["rows"][0]["slip_eq"] is None

    con = sqlite3.connect(db)
    try:
        con.execute(
            "UPDATE disc_campaigns SET approved_at = ? WHERE id = 'camp'",
            ("2026-11-24T00:00:00+00:00",),
        )
        row = con.execute(
            "SELECT metrics_json FROM disc_evaluations"
            " WHERE strategy_id = ? AND segment = 'fitness_is'",
            (strategy_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["is"]["mean_risk_price"] = 0.5
        con.execute(
            "UPDATE disc_evaluations SET metrics_json = ?"
            " WHERE strategy_id = ? AND segment = 'fitness_is'",
            (json.dumps(payload), strategy_id),
        )
        con.commit()
    finally:
        con.close()

    report = results.campaign_results("camp", db_path=db)
    row = report["rows"][0]
    assert row["slip_eq"] == -0.0755 * 0.5 / 2.0
    assert row["slip_eq_status"] == "ok"


def test_discovery_results_cli(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    _campaign(db)

    result = CliRunner().invoke(
        cli_mod.app,
        ["discovery", "results", "camp", "--db", str(db)],
        env={"COLUMNS": "240"},
    )

    assert result.exit_code == 0, result.output
    assert "Bruto R" in result.output
    assert "Neto R" in result.output
    assert "threshold=25" in result.output
    assert "DESCARTADO" in result.output
    assert "descartado: IS completa" in result.output
    assert "solo IS; OOS-2 no se lee." in result.output


def test_campaign_results_params_del_grid_y_veredicto(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    databank.add_campaign(
        "n2",
        {
            "instrument": "XAUUSD",
            "timeframe": "H4",
            "template": "donchian_vol_h4",
            "grid": {
                "dimensions": [
                    {
                        "name": "channel_n",
                        "kind": "path",
                        "path": "long_entry.args[0].right.n",
                        "values": [20, 40, 55],
                    },
                    {
                        "name": "vol_pct",
                        "kind": "path",
                        "path": "long_entry.args[1].params.pct",
                        "values": [0.6, 0.7, 0.8],
                    },
                    {
                        "name": "stop_mult",
                        "kind": "path",
                        "path": "exit.stop.mult",
                        "values": [1.5, 2.0, 2.5],
                    },
                ]
            },
        },
        instrument="XAUUSD",
        timeframe="H4",
        template="donchian_vol_h4",
        status="done",
        n_total=27,
        db_path=db,
    )
    strategy = {
        "dsl_version": "1",
        "instrument": "XAUUSD",
        "market": "cfd",
        "timeframe": "H4",
        "session": {"start": "00:00", "end": "23:59", "flat_at": "23:59"},
        "long_entry": {
            "kind": "and",
            "args": [
                {
                    "kind": "cross_up",
                    "left": {"kind": "price", "price": "close"},
                    "right": {"kind": "level", "level": "donchian_high", "n": 40},
                },
                {
                    "kind": "regime",
                    "regime": "vol_high",
                    "n": 14,
                    "lookback": 100,
                    "params": {"pct": 0.7},
                },
            ],
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "atr", "mult": 2.5, "n": 14},
            "target": {"type": "rr", "rr": 2.0},
        },
        "limits": {"max_trades_per_day": 1, "cooldown_bars": 0},
    }
    strategy_id = databank.add_strategy(
        "n2", strategy, level=1, status="finalist", db_path=db
    )
    databank.add_evaluation(
        strategy_id,
        segment="fitness_is",
        cost_profile="best:CFD-001+CFD-006:XAUUSD",
        metrics={
            "is": {
                "expectancy_r": 0.0138,
                "gross_expectancy_r": 0.0414,
                "trades": 361,
                "profit_factor": 1.029,
                "cost_by_account": {"CFD-001": 0.0197, "CFD-006": 0.0169},
            },
            "folds": [
                {"expectancy_r": 0.0053},
                {"expectancy_r": -0.0667},
                {"expectancy_r": 0.0967},
            ],
        },
        trades_count=361,
        returns=[0.0138],
        db_path=db,
    )
    databank.add_lineage(
        strategy_id,
        parent_a=None,
        parent_b=None,
        operator=None,
        rank=0,
        db_path=db,
    )
    databank.set_strategy_selection(
        strategy_id,
        "finalist",
        "finalista: OOS-1 expectativa 0.39421538420575275 PF 2.1200475153558203",
        db_path=db,
    )

    report = results.campaign_results("n2", db_path=db)
    row = report["rows"][0]
    assert row["params"] == {
        "channel_n": 40,
        "vol_pct": 0.7,
        "stop_mult": 2.5,
    }
    assert row["verdict"] == "FINALISTA"
    assert row["verdict_source"] == "selection"

    databank.set_strategy_verdict(strategy_id, 3, "MODERADA", db_path=db)
    report = results.campaign_results("n2", db_path=db)
    row = report["rows"][0]
    assert row["verdict"] == "MODERADA"
    assert row["verdict_source"] == "stored"
