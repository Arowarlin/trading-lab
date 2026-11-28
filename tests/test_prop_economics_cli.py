"""FUT-A8: pools, informe y sub-app ``lab propecon`` (CLI sin red)."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pytest
from typer.testing import CliRunner

from tradinglab.config import ROOT
from tradinglab.prop_economics.cli import app
from tradinglab.prop_economics.paths import TradeSpec, from_trades
from tradinglab.prop_economics.pools import dump_pool, load_pool, synthetic_pool
from tradinglab.prop_economics.project import ProjectConfig, simulate_project
from tradinglab.prop_economics.report import build_report, pool_hash, to_markdown
from tradinglab.prop_economics.rules import load_program

runner = CliRunner()


def test_pool_roundtrip(tmp_path):
    pool = [from_trades(date(2027, 1, 4), [TradeSpec(100, 150, 40, 2.5)], risk_usd=50.0, source="forward"),
            from_trades(date(2027, 1, 5), [], source="forward")]
    dump_pool(pool, tmp_path / "p.jsonl")
    back = load_pool(tmp_path / "p.jsonl")
    assert [d.marks.tolist() for d in back] == [d.marks.tolist() for d in pool]
    assert pool_hash(back) == pool_hash(pool)


def test_synthetic_pool_win_rate_and_labels():
    pool = synthetic_pool(mu_gross_r=0.13, rr=1.5, risk_usd=50.0, cost_rt=2.22, n_days=4000, seed=3)
    wins = np.mean([d.marks[-1] > 0 for d in pool])
    assert abs(wins - 1.13 / 2.5) < 0.025
    assert {d.source for d in pool} == {"synthetic"}
    assert all(d.marks[-1] in (75.0 - 2.22, -50.0 - 2.22) for d in pool)
    with pytest.raises(ValueError):
        synthetic_pool(mu_gross_r=2.0, rr=1.5, risk_usd=50.0, cost_rt=2.22, n_days=10, seed=1)


def test_report_flags_hypothetical():
    prog = load_program(ROOT / "config" / "prop_economics" / "programs" / "topstep_50k_combine_xfa.yaml")
    pool = synthetic_pool(mu_gross_r=0.13, rr=1.5, risk_usd=50.0, cost_rt=2.22, n_days=200, seed=1)
    cfg = ProjectConfig(contracts_eval=10, contracts_funded=10, budget=1500.0, start_date=date(2027, 1, 4),
                        horizons_days=(90,), assume_processing_days=3)
    res = simulate_project(prog, pool, cfg, n_paths=300, seed=1, mean_block=1.0)
    rep = build_report(prog, pool, cfg, res, n_paths=300, seed=1, today=date(2026, 12, 1))
    assert rep["data"]["hypothetical"] is True
    assert rep["program"]["expired"] is False
    md = to_markdown(rep)
    assert "HIPOTÉTICO" in md and "| 90 |" in md


def test_cli_programs_lists_three():
    r = runner.invoke(app, ["programs", "--today", "2026-12-01"])
    assert r.exit_code == 0, r.output
    for pid in ("topstep_50k_combine_xfa", "lucid_flex_50k", "myfundedfutures_rapid_50k"):
        assert pid in r.output


def test_cli_simulate_synthetic(tmp_path):
    out = tmp_path / "rep.json"
    r = runner.invoke(app, ["simulate", "--program", "topstep_50k_combine_xfa", "--synthetic-mu", "0.13",
                            "--days", "200", "--paths", "400", "--seed", "2", "--mean-block", "1",
                            "--assume-processing-days", "3", "--horizons", "30,90", "--out", str(out)])
    assert r.exit_code == 0, r.output
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["data"]["hypothetical"] is True
    assert set(rep["horizons"]) == {"30", "90"}
    assert rep["config"]["assume_processing_days"] == 3


def test_cli_simulate_requires_assumption_for_unknown_price(tmp_path):
    r = runner.invoke(app, ["simulate", "--program", "lucid_flex_50k", "--synthetic-mu", "0.13", "--days", "50",
                            "--paths", "50", "--horizons", "30"])
    assert r.exit_code != 0
    r = runner.invoke(app, ["simulate", "--program", "lucid_flex_50k", "--synthetic-mu", "0.13", "--days", "50",
                            "--paths", "50", "--horizons", "30", "--mean-block", "1",
                            "--assume", "fees.evaluation=125", "--out", str(tmp_path / "l.md")])
    assert r.exit_code == 0, r.output


def test_cli_ledger_roundtrip(tmp_path):
    db = tmp_path / "ledger.db"
    assert runner.invoke(app, ["ledger", "summary", "--db", str(db)]).output.strip().startswith("Sin datos")
    r = runner.invoke(app, ["ledger", "add-account", "A1", "--firm", "topstep", "--program", "topstep_50k_combine_xfa",
                            "--rules-version", "2026-11-27.1", "--origin", "semi_manual", "--opened-at", "2027-01-02",
                            "--db", str(db)])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["ledger", "add", "A1", "fee_paid", "--amount-usd", "-49", "--ts", "2027-01-02",
                            "--db", str(db)])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["ledger", "summary", "--today", "2027-01-03", "--db", str(db)])
    assert r.exit_code == 0 and '"net_real": -49.0' in r.output


def test_cli_allocate_synthetic(tmp_path):
    out = tmp_path / "orpae.md"
    r = runner.invoke(app, ["allocate", "--program", "topstep_50k_combine_xfa", "--synthetic-mu", "0.2",
                            "--days", "300", "--paths", "200", "--seed", "3", "--mean-block", "1",
                            "--assume-processing-days", "3", "--out", str(out)])
    assert r.exit_code == 0, r.output
    text = out.read_text(encoding="utf-8")
    assert "SIMULADO" in text and "HIPOTÉTICO" in text and "Escalera de evidencia" in text
    for pol in ("fixed_250", "fixed_500", "fixed_750", "fixed_1000", "cushion_k0.25_max1000"):
        assert pol in text
