"""FUT-J4: puente por ficheros con NinjaTrader 8 (lado Python; la NinjaScript no se compila aquí)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tradinglab.config import ROOT
from tradinglab.futures.execution.intent import build_intent, load_execution_config
from tradinglab.futures.execution.nt8_bridge import NT8Bridge
from tradinglab.futures.execution.riskcheck import AccountView, CheckContext, check
from tradinglab.prop_economics.rules import load_program

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 12, 1, 10, 0, tzinfo=NY)
CFG = load_execution_config()
LUCID = load_program(ROOT / "config" / "prop_economics" / "programs" / "lucid_flex_50k.yaml")


def make(qty=3, stop=20990.0):
    i = build_intent(program=LUCID, cfg=CFG, strategy_id="S1", hypothesis_id="forward:t", account_id="A",
                     phase="evaluation", root="MNQ", contract="MNQZ6", side="buy", qty=qty, entry_type="market",
                     entry_price=21000.0, stop_price=stop, target_price=21015.0,
                     exit_by=datetime(2026, 12, 1, 15, 0, tzinfo=NY), origin="automated", adapter="nt8",
                     signal_hash="h", created_at=NOW)
    return i, check(i, LUCID, AccountView("A", 50000.0, 50000.0),
                    CheckContext(now=NOW, firm_category="allowed", policy_risk_usd=500.0), CFG)


def test_rejects_non_sim_accounts(tmp_path):
    with pytest.raises(ValueError):
        NT8Bridge(tmp_path, nt_account="Lucid-12345", max_contracts=5)


def test_writes_atomic_outbox_and_reads_ack(tmp_path):
    bridge = NT8Bridge(tmp_path, nt_account="Sim101", max_contracts=5)
    i, res = make()
    assert res.ok, res.reasons
    assert bridge.submit(i, res).status == "queued_nt8"
    files = list((tmp_path / "outbox").glob("*.json"))
    assert [f.name for f in files] == [f"{i.intent_id}.json"]
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert (payload["nt_account"], payload["qty"], payload["stop_price"]) == ("Sim101", 3, 20990.0)
    assert not list((tmp_path / "outbox").glob("*.tmp"))
    assert bridge.read_ack(i.intent_id) is None
    (tmp_path / "inbox" / f"{i.intent_id}.ack.json").write_text('{"status": "submitted_sim"}', encoding="utf-8")
    assert bridge.read_ack(i.intent_id) == {"status": "submitted_sim"}


def test_bridge_limits_and_rejections(tmp_path):
    bridge = NT8Bridge(tmp_path, nt_account="Playback101", max_contracts=2)
    i, res = make(qty=3)
    assert bridge.submit(i, res).reasons == ("bridge_max_contracts",)
    i, res = make(stop=21010.0)
    assert bridge.submit(i, res).status == "rejected"
    assert not list((tmp_path / "outbox").glob("*.json"))


def test_ninjascript_guards_present():
    cs = (Path(ROOT) / "integrations" / "nt8" / "TradingLabBridge.cs").read_text(encoding="utf-8")
    assert "NO COMPILADO" in cs and "IsUnmanaged = true" in cs
    assert 'StartsWith("Sim")' in cs and 'StartsWith("Playback")' in cs and "MaxContracts" in cs
