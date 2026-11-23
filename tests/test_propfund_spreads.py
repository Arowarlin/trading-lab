"""Spreads medidos por cuenta CFD: conversión, cierres y escritura YAML."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from tradinglab.broker_costs import load_spreads, persist_spreads
from tradinglab.propfund import measure
from tradinglab.propfund.costs import load_profile
from tradinglab.propfund.models import Market

COSTS_YAML = """# cabecera que debe sobrevivir
version: 1

accounts:
  CFD-001:
    symbols:
      US100: {spread_price: null, spread_p75_price: null, slippage_price: 1.0, source: "slippage: config/ai_trader.yaml global.slippage_price"}
  CFD-002:
    symbols:
      US100: {spread_price: null, spread_p75_price: null, source: "otra cuenta"}
"""

AI_TRADER_YAML = """global:
  slippage_price:
    US100.cash: 1.0
    XAUUSD: 0.15
    EURUSD: 0.00005
    GBPUSD: 0.00005
    USDJPY: 0.005
"""


def _registry(*allowed: str):
    account = SimpleNamespace(
        id="CFD-001", firm="ftmo", market=Market.CFD,
        allowed_instruments=list(allowed),
    )
    return SimpleNamespace(accounts={"CFD-001": account})


def _rows():
    return [
        {"symbol": "US100.CASH", "hour_utc": 0, "median_bps": 10.0, "p75_bps": 12.0, "n_ticks": 100,
         "from_ts": "2026-11-18T00:00:00+00:00", "to_ts": "2026-11-18T00:30:00+00:00", "source": "broker"},
        {"symbol": "US100.CASH", "hour_utc": 1, "median_bps": 20.0, "p75_bps": 16.0, "n_ticks": 100,
         "from_ts": "2026-11-18T01:00:00+00:00", "to_ts": "2026-11-18T01:30:00+00:00", "source": "broker"},
        {"symbol": "US100.CASH", "hour_utc": 2, "median_bps": 30.0, "p75_bps": 20.0, "n_ticks": 100,
         "from_ts": "2026-11-18T02:00:00+00:00", "to_ts": "2026-11-18T02:30:00+00:00", "source": "broker"},
        {"symbol": "US100.CASH", "hour_utc": 3, "median_bps": 40.0, "p75_bps": 24.0, "n_ticks": 100,
         "from_ts": "2026-11-18T03:00:00+00:00", "to_ts": "2026-11-18T03:30:00+00:00", "source": "broker"},
        {"symbol": "USDJPY", "hour_utc": 0, "median_bps": 0.4, "p75_bps": 0.5, "n_ticks": 50,
         "from_ts": "2026-11-18T00:00:00+00:00", "to_ts": "2026-11-18T00:30:00+00:00", "source": "broker"},
        {"symbol": "USDJPY", "hour_utc": 1, "median_bps": 0.6, "p75_bps": 0.7, "n_ticks": 50,
         "from_ts": "2026-11-18T01:00:00+00:00", "to_ts": "2026-11-18T01:30:00+00:00", "source": "broker"},
    ]


def _costs(tmp_path):
    path = tmp_path / "costs.yaml"
    path.write_text(COSTS_YAML, encoding="utf-8")
    return path


def _ai_trader(tmp_path):
    path = tmp_path / "ai_trader.yaml"
    path.write_text(AI_TRADER_YAML, encoding="utf-8")
    return path


def _db(tmp_path):
    db = tmp_path / "lab.db"
    persist_spreads(_rows(), db_path=db)
    return db


def _sync(tmp_path, **kwargs):
    return measure.sync_spreads(
        "CFD-001",
        db_path=_db(tmp_path),
        costs_path=_costs(tmp_path),
        ai_trader_path=_ai_trader(tmp_path),
        registry=_registry("US100", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"),
        **kwargs,
    )


# ---------------------------------------------------------------- estadística
def test_p50_es_mediana_y_p75_es_percentil_75_de_los_horarios(tmp_path):
    db = tmp_path / "stats.db"
    persist_spreads(_rows(), db_path=db)
    stats = measure.spread_stats(load_spreads(db, symbol="US100.CASH", source="broker"))
    assert stats["p50_bps"] == pytest.approx(25.0)
    assert stats["p75_bps"] == pytest.approx(21.0)   # percentil 75 de [12,16,20,24]
    assert stats["hours"] == 4
    assert stats["ticks"] == 400
    assert stats["measured_at"] == "2026-11-18T03:30:00+00:00"


def test_sin_filas_no_inventa_nada():
    stats = measure.spread_stats(pd.DataFrame(columns=["symbol", "median_bps", "p75_bps"]))
    assert stats["p50_bps"] is None and stats["p75_bps"] is None
    assert stats["hours"] == 0


def test_bps_a_precio():
    assert measure.price_from_bps(25.0, 100.0) == pytest.approx(0.25)
    assert measure.price_from_bps(0.09, 1.09675) == pytest.approx(0.00001, abs=1e-9)


# ---------------------------------------------------------------- cierres
def test_ultimo_cierre_ignora_la_vela_en_curso(tmp_path):
    cache = tmp_path / "mt5"
    cache.mkdir()
    index = pd.date_range("2026-11-18 10:00", periods=3, freq="h", tz="UTC")
    pd.DataFrame({"close": [97.0, 98.0, 99.0]}, index=index).to_parquet(
        cache / "US100.CASH_H1.parquet"
    )
    last = measure.read_last_close(
        cache, "US100.CASH", now=datetime(2026, 11, 18, 11, 30, tzinfo=timezone.utc)
    )
    assert last["price"] == pytest.approx(97.0)      # la vela de 11:00 cierra a las 12:00
    assert last["timeframe"] == "H1"
    assert last["close_ts"] == "2026-11-18T11:00:00+00:00"


def test_sin_cache_devuelve_none(tmp_path):
    assert measure.read_last_close(tmp_path, "US100.CASH", now=datetime.now(timezone.utc)) is None


# ---------------------------------------------------------------- dry-run
def test_dry_run_no_escribe_y_calcula_spreads(tmp_path):
    costs = _costs(tmp_path)
    before = costs.read_bytes()
    report = _sync(tmp_path, close_prices={"US100": 100.0, "USDJPY": 150.0})

    assert report["dry_run"] is True and report["written"] is False
    assert costs.read_bytes() == before
    us100 = next(row for row in report["symbols"] if row["symbol"] == "US100")
    assert us100["spread_price"] == pytest.approx(0.25)
    assert us100["spread_p75_price"] == pytest.approx(0.21)
    assert "broker_spreads" in us100["source"]


def test_dry_run_incluye_usdjpy_y_deja_gbpusd_sin_datos(tmp_path):
    report = _sync(tmp_path, close_prices={"US100": 100.0, "USDJPY": 150.0})
    by_symbol = {row["symbol"]: row for row in report["symbols"]}
    assert set(by_symbol) == {"US100", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}
    assert by_symbol["USDJPY"]["status"] == "ok"
    assert by_symbol["USDJPY"]["spread_price"] == pytest.approx(0.0075)
    assert by_symbol["USDJPY"]["spread_p75_price"] == pytest.approx(0.00975)
    assert by_symbol["USDJPY"]["slippage_price"] == pytest.approx(0.005)
    assert "config/ai_trader.yaml global.slippage_price" in by_symbol["USDJPY"]["source"]
    assert by_symbol["GBPUSD"]["status"] == "sin datos"
    assert by_symbol["GBPUSD"]["spread_price"] is None
    assert by_symbol["GBPUSD"]["slippage_price"] == pytest.approx(0.00005)


def test_sin_cierre_no_convierte(tmp_path):
    report = _sync(tmp_path, close_prices={})
    us100 = next(row for row in report["symbols"] if row["symbol"] == "US100")
    assert us100["status"] == "sin cierre"
    assert us100["spread_price"] is None
    assert any("sin cierre" in warning for warning in report["warnings"])


# ---------------------------------------------------------------- escritura
def test_write_conserva_comentarios_y_otras_cuentas(tmp_path):
    costs = _costs(tmp_path)
    report = _sync(tmp_path, write=True, close_prices={"US100": 100.0, "USDJPY": 150.0})

    assert report["written"] is True
    text = costs.read_text(encoding="utf-8")
    assert text.startswith("# cabecera que debe sobrevivir")
    assert "otra cuenta" in text

    data = yaml.safe_load(text)
    us100 = data["accounts"]["CFD-001"]["symbols"]["US100"]
    assert us100["spread_price"] == pytest.approx(0.25)
    assert us100["spread_p75_price"] == pytest.approx(0.21)
    assert us100["measured_at"] == "2026-11-18T03:30:00+00:00"
    assert us100["needs_verification"] is False
    assert "broker_spreads" in us100["source"]

    usdjpy = data["accounts"]["CFD-001"]["symbols"]["USDJPY"]
    assert usdjpy["spread_price"] == pytest.approx(0.0075)
    assert usdjpy["slippage_price"] == pytest.approx(0.005)

    gbpusd = data["accounts"]["CFD-001"]["symbols"]["GBPUSD"]
    assert gbpusd["spread_price"] is None
    assert gbpusd["spread_p75_price"] is None
    assert gbpusd["needs_verification"] is True
    assert data["accounts"]["CFD-002"]["symbols"]["US100"]["spread_price"] is None

    profile = load_profile(
        "CFD-001", "US100", path=costs,
        legacy_path=tmp_path / "sin_costs_legacy.yaml",
    )
    assert profile.spread_price == pytest.approx(0.25)
    assert profile.spread_p75_price == pytest.approx(0.21)
    assert "broker_spreads" in profile.source


def test_write_no_borra_un_spread_ya_medido_si_falta_la_medicion(tmp_path):
    costs = _costs(tmp_path)
    data = yaml.safe_load(costs.read_text(encoding="utf-8"))
    data["accounts"]["CFD-001"]["symbols"]["US100"]["spread_price"] = 0.5
    data["accounts"]["CFD-001"]["symbols"]["US100"]["spread_p75_price"] = 0.7
    costs.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    db = tmp_path / "vacia.db"

    measure.sync_spreads(
        "CFD-001", write=True, db_path=db, costs_path=costs,
        ai_trader_path=_ai_trader(tmp_path), registry=_registry("US100"),
        close_prices={"US100": 100.0},
    )
    after = yaml.safe_load(costs.read_text(encoding="utf-8"))
    entry = after["accounts"]["CFD-001"]["symbols"]["US100"]
    assert entry["spread_price"] == pytest.approx(0.5)
    assert entry["spread_p75_price"] == pytest.approx(0.7)


# ---------------------------------------------------------------- errores
def test_cuenta_futuros_se_rechaza(tmp_path):
    fut = SimpleNamespace(
        id="FUT-001", firm="topstep", market=Market.FUTURES,
        allowed_instruments=["MNQ"],
    )
    registry = SimpleNamespace(accounts={"FUT-001": fut})
    with pytest.raises(ValueError, match="solo aplica a cuentas CFD"):
        measure.sync_spreads(
            "FUT-001", costs_path=_costs(tmp_path), registry=registry,
        )


def test_cuenta_sin_bloque_en_costs_se_rechaza(tmp_path):
    registry = _registry("US100").accounts
    account = registry["CFD-001"]
    registry["CFD-999"] = SimpleNamespace(
        id="CFD-999", firm="ftmo", market=account.market,
        allowed_instruments=["US100"],
    )
    with pytest.raises(ValueError, match="sin bloque de símbolos"):
        measure.sync_spreads(
            "CFD-999", costs_path=_costs(tmp_path),
            registry=SimpleNamespace(accounts=registry),
        )


# ---------------------------------------------------------------- multi-terminal
def test_sync_spreads_usa_alias_y_source_de_la_cuenta(tmp_path):
    costs = tmp_path / "costs.yaml"
    costs.write_text(
        "accounts:\n  CFD-006:\n    symbols:\n"
        "      US100: {spread_price: null, spread_p75_price: null}\n",
        encoding="utf-8",
    )
    db = tmp_path / "lab.db"
    persist_spreads(
        [
            {
                "symbol": "NDX100", "hour_utc": 0, "median_bps": 10.0,
                "p75_bps": 12.0, "n_ticks": 10,
                "from_ts": "2026-11-20T00:00:00+00:00",
                "to_ts": "2026-11-20T00:30:00+00:00",
                "source": "broker:CFD-006",
            }
        ],
        db_path=db,
    )
    account = SimpleNamespace(
        id="CFD-006", firm="fundingpips", market=Market.CFD,
        allowed_instruments=["US100"],
        spread_source="broker:CFD-006",
        broker_symbols={"US100": "NDX100"},
    )
    registry = SimpleNamespace(accounts={"CFD-006": account})
    report = measure.sync_spreads(
        "CFD-006",
        db_path=db,
        costs_path=costs,
        ai_trader_path=_ai_trader(tmp_path),
        registry=registry,
        close_prices={"US100": 20000.0},
    )

    row = report["symbols"][0]
    assert row["broker_symbol"] == "NDX100"
    assert row["p50_bps"] == pytest.approx(10.0)
    assert "broker:CFD-006" in row["source"]
    assert row["spread_price"] == pytest.approx(20.0)


class _FakeMeasureBroker:
    def __init__(self):
        self.shutdown_called = False

    def connect(self):
        return {"login": 40000459328, "server": "FundingPips-Trial", "mode": "demo", "connected": True}

    def copy_ticks(self, symbol, start, end):
        return pd.DataFrame(
            {
                "ts": [
                    pd.Timestamp("2026-11-20T10:00:00Z"),
                    pd.Timestamp("2026-11-20T10:30:00Z"),
                ],
                "bid": [19999.0, 19999.0],
                "ask": [20019.0, 20019.0],
            }
        )

    def rates(self, symbol, timeframe="M5", count=10):
        index = pd.DatetimeIndex(
            [pd.Timestamp("2026-11-20T11:50:00Z"), pd.Timestamp("2026-11-20T11:55:00Z")]
        )
        return pd.DataFrame({"close": [20000.0, 20010.0]}, index=index)

    def shutdown(self):  # pragma: no cover - no debe llamarse
        self.shutdown_called = True
        raise AssertionError("measure_account_spreads no debe llamar a shutdown")


def test_measure_account_spreads_inyecta_broker_sin_shutdown(tmp_path):
    account = SimpleNamespace(
        id="CFD-006", firm="fundingpips", market=Market.CFD,
        allowed_instruments=["US100"],
        spread_source="broker:CFD-006",
        broker_symbols={"US100": "NDX100"},
    )
    registry = SimpleNamespace(accounts={"CFD-006": account})
    broker = _FakeMeasureBroker()
    db = tmp_path / "lab.db"
    report = measure.measure_account_spreads(
        "CFD-006",
        db_path=db,
        broker=broker,
        registry=registry,
        now=datetime(2026, 11, 20, 11, 58, tzinfo=timezone.utc),
    )

    assert broker.shutdown_called is False
    assert report["source"] == "broker:CFD-006"
    assert report["close_prices"]["US100"] == pytest.approx(20000.0)
    assert report["symbols"][0]["p50_bps"] == pytest.approx(10.0, rel=1e-3)
    rows = load_spreads(db, symbol="NDX100", source="broker:CFD-006")
    assert len(rows) == 1


def test_compare_spreads_ftmo_vs_fundingpips(tmp_path):
    db = tmp_path / "lab.db"
    persist_spreads(_rows(), db_path=db)
    persist_spreads(
        [
            {
                "symbol": "NDX100", "hour_utc": 0, "median_bps": 10.0,
                "p75_bps": 12.0, "n_ticks": 10,
                "from_ts": "2026-11-20T00:00:00+00:00",
                "to_ts": "2026-11-20T00:30:00+00:00",
                "source": "broker:CFD-006",
            }
        ],
        db_path=db,
    )
    ftmo = SimpleNamespace(
        id="CFD-001", firm="ftmo", allowed_instruments=["US100"],
        spread_source=None, broker_symbols={},
    )
    funding = SimpleNamespace(
        id="CFD-006", firm="fundingpips", allowed_instruments=["US100"],
        spread_source="broker:CFD-006", broker_symbols={"US100": "NDX100"},
    )
    registry = SimpleNamespace(accounts={"CFD-001": ftmo, "CFD-006": funding})
    report = measure.compare_spreads(
        ["CFD-001", "CFD-006"], symbols=["US100"], db_path=db, registry=registry
    )

    assert report["symbols"] == ["US100"]
    by_account = {row["account"]: row for row in report["rows"]}
    assert by_account["CFD-001"]["p50_bps"] == pytest.approx(25.0)
    assert by_account["CFD-006"]["p50_bps"] == pytest.approx(10.0)
    assert by_account["CFD-006"]["broker_symbol"] == "NDX100"


# ---------------------------------------------------------------- CLI
def test_cli_dry_run_por_defecto(monkeypatch):
    from typer.testing import CliRunner

    from tradinglab.propfund import cli as cli_mod

    calls = []

    def fake(account, write=False):
        calls.append((account, write))
        return {
            "account": account, "dry_run": not write, "written": write,
            "costs_path": "costs.yaml", "symbols": [], "planned": [], "warnings": [],
        }

    monkeypatch.setattr(cli_mod, "sync_spreads_report", fake)
    runner = CliRunner()
    assert runner.invoke(cli_mod.app, ["sync-spreads", "--account", "CFD-001"]).exit_code == 0
    assert runner.invoke(
        cli_mod.app, ["sync-spreads", "--account", "CFD-001", "--write"]
    ).exit_code == 0
    assert calls == [("CFD-001", False), ("CFD-001", True)]
