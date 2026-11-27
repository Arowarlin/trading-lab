"""API de solo lectura de la consola Discovery Lab sobre una base temporal."""

from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path

from tradinglab import web
from tradinglab.config import Settings
from tradinglab.discovery import console as discovery_console

DSL = {
    "dsl_version": "1",
    "instrument": "US100",
    "market": "cfd",
    "timeframe": "M5",
    "session": {"start": "09:30", "end": "16:00", "flat_at": "15:45"},
    "long_entry": {
        "kind": "gt",
        "left": {"kind": "price", "price": "close"},
        "right": {"kind": "const", "value": 0.0},
    },
    "short_entry": None,
    "exit": {
        "stop": {"type": "atr", "mult": 2.0, "n": 14},
        "target": {"type": "rr", "rr": 2.0},
    },
    "limits": {"max_trades_per_day": 2, "cooldown_minutes": 0},
}


def _discovery_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE disc_campaigns (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, instrument TEXT NOT NULL,
            timeframe TEXT NOT NULL, template TEXT, engine_profile TEXT,
            config_json TEXT NOT NULL, config_hash TEXT, is_start TEXT, is_end TEXT,
            oos1_start TEXT, oos1_end TEXT, oos2_start TEXT, oos2_end TEXT,
            dataset_hash TEXT, n_total INTEGER, n_evaluated INTEGER NOT NULL DEFAULT 0,
            n_effective INTEGER, status TEXT NOT NULL DEFAULT 'registered',
            engine_version TEXT, approved_at TEXT, approved_by TEXT, quality_json TEXT,
            reject_reason TEXT, n_finalists INTEGER, last_error TEXT, snapshot_path TEXT,
            snapshot_hash TEXT, snapshot_rows INTEGER, snapshot_at TEXT, supersedes TEXT,
            superseded_by TEXT, superseded_at TEXT
        );
        CREATE TABLE disc_strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
            strategy_hash TEXT NOT NULL, dsl_json TEXT NOT NULL, family TEXT,
            instrument TEXT, timeframe TEXT, session TEXT,
            generation INTEGER NOT NULL DEFAULT 0, origin TEXT NOT NULL DEFAULT 'random',
            level INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'generated',
            reject_reason TEXT, created_at TEXT NOT NULL, selection_reason TEXT, verdict TEXT,
            UNIQUE(campaign_id, strategy_hash)
        );
        CREATE TABLE disc_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER NOT NULL,
            segment TEXT NOT NULL, cost_profile TEXT, metrics_json TEXT,
            trades_count INTEGER, returns_blob BLOB, computed_at TEXT NOT NULL,
            UNIQUE(strategy_id, segment, cost_profile)
        );
        CREATE TABLE disc_validations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER NOT NULL,
            test TEXT NOT NULL, result_json TEXT, passed INTEGER,
            computed_at TEXT NOT NULL, UNIQUE(strategy_id, test)
        );
        CREATE TABLE disc_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER NOT NULL,
            parent_a INTEGER, parent_b INTEGER, operator TEXT, param_diff_json TEXT,
            generation INTEGER NOT NULL DEFAULT 0, fitness_json TEXT, rank INTEGER,
            crowding REAL, reason TEXT, final INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    con.execute(
        "INSERT INTO disc_campaigns (id, created_at, instrument, timeframe, template,"
        " config_json, oos1_start, oos1_end, oos2_start, oos2_end, dataset_hash,"
        " n_total, n_evaluated, n_effective, status, approved_at, quality_json,"
        " n_finalists) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "camp-1",
            "2026-11-20T10:00:00+00:00",
            "US100.CASH",
            "M5",
            "demo_template",
            json.dumps({"mode": "ga", "data_source": "broker", "oos2_start": "2025-01-01"}),
            "2024-01-01",
            "2024-06-30",
            "2025-01-01",
            "2025-06-30",
            "abc123",
            7,
            4,
            2,
            "done",
            "2026-11-20T11:00:00+00:00",
            "{}",
            1,
        ),
    )
    con.execute(
        "INSERT INTO disc_strategies (id, campaign_id, strategy_hash, dsl_json, family,"
        " instrument, timeframe, generation, origin, level, status, created_at,"
        " selection_reason, verdict) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            5,
            "camp-1",
            "hash-5",
            json.dumps(DSL),
            "demo_template",
            "US100.CASH",
            "M5",
            2,
            "random",
            3,
            "finalist",
            "2026-11-20T10:05:00+00:00",
            "finalista IS",
            "SOBREAJUSTADA",
        ),
    )
    for segment, expectancy in (("fitness_is", 0.041), ("oos1", 0.032), ("oos2", 9.9)):
        con.execute(
            "INSERT INTO disc_evaluations (strategy_id, segment, cost_profile,"
            " metrics_json, trades_count, computed_at) VALUES (?,?,?,?,?,?)",
            (
                5,
                segment,
                "CFD-001:US100",
                json.dumps({"is": {"expectancy_r": expectancy, "profit_factor": 1.2}}),
                120,
                "2026-11-20T12:00:00+00:00",
            ),
        )
    validations = (
        ("pbo", {"pbo": 0.7432, "prob_oos_loss": 0.43, "n_slices": 16}, 0),
        ("wf", {"ok": False, "verdict": "fail", "n_folds": 4}, 0),
        ("hour_weekday", {"status": "ok", "groups": {"09:0": {"expectancy_r": 0.1, "trades": 3}}}, 1),
        ("streaks", {"status": "ok", "max_winning_streak": 5, "max_losing_streak": 4}, 1),
        (
            "optimizer_plateau",
            {
                "parameters": [
                    {
                        "name": "long_entry.args[1].n",
                        "base": 14.0,
                        "minus": 13.0,
                        "plus": 15.0,
                        "metrics": {
                            "base": {"expectancy_r": 0.04},
                            "minus": {"expectancy_r": 0.03},
                            "plus": {"expectancy_r": 0.02},
                        },
                    }
                ]
            },
            1,
        ),
        (
            "retest",
            {
                "base": {"expectancy_r": 0.04},
                "cost_x1_5": {"expectancy_r": 0.01},
                "stress_cost_x1_5_ok": False,
                "returns": [1, 2, 3],
            },
            0,
        ),
        (
            "challenge",
            {
                "accounts": {
                    "CFD-001": {
                        "firm": "ftmo",
                        "pass_rate": 0.64,
                        "breach_rate": 0.02,
                        "median_days_to_pass": 45,
                        "paths": 5000,
                        "rules": "FTMO",
                    }
                }
            },
            1,
        ),
        ("oos2", {"sharpe": 9.9}, 1),
    )
    for test, result, passed in validations:
        con.execute(
            "INSERT INTO disc_validations (strategy_id, test, result_json, passed,"
            " computed_at) VALUES (?,?,?,?,?)",
            (5, test, json.dumps(result), passed, "2026-11-20T12:00:00+00:00"),
        )
    con.execute(
        "INSERT INTO disc_lineage (strategy_id, parent_a, parent_b, operator,"
        " param_diff_json, generation, fitness_json, rank, crowding, reason, final)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (5, 1, 2, "nsga2", "{}", 2, "{}", 0, 0.1, "frontier", 1),
    )
    con.commit()
    con.close()


