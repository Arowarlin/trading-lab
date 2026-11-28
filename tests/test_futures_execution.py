"""FUT-J1: OrderIntent y RiskCheck R01-R16 con los vectores V1-V16 de execution_spec.md §6."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tradinglab.config import ROOT
from tradinglab.futures.execution.intent import build_intent, load_execution_config
from tradinglab.futures.execution.paper import PaperAdapter
from tradinglab.futures.execution.riskcheck import AccountView, CheckContext, check, mll_threshold
from tradinglab.prop_economics.rules import load_program

PROGRAMS = ROOT / "config" / "prop_economics" / "programs"
CT = ZoneInfo("America/Chicago")
NY = ZoneInfo("America/New_York")
CFG = load_execution_config()
TOPSTEP = load_program(PROGRAMS / "topstep_50k_combine_xfa.yaml")
LUCID = load_program(PROGRAMS / "lucid_flex_50k.yaml")
MFF = load_program(PROGRAMS / "myfundedfutures_rapid_50k.yaml")
SYN = load_program(PROGRAMS / "synthetic_static.yaml")
NOW = datetime(2026, 12, 1, 10, 0, tzinfo=CT)


def intent(program=TOPSTEP, *, root="MNQ", qty=5, entry=21000.0, stop=20990.0, target=None, side="buy",
           phase="evaluation", origin="automated", adapter="paper", strategy="S1", account="A", exit_by=None,
           cfg=CFG):
    return build_intent(program=program, cfg=cfg, strategy_id=strategy, hypothesis_id="forward:test",
                        account_id=account, phase=phase, root=root, contract=f"{root}Z6", side=side, qty=qty,
                        entry_type="limit", entry_price=entry, stop_price=stop, target_price=target,
                        exit_by=exit_by or datetime(2026, 12, 1, 14, 0, tzinfo=CT), origin=origin, adapter=adapter,
                        signal_hash="h", created_at=NOW)


def acc(**kw) -> AccountView:
    base = dict(account_id="A", equity=50000.0, peak_eod=50000.0)
    base.update(kw)
    return AccountView(**base)


def ctx(**kw) -> CheckContext:
    base = dict(now=NOW, firm_category="allowed", policy_risk_usd=5000.0)
    base.update(kw)
    return CheckContext(**base)


def reasons(i, program=TOPSTEP, a=None, c=None, cfg=CFG):
    return check(i, program, a or acc(), c or ctx(), cfg).reasons


def test_v1_risk_mnq():
    i = intent()
    assert i.risk_usd == pytest.approx(111.10)
    assert i.cost_usd == pytest.approx(11.10)
    assert i.cost_assumed is False


def test_v2_risk_nq_and_micro_eq():
    i = intent(root="NQ", qty=1)
    assert i.risk_usd == pytest.approx(213.78)
    assert i.micro_eq == 10.0


@pytest.mark.parametrize("open_eq, root, qty, blocked", [
    (45, "MNQ", 10, True), (45, "MNQ", 5, False), (40, "MNQ", 10, False), (40, "MNQ", 11, True),
])
def test_v3_max_contracts(open_eq, root, qty, blocked):
    r = reasons(intent(root=root, qty=qty, stop=20999.0), a=acc(open_micro_eq=open_eq))
    assert ("max_contracts" in r) is blocked


@pytest.mark.parametrize("profit, qty, blocked", [(999, 20, False), (999, 21, True), (1000, 30, False),
                                                  (1000, 31, True), (2000, 40, False)])
def test_v4_lucid_scaling(profit, qty, blocked):
    i = intent(LUCID, qty=qty, stop=20999.0, phase="funded")
    a = acc(equity=50000.0 + profit, peak_eod=50000.0 + profit, profit_eod=profit)
    assert ("max_contracts" in reasons(i, LUCID, a)) is blocked


def test_v5_mll_room_topstep():
    a = acc(equity=50200.0, peak_eod=51500.0)
    assert mll_threshold(TOPSTEP, "evaluation", a) == 49500.0
    assert check(intent(qty=10, stop=20969.5), TOPSTEP, a, ctx(), CFG).metrics["mll_room"] == pytest.approx(630.0)
    assert "mll_room" in reasons(intent(qty=10, stop=20969.5), a=a)          # 10·(61 + 2,22) = 632,2 > 630
    assert "mll_room" not in reasons(intent(qty=10, stop=20970.0), a=a)      # 10·(60 + 2,22) = 622,2
    assert mll_threshold(TOPSTEP, "evaluation", acc(equity=50200.0, peak_eod=52500.0)) == 50000.0


def test_v6_mll_room_lucid_after_payout():
    a = acc(equity=50600.0, peak_eod=51000.0, payout_requested=True, profit_eod=600.0)
    assert mll_threshold(LUCID, "funded", a) == 50100.0
    assert "mll_room" in reasons(intent(LUCID, qty=10, stop=20978.0, phase="funded"), LUCID, a)      # 460 > 450
    assert "mll_room" not in reasons(intent(LUCID, qty=10, stop=20979.0, phase="funded"), LUCID, a)  # 440
    no_payout = acc(equity=50600.0, peak_eod=51000.0, profit_eod=600.0)
    assert mll_threshold(LUCID, "funded", no_payout) == 49000.0


@pytest.mark.parametrize("hh, mm, ss, blocked", [(15, 4, 59, False), (15, 5, 0, True)])
def test_v7_time_window(hh, mm, ss, blocked):
    now = datetime(2026, 12, 1, hh, mm, ss, tzinfo=CT)
    i = intent(exit_by=datetime(2026, 12, 1, 15, 9, tzinfo=CT))
    assert ("time_window" in reasons(i, c=ctx(now=now))) is blocked


@pytest.mark.parametrize("firm_cat, program, origin, adapter, ack, expected", [
    ("prohibited", SYN, "automated", "paper", [], "automation_prohibited"),
    ("prohibited", SYN, "semi_manual", "ticket", [], None),
    ("allowed", LUCID, "automated", "nt8", [], None),
    ("conditional", TOPSTEP, "automated", "nt8", ["topstep"], "platform_unsupported"),
    ("conditional", TOPSTEP, "automated", "projectx", [], "automation_conditions_not_acked"),
    ("conditional", TOPSTEP, "automated", "projectx", ["topstep"], None),
])
def test_v8_automation_and_platform(firm_cat, program, origin, adapter, ack, expected):
    cfg = {**CFG, "firm_conditions_ack": ack, "platform_support": {**CFG["platform_support"], "synthetic": ["ticket"]}}
    i = intent(program, origin=origin, adapter=adapter, cfg=cfg,
               exit_by=datetime(2026, 12, 1, 14, 0, tzinfo=NY if program is LUCID else CT))
    r = reasons(i, program, c=ctx(firm_category=firm_cat), cfg=cfg)
    auto_codes = {"automation_prohibited", "automation_conditions_not_acked", "platform_unsupported"}
    if expected is None:
        assert not (set(r) & auto_codes), r
    else:
        assert expected in r


def test_v9_no_martingale():
    i650 = intent(qty=10, stop=20970.0)        # 622,2 USD
    i500 = intent(qty=8, stop=20970.0)         # 497,76 USD
    c_loss = ctx(policy_risk_usd=500.0, last_trade=(497.76, -497.76))
    r = reasons(i650, c=c_loss)
    assert "risk_above_policy" in r and "risk_increase_after_loss" in r
    assert not {"risk_above_policy", "risk_increase_after_loss"} & set(reasons(i500, c=c_loss))
    r = reasons(i650, c=ctx(policy_risk_usd=500.0, last_trade=(497.76, 700.0)))
    assert "risk_above_policy" in r and "risk_increase_after_loss" not in r


@pytest.mark.parametrize("day, expired", [(26, False), (27, True)])
def test_v10_rules_expiry(day, expired):
    now = datetime(2026, 12, day, 10, 0, tzinfo=CT)
    i = intent(exit_by=datetime(2026, 12, day, 14, 0, tzinfo=CT))
    assert ("rules_expired" in reasons(i, c=ctx(now=now))) is expired


def test_v11_news_calendar_required_in_mff_funded():
    exit_ny = datetime(2026, 12, 1, 14, 0, tzinfo=NY)
    funded = intent(MFF, phase="funded", exit_by=exit_ny)
    assert "sin_datos_calendario" in reasons(funded, MFF, acc(profit_eod=0.0))
    ev = intent(MFF, phase="evaluation", exit_by=exit_ny)
    assert "sin_datos_calendario" not in reasons(ev, MFF)
    event = datetime(2026, 12, 1, 11, 1, tzinfo=CT)
    assert "news_window" in reasons(funded, MFF, acc(), ctx(news_events=[event]))


def test_v12_duplicate_exposure():
    c = ctx(open_keys=frozenset({("S1", "A", "MNQ")}))
    assert "duplicate_exposure" in reasons(intent(), c=c)
    assert "duplicate_exposure" not in reasons(intent(account="B"), c=c)
    assert "global_underlying_limit" in reasons(intent(account="B"), c=ctx(underlying_micro_eq={"NASDAQ100": 98.0}))


def test_v13_live_always_blocked():
    assert "live_blocked" in reasons(intent(), c=ctx(endpoint_is_live=True))


@pytest.mark.parametrize("root, entry, stop, bad", [
    ("MNQ", 21000.10, 20990.0, True), ("MGC", 2660.0, 2650.05, True), ("MGC", 2660.0, 2650.10, False),
])
def test_v14_tick_alignment(root, entry, stop, bad):
    i = intent(root=root, entry=entry, stop=stop, qty=1)
    assert ("tick_misaligned" in reasons(i)) is bad


def test_v15_unknown_commission():
    paper = intent(SYN, adapter="paper")
    assert paper.cost_assumed is True
    assert paper.cost_usd == pytest.approx(5 * (1.5 + 1.0))
    assert "cost_unknown" not in reasons(paper, SYN)
    real = intent(SYN, adapter="projectx")
    assert "cost_unknown" in reasons(real, SYN)


def test_v16_stop_side():
    assert "stop_side" in reasons(intent(stop=21010.0))
    assert "stop_side" in reasons(intent(side="sell", stop=20990.0))


def test_topstep_funded_fails_closed_without_scaling_plan():
    i = intent(phase="funded")
    assert "rules_unknown:max_contracts" in reasons(i)


def test_paper_adapter_only_accepts_ok():
    adapter = PaperAdapter()
    i = intent()
    ok = check(i, TOPSTEP, acc(), ctx(), CFG)
    assert ok.ok, ok.reasons
    assert adapter.submit(i, ok).status == "accepted_paper"
    bad = check(i, TOPSTEP, acc(), ctx(endpoint_is_live=True), CFG)
    assert adapter.submit(i, bad).status == "rejected"


@settings(max_examples=500, deadline=None)
@given(st.sampled_from(["MNQ", "NQ", "MES", "ES"]), st.integers(1, 30), st.integers(1, 200), st.floats(0, 60))
def test_property_risk_and_contract_cap(root, qty, stop_ticks, open_eq):
    i = intent(root=root, qty=qty, entry=5000.0, stop=5000.0 - stop_ticks * 0.25)
    if root in ("MES", "ES"):
        assert "cost_unknown" in check(i, TOPSTEP, acc(), ctx(), CFG).reasons   # sin comisión ni dato del laboratorio
        return
    assert i.risk_usd >= i.cost_usd > 0
    res = check(i, TOPSTEP, acc(open_micro_eq=open_eq), ctx(), CFG)
    if open_eq + i.micro_eq > 50 + 1e-9:
        assert "max_contracts" in res.reasons
