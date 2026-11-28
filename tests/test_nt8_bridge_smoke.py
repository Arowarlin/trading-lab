"""El script de humo del puente NT8 construye un intent válido para Sim101 (sin NinjaTrader)."""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_intent_passes_riskcheck():
    spec = importlib.util.spec_from_file_location("smoke", ROOT / "scripts" / "nt8_bridge_smoke.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    now = datetime(2026, 12, 1, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    intent, res = mod.build("Sim101", 21000.0, 20.0, now)
    assert res.ok, res.reasons
    assert (intent.qty, intent.adapter, intent.risk_usd) == (1, "nt8", 40.0 + 2 * (0.5 + 0.5))
