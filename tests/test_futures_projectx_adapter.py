"""FUT-J3: envoltorio dry-run de ProjectX (sin red; cliente doble)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tradinglab.config import ROOT
from tradinglab.futures.execution.intent import build_intent, load_execution_config
from tradinglab.futures.execution.projectx_adapter import LiveBlockedError, ProjectXAdapter
from tradinglab.futures.execution.riskcheck import AccountView, CheckContext, check
from tradinglab.prop_economics.rules import load_program

CT = ZoneInfo("America/Chicago")
NOW = datetime(2026, 12, 1, 10, 0, tzinfo=CT)
CFG = {**load_execution_config(), "firm_conditions_ack": ["topstep"]}
TOPSTEP = load_program(ROOT / "config" / "prop_economics" / "programs" / "topstep_50k_combine_xfa.yaml")


class FakeClient:
    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.calls = []

    def place_order(self, contract_id, side, size, **kw):
        self.calls.append((contract_id, side, size, kw))
        return {"order_id": None, "status": "preview", "dry_run": self.dry_run}


def make(stop=20990.0, target=21015.0, adapter="projectx"):
    i = build_intent(program=TOPSTEP, cfg=CFG, strategy_id="S1", hypothesis_id="forward:t", account_id="A",
                     phase="evaluation", root="MNQ", contract="MNQZ6", side="buy", qty=3, entry_type="limit",
                     entry_price=21000.0, stop_price=stop, target_price=target,
                     exit_by=datetime(2026, 12, 1, 14, 0, tzinfo=CT), origin="automated", adapter=adapter,
                     signal_hash="h", created_at=NOW)
    res = check(i, TOPSTEP, AccountView("A", 50000.0, 50000.0),
                CheckContext(now=NOW, firm_category="conditional", policy_risk_usd=500.0), CFG)
    return i, res


def test_dry_run_translates_brackets():
    i, res = make()
    assert res.ok, res.reasons
    client = FakeClient()
    ack = ProjectXAdapter(client).submit(i, res, contract_id="CON.F.US.MNQ.Z26")
    assert ack.status == "preview"
    (cid, side, size, kw), = client.calls
    assert (cid, side, size) == ("CON.F.US.MNQ.Z26", "buy", 3)
    assert (kw["stop_loss_ticks"], kw["take_profit_ticks"], kw["limit_price"]) == (40, 60, 21000.0)
    assert kw["custom_tag"] == i.intent_id[:64] and kw["bot"] == "S1"


def test_live_client_is_blocked():
    i, res = make()
    with pytest.raises(LiveBlockedError):
        ProjectXAdapter(FakeClient(dry_run=False)).submit(i, res, contract_id="X")


def test_bracket_minimum_and_rejections():
    i, res = make(stop=20999.5)                    # 2 ticks < 4
    assert res.ok
    assert ProjectXAdapter(FakeClient()).submit(i, res, contract_id="X").reasons == ("bracket_too_close",)
    i, res = make(stop=21010.0)                    # stop al lado equivocado: el control lo rechaza
    client = FakeClient()
    assert ProjectXAdapter(client).submit(i, res, contract_id="X").status == "rejected" and client.calls == []
    i, res = make(adapter="paper")
    assert ProjectXAdapter(FakeClient()).submit(i, res, contract_id="X").reasons == ("wrong_adapter",)
