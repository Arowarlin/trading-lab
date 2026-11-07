from __future__ import annotations

import pandas as pd
import yaml

from tradinglab import botlab
from tradinglab.config import Settings
from tradinglab.orchestrator import BotSpec


def _ohlcv(ups: bool = True) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=320, freq="D")
    close = [100 + (i if ups else -i * 0.1) for i in range(320)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": [1_000] * 320,
        },
        index=dates,
    )


def test_propose_bot_nace_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(botlab, "PROPOSED_FILE", tmp_path / "bots_proposed.yaml")
    monkeypatch.setattr(botlab, "load_bots", lambda: [])
    monkeypatch.setattr(botlab, "load_proposed", lambda: [])

    spec = botlab.propose_bot(
        id="test-trend",
        strategy="trend",
        universe=["spy"],
        params={"fast": 20, "slow": 100, "regime": 200},
        exposure=0.5,
        description="prueba",
    )
    assert spec.enabled is False
    assert spec.universe == ["SPY"]
    data = yaml.safe_load((tmp_path / "bots_proposed.yaml").read_text(encoding="utf-8"))
    assert data["bots"][0]["enabled"] is False
    assert data["bots"][0]["exposure"] == 0.5


def test_archive_y_restore_sin_borrar(tmp_path, monkeypatch):
    monkeypatch.setattr(botlab, "ARCHIVE_FILE", tmp_path / "bots_archive.yaml")
    monkeypatch.setattr(botlab, "ROOT", tmp_path)

    ids = botlab.archive_bot("viejo", reason="sin edge")
    assert "viejo" in ids
    assert "viejo" in botlab.load_archive()
    assert (tmp_path / "config" / "bots_archive_reasons.yaml").exists()

    ids = botlab.restore_bot("viejo")
    assert "viejo" not in ids


def test_metrics_deterministas(monkeypatch):
    monkeypatch.setattr("tradinglab.data.fetch", lambda *args, **kwargs: _ohlcv())
    spec = BotSpec(
        id="test-trend",
        type="deterministic",
        strategy="trend",
        universe=["SPY"],
        enabled=False,
        params={"fast": 50, "slow": 200, "regime": 200},
        exposure=0.35,
    )
    metrics = botlab._metrics_for(spec, Settings(), "2024-01-01")
    assert metrics["status"] in {"mantener", "muestra_insuficiente", "archivar"}
    assert "num_trades" in metrics


def test_metricas_no_evaluables():
    spec = BotSpec(id="llm", type="llm", strategy="tradingagents", universe=["SPY"], enabled=False)
    metrics = botlab._metrics_for(spec, Settings(), "2024-01-01")
    assert metrics["status"] == "no_evaluable"
