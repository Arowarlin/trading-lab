from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import tradinglab.daytrader as daytrader
from tradinglab import cli as cli_mod
from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.operator import OperatorService

FIXTURES = Path(__file__).parent / "fixtures" / "daytrader"


def _prepare(
    tmp_path: Path,
    *,
    risk: str | None = "pass",
    orders: str = "orders.json",
) -> Path:
    shutil.copy(FIXTURES / "watchlist.json", tmp_path / "watchlist.json")
    shutil.copy(FIXTURES / orders, tmp_path / "orders.json")
    if risk is not None:
        state = tmp_path / "state"
        state.mkdir(parents=True, exist_ok=True)
        source = FIXTURES / ("state/risk.json" if risk == "pass" else "risk_block.json")
        shutil.copy(source, state / "risk.json")
    return tmp_path


def _settings(tmp_path: Path, *, enabled: bool = False) -> Settings:
    return Settings(
        mode="paper",
        data={"cache_dir": str(tmp_path / "cache")},
        daytrader={
            "dir": str(tmp_path),
            "account": "alpaca_paper",
            "enabled": enabled,
        },
    )


def _fake_plan(calls: list[dict]):
    def fake(self, params: dict) -> dict:
        calls.append(dict(params))
        return {
            "summary": {
                "action": "order",
                "account": params["account"],
                "symbol": params["ticker"],
                "side": params["side"],
                "qty": params["qty"],
                "price": params["price"],
                "sl": params["sl"],
                "risk_usd": 10.0,
                "guard": "ok",
            },
            "payload": {
                "kind": "order",
                "account": params["account"],
                "symbol": params["ticker"],
                "side": params["side"],
                "qty": params["qty"],
                "price": params["price"],
                "sl": params["sl"],
                "risk_usd": 10.0,
            },
        }

    return fake


def _fake_execute(calls: list[dict]):
    def fake(self, payload: dict) -> dict:
        calls.append(dict(payload))
        return {"ok": True, "order": {"id": "fake-order"}}

    return fake


def test_watchlist_importa_senales_y_no_duplica(tmp_path: Path) -> None:
    _prepare(tmp_path)
    db = tmp_path / "lab.db"
    init_db(db)
    settings = _settings(tmp_path)

    with connect(db) as con:
        first = daytrader.import_signals(settings, con, tmp_path)
    assert first["inserted"] == 3
    assert first["skipped"] == 0

    with connect(db) as con:
        second = daytrader.import_signals(settings, con, tmp_path)
    assert second["inserted"] == 0
    assert second["skipped"] == 3

    with connect(db) as con:
        rows = con.execute(
            "SELECT ticker, bot, reason FROM signals ORDER BY ticker, reason"
        ).fetchall()
    assert len(rows) == 3
    assert {row["ticker"] for row in rows} == {"AAPL", "MSFT"}
    assert all(row["bot"] == "daytrader" for row in rows)
    assert any("setup=breakout_20d" in row["reason"] for row in rows)


def test_orden_pass_pasa_a_previsualizacion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, risk="pass")
    settings = _settings(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(OperatorService, "_plan_order", _fake_plan(calls))

    result = daytrader.plan_orders(settings, tmp_path, execute=False)
    assert result["orders_file"] is True
    assert result["risk_file"] is True
    assert result["can_execute"] is False
    assert len(result["orders"]) == 1
    item = result["orders"][0]
    assert item["external_verdict"] == "PASS"
    assert item["guard_verdict"] == "PASS"
    assert item["action"] == "dry-run"
    assert item["qty"] == 8
    assert item["stop"] == 340.0
    assert item["target"] == 370.0
    assert len(calls) == 1
    assert calls[0]["ticker"] == "AAPL"
    assert calls[0]["price"] == pytest.approx(350.69)


def test_orden_block_se_rechaza(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, risk="block")
    settings = _settings(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(OperatorService, "_plan_order", _fake_plan(calls))

    result = daytrader.plan_orders(settings, tmp_path, execute=False)
    item = result["orders"][0]
    assert item["external_verdict"] == "BLOCK"
    assert item["guard_verdict"] == "NO EVALUADO"
    assert item["action"] == "rechazada"
    assert calls == []


def test_risk_ausente_rechaza_todo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, risk=None)
    settings = _settings(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(OperatorService, "_plan_order", _fake_plan(calls))

    result = daytrader.plan_orders(settings, tmp_path, execute=False)
    assert result["risk_file"] is False
    item = result["orders"][0]
    assert item["external_verdict"] == "BLOCK"
    assert item["action"] == "rechazada"
    assert "no existe" in item["reason"]
    assert calls == []


def test_execute_sin_enabled_no_ejecuta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, risk="pass")
    settings = _settings(tmp_path, enabled=False)
    plan_calls: list[dict] = []
    exec_calls: list[dict] = []
    monkeypatch.setattr(OperatorService, "_plan_order", _fake_plan(plan_calls))
    monkeypatch.setattr(OperatorService, "_execute_order", _fake_execute(exec_calls))

    result = daytrader.plan_orders(settings, tmp_path, execute=True)
    item = result["orders"][0]
    assert result["can_execute"] is False
    assert item["action"] == "dry-run"
    assert "enabled=false" in item["reason"]
    assert len(plan_calls) == 1
    assert exec_calls == []


def test_execute_con_tres_condiciones_ejecuta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, risk="pass")
    settings = _settings(tmp_path, enabled=True)
    plan_calls: list[dict] = []
    exec_calls: list[dict] = []
    monkeypatch.setattr(OperatorService, "_plan_order", _fake_plan(plan_calls))
    monkeypatch.setattr(OperatorService, "_execute_order", _fake_execute(exec_calls))

    result = daytrader.plan_orders(settings, tmp_path, execute=True)
    item = result["orders"][0]
    assert result["can_execute"] is True
    assert item["action"] == "ejecutada"
    assert len(plan_calls) == 1
    assert len(exec_calls) == 1
    assert exec_calls[0]["symbol"] == "AAPL"


def test_qty_fraccional_se_rechaza(tmp_path: Path) -> None:
    _prepare(tmp_path, risk="pass", orders="orders_fractional.json")
    with pytest.raises(daytrader.DaytraderError, match="qty"):
        daytrader.load_orders(tmp_path)


def test_cli_import_sin_orders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shutil.copy(FIXTURES / "watchlist.json", tmp_path / "watchlist.json")
    db = tmp_path / "lab.db"
    monkeypatch.setattr(cli_mod, "DEFAULT_DB", db)
    monkeypatch.setattr(cli_mod, "get_settings", lambda: _settings(tmp_path))

    result = CliRunner().invoke(cli_mod.app, ["daytrader", "import"])
    assert result.exit_code == 0
    assert "No hay orders.json" in result.output
    assert "Señales:" in result.output
