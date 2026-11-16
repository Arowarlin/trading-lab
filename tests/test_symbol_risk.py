from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.accounts import load_accounts
from tradinglab.prop.guard import AccountSnapshot, PropGuard, evaluate_account
from tradinglab.prop.rules import from_yaml
from tradinglab.symbol_risk import (
    account_magics,
    alert_risk_events,
    effective_symbol_cap,
    effective_total_cap,
    group_cap_usd,
    open_risk_by_symbol,
    open_risk_report,
    position_risk_usd,
    risk_group,
    risk_snapshot,
    symbol_cap_usd,
    total_cap_usd,
)


class _Broker:
    def symbol_spec(self, symbol: str) -> dict:
        return {
            "tick_size": 0.01,
            "tick_value": 0.01,
            "point": 0.01,
            "contract_size": 1.0,
        }

    def positions(self):
        return [
            # Carril del forward con 50 puntos de stop.
            {"ticket": 1, "symbol": "US100.cash", "magic": 20261151,
             "volume": 1.0, "price_open": 20_000.0, "sl": 19_950.0},
            # EA principal: 50 puntos con 2 lotes.
            {"ticket": 2, "symbol": "US100.cash", "magic": 93010001,
             "volume": 2.0, "price_open": 20_100.0, "sl": 20_050.0},
            # Otro magic gestionado por el EA.
            {"ticket": 3, "symbol": "US100.cash", "magic": 93020001,
             "volume": 0.5, "price_open": 20_200.0, "sl": 20_100.0},
            # Ajeno al lab y al EA: no suma.
            {"ticket": 4, "symbol": "US100.cash", "magic": 777,
             "volume": 5.0, "price_open": 20_000.0, "sl": 19_000.0},
        ]


def _state(**kwargs) -> AccountSnapshot:
    base = dict(
        equity=100_000,
        day_start_equity=100_000,
        initial_balance=100_000,
        peak_equity=100_000,
    )
    base.update(kwargs)
    return AccountSnapshot(**base)


def test_magics_de_cuenta_incluyen_lab_y_ea():
    magics = account_magics("ftmo_demo")
    assert 20261151 in magics
    assert 93010001 in magics
    assert 93020001 in magics
    assert account_magics("ftmo_trial_ea") == []


def test_riesgo_por_simbolo_suma_carriles_y_eas():
    broker = _Broker()
    risk = open_risk_by_symbol(broker.positions(), broker, account_id="ftmo_demo")
    # (50 × 1) + (50 × 2) + (100 × 0,5) = 200 USD; el magic 777 no cuenta.
    assert risk["US100.CASH"] == pytest.approx(200.0)
    assert position_risk_usd(broker.positions()[1], broker) == pytest.approx(100.0)


def test_tope_por_simbolo_en_accounts_yaml():
    account = load_accounts()["ftmo_demo"]
    assert symbol_cap_usd(account, "US100.cash") == pytest.approx(2_000.0)
    assert symbol_cap_usd(account, "EURUSD") == pytest.approx(2_000.0)
    assert group_cap_usd(account, "indices_us") == pytest.approx(3_000.0)
    assert group_cap_usd(account, "usd") == pytest.approx(3_000.0)
    assert group_cap_usd(account, "metales") == pytest.approx(3_000.0)
    assert total_cap_usd(account) == pytest.approx(2_000.0)


def test_grupos_de_riesgo():
    account = load_accounts()["ftmo_demo"]
    assert risk_group(account, "US100.cash") == "indices_us"
    assert risk_group(account, "US500.cash") == "indices_us"
    assert risk_group(account, "XAUUSD") == "metales"
    assert risk_group(account, "EURUSD") == "usd"
    assert risk_group(account, "EURJPY") == "symbol:EURJPY"


def test_guard_bloquea_apertura_que_supera_el_tope_del_simbolo():
    rules = from_yaml("ftmo", "challenge", 100_000)
    blocked = evaluate_account(
        rules,
        _state(),
        proposed_risk_usd=1_950.0,
        symbol_open_risk_usd=100.0,
        symbol_risk_cap_usd=2_000.0,
        symbol="US100.cash",
    )
    assert blocked.allowed is False
    assert "riesgo del símbolo" in blocked.reason
    assert blocked.symbol_risk_usd == pytest.approx(2_050.0)

    allowed = evaluate_account(
        rules,
        _state(),
        proposed_risk_usd=1_800.0,
        symbol_open_risk_usd=100.0,
        symbol_risk_cap_usd=2_000.0,
        symbol="US100.cash",
    )
    assert allowed.allowed is True
    assert allowed.symbol_risk_usd == pytest.approx(1_900.0)


def test_propguard_tambien_rechaza_por_simbolo():
    rules = from_yaml("ftmo", "challenge", 100_000)
    guard = PropGuard(rules)
    state = guard.state_from_equity(
        rules,
        pd.Series(
            [100_000.0, 100_000.0],
            index=pd.date_range("2026-11-12", periods=2, freq="h", tz="UTC"),
        ),
        initial_balance=100_000,
    )
    report = guard.evaluate(
        state,
        proposed_lots=1.0,
        risk_per_lot=1_500.0,
        open_risk_usd=0.0,
        new_position=True,
        symbol_open_risk_usd=700.0,
        symbol_risk_cap_usd=2_000.0,
        symbol="US100.cash",
    )
    assert report.allowed is False
    assert "riesgo del símbolo" in report.reason


