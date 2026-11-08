from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
import yaml

from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.f13 import (
    activate,
    config_check,
    config_hash,
    daily_report,
    execution_metrics,
    freeze,
    load_criteria,
    record_snapshot,
    signal_check,
    status,
)
from tradinglab.orchestrator import BotSpec
from tradinglab.runtime import get_bot_state


class FakeBroker:
    def snapshot(self, prices=None):
        return {
            "equity": 100_100.0,
            "cash": 90_000.0,
            "positions_value": 10_100.0,
            "positions": [{"ticker": "QQQ", "qty": 10.0}],
        }


def test_hash_y_criterios():
    assert len(config_hash()) == 64
    criteria = load_criteria()
    assert criteria["window_weeks"] == 8
    assert "hard_stops" in criteria
    assert config_hash() == config_hash()


def test_freeze_y_status(tmp_path):
    db = tmp_path / "lab.db"
    row = freeze(db, bot="qqq-trend-f13", symbol="QQQ", start_date="2026-11-09")
    assert row["bot"] == "qqq-trend-f13"
    assert len(row["config_hash"]) == 64
    assert status(db)["start_date"] == "2026-11-09"
    assert config_check(db)["ok"] is True


def test_freeze_no_cambia_enabled(tmp_path):
    root = tmp_path / "repo"
    config = root / "config"
    config.mkdir(parents=True)
    bots = config / "bots.yaml"
    bots.write_text(
        "bots:\n"
        "  - id: qqq-trend-f13\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    db = tmp_path / "lab.db"
    assert status(db) is None
    freeze(db, bot="qqq-trend-f13", symbol="QQQ", start_date="2026-11-09", root=root)
    assert yaml.safe_load(bots.read_text(encoding="utf-8"))["bots"][0]["enabled"] is False
    assert status(db) is not None


def test_record_snapshot(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    result = record_snapshot(db, FakeBroker(), bot="qqq-trend-f13", spy_close=600.0)
    assert result["equity"] == pytest.approx(100_100.0)
    with connect(db) as con:
        row = con.execute("SELECT * FROM f13_metrics").fetchone()
    assert row["open_positions"] == 1
    assert row["notes"] == "qqq-trend-f13"


def test_execution_metrics_slippage(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
            "VALUES(?,?,?,?,?,?,?)",
            ("2026-11-07T14:00:00+00:00", "QQQ", "qqq-trend-f13", "long", 1.0, 100.0, "test"),
        )
        con.execute(
            "INSERT INTO orders(ts, ticker, side, qty, status, bot) VALUES(?,?,?,?,?,?)",
            ("2026-11-07T14:30:00+00:00", "QQQ", "buy", 10, "filled", "qqq-trend-f13"),
        )
        order_id = con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        con.execute(
            "INSERT INTO fills(order_id, ts, qty, price, commission) VALUES(?,?,?,?,?)",
            (order_id, "2026-11-07T14:30:00+00:00", 10, 101.0, 0.0),
        )
    metrics = execution_metrics(db, bot="qqq-trend-f13", start_date="2026-11-01")
    assert metrics["fills"] == 1
    assert metrics["slippage_p50_bps"] == pytest.approx(100.0)
    assert metrics["size_error_max"] == pytest.approx(0.0)


def test_signal_check_recalcula(monkeypatch, tmp_path):
    dates = pd.date_range("2024-01-01", periods=300, freq="D")
    df = pd.DataFrame(
        {
            "open": range(100, 400),
            "high": range(101, 401),
            "low": range(99, 399),
            "close": [100 + i for i in range(300)],
            "volume": [1_000] * 300,
        },
        index=dates,
    )
    monkeypatch.setattr("tradinglab.data.fetch", lambda *args, **kwargs: df)
    spec = BotSpec(
        id="qqq-trend-f13",
        type="deterministic",
        strategy="trend",
        universe=["QQQ"],
        enabled=False,
        params={"fast": 50, "slow": 200, "regime": 200},
        exposure=0.35,
    )
    result = signal_check(Settings(), spec, tmp_path / "lab.db")
    assert result["ok"]
    assert result["target"] == pytest.approx(1.0)
    assert result["match"] is None


def _dryrun(root, stamp: str) -> None:
    folder = root / "data" / "dryrun"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"dryrun_{stamp}.json").write_text("{}", encoding="utf-8")


def _reconcile(db, ts: str, status: str = "ok") -> None:
    with connect(db) as con:
        con.execute(
            "INSERT INTO reconciliation(ts, source, status, details) "
            "VALUES(?,?,?,?)",
            (ts, "paper", status, "" if status == "ok" else "diferencia"),
        )


def test_daily_report_ciclos_reconciliaciones_y_lunes(tmp_path):
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    _dryrun(root, "20261109_212000")
    _dryrun(root, "20261110_212000")
    _reconcile(db, "2026-11-09T21:30:00+00:00")
    _reconcile(db, "2026-11-10T21:30:00+00:00")

    report = daily_report(db, root=root, today=date(2026, 11, 10))
    assert report["status"] == "ok"
    assert report["read_only"] is True
    assert report["cycles"]["expected"] == 1
    assert report["cycles"]["executed"] == 1
    assert report["cycles"]["pct"] == pytest.approx(1.0)
    assert report["cycles"]["monday"] == {"date": "2026-11-09", "ok": True}
    assert report["cycles"]["last_cycle_at"] == "2026-11-10T21:20:00Z"
    assert report["reconciliations"]["count"] == 2
    assert report["reconciliations"]["ok_pct"] == pytest.approx(1.0)
    assert report["alerts"] == []

    out = root / "reports" / "f13"
    assert (out / "2026-11-10.json").exists()
    assert (out / "latest.json").exists()
    markdown = (out / "2026-11-10.md").read_text(encoding="utf-8")
    assert "## Ciclos" in markdown
    assert "## Reconciliaciones" in markdown
    assert "## Slippage y tamaño" in markdown
    assert "Sin alertas" in markdown


def test_daily_report_alerta_si_falta_el_lunes(tmp_path):
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    report = daily_report(db, root=root, today=date(2026, 11, 10))
    assert report["status"] == "warn"
    assert report["cycles"]["monday"] == {"date": "2026-11-09", "ok": False}
    assert any(
        alert["id"] == "f13_monday_missed" for alert in report["alerts"]
    )
    assert report["cycles"]["missing"] == ["2026-11-09"]


def test_daily_report_no_alerta_antes_del_inicio(tmp_path):
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    report = daily_report(db, root=root, today=date(2026, 11, 8))
    assert report["cycles"]["expected"] == 0
    assert report["cycles"]["monday"] == {"date": None, "ok": True}
    assert report["alerts"] == []
    assert report["status"] == "ok"


def test_daily_report_no_modifica_estado_operativo(tmp_path):
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    tables = ("f13_metrics", "orders", "fills", "signals", "reconciliation")
    with connect(db) as con:
        before = {
            table: con.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in tables
        }
    daily_report(db, root=root, today=date(2026, 11, 10))
    with connect(db) as con:
        after = {
            table: con.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in tables
        }
    assert after == before


def test_daily_report_slippage_y_tamano(tmp_path):
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    with connect(db) as con:
        con.execute(
            "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
            "VALUES(?,?,?,?,?,?,?)",
            ("2026-11-09T14:00:00+00:00", "QQQ", "qqq-trend-f13", "long", 1.0, 100.0, "test"),
        )
        con.execute(
            "INSERT INTO orders(ts, ticker, side, qty, status, bot) VALUES(?,?,?,?,?,?)",
            ("2026-11-09T14:30:00+00:00", "QQQ", "buy", 10, "filled", "qqq-trend-f13"),
        )
        order_id = con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        con.execute(
            "INSERT INTO fills(order_id, ts, qty, price, commission) VALUES(?,?,?,?,?)",
            (order_id, "2026-11-09T14:30:00+00:00", 10, 101.0, 0.0),
        )

    report = daily_report(db, root=root, today=date(2026, 11, 10))
    assert report["slippage"]["fills"] == 1
    assert report["slippage"]["p50_bps"] == pytest.approx(100.0)
    assert report["slippage"]["ok"] is False
    assert report["size"]["max_error_shares"] == pytest.approx(0.0)
    assert report["size"]["ok"] is True
    assert any(alert["id"] == "f13_slippage_high" for alert in report["alerts"])


def _repo(tmp_path):
    root = tmp_path / "repo"
    config = root / "config"
    config.mkdir(parents=True)
    (config / "bots.yaml").write_text(
        "bots:\n"
        "  - id: other-bot\n"
        "    enabled: false\n"
        "  - id: qqq-trend-f13\n"
        "    type: deterministic\n"
        "    enabled: false  # pendiente\n"
        "    params: {fast: 50, slow: 200, regime: 200}\n",
        encoding="utf-8",
    )
    (config / "f13.yaml").write_text(
        "criteria:\n  window_weeks: 8\n  min_cycles_pct: 0.95\n",
        encoding="utf-8",
    )
    return root


def test_activate_solo_cambia_su_bot_y_recongela(tmp_path) -> None:
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    before = status(db)["config_hash"]
    row = activate(
        db,
        bot="qqq-trend-f13",
        root=root,
        settings=Settings(mode="paper"),
    )
    assert row["config_hash"] != before
    assert row["start_date"] == "2026-11-09"
    assert config_check(db, root)["ok"] is True
    data = yaml.safe_load((root / "config" / "bots.yaml").read_text(encoding="utf-8"))
    bots = {item["id"]: item for item in data["bots"]}
    assert bots["qqq-trend-f13"]["enabled"] is True
    assert bots["other-bot"]["enabled"] is False
    text = (root / "config" / "bots.yaml").read_text(encoding="utf-8")
    assert "# pendiente" in text
    state = get_bot_state(db, "qqq-trend-f13")
    assert state is not None and state["enabled"] == 1


def test_activate_rechaza_hash_cambiado(tmp_path) -> None:
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    path = root / "config" / "bots.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "# cambio\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        activate(
            db,
            bot="qqq-trend-f13",
            root=root,
            settings=Settings(mode="paper"),
        )
    assert "enabled: true" not in path.read_text(encoding="utf-8")


