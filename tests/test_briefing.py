from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from tradinglab.briefing import build_report, send_report
from tradinglab.config import Settings
from tradinglab.db import init_db
from tradinglab.intel.calendar import add_calendar_event


def _frame() -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-02", periods=300)
    close = 100 + np.arange(300) * 0.1
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        },
        index=idx,
    )


def _fake_agent(ticker, when, settings, **kwargs):
    return {
        "rating": "Hold",
        "confidence": 0.5,
        "thesis": "sin señal clara",
        "risks": "datos",
        "horizon_days": 1,
        "model": "qwen-test",
        "elapsed_s": 1.0,
        "context": {"price": 129.9},
    }


def test_briefing_con_datos_calendario_y_qwen(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    add_calendar_event(
        db,
        event="US CPI",
        ts_utc=datetime.now(timezone.utc) + timedelta(hours=2),
        importance="high",
        source="test",
    )
    monkeypatch.setattr("tradinglab.briefing._rates", lambda *a, **k: _frame())
    report = build_report(
        db,
        Settings(),
        tickers=["US100", "XAUUSD"],
        agent_runner=_fake_agent,
        day=date.today(),
        session="pre_london",
    )
    text = report["text"]
    assert "Briefing pre-Londres" in text
    assert "US100" in text and "XAUUSD" in text
    assert "Hold" in text
    assert "US CPI" in text
    assert "no envía órdenes" in text.lower()
    assert report["errors"] == []
    assert len(report["rows"]) == 2
    assert report["source"] == "mt5" and report["read_only"] is True


def test_briefing_sin_llm_muestra_sin_datos(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    monkeypatch.setattr("tradinglab.briefing._rates", lambda *a, **k: _frame())
    report = build_report(
        db,
        Settings(),
        tickers=["EURUSD"],
        include_llm=False,
        day=date.today(),
    )
    assert "Sin datos" in report["text"]
    assert report["rows"][0]["result"] is None


def test_briefing_sin_mt5_no_inventa(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    monkeypatch.setattr("tradinglab.briefing._rates", lambda *a, **k: None)
    report = build_report(
        db,
        Settings(),
        tickers=["US500"],
        agent_runner=_fake_agent,
        day=date.today(),
    )
    assert "Sin datos" in report["text"]
    assert "MT5" in report["rows"][0]["error"]


def test_send_report_usa_telegram(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        "tradinglab.telegram.send_configured",
        lambda text: calls.append(text),
    )
    send_report("hola")
    assert calls == ["hola"]
