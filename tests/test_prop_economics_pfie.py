"""FUT-P1 (registro), FUT-P3 (compatibilidad) y FUT-P4 (ranking ponderado con evidencia)."""

from __future__ import annotations

from datetime import date, time

import pytest

from tradinglab.futures.execution.intent import load_execution_config
from tradinglab.prop_economics.compat import StrategyProfile, verdict
from tradinglab.prop_economics.registry import load_firms, load_programs, registry_report
from tradinglab.prop_economics.scoring import score_firms

FIRMS = load_firms()
PROGRAMS = load_programs()
SUPPORT = load_execution_config()["platform_support"]


def test_registry_report():
    rep = registry_report(date(2026, 12, 1))
    assert rep["programs_by_firm"]["topstep"] == ["topstep_50k_combine_xfa"]
    assert rep["programs_by_firm"]["lucid"] == ["lucid_flex_50k"]
    assert rep["unknown_firm_programs"] == [] and rep["expired"] == []
    assert "apex" in rep["firms_without_program"]
    assert registry_report(date(2026, 12, 27))["expired"] == sorted(
        ["lucid_flex_50k", "myfundedfutures_rapid_50k", "topstep_50k_combine_xfa"])
    assert len(FIRMS) == 10


def test_scoring_reproduces_report():
    s = score_firms()
    ranked = [(r["firm"], r["total"]) for r in s["ranking"]]
    assert ranked == [("myfundedfutures", pytest.approx(3.55)), ("tradeify", pytest.approx(3.45)),
                      ("tradeday", pytest.approx(3.00)), ("topstep", pytest.approx(2.85)),
                      ("alphafutures", pytest.approx(2.80))]
    nr = {r["firm"]: r for r in s["not_ranked"]}
    assert nr["lucid"]["partial"] == pytest.approx(3.70) and nr["lucid"]["provisional"] == pytest.approx(3.70 / 0.9)
    assert nr["bulenox"]["partial"] == pytest.approx(2.45) and nr["bulenox"]["provisional"] == pytest.approx(2.45 / 0.8)
    assert nr["apex"]["provisional"] is None and nr["lucid"]["missing"] == ["costs"]


def profile(**kw) -> StrategyProfile:
    base = dict(automated=True, platform="nt8", root="MNQ", max_micro_eq=10, median_hold_s=600,
                last_exit_local=time(15, 0), trades_news=False)
    base.update(kw)
    return StrategyProfile(**base)


def test_compat_lucid_automated_nt8_is_compatible():
    v, why = verdict(FIRMS["lucid"], PROGRAMS["lucid_flex_50k"], profile(), SUPPORT)
    assert (v, why) == ("compatible", [])


def test_compat_reasons_cite_rules():
    v, why = verdict(FIRMS["lucid"], PROGRAMS["lucid_flex_50k"], profile(median_hold_s=12, max_micro_eq=45), SUPPORT)
    assert v == "incompatible"
    assert any("microscalping" in w for w in why) and any("máximo 40" in w for w in why)
    v, why = verdict(FIRMS["topstep"], PROGRAMS["topstep_50k_combine_xfa"], profile(), SUPPORT)
    assert v == "incompatible" and any("plataforma nt8" in w for w in why)
    v, why = verdict(FIRMS["topstep"], PROGRAMS["topstep_50k_combine_xfa"], profile(platform="projectx"), SUPPORT)
    assert v == "con_condiciones" and any("condicional" in w for w in why)


def test_compat_silence_is_not_permission_and_semi_manual_works():
    alpha = FIRMS["alphafutures"]
    prog = PROGRAMS["lucid_flex_50k"]          # cualquier programa: el veredicto lo decide la firma
    v, why = verdict(alpha, prog, profile(platform="ticket"), SUPPORT)
    assert v == "incompatible" and any("automatización prohibited" in w for w in why)
    v, _ = verdict(alpha, prog, profile(automated=False, platform="ticket"), SUPPORT)
    assert v == "compatible"


def test_compat_flat_time_and_news():
    v, why = verdict(FIRMS["myfundedfutures"], PROGRAMS["myfundedfutures_rapid_50k"],
                     profile(last_exit_local=time(16, 30), trades_news=True), SUPPORT)
    assert v == "incompatible" and any("cierre obligatorio" in w for w in why) and any("noticias" in w for w in why)