def test_activate_rechaza_live(tmp_path) -> None:
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    with pytest.raises(ValueError, match="live"):
        activate(
            db,
            bot="qqq-trend-f13",
            root=root,
            settings=Settings(mode="live"),
        )
    data = yaml.safe_load((root / "config" / "bots.yaml").read_text(encoding="utf-8"))
    assert next(item for item in data["bots"] if item["id"] == "qqq-trend-f13")[
        "enabled"
    ] is False


def test_activate_rechaza_bot_ya_enabled(tmp_path) -> None:
    root = _repo(tmp_path)
    path = root / "config" / "bots.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "    enabled: false  # pendiente",
            "    enabled: true  # pendiente",
        ),
        encoding="utf-8",
    )
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    with pytest.raises(ValueError, match="enabled"):
        activate(
            db,
            bot="qqq-trend-f13",
            root=root,
            settings=Settings(mode="paper"),
        )


def test_activate_restaura_yaml_si_freeze_falla(tmp_path, monkeypatch) -> None:
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    path = root / "config" / "bots.yaml"
    original = path.read_text(encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr("tradinglab.f13.freeze", boom)
    with pytest.raises(RuntimeError):
        activate(
            db,
            bot="qqq-trend-f13",
            root=root,
            settings=Settings(mode="paper"),
        )
    assert path.read_text(encoding="utf-8") == original
    assert config_check(db, root)["ok"] is True
