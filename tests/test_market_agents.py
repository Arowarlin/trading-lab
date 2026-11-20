from __future__ import annotations

import pytest

from tradinglab.config import Settings
from tradinglab.market_agents import (
    MarketAgentError,
    coordinate,
    load_markets,
    market_for_symbol,
    market_payload,
    run_market_agent,
)


def test_mercados_y_routing_por_clase() -> None:
    specs = load_markets()
    assert {"forex", "futures", "cfd"} <= set(specs)
    assert "equity" not in specs
    assert specs["forex"].profile == "intraday_fx"
    assert specs["futures"].profile == "intraday_futures"
    assert market_for_symbol("US100") == "cfd"
    assert market_for_symbol("EURUSD.a") == "forex"
    assert market_for_symbol("MES") == "futures"
    with pytest.raises(MarketAgentError):
        market_for_symbol("NOEXISTE")


def test_run_market_agent_valida_y_enruta(monkeypatch) -> None:
    calls = {}
    settings = Settings()

    def fake_lite(ticker, analysis_date, settings, client=None):
        calls["lite"] = (ticker, analysis_date, client)
        return {"rating": "Hold"}

    def fake_deep(ticker, analysis_date=None, analysts="", **kwargs):
        calls["deep"] = (ticker, analysis_date, analysts)
        return {"rating": "Buy"}

    monkeypatch.setattr("tradinglab.agents.lite.run_lite_agent", fake_lite)
    monkeypatch.setattr("tradinglab.agents.bridge.run_tradingagents", fake_deep)
    assert run_market_agent("cfd", "US100", settings, mode="lite")["rating"] == "Hold"
    assert calls["lite"][0] == "US100"
    assert run_market_agent("futures", "MES", settings, mode="deep")["rating"] == "Buy"
    assert calls["deep"][0] == "MES"
    assert "macro" in calls["deep"][2]
    with pytest.raises(MarketAgentError):
        run_market_agent("forex", "US100", settings)
    with pytest.raises(MarketAgentError):
        run_market_agent("inexistente", "US100", settings)


def test_coordinador_determinista_y_topes() -> None:
    signals = [
        {"symbol": "US100", "rating": "Buy", "confidence": 1.0},
        {"symbol": "GER40", "rating": "Buy", "confidence": 1.0},
        {"symbol": "EURUSD", "rating": "Overweight", "confidence": 0.8},
        {"symbol": "MES", "rating": "Buy", "confidence": 0.8},
        {"symbol": "XAUUSD", "rating": "Hold", "confidence": 1.0},
        {"symbol": "NOEXISTE", "rating": "Sell", "confidence": 1.0},
    ]
    first = coordinate(signals)
    second = coordinate(list(reversed(signals)))
    assert first["allocations"] == second["allocations"]
    assert first["gross_weight"] <= first["max_gross"] + 1e-9
    assert first["cash_weight"] == pytest.approx(1 - first["gross_weight"])
    assert all(item["weight"] > 0 for item in first["allocations"])
    assert all(
        weight <= load_markets()[market].max_weight + 1e-9
        for market, weight in first["by_market"].items()
    )
    assert first["by_market"]["cfd"] <= 0.25 + 1e-9
    assert first["by_market"]["forex"] <= 0.40 + 1e-9
    assert len(first["skipped"]) == 2


def test_coordinador_sin_senales_queda_cash() -> None:
    result = coordinate([])
    assert result["allocations"] == []
    assert result["cash_weight"] == 1.0
    assert result["gross_weight"] == 0.0


def test_market_payload_para_consola() -> None:
    payload = market_payload()
    assert payload["count"] == 3
    rows = {row["market"]: row for row in payload["markets"]}
    assert rows["cfd"]["symbols"]
    assert rows["forex"]["symbols"]
    assert rows["cfd"]["profile_found"] is True
    assert rows["futures"]["max_weight"] == pytest.approx(0.30)
    assert payload["max_gross"] == pytest.approx(0.90)
