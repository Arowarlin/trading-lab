from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import tradinglab.agents.lite as lite
from tradinglab.agents import AgentError
from tradinglab.config import get_settings


def frame(n: int = 320, slope: float = 0.5) -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-02", periods=n)
    close = 100 + np.arange(n) * slope
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.linspace(1_000_000, 2_000_000, n),
        },
        index=idx,
    )


class FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def chat_json(self, messages, *, purpose="json", schema=None):
        self.calls.append({"messages": messages, "purpose": purpose, "schema": schema})
        return self.payload


def test_build_context_is_compact_and_directional():
    ctx = lite.build_context(frame(), "nvda", "2026-11-05")
    assert ctx["ticker"] == "NVDA"
    assert ctx["trend"] == "up"
    assert ctx["price"] > ctx["sma"]["200"]
    assert ctx["returns_pct"]["20d"] > 0
    assert ctx["rsi14"] is not None and ctx["rsi14"] > 70  # subida monótona
    assert ctx["distance_from_high_pct"] <= 0
    # El contexto debe ser pequeño: una sola llamada, no un informe.
    assert len(json.dumps(ctx)) < 2000


def test_build_context_rejects_short_history():
    with pytest.raises(AgentError):
        lite.build_context(frame(n=50), "NVDA", "2026-11-05")


def test_lite_agent_sanitizes_rating_and_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(lite, "fetch", lambda *a, **k: frame())
    client = FakeClient(
        {
            "rating": "Comprar",  # inválido -> Hold
            "confidence": 5,
            "thesis": "x" * 2000,
            "risks": "riesgo",
            "horizon_days": 999,
        }
    )
    result = lite.run_lite_agent(
        "nvda", "2026-11-05", get_settings(), client=client, out_dir=tmp_path
    )

    assert result["rating"] == "Hold"
    assert result["confidence"] == 1.0
    assert result["horizon_days"] == 120
    assert len(result["decision"]) == 600
    assert client.calls[0]["purpose"] == "agent-lite:NVDA"
    assert (tmp_path / "lite_NVDA_2026-11-05.json").exists()


def test_lite_agent_maps_valid_rating(tmp_path, monkeypatch):
    monkeypatch.setattr(lite, "fetch", lambda *a, **k: frame())
    client = FakeClient(
        {
            "rating": "Overweight",
            "confidence": 0.7,
            "thesis": "tendencia alcista",
            "risks": "reversión",
            "horizon_days": 30,
        }
    )
    result = lite.run_lite_agent(
        "NVDA", "2026-11-05", get_settings(), client=client, out_dir=tmp_path
    )
    assert result["rating"] == "Overweight"
    assert result["horizon_days"] == 30


def test_lite_agent_permite_modelo_alternativo_sin_cambiar_default(tmp_path, monkeypatch):
    monkeypatch.setattr(lite, "fetch", lambda *a, **k: frame())
    client = FakeClient(
        {
            "rating": "Hold",
            "confidence": 0.5,
            "thesis": "sin señal",
            "risks": "ninguno",
            "horizon_days": 20,
        }
    )
    settings = get_settings()
    default_model = settings.llm.model
    result = lite.run_lite_agent(
        "NVDA",
        "2026-11-05",
        settings,
        client=client,
        out_dir=tmp_path,
        model="moe-30b-test",
    )
    assert result["model"] == "moe-30b-test"
    assert settings.llm.model == default_model