def _lab_db(path: Path) -> None:
    from datetime import date, datetime, timedelta, timezone

    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE strategy_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, ts TEXT, run_id INTEGER,
            counted INTEGER DEFAULT 1
        );
        """
    )
    iso = datetime.now(timezone.utc).isocalendar()
    week_start = date.fromisocalendar(int(iso.year), int(iso.week), 1)
    stamp = (week_start + timedelta(days=1)).isoformat() + "T10:00:00"
    con.execute(
        "INSERT INTO strategy_trials (symbol, ts, run_id, counted) VALUES (?,?,?,?)",
        ("US100.CASH", stamp, 1, 1),
    )
    con.commit()
    con.close()


def _server(tmp_path: Path):
    discovery = tmp_path / "discovery.db"
    lab = tmp_path / "lab.db"
    _discovery_db(discovery)
    _lab_db(lab)
    data = web.LabData(
        Settings(),
        root=tmp_path,
        db_path=lab,
        discovery_db=discovery,
        costs_db=lab,
        data_root=tmp_path,
        external=False,
    )
    server = web.DashboardServer(("127.0.0.1", 0), data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, data


def _get(base: str, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(f"{base}{path}", timeout=10) as response:
        return response.status, json.load(response)


def test_count_tests_readonly_incluye_incubados(tmp_path: Path) -> None:
    lab = tmp_path / "lab.db"
    con = sqlite3.connect(lab)
    con.executescript(
        """
        CREATE TABLE lesson_tests (id INTEGER PRIMARY KEY);
        CREATE TABLE optimization_trials (id INTEGER PRIMARY KEY);
        CREATE TABLE holdout_reads (id INTEGER PRIMARY KEY);
        CREATE TABLE strategy_trials (id INTEGER PRIMARY KEY, counted INTEGER);
        CREATE TABLE lifecycle_bots (id INTEGER PRIMARY KEY, frozen_at TEXT);
        CREATE TABLE campaign_registry (id INTEGER PRIMARY KEY, n_total INTEGER);
        INSERT INTO lesson_tests DEFAULT VALUES;
        INSERT INTO optimization_trials DEFAULT VALUES;
        INSERT INTO holdout_reads DEFAULT VALUES;
        INSERT INTO strategy_trials (counted) VALUES (1), (0);
        INSERT INTO lifecycle_bots (frozen_at) VALUES ('2026-01-01'), (NULL);
        INSERT INTO campaign_registry (n_total) VALUES (11);
        """
    )
    con.commit()
    con.close()
    counts = discovery_console.count_tests_readonly(lab)
    assert counts == {
        "lessons": 1,
        "optimization_trials": 1,
        "holdout_reads": 1,
        "strategy_trials": 1,
        "incubated": 1,
        "campaign_registry": 11,
        "informal_trials": 0,
        "discovery": 0,
        "total": 16,
    }


def test_api_discovery_solo_lectura(tmp_path: Path, monkeypatch) -> None:
    server, thread, data = _server(tmp_path)
    before = (tmp_path / "discovery.db").read_bytes()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, summary = _get(base, "/api/discovery/summary")
        assert status == 200
        assert summary["read_only"] is True
        assert summary["campaigns"]["total"] == 1
        assert summary["campaigns"]["n_total"] == 7
        assert summary["count_tests"]["discovery"] == 7
        assert summary["budget"][0]["used"] == 1
        assert "oos2" not in json.dumps(summary)

        _, campaigns = _get(base, "/api/discovery/campaigns")
        assert campaigns["n"] == 1
        assert [item["id"] for item in campaigns["strategies"]] == [5]
        assert "oos2" not in json.dumps(campaigns)

        _, campaign = _get(base, "/api/discovery/campaign/camp-1")
        assert campaign["campaign"]["id"] == "camp-1"
        assert campaign["campaign"]["timeframe"] == "M5"
        assert campaign["campaign"]["instrument"] == "US100.CASH"
        assert campaign["costs_by_account"]
        assert "swap_long" in campaign["costs_by_account"][0]
        assert campaign["diagnostics"]["n_finalists"] == 1
        assert campaign["generations"][0]["generation"] == 2
        assert campaign["frontier"][0]["id"] == 5
        assert "oos2" not in json.dumps(campaign)

        _, strategy = _get(base, "/api/discovery/strategy/5")
        assert strategy["strategy"]["verdict_chip"] == "SOBREAJUSTADA"
        assert strategy["rules"]
        assert [row["segment"] for row in strategy["metrics"]["rows"]] == [
            "fitness_is",
            "oos1",
        ]
        assert strategy["cost_stress"]["cost_x1_5"]["expectancy_r"] == 0.01
        assert "returns" not in strategy["cost_stress"]
        assert "swap_long" in strategy["costs_by_account"][0]
        assert strategy["challenge_accounts"]["CFD-001"]["rules"] == "FTMO"
        assert strategy["plateau"]["parameters"][0]["name"].startswith("long_entry")
        assert "oos2" not in json.dumps(strategy)
        assert "9.9" not in json.dumps(strategy)

        monkeypatch.setattr(
            discovery_console,
            "edge_map_payload",
            lambda *args, **kwargs: {
                "report": {
                    "firms": [],
                    "combos": [],
                    "disconnected_accounts": [{"id": "CFD-002"}],
                    "blocked": [],
                },
                "by": [],
                "view": kwargs.get("by"),
                "read_only": True,
            },
        )
        _, edge = _get(base, "/api/discovery/edge-map?by=cuenta")
        assert edge["view"] == "cuenta"
        assert edge["report"]["disconnected_accounts"][0]["id"] == "CFD-002"

        monkeypatch.setattr(
            discovery_console,
            "suggest_payload",
            lambda *args, **kwargs: {
                "rows": [{"template": "demo", "label": "por probar"}],
                "n_rows": 1,
                "label": "por probar",
            },
        )
        _, suggest = _get(base, "/api/discovery/suggest")
        assert suggest["label"] == "por probar"

        try:
            urllib.request.urlopen(f"{base}/api/discovery/strategy/999", timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("strategy/999 debía devolver 404")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert (tmp_path / "discovery.db").read_bytes() == before
    assert data.discovery_db == tmp_path / "discovery.db"


def test_api_discovery_no_expone_rutas_de_escritura() -> None:
    assert not any(
        route.startswith("/api/discovery/") for route in web.WRITE_ROUTES
    )
