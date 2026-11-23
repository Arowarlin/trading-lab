"""Prop Fund: protección, registro, universo, costes, riesgo y router."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tradinglab.propfund import protected
from tradinglab.propfund.console import payload
from tradinglab.propfund.costs import CostProfile, estimate_cfd, estimate_futures, load_profile
from tradinglab.propfund.instruments import (
    is_in_universe,
    micro_equivalent,
    notional_usd,
    resolve,
    same_underlying,
)
from tradinglab.propfund.models import Market
from tradinglab.propfund.registry import RegistryError, load_registry
from tradinglab.propfund.risk import (
    AccountSnapshot,
    GlobalLimits,
    PositionView,
    check_global,
    exposure_by_underlying,
)
from tradinglab.propfund.router import Decision, Signal, route

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- protección
def test_componentes_protegidos_intactos():
    """Si falla: se tocó el EA, ai_trader, el forward FTMO, su riesgo o el hash F13."""
    report = protected.verify(ROOT)
    assert report["status"] != "SIN_MANIFIESTO", "falta config/propfund/protected_manifest.json"
    assert report["ok"], report["issues"]


def test_el_manifiesto_cubre_los_identificadores_protegidos():
    files = protected.protected_files(ROOT)
    flat = {f for group in files.values() for f in group}
    assert "integrations/mt5/us100_ftmo1/US100_EA.mq5" in flat
    assert "config/mt5_eas.yaml" in flat
    assert "src/tradinglab/ai_trader.py" in flat
    assert "config/intraday_forward.yaml" in flat
    assert "src/tradinglab/prop/rules.py" in flat


def test_verify_detecta_un_cambio(tmp_path):
    (tmp_path / "config" / "propfund").mkdir(parents=True)
    target = tmp_path / "config" / "lab.yaml"
    target.write_bytes(b"mode: paper\n")
    original = protected.PROTECTED_GROUPS
    protected.PROTECTED_GROUPS = {"x": {"description": "t", "paths": ["config/lab.yaml"]}}
    try:
        protected.write_manifest(tmp_path)
        assert protected.verify(tmp_path)["ok"]
        target.write_bytes(b"mode: live\n")
        report = protected.verify(tmp_path)
        assert not report["ok"] and report["issues"][0]["kind"] == "changed"
        # CRLF no cuenta como cambio
        target.write_bytes(b"mode: paper\r\n")
        assert protected.verify(tmp_path)["ok"]
    finally:
        protected.PROTECTED_GROUPS = original


# ---------------------------------------------------------------- registro
def test_registro_real_carga_10_firmas_y_separa_mercados():
    reg = load_registry()
    cfd = {f.id for f in reg.firms.values() if f.market is Market.CFD}
    fut = {f.id for f in reg.firms.values() if f.market is Market.FUTURES}
    assert cfd == {"ftmo", "the5ers", "fundednext", "fundingpips", "fxify"}
    assert fut == {"topstep", "apex", "myfundedfutures", "tradeify", "takeprofittrader"}
    assert reg.firms["ftmo"].protected
    for firm in reg.firms.values():
        assert firm.automation.sources, f"{firm.id} sin fuente de su política"


def test_sin_cuentas_de_capital_propio_ni_live():
    reg = load_registry()
    for acc in reg.accounts.values():
        assert acc.legacy_account not in {"paper_main", "alpaca_paper"}
        assert not acc.connection_state.value.startswith("LIVE")


def test_apex_y_take_profit_trader_prohiben_automatizacion():
    reg = load_registry()
    assert not reg.firms["apex"].automation.permission.allows_auto_orders
    assert not reg.firms["takeprofittrader"].automation.permission.allows_auto_orders
    assert reg.firms["tradeify"].automation.exclusive_to_firm


def test_affected_accounts_por_cambio_de_reglas():
    reg = load_registry()
    assert reg.affected_accounts("ftmo") == ["CFD-001", "CFD-002"]


def _write_cfg(tmp: Path, *, firms=None, accounts=None, strategies=None, assignments=None) -> Path:
    base = ROOT / "config" / "propfund"
    for name, override in (("firms", firms), ("accounts", accounts),
                           ("strategies", strategies), ("assignments", assignments)):
        data = yaml.safe_load((base / f"{name}.yaml").read_text(encoding="utf-8"))
        if override is not None:
            data[name] = override(data[name])
        (tmp / f"{name}.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return tmp


def test_registro_rechaza_acciones_y_mezcla_de_motores(tmp_path):
    def bad_accounts(items):
        items[0]["allowed_instruments"] = ["SPY"]
        return items
    with pytest.raises(RegistryError, match="fuera del universo"):
        load_registry(_write_cfg(tmp_path, accounts=bad_accounts))

    def cfd_on_futures(items):
        items.append({"id": "A-X", "strategy": "gold-asian-rev", "account": "FUT-001",
                      "instruments": ["XAUUSD"]})
        return items
    with pytest.raises(RegistryError, match="no se mezclan"):
        load_registry(_write_cfg(tmp_path, assignments=cfd_on_futures))


def test_no_se_asignan_estrategias_protegidas(tmp_path):
    def protected_asg(items):
        items.append({"id": "A-P", "strategy": "ai_trader", "account": "CFD-001",
                      "instruments": ["XAUUSD"]})
        return items
    with pytest.raises(RegistryError, match="protegida"):
        load_registry(_write_cfg(tmp_path, assignments=protected_asg))


# ---------------------------------------------------------------- universo
def test_alias_y_subyacentes():
    assert resolve("US100.cash").id == "US100"
    assert resolve("NAS100").id == resolve("USTEC").id == "US100"
    assert resolve("EURUSD.a").id == "EURUSD"
    assert resolve("MNQZ6").id == "MNQ"
    assert resolve("GCZ2026").id == "GC"
    assert resolve("US100").market is Market.CFD and resolve("NQ").market is Market.FUTURES
    assert same_underlying("NQ", "MNQ") and same_underlying("US100.cash", "NQ")
    assert same_underlying("XAUUSD", "MGC")
    assert not is_in_universe("SPY") and not is_in_universe("AAPL")


def test_equivalencias_micro_y_nocional():
    assert micro_equivalent("NQ") == 10
    assert micro_equivalent("GC") == 10
    assert notional_usd("NQ", 1, 20_000) == 400_000
    assert notional_usd("MNQ", 10, 20_000) == 400_000
    assert notional_usd("US100", 1, 20_000) is None  # tamaño de contrato CFD: del bróker
    assert notional_usd("US100", 1, 20_000, contract_size=1) == 20_000


# ---------------------------------------------------------------- costes
def test_coste_ftmo_usa_la_tabla_verificada():
    profile = load_profile("CFD-001", "EURUSD", firm="ftmo")
    assert profile.commission_type == "per_lot_usd" and profile.commission_value == 2.5
    # Spread medido por cuenta (Tarea A): ya no es None, y el p75 es conservador.
    assert profile.spread_price is not None and profile.spread_price > 0
    assert profile.spread_p75_price is not None
    assert profile.spread_p75_price >= profile.spread_price
    assert profile.measured_at and "broker_spreads" in profile.source
    est = estimate_cfd(profile, lots=1, price=1.1, contract_size=100_000, risk_usd=500)
    assert est.complete
    assert est.components["spread"] > 0


def test_coste_fundingpips_trial_comisiones_oficiales():
    index = load_profile("CFD-006", "US100")
    assert index.commission_type == "zero"
    assert index.commission_value == 0.0
    assert "fundingpips.com" in (index.commission_source or "")
    fx = load_profile("CFD-006", "EURUSD")
    assert fx.commission_type == "per_lot_usd"
    assert fx.commission_value == 5.0
    assert fx.commission_side == "round_turn"
    assert "ida y vuelta" in (fx.commission_source or "")
    assert "fundingpips.com" in (fx.commission_source or "")
    metal = load_profile("CFD-006", "XAUUSD")
    assert metal.commission_type == "per_lot_usd"
    assert metal.commission_value == 5.0
    assert metal.commission_side == "round_turn"
    assert "fundingpips.com" in (metal.commission_source or "")


def test_fundingpips_cfd006_es_2step_standard():
    from tradinglab.propfund.registry import load_registry

    reg = load_registry()
    account = reg.accounts["CFD-006"]
    assert account.limits.daily_loss == 5_000
    assert account.limits.max_loss == 10_000
    assert account.limits.profit_target == 8_000
    assert account.limits.min_trading_days == 3
    assert account.limits.drawdown_mode == "static"
    assert account.limits.daily_loss_base == "higher_of_balance_or_equity"
    assert account.limits.max_lots == 20
    # El riesgo interno (0,5 %/trade) queda por debajo del 2 % de una cuenta
    # fondeada de 100K; no se cambia el presupuesto del operador.
    assert account.risk.per_trade_risk_pct <= 0.02

    program = reg.firms["fundingpips"].program("fundingpips_2step")
    assert program is not None
    rules = {(rule.key, rule.phase, rule.instrument): rule for rule in program.rules}
    assert rules[("profit_target_pct", "evaluation", "all")].value == 0.08
    assert rules[("profit_target_pct", "verification", "all")].value == 0.05
    assert rules[("max_daily_loss_pct", "all", "all")].value == 0.05
    assert rules[("max_loss_pct", "all", "all")].value == 0.10
    assert rules[("drawdown_mode", "all", "all")].value == "static"
    assert rules[("min_trading_days", "evaluation", "all")].value == 3
    assert (
        rules[("daily_loss_base", "all", "all")].value
        == "higher_of_balance_or_equity"
    )
    assert (
        rules[("commission_per_lot_usd", "all", "forex_metals")].value == 5.0
    )
    assert (
        rules[("commission_per_lot_usd", "all", "indices_energy")].value == 0.0
    )
    assert rules[("max_risk_per_trade_pct", "funded", "all")].value == 0.02


def test_cfd006_rules_para_mc_declaran_equity_y_avisan_del_mayor():
    from tradinglab.propfund.registry import load_registry
    from tradinglab.propfund.snapshots import _rules_from_account

    account = load_registry().accounts["CFD-006"]
    rules = _rules_from_account(account, {"server_utc_offset_hours": 2})
    assert rules.max_daily_loss_pct == pytest.approx(0.05)
    assert rules.max_loss_pct == pytest.approx(0.10)
    assert rules.profit_target_pct == pytest.approx(0.08)
    assert rules.max_loss_mode == "static"
    assert rules.daily_loss_mode == "equity"
    assert rules.min_trading_days == 3
    assert rules.reset_time == "00:00"
    assert rules.reset_tz == "Etc/GMT-2"
    assert "MAYOR de balance o equidad" in rules.notes


def test_fundingpips_comision_ida_y_vuelta_no_se_duplica():
    from tradinglab.propfund.costs import estimate_cfd

    fx = load_profile("CFD-006", "EURUSD")
    estimate = estimate_cfd(
        fx, lots=1, price=1.10, contract_size=100_000, use_p75=True
    )
    assert estimate.components["commission"] == 5.0
    metal = load_profile("CFD-006", "XAUUSD")
    metal_estimate = estimate_cfd(
        metal, lots=1, price=2_000.0, contract_size=100, use_p75=True
    )
    assert metal_estimate.components["commission"] == 5.0
    index = load_profile("CFD-006", "US100")
    index_estimate = estimate_cfd(
        index, lots=1, price=20_000.0, contract_size=1, use_p75=True
    )
    assert index_estimate.components["commission"] == 0.0


def test_coste_futuros_no_usa_spreads_mt5():
    profile = CostProfile("FUT-T", "MNQ", Market.FUTURES, commission_value=0.37,
                          exchange_fee_per_side=0.35, clearing_fee_per_side=0.0,
                          nfa_fee_per_side=0.02, slippage_ticks=1)
    est = estimate_futures(profile, contracts=2, risk_usd=100)
    assert est.complete
    assert est.total_usd == pytest.approx(2 * 2 * (0.37 + 0.35 + 0.02) + 1 * 0.5 * 2 * 2)
    with pytest.raises(ValueError):
        estimate_cfd(profile, lots=1, price=1, contract_size=1)


# ---------------------------------------------------------------- riesgo
def test_riesgo_global_agrega_cfd_y_futuros_del_mismo_subyacente():
    positions = [
        PositionView("FUT-001", "topstep", "s1", "NQ", 1, 20_000, risk_usd=500),
        PositionView("FUT-002", "myfundedfutures", "s2", "MNQ", 5, 20_000, risk_usd=200),
        PositionView("CFD-001", "ftmo", "ea:us100-ftmo1", "US100.cash", 2, 20_000,
                     contract_size=1, risk_usd=300),
    ]
    expo = exposure_by_underlying(positions)["NASDAQ100"]
    assert expo["gross_notional_usd"] == 400_000 + 200_000 + 40_000
    assert expo["cross_market"]


def test_riesgo_global_bloquea_hedging_entre_cuentas():
    positions = [PositionView("FUT-001", "topstep", "s1", "MNQ", 2, 20_000, risk_usd=100)]
    check = check_global(positions, account="FUT-003", firm="tradeify", strategy="s2",
                         symbol="NQ", quantity=-1, price=20_000, risk_usd=100,
                         limits=GlobalLimits(max_notional_per_underlying_usd=10_000_000))
    assert not check.ok and any("hedging" in r for r in check.reasons)


# ---------------------------------------------------------------- router
def _router_cfg(tmp_path: Path) -> Path:
    def accounts(items):
        for acc in items:
            if acc["id"] == "FUT-001":
                acc.update(template=False, connection_state="DEMO", automation_acknowledged=True,
                           limits={"daily_loss": 1000, "max_loss": 2000, "drawdown_mode": "trailing_eod"})
            if acc["id"] == "FUT-004":
                acc.update(template=False, connection_state="DEMO")
        return items

    def assignments(items):
        for a in items:
            a["enabled"] = True
        return items
    return _write_cfg(tmp_path, accounts=accounts, assignments=assignments)


def _snap(acc_id: str, equity: float = 50_000) -> AccountSnapshot:
    return AccountSnapshot(acc_id, equity, equity, equity, equity)


def _mnq_costs() -> dict:
    return {"FUT-001": CostProfile("FUT-001", "MNQ", Market.FUTURES, commission_value=0.37,
                                   exchange_fee_per_side=0.35, clearing_fee_per_side=0.0,
                                   nfa_fee_per_side=0.02, slippage_ticks=1)}


def test_router_decide_por_cuenta_de_forma_independiente(tmp_path):
    reg = load_registry(_router_cfg(tmp_path))
    signal = Signal("nq-orb-ny", "MNQ", "long", entry=20_000, stop=19_990)
    decisions = {d.account: d for d in route(
        signal, reg, snapshots={"FUT-001": _snap("FUT-001"), "FUT-004": _snap("FUT-004")},
        cost_profiles=_mnq_costs(),
    )}
    topstep, apex = decisions["FUT-001"], decisions["FUT-004"]
    assert topstep.decision is Decision.READY_DRY_RUN, topstep.steps
    assert topstep.request["dry_run"] and topstep.request["mode"] == "DEMO"
    # 50.000 × 0,25 % = 125 USD; 10 pts = 40 ticks × 0,50 = 20 USD/contrato → 6 MNQ
    assert topstep.quantity == 6 and topstep.risk_usd == 120
    assert apex.decision is Decision.ALERT_ONLY  # Apex: automatización prohibida


def test_router_rechaza_plantillas_y_estrategias_protegidas():
    reg = load_registry()  # config real: todo deshabilitado y en plantilla
    decisions = route(Signal("nq-orb-ny", "MNQ", "long", 20_000, 19_990), reg,
                      snapshots={}, include_disabled=True)
    assert decisions and all(d.decision is Decision.REJECTED_ELIGIBILITY for d in decisions)
    assert route(Signal("ai_trader", "XAUUSD", "long", 2000, 1990), reg, snapshots={}) == []


def test_router_sin_costes_no_opera(tmp_path):
    reg = load_registry(_router_cfg(tmp_path))
    decisions = {d.account: d for d in route(
        Signal("nq-orb-ny", "MNQ", "long", 20_000, 19_990), reg,
        snapshots={"FUT-001": _snap("FUT-001")},
    )}
    assert decisions["FUT-001"].decision is Decision.REJECTED_COST


def test_router_respeta_el_riesgo_de_cuenta(tmp_path):
    reg = load_registry(_router_cfg(tmp_path))
    snap = AccountSnapshot("FUT-001", 50_000, 49_200, 50_000, 50_000)  # ya pierde 800 hoy
    decisions = {d.account: d for d in route(
        Signal("nq-orb-ny", "MNQ", "long", 20_000, 19_990), reg,
        snapshots={"FUT-001": snap}, cost_profiles=_mnq_costs(),
    )}
    assert decisions["FUT-001"].decision is Decision.REJECTED_RISK


# ---------------------------------------------------------------- consola
def test_payload_de_consola():
    data = payload()
    assert data["ok"]
    assert data["summary"]["firms"] == 10
    assert data["summary"]["mode"] == "PAPER/DEMO"
    assert data["protection"]["ok"]
    assert all(i["market"] in {"cfd", "futures"} for i in data["instruments"])