def test_informe_de_riesgo_usa_el_tope_de_la_cuenta():
    account = load_accounts()["ftmo_demo"]
    payload = open_risk_report("unused.db", account, broker=_Broker())
    item = payload["symbols"]["US100.CASH"]
    assert item["open_risk_usd"] == pytest.approx(200.0)
    assert item["cap_usd"] == pytest.approx(2_000.0)
    assert item["remaining_usd"] == pytest.approx(1_800.0)
    assert payload["groups"]["indices_us"]["cap_usd"] == pytest.approx(3_000.0)
    assert payload["total"]["cap_usd"] == pytest.approx(2_000.0)
    assert "accounts.yaml" in payload["total"]["source"]


def test_limite_nuevo_no_afloja_el_existente():
    account = load_accounts()["ftmo_demo"]
    symbol_cap = effective_symbol_cap(
        account, "US100.cash", balance=105_000, ai_pct=0.02
    )
    assert symbol_cap["usd"] == pytest.approx(2_000.0)
    assert "symbol_risk_caps" in symbol_cap["source"]

    total_cap = effective_total_cap(
        account, balance=105_000, prop_pct=0.02, ai_pct=0.02
    )
    assert total_cap["usd"] == pytest.approx(2_000.0)
    assert "prop.yaml" in total_cap["source"]
    assert "accounts.yaml" in total_cap["source"]
    assert total_cap["usd"] < 0.04 * 105_000


def test_tres_carriles_us100_el_tercero_no_abre():
    rules = from_yaml("ftmo", "challenge", 100_000)
    open_risk = 0.0
    results = []
    report = None
    for _ in range(3):
        report = evaluate_account(
            rules,
            _state(open_risk_usd=open_risk),
            proposed_risk_usd=700.0,
            symbol_open_risk_usd=open_risk,
            symbol_risk_cap_usd=2_000.0,
            symbol="US100.CASH",
            total_open_risk_usd=open_risk,
            total_risk_cap_usd=4_000.0,
        )
        results.append(report.allowed)
        if report.allowed:
            open_risk += 700.0
    assert results == [True, True, False]
    assert report is not None
    assert "riesgo agregado (símbolo" in report.reason


def test_posicion_sin_sl_bloquea_todo(monkeypatch):
    monkeypatch.setattr(
        "tradinglab.symbol_risk.account_magics", lambda account_id: [1]
    )
    monkeypatch.setattr("tradinglab.symbol_risk.ea_magics", lambda account_id: [])
    account = load_accounts()["ftmo_demo"]
    position = {
        "symbol": "US100.cash",
        "magic": 1,
        "volume": 1.0,
        "price_open": 20_000.0,
        "sl": 0.0,
    }
    risk = risk_snapshot(
        [position],
        _Broker(),
        account_id="ftmo_demo",
        account=account,
        balance=100_000,
    )
    assert risk["missing_sl"]
    assert risk["total_usd"] == pytest.approx(2_000.0)

    report = evaluate_account(
        from_yaml("ftmo", "challenge", 100_000),
        _state(),
        proposed_risk_usd=10.0,
        total_open_risk_usd=risk["total_usd"],
        total_risk_cap_usd=4_000.0,
        missing_sl=True,
    )
    assert report.allowed is False
    assert "sin SL" in report.reason


def test_alerta_critical_por_sl_ausente(monkeypatch):
    import tradinglab.alerts as alerts_mod

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        alerts_mod,
        "send_once",
        lambda event, message, **kwargs: sent.append(
            (event, str(kwargs.get("severity")))
        ),
    )
    risk = {
        "missing_sl": [{"symbol": "US100.cash", "magic": 1}],
        "ea_over": [],
    }
    alert_risk_events("ftmo_demo", risk, db_path="unused.db")
    assert any(event.startswith("missing_sl:") for event, _ in sent)
    assert any(severity == "critical" for _, severity in sent)


def test_ea_cuenta_en_el_total_y_alerta_warning(monkeypatch):
    import tradinglab.alerts as alerts_mod

    monkeypatch.setattr(
        "tradinglab.symbol_risk.account_magics",
        lambda account_id: [1, 93010001],
    )
    monkeypatch.setattr(
        "tradinglab.symbol_risk.ea_magics", lambda account_id: [93010001]
    )
    account = load_accounts()["ftmo_demo"]
    positions = [
        {
            "symbol": "US100.cash",
            "magic": 1,
            "volume": 70.0,
            "price_open": 20_000.0,
            "sl": 19_990.0,
        },
        {
            "symbol": "US100.cash",
            "magic": 93010001,
            "volume": 410.0,
            "price_open": 20_000.0,
            "sl": 19_990.0,
        },
    ]
    risk = risk_snapshot(
        positions,
        _Broker(),
        account_id="ftmo_demo",
        account=account,
        balance=100_000,
    )
    assert risk["total_usd"] == pytest.approx(4_800.0)
    assert risk["ea_total_usd"] == pytest.approx(4_100.0)
    assert risk["lab_total_usd"] == pytest.approx(700.0)
    assert any(item["kind"] == "total" for item in risk["ea_over"])

    blocked = evaluate_account(
        from_yaml("ftmo", "challenge", 100_000),
        _state(),
        proposed_risk_usd=100.0,
        total_open_risk_usd=risk["total_usd"],
        total_risk_cap_usd=4_000.0,
    )
    assert blocked.allowed is False
    assert "riesgo agregado (total)" in blocked.reason

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        alerts_mod,
        "send_once",
        lambda event, message, **kwargs: sent.append(
            (event, str(kwargs.get("severity")))
        ),
    )
    alert_risk_events("ftmo_demo", risk, db_path="unused.db")
    assert any(event.startswith("ea_risk_cap:") for event, _ in sent)
    assert any(severity == "warning" for _, severity in sent)
