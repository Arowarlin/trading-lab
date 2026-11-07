from __future__ import annotations

from pathlib import Path

import pytest

from tradinglab import web
from tradinglab.accounts import add_cash_flow, cash_flows, load_accounts
from tradinglab.config import FundHealthSettings, Settings
from tradinglab.db import connect, init_db
from tradinglab.health import score_account, time_weighted_return
from tradinglab.journal import ClosedTrade


def _trade(day: str, pnl: float, index: int = 1) -> ClosedTrade:
    stamp = f"{day}T15:00:00+00:00"
    return ClosedTrade(
        bot="trend-spy",
        account="paper_main",
        profile="swing_equity",
        ticker="SPY",
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
        hour=15,
        entry_order_id=index,
        exit_order_id=index + 1,
        exit_fill_id=index + 2,
    )


def test_health_score_desglose_y_cobertura() -> None:
    cfg = FundHealthSettings()
    usage = {"daily_used_pct": 0.10, "drawdown_used_pct": 0.20}
    trades = [
        _trade("2026-01-05", 100.0, 1),
        _trade("2026-01-06", -20.0, 2),
        _trade("2026-01-07", -30.0, 3),
        _trade("2026-01-08", -40.0, 4),
    ]
    result = score_account(
        usage=usage,
        trades=trades,
        drift_statuses=["ok", "vigilar"],
        cfg=cfg,
    )
    assert result["score"] is not None
    assert 0 <= result["score"] <= 100
    assert result["coverage"] == pytest.approx(1.0)
    assert result["partial"] is False
    assert set(result["components"]) == {
        "daily_cushion",
        "drawdown_cushion",
        "streak",
        "drift",
        "concentration",
    }
    assert result["components"]["daily_cushion"]["score"] == pytest.approx(90.0)
    assert result["components"]["drawdown_cushion"]["score"] == pytest.approx(80.0)
    assert result["components"]["streak"]["score"] == pytest.approx(40.0)
    assert result["components"]["drift"]["score"] == pytest.approx(50.0)
    assert result["components"]["concentration"]["score"] is not None
    assert "top3/neto" in result["components"]["concentration"]["detail"]


def test_health_sin_datos_es_parcial() -> None:
    result = score_account(
        usage={},
        trades=[],
        drift_statuses=[],
        cfg=FundHealthSettings(),
    )
    assert result["score"] is None
    assert result["label"] == "Sin datos"
    assert result["coverage"] == pytest.approx(0.0)


def test_twr_descuenta_deposito_y_retiro() -> None:
    deposit = time_weighted_return(
        [
            {"ts": "2026-01-01T20:00:00+00:00", "equity": 100_000.0},
            {"ts": "2026-01-02T20:00:00+00:00", "equity": 160_000.0},
        ],
        [{"ts": "2026-01-02T20:00:00+00:00", "kind": "deposit", "amount": 50_000.0}],
    )
    assert deposit["twr"] == pytest.approx(0.10)
    withdrawal = time_weighted_return(
        [
            {"ts": "2026-01-01T20:00:00+00:00", "equity": 100_000.0},
            {"ts": "2026-01-02T20:00:00+00:00", "equity": 90_000.0},
        ],
        [{"ts": "2026-01-02T20:00:00+00:00", "kind": "withdrawal", "amount": 10_000.0}],
    )
    assert withdrawal["twr"] == pytest.approx(0.0)
    no_flow = time_weighted_return(
        [
            {"ts": "2026-01-01T20:00:00+00:00", "equity": 100_000.0},
            {"ts": "2026-01-02T20:00:00+00:00", "equity": 110_000.0},
        ],
        [],
    )
    assert no_flow["twr"] == pytest.approx(0.10)


def test_cash_flows_validacion_y_listado(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    flow = add_cash_flow(
        db,
        account_id="paper_main",
        kind="deposit",
        amount=1_000.0,
        ts="2026-01-02T10:00:00+00:00",
        note="test",
        accounts=load_accounts(),
    )
    assert flow["amount"] == pytest.approx(1_000.0)
    rows = cash_flows(db, "paper_main")
    assert len(rows) == 1
    assert rows[0]["kind"] == "deposit"
    with pytest.raises(ValueError):
        add_cash_flow(
            db,
            account_id="paper_main",
            kind="transfer",
            amount=100,
            accounts=load_accounts(),
        )
    with pytest.raises(ValueError):
        add_cash_flow(
            db,
            account_id="paper_main",
            kind="deposit",
            amount=-5,
            accounts=load_accounts(),
        )


def test_fund_incluye_salud_flujos_y_twr(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO equity(ts, cash, positions_value, equity) VALUES(?,?,?,?)",
            ("2026-01-01T20:00:00+00:00", 100_000.0, 0.0, 100_000.0),
        )
        con.execute(
            "INSERT INTO equity(ts, cash, positions_value, equity) VALUES(?,?,?,?)",
            ("2026-01-02T20:00:00+00:00", 110_000.0, 0.0, 110_000.0),
        )
    add_cash_flow(
        db,
        account_id="paper_main",
        kind="deposit",
        amount=5_000.0,
        ts="2026-01-02T20:00:00+00:00",
        accounts=load_accounts(),
    )
    data = web.LabData(
        Settings(), root=tmp_path, db_path=db, external=False
    )
    payload = data.fund()
    paper = next(row for row in payload["accounts"] if row["id"] == "paper_main")
    assert paper["cash_flows"]
    assert paper["cash_flow_net"] == pytest.approx(5_000.0)
    assert paper["health"]["score"] is not None
    assert paper["health"]["partial"] is True
    assert paper["twr"]["twr"] == pytest.approx((110_000 - 5_000) / 100_000 - 1)
    assert payload["fund_return"]["twr"] == pytest.approx(0.05)
    assert payload["fund_return"]["coverage"] > 0
    assert payload["health"]["score"] is not None
