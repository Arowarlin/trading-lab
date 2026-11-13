from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from tradinglab.ai_trader import (
    _noplan_side,
    _reset_date,
    _shadow_sim,
    _twin_levels,
    create_plan,
    panel,
    scoreboard,
    session_activity,
)
from tradinglab.config import get_settings
from tradinglab.db import connect, init_db


class _Broker:
    def positions(self):
        return []


def _trade(db, i: int, *, r: float = 0.5, shadow: float | None = 0.2,
           noplan: float | None = 0.1, style: str = "scalping",
           strategy: str = "orb_5m", symbol: str = "US100.cash",
           timeframe: str = "M5", source: str = "forward",
           status: str = "closed", ticket: int | None = None,
           risk_usd: float = 100.0, pnl: float | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, style, symbol, setup, side, "
            "timeframe, status, source, ticket, result_r, shadow_r, shadow2_r, "
            "cost_ratio, risk_usd, pnl, exit_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"p{i}", now, style, symbol, strategy, "buy", timeframe,
                status, source, ticket, r, shadow, noplan, 0.02, risk_usd,
                pnl if pnl is not None else (r * risk_usd if r is not None else None),
                now,
            ),
        )


def test_sombra_determinista_y_sin_plan():
    first = _twin_levels(100.0, 99.0, 102.0, seed=7)
    second = _twin_levels(100.0, 99.0, 102.0, seed=7)
    assert first == second
    assert first["side"] in {"buy", "sell"}
    assert _noplan_side("scalping", "buy") == "sell"
    assert _noplan_side("scalping", "sell") == "buy"
    assert _noplan_side("intraday", "buy") is None
    opposite = _twin_levels(100.0, 99.0, 102.0, seed=7, side="sell")
    assert opposite["side"] == "sell"
    assert opposite["sl"] == pytest.approx(101.0)
    assert opposite["tp"] == pytest.approx(98.0)


def test_sombra_sin_tp_no_es_sin_datos():
    index = pd.date_range("2026-01-01", periods=30, freq="1D", tz="UTC")
    close = pd.Series([100.0 + i for i in range(30)], index=index)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
        },
        index=index,
    )
    row = {
        "shadow_side": "buy", "shadow_entry": 100.0,
        "shadow_sl": 90.0, "shadow_tp": None,
        "setup": "donchian_turtle",
    }
    result = _shadow_sim(row, bars)
    assert result["status"] in {"open", "closed"}
    assert result["r"] is not None


def test_scoreboard_ganadora_y_diferencias(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    for i in range(30):
        _trade(db, i)
    board = scoreboard(broker=_Broker(), db_path=db)
    assert len(board["cells"]) == 1
    cell = board["cells"][0]
    assert cell["n"] == 30
    assert cell["state"] == "winner"
    assert cell["ci90_r"] == [0.5, 0.5]
    assert cell["avg_r"] == pytest.approx(0.5)
    assert cell["hit"] == pytest.approx(1.0)
    assert cell["shadow"]["diff"] == pytest.approx(0.3)
    assert cell["noplan"]["diff"] == pytest.approx(0.4)
    assert cell["cell_status"] == "active"


def test_scoreboard_perdedora_pausa_y_explorando(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    for i in range(30):
        _trade(db, i, r=-0.5, shadow=-0.2, noplan=-0.1)
    board = scoreboard(broker=_Broker(), db_path=db)
    cell = board["cells"][0]
    assert cell["state"] == "loser"
    assert cell["cell_status"] == "active"

    db2 = tmp_path / "lab2.db"
    init_db(db2)
    for i in range(10):
        _trade(db2, i)
    board2 = scoreboard(broker=_Broker(), db_path=db2)
    cell2 = board2["cells"][0]
    assert cell2["state"] == "exploring"
    assert cell2["insufficient"] is True


def test_scoreboard_neutral_y_slippage(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    for i in range(30):
        _trade(db, i, r=0.5 if i % 2 else -0.5, shadow=0.0, noplan=0.0)
    now = datetime.now(timezone.utc).isoformat()
    with connect(db) as con:
        con.execute(
            "INSERT INTO tca(bot, symbol, slippage_bps, ts_utc) "
            "VALUES('ai:scalping','US100.cash',2.0,?)",
            (now,),
        )
    board = scoreboard(broker=_Broker(), db_path=db)
    cell = board["cells"][0]
    assert cell["state"] == "neutral"
    assert cell["slippage_avg"] == pytest.approx(2.0)
    assert cell["slippage_n"] == 1


def test_scoreboard_excluye_replay(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    for i in range(30):
        _trade(db, i, r=-10.0, source="replay")
    board = scoreboard(broker=_Broker(), db_path=db)
    assert board["trades"] == []
    assert board["cells"] == []


def test_panel_presupuesto_posiciones_y_plan(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    _trade(db, 1, r=0.5, pnl=50.0)
    _trade(
        db, 2, r=None, status="open", style="intraday", strategy="ema_pullback",
        symbol="EURUSD", timeframe="H1", ticket=42, risk_usd=250.0, pnl=None,
        shadow=None, noplan=None,
    )
    cfg = get_settings()
    create_plan(
        {
            "symbol": "US100.cash",
            "setups": ["orb_5m"],
            "bias": "both",
            "forbidden_hours": [],
            "reason": "plan de prueba",
        },
        settings=cfg,
        db_path=db,
    )
    data = panel(db, equity=100_000.0)
    assert data["budget"]["equity"] == pytest.approx(100_000.0)
    assert data["budget"]["global"]["limit_usd"] == pytest.approx(3_000.0)
    assert data["budget"]["styles"]["intraday"]["open_risk_usd"] == pytest.approx(250.0)
    assert data["open_by_style"]["intraday"][0]["ticket"] == 42
    assert data["cells"][0]["state"] == "exploring"
    assert data["cells"][0]["n"] == 1
    assert data["plans"][0]["symbol"] == "US100.cash"
    assert data["closed"]["n"] == 1


def test_session_activity_avisa_sesion_sin_filas(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    settings = get_settings()
    session_date = _reset_date(settings)
    now = datetime.now(timezone.utc).isoformat()
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_decisions(ts, decision_date, session, style, symbol, "
            "timeframe, strategy, setup_valid, decision, reason, source) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (now, session_date, "Londres", "intraday", "EURUSD", "H1",
             "ema_pullback", 0, "skip", "sin setup", "forward"),
        )
    activity = session_activity(
        db, settings=settings,
        now=datetime(2026, 11, 12, 13, 30, tzinfo=timezone.utc),
    )
    assert activity["london"] is True
    assert not any("Londres" in warning for warning in activity["warnings"])
    late = session_activity(
        db, settings=settings,
        now=datetime(2026, 11, 12, 21, 30, tzinfo=timezone.utc),
    )
    assert any("Nueva York sin filas" in warning for warning in late["warnings"])
    assert any("swing/daily sin filas" in warning for warning in late["warnings"])

def test_sombra_con_una_sola_vela_no_es_sin_datos():
    index = pd.DatetimeIndex(["2026-11-13T14:49:00Z"])
    bars = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5]},
        index=index,
    )
    row = {
        "shadow_side": "buy", "shadow_entry": 100.0,
        "shadow_sl": 98.0, "shadow_tp": 102.0, "setup": "orb_5m",
    }
    result = _shadow_sim(row, bars)
    assert result["r"] is not None
    assert result["status"] in {"open", "closed"}
