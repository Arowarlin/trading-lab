from __future__ import annotations

import hashlib
import json
import threading
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pytest

import tradinglab.journal as journal_mod
from tradinglab import web
from tradinglab.accounts import AccountDefinition, load_accounts
from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.journal import (
    ClosedTrade,
    _concentration,
    build_journal,
    filter_trades,
    load_closed_trades,
    summarize,
)
from tradinglab.orchestrator import BotSpec


def _fill(
    con,
    *,
    bot: str,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    ts: str,
    commission: float = 0.0,
) -> int:
    cursor = con.execute(
        "INSERT INTO orders(ts, ticker, side, qty, order_type, status, bot, reason) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (ts, ticker, side, qty, "market", "filled", bot, "test"),
    )
    order_id = int(cursor.lastrowid)
    con.execute(
        "INSERT INTO fills(order_id, ts, qty, price, commission) VALUES(?,?,?,?,?)",
        (order_id, ts, qty, price, commission),
    )
    return order_id


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "lab.db"
    init_db(db)
    return db


def _trade(
    day: str,
    pnl: float,
    *,
    bot: str = "trend-spy",
    account: str | None = "paper_main",
    profile: str | None = "swing_equity",
    ticker: str = "SPY",
    hour: int = 15,
) -> ClosedTrade:
    stamp = f"{day}T{hour:02d}:00:00+00:00"
    return ClosedTrade(
        bot=bot,
        account=account,
        profile=profile,
        ticker=ticker,
        qty=1.0,
        entry_price=100.0,
        exit_price=100.0 + pnl,
        entry_ts=stamp,
        exit_ts=stamp,
        pnl=pnl,
        fees=0.0,
        return_pct=pnl / 100.0,
        holding_hours=1.0,
        day=day,
        hour=hour,
        entry_order_id=1,
        exit_order_id=2,
        exit_fill_id=2,
    )


