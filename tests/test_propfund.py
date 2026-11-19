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
    assert "config/prop.yaml" in flat


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
    assert profile.spread_price is None  # sin medición: nunca un spread fijo
    est = estimate_cfd(profile, lots=1, price=1.1, contract_size=100_000, risk_usd=500)
    assert not est.complete and "spread" in est.missing


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
