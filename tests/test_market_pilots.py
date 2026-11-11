from __future__ import annotations

from pathlib import Path

import pytest

from tradinglab.accounts import load_accounts
from tradinglab.f13 import config_hash
from tradinglab.market_pilots import (
    PilotError,
    PilotSpec,
    active_market,
    allows_market,
    clear_pilots,
    init_pilots,
    load_pilots,
    market_for_account,
    market_for_bot,
    pilot_status,
    select_pilot,
)
from tradinglab.orchestrator import BotSpec, load_bots


def test_pilotos_iniciales_y_bloqueos(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_pilots(db)
    status = pilot_status(db)
    assert status["active_market"] is None
    assert status["count"] == 3
    rows = {row["market"]: row for row in status["pilots"]}
    assert rows["equity"]["bot"] == "qqq-trend-f13"
    assert rows["equity"]["status"] == "paper"
    assert rows["forex"]["bot"] == "eurusd-london-pullback-forward"
    assert rows["forex"]["status"] == "paper"
    # Futuros sigue bloqueado por ProjectX (sin credenciales): no se selecciona.
    assert rows["futures"]["status"] == "blocked"
    with pytest.raises(PilotError):
        select_pilot(db, "equity", confirm=False)
    with pytest.raises(PilotError):
        select_pilot(db, "futures", confirm=True)


def test_un_mercado_a_la_vez_y_limpieza(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_pilots(db)
    select_pilot(db, "equity", confirm=True)
    assert active_market(db) == "equity"
    assert allows_market(db, "equity")[0] is True
    assert allows_market(db, "forex")[0] is False
    specs = dict(load_pilots())
    specs["forex"] = PilotSpec(
        market="forex",
        label="Forex",
        bot=None,
        profile="intraday_fx",
        status="not_started",
        reason="test",
    )
    select_pilot(db, "forex", confirm=True, specs=specs)
    assert active_market(db) == "forex"
    status = pilot_status(db)
    assert sum(1 for row in status["pilots"] if row["active"]) == 1
    assert next(row for row in status["pilots"] if row["market"] == "equity")["active"] is False
    with pytest.raises(PilotError):
        clear_pilots(db, confirm=False)
    clear_pilots(db, confirm=True)
    assert active_market(db) is None


def test_clase_por_bot_y_cuenta() -> None:
    spec = BotSpec(
        id="trend-spy",
        type="deterministic",
        strategy="trend",
        universe=["SPY"],
        enabled=True,
        profile="swing_equity",
        account="paper_main",
    )
    assert market_for_bot(spec) == "equity"
    spec2 = BotSpec(
        id="fx",
        type="deterministic",
        strategy="trend",
        universe=["EURUSD"],
        enabled=True,
        profile="intraday_fx",
    )
    assert market_for_bot(spec2) == "forex"
    accounts = load_accounts()
    assert market_for_account(accounts["paper_main"]) == "equity"
    assert market_for_account(accounts["ftmo_demo"]) == "forex"
    assert market_for_account(accounts["topstep_template"]) == "futures"


def test_piloto_no_cambia_bots_ni_hash_f13(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_pilots(db)
    before_hash = config_hash()
    before_bots = {bot.id: bot.enabled for bot in load_bots()}
    select_pilot(db, "equity", confirm=True)
    after_bots = {bot.id: bot.enabled for bot in load_bots()}
    assert before_hash == config_hash()
    assert before_bots == after_bots