def test_fifo_reconstruye_operaciones_y_no_escribe(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with connect(db) as con:
        _fill(con, bot="trend-spy", ticker="SPY", side="buy", qty=10, price=100.0,
              ts="2026-01-05T15:00:00+00:00", commission=1.0)
        _fill(con, bot="trend-spy", ticker="SPY", side="buy", qty=10, price=110.0,
              ts="2026-01-06T15:00:00+00:00", commission=1.0)
        _fill(con, bot="trend-spy", ticker="SPY", side="sell", qty=10, price=120.0,
              ts="2026-01-07T15:00:00+00:00", commission=1.0)
        _fill(con, bot="trend-spy", ticker="SPY", side="sell", qty=5, price=90.0,
              ts="2026-01-08T15:00:00+00:00", commission=0.5)
        _fill(con, bot="fx-bot", ticker="EURUSD", side="buy", qty=1, price=1.1,
              ts="2026-01-08T16:00:00+00:00")
        _fill(con, bot="fx-bot", ticker="EURUSD", side="sell", qty=1, price=1.105,
              ts="2026-01-09T16:00:00+00:00")
        _fill(con, bot="ghost", ticker="TSLA", side="sell", qty=2, price=50.0,
              ts="2026-01-09T17:00:00+00:00")

    before = hashlib.sha256(db.read_bytes()).hexdigest()
    trades, diagnostics = load_closed_trades(
        db,
        tz="UTC",
        bots={
            "trend-spy": {"account": "paper_main", "profile": "swing_equity"},
            "fx-bot": {"account": "ftmo_demo", "profile": "intraday_fx"},
        },
    )
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before

    assert len(trades) == 3
    assert diagnostics["fills_total"] == 7
    assert diagnostics["unmatched_sell_qty"] == pytest.approx(2.0)
    assert diagnostics["open_lots_qty"] == pytest.approx(5.0)

    sp = [trade for trade in trades if trade.ticker == "SPY"]
    assert sp[0].qty == pytest.approx(10.0)
    assert sp[0].entry_price == pytest.approx(100.0)
    assert sp[0].exit_price == pytest.approx(120.0)
    assert sp[0].pnl == pytest.approx(198.0)
    assert sp[0].fees == pytest.approx(2.0)
    assert sp[0].return_pct == pytest.approx(0.198)
    assert sp[0].holding_hours == pytest.approx(48.0)
    assert sp[0].account == "paper_main"
    assert sp[0].profile == "swing_equity"
    assert sp[0].day == "2026-01-07"

    assert sp[1].qty == pytest.approx(5.0)
    assert sp[1].entry_price == pytest.approx(110.0)
    assert sp[1].pnl == pytest.approx(-101.0)
    assert sp[1].fees == pytest.approx(1.0)

    fx = next(trade for trade in trades if trade.ticker == "EURUSD")
    assert fx.pnl == pytest.approx(0.005)
    assert fx.account == "ftmo_demo"
    assert fx.profile == "intraday_fx"


def test_build_journal_filtros_y_agrupacion(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path)
    with connect(db) as con:
        _fill(con, bot="trend-spy", ticker="SPY", side="buy", qty=1, price=100.0,
              ts="2026-01-05T15:00:00+00:00")
        _fill(con, bot="trend-spy", ticker="SPY", side="sell", qty=1, price=110.0,
              ts="2026-01-06T15:00:00+00:00")
        _fill(con, bot="fx-bot", ticker="EURUSD", side="buy", qty=1, price=1.1,
              ts="2026-01-07T16:00:00+00:00")
        _fill(con, bot="fx-bot", ticker="EURUSD", side="sell", qty=1, price=1.12,
              ts="2026-01-08T16:00:00+00:00")

    specs = [
        BotSpec(id="trend-spy", type="deterministic", strategy="trend", universe=["SPY"],
                enabled=True, profile="swing_equity", account="paper_main"),
        BotSpec(id="fx-bot", type="deterministic", strategy="trend", universe=["EURUSD"],
                enabled=True, profile="intraday_fx", account="ftmo_demo"),
    ]
    monkeypatch.setattr(journal_mod, "load_bots", lambda: specs)

    payload = build_journal(db, tz="UTC", group_by="account")
    assert payload["read_only"] is True
    assert payload["total_trades"] == 2
    assert payload["filters_available"]["accounts"] == ["ftmo_demo", "paper_main"]
    accounts = {row["key"]: row for row in payload["by_account"]}
    assert accounts["paper_main"]["n"] == 1
    assert accounts["ftmo_demo"]["n"] == 1
    assert accounts["paper_main"]["total_return"] == pytest.approx(0.0001)
    assert accounts["ftmo_demo"]["total_return"] == pytest.approx(0.0000002)

    filtered = build_journal(db, tz="UTC", account="paper_main")
    assert filtered["total_trades"] == 1
    assert filtered["summary"]["n"] == 1
    assert filtered["summary"]["sample_ok"] is False
    assert "N=1" in filtered["summary"]["sample_warning"]

    by_ticker = build_journal(db, tz="UTC", ticker="eurusd")
    assert by_ticker["total_trades"] == 1

    since = build_journal(db, tz="UTC", since="2026-01-08")
    assert since["total_trades"] == 1
    with pytest.raises(ValueError):
        build_journal(db, tz="UTC", since="2026-13-01")
    with pytest.raises(ValueError):
        build_journal(db, tz="UTC", group_by="inventado")


def test_metricas_muestra_y_distribucion(tmp_path: Path) -> None:
    accounts = load_accounts()
    start = date(2026, 1, 5)
    trades = [
        _trade((start + timedelta(days=index)).isoformat(), 100.0 if index % 2 == 0 else -50.0)
        for index in range(35)
    ]
    summary = summarize(trades, accounts)
    assert summary["n"] == 35
    assert summary["sample_ok"] is True
    assert summary["sample_warning"] is None
    assert summary["net_pnl"] == pytest.approx(950.0)
    assert summary["win_rate"] == pytest.approx(18 / 35)
    assert summary["profit_factor"] == pytest.approx(1800 / 850)
    assert summary["expectancy"] == pytest.approx(950 / 35)
    assert summary["total_return"] == pytest.approx(0.0095)
    assert summary["sharpe"] is not None
    assert summary["sortino"] is not None
    assert summary["calmar"] is not None
    assert summary["sqn"] is not None
    assert summary["recovery_factor"] is not None
    assert summary["risk_of_ruin"] is not None
    assert summary["metrics_warning"] is None
    assert summary["max_drawdown"] is not None and summary["max_drawdown"] < 0
    assert summary["max_drawdown_usd"] is not None and summary["max_drawdown_usd"] < 0
    distribution = summary["distribution"]
    assert distribution["n"] == 35
    assert sum(bucket["count"] for bucket in distribution["histogram"]) == 35
    assert distribution["p5"] <= distribution["median"] <= distribution["p95"]
    concentration = summary["concentration"]
    assert concentration["top3_share"] == pytest.approx(300 / 950, abs=1e-6)
    assert concentration["top3_gross_share"] == pytest.approx(300 / 1800, abs=1e-6)
    assert concentration["best_day_share"] == pytest.approx(100 / 950, abs=1e-6)
    assert concentration["consistency_ok"] is None

    two = summarize(trades[:2], accounts)
    assert two["sample_ok"] is False
    assert "N=2" in two["sample_warning"]
    assert two["metrics_warning"] is not None
    assert "N=2" in two["metrics_warning"]


def test_concentracion_contra_regla_de_firma() -> None:
    funded = AccountDefinition(
        id="topstep_funded",
        name="Topstep",
        type="fondeo",
        broker="projectx",
        platform="projectx",
        status="demo",
        account_size=50_000.0,
        pocket="intraday_futures",
        firm="topstep",
        phase="challenge",
        defaults=load_accounts()["topstep_template"].defaults,
    )
    trades = [
        _trade("2026-01-05", 1_000.0, account="topstep_funded", profile="intraday_futures"),
        _trade("2026-01-06", -100.0, account="topstep_funded", profile="intraday_futures"),
        _trade("2026-01-07", 10.0, account="topstep_funded", profile="intraday_futures"),
    ]
    summary = summarize(trades, {"topstep_funded": funded})
    concentration = summary["concentration"]
    assert concentration["consistency_pct"] == pytest.approx(0.55)
    assert concentration["best_day_share"] == pytest.approx(1000 / 910)
    assert concentration["consistency_ok"] is False
    assert _concentration(trades, consistency_pct=None)["consistency_ok"] is None


def test_sin_cuenta_no_inventa_retorno(tmp_path: Path) -> None:
    trades = [_trade("2026-01-05", 50.0, bot="ghost", account=None, profile=None)]
    summary = summarize(trades, load_accounts())
    assert summary["capital"] is None
    assert summary["total_return"] is None
    assert summary["capital_missing"] == ["ghost"]
    assert summary["consistency_note"]


def test_filtro_sin_datos_y_fechas() -> None:
    trades = [
        _trade("2026-01-05", 10.0),
        _trade("2026-02-05", -5.0, account=None, profile=None),
    ]
    assert len(filter_trades(trades, account="sin datos")) == 1
    assert len(filter_trades(trades, since="2026-02-01")) == 1
    assert len(filter_trades(trades, until="2026-01-31")) == 1


def test_api_journal_responde(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path)
    with connect(db) as con:
        _fill(con, bot="trend-spy", ticker="SPY", side="buy", qty=1, price=100.0,
              ts="2026-01-05T15:00:00+00:00")
        _fill(con, bot="trend-spy", ticker="SPY", side="sell", qty=1, price=110.0,
              ts="2026-01-06T15:00:00+00:00")
    specs = [
        BotSpec(id="trend-spy", type="deterministic", strategy="trend", universe=["SPY"],
                enabled=True, profile="swing_equity", account="paper_main")
    ]
    monkeypatch.setattr(journal_mod, "load_bots", lambda: specs)
    data = web.LabData(Settings(), root=tmp_path, db_path=db, external=False)
    server = web.DashboardServer(("127.0.0.1", 0), data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base}/api/journal", timeout=5) as response:
            payload = json.load(response)
        assert payload["total_trades"] == 1
        assert payload["summary"]["net_pnl"] == pytest.approx(10.0)
        with urllib.request.urlopen(
            f"{base}/api/journal?account=paper_main&group_by=day", timeout=5
        ) as response:
            filtered = json.load(response)
        assert filtered["filters"]["group_by"] == "day"
        assert filtered["groups"][0]["key"] == "2026-01-06"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
