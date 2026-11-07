from __future__ import annotations

import pytest

from tradinglab.instruments import (
    INSTRUMENTS,
    Instrument,
    InstrumentError,
    catalog,
    get_instrument,
    list_instruments,
    register,
    validate_catalog,
)


def test_eurusd_tick_and_pip_values():
    inst = get_instrument("EURUSD")
    assert inst.is_fx
    assert inst.pip_size() == pytest.approx(0.0001)
    assert inst.tick_value_usd() == pytest.approx(1.0)
    assert inst.risk_per_lot(0.0020) == pytest.approx(200.0)  # 20 pips


def test_jpy_pair_needs_quote_rate():
    inst = get_instrument("USDJPY")
    assert inst.pip_size() == pytest.approx(0.01)
    with pytest.raises(InstrumentError):
        inst.tick_value_usd()
    # 150 JPY por 1 USD -> 1 lote = 100.000 USD; 1 tick (0.001) = 100.000/150*0.001
    assert inst.tick_value_usd(quote_rate=150.0) == pytest.approx(0.666666, rel=1e-5)


def test_futures_risk_per_contract():
    mes = get_instrument("MES")
    assert mes.tick_value_usd() == pytest.approx(1.25)
    assert mes.risk_per_lot(0.25) == pytest.approx(1.25)  # 1 tick
    assert mes.risk_per_lot(2.00) == pytest.approx(10.00)  # 8 ticks


def test_lots_for_risk_rounds_down():
    inst = get_instrument("EURUSD")
    # 100 USD de riesgo / 200 USD por lote = 0.5 lotes exactos
    assert inst.lots_for_risk(100, 0.0020) == pytest.approx(0.50)
    # 110 USD -> 0.55, pero el step es 0.01: 0.55 es válido
    assert inst.lots_for_risk(110, 0.0020) == pytest.approx(0.55)
    # 105 USD -> 0.525 -> se queda en 0.52, nunca en 0.53
    assert inst.lots_for_risk(105, 0.0020) == pytest.approx(0.52)


def test_lots_for_risk_returns_zero_below_min_lot():
    inst = get_instrument("EURUSD")
    assert inst.lots_for_risk(1.0, 0.0020) == 0.0


def test_lots_respects_cap_and_max():
    inst = get_instrument("MES")
    lots = inst.lots_for_risk(1_000_000, 1.0, cap_lots=7)
    assert lots == pytest.approx(7)
    assert lots <= inst.max_lot


def test_unknown_symbol_with_broker_suffix_resolves():
    inst = get_instrument("EURUSD.a")
    assert inst.symbol == "EURUSD.A"
    assert inst.contract_size == 100_000


def test_catalog_has_all_asset_classes():
    classes = {i.asset_class for i in list_instruments()}
    assert {"equity", "forex", "futures"} <= classes


def test_catalogo_unico_fuente_y_validacion():
    rows = catalog()
    assert rows
    for row in rows:
        assert row["data_source"]
        assert row["session"]
        assert row["session_tz"]
        assert row["tick_size"] > 0
    assert catalog("forex")
    assert all(row["asset_class"] == "forex" for row in catalog("forex"))
    result = validate_catalog()
    assert result["ok"] is True
    assert {"equity", "forex", "futures"} <= set(result["classes"])
    inst = get_instrument("EURUSD.a")
    assert inst.data_source == "mt5"
    assert inst.session_tz == "UTC"


def test_cfd_solo_con_especificacion_verificada():
    cfd = Instrument(
        symbol="TESTCFD",
        asset_class="cfd",
        quote_ccy="USD",
        tick_size=0.1,
        contract_size=10,
        tick_value=1.0,
        session="09:00-17:00",
        session_tz="Europe/Prague",
        data_source="mt5",
    )
    register(cfd)
    try:
        result = validate_catalog()
        assert result["ok"] is True
        assert "cfd" in result["classes"]
        assert any(row["symbol"] == "TESTCFD" for row in catalog("cfd"))
    finally:
        INSTRUMENTS.pop("TESTCFD", None)
