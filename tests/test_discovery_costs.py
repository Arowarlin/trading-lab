"""Costes multifirma: worst/target, hora local, DST y slippage asumido."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradinglab.config import ROOT
from tradinglab.discovery import campaigns, costs, databank, fastbt
from tradinglab.discovery.config import AssumedSlippageConfig, load_engine_config
from tradinglab.learning import count_tests
from tradinglab.propfund.costs import CostProfile
from tradinglab.propfund.models import Market

SEGMENTS = {
    "is": ["2023-01-02", "2023-04-30"],
    "oos1": ["2023-05-01", "2023-05-31"],
    "oos2": ["2023-06-01", None],
}


def _panel(values: list[float]) -> fastbt.CostPanel:
    array = np.asarray(values, dtype=float)
    return fastbt.CostPanel(
        spread_bps=array.copy(),
        slip_bps=np.zeros_like(array),
        comm_bps=np.zeros_like(array),
        legacy_entry_bps=array,
        legacy_stop_bps=array.copy(),
        legacy_target_bps=np.zeros_like(array),
    )


def _fake(account: str, panel: fastbt.CostPanel) -> SimpleNamespace:
    return SimpleNamespace(
        account=account,
        instrument="US100",
        assumed_slippage=1.0,
        slippage_source="assumption",
        panel=lambda bars: panel,
    )


def _trade() -> fastbt.Trade:
    return fastbt.Trade(
        side="long",
        entry_index=0,
        exit_index=2,
        entry_time=pd.Timestamp("2024-01-10 15:00", tz="UTC"),
        exit_time=pd.Timestamp("2024-01-10 15:30", tz="UTC"),
        entry_price=100.0,
        exit_price=101.0,
        stop=99.0,
        target=None,
        reason="force_exit",
        bars_held=6,
        risk_price=1.0,
        entry_cost_bps=0.0,
        exit_cost_bps=0.0,
        r_gross=0.5,
        r_cost=0.0,
        r_net=0.5,
    )


def test_us30_en_cfd006_usa_dji30() -> None:
    from tradinglab.propfund.registry import load_registry

    assert costs.eligible_cost_accounts("US30") == ["CFD-006"]
    assert costs.assumed_slippage_for("US30")[0] == pytest.approx(2.5)
    account = load_registry().accounts["CFD-006"]
    assert account.broker_symbols["US30"] == "DJI30"
    assert "US30" in account.allowed_instruments


def test_best_toma_el_minimo_por_operacion_y_guarda_ambas() -> None:
    book = costs.CostBook(
        [
            _fake("A", _panel([20.0, 1.0, 0.0])),
            _fake("B", _panel([1.0, 1.0, 1.0])),
        ],
        mode="best",
        session_tz="UTC",
    )
    bars = pd.DataFrame(
        {"open": [100.0] * 3, "high": [101.0] * 3, "low": [99.0] * 3, "close": [100.0] * 3},
        index=pd.date_range("2024-01-10 15:00", periods=3, freq="5min", tz="UTC"),
    )
    book.panel(bars)
    applied = book.apply([_trade()], session_tz="UTC")
    assert applied.trades[0].r_cost == pytest.approx(0.02)
    assert applied.cost_by_account["A"] == pytest.approx(0.20)
    assert applied.cost_by_account["B"] == pytest.approx(0.02)
    assert applied.best_account == "B"
    assert applied.best_share == pytest.approx(1.0)
    assert applied.selected_account == "B"
    assert applied.selected_share == pytest.approx(1.0)


def test_apply_result_guarda_neto_de_ambas_y_la_mas_barata() -> None:
    book = costs.CostBook(
        [
            _fake("A", _panel([20.0, 1.0, 0.0])),
            _fake("B", _panel([1.0, 1.0, 1.0])),
        ],
        mode="best",
        session_tz="UTC",
    )
    bars = pd.DataFrame(
        {"open": [100.0] * 3, "high": [101.0] * 3, "low": [99.0] * 3, "close": [100.0] * 3},
        index=pd.date_range("2024-01-10 15:00", periods=3, freq="5min", tz="UTC"),
    )
    book.panel(bars)
    result = fastbt.FastResult(
        trades=[_trade()],
        daily_r=pd.Series(dtype=float),
        metrics={},
    )
    _applied, metrics = costs.apply_result(
        book, result, session_tz="UTC", max_cost_r=0.10
    )
    assert metrics["cost_by_account"]["A"] == pytest.approx(0.20)
    assert metrics["cost_by_account"]["B"] == pytest.approx(0.02)
    assert metrics["best_account"] == "B"
    assert metrics["cost_viable_by_account"] == {"A": False, "B": True}
    assert metrics["selected_account"] == "B"


def test_best_es_el_modo_por_defecto(tmp_path: Path) -> None:
    frame = __import__("tradinglab.discovery.engine", fromlist=["x"]).synthetic_frame(
        years=0.5, seed=17
    )
    preview = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="best-default",
        dry_run=True,
        db_path=tmp_path / "discovery.db",
    )
    assert preview["config"]["cost"]["mode"] == "best"


def test_worst_toma_el_maximo_por_operacion_no_por_vela() -> None:
    book = costs.CostBook(
        [
            _fake("A", _panel([20.0, 1.0, 0.0])),
            _fake("B", _panel([0.0, 1.0, 20.0])),
        ],
        mode="worst",
        session_tz="UTC",
    )
    bars = pd.DataFrame(
        {"open": [100.0] * 3, "high": [101.0] * 3, "low": [99.0] * 3, "close": [100.0] * 3},
        index=pd.date_range("2024-01-10 15:00", periods=3, freq="5min", tz="UTC"),
    )
    worst_panel = book.panel(bars)
    # El panel por vela sumaría 20 de entrada + 20 de salida; la operación
    # exacta elige A (20+0) o B (0+20), no la mezcla.
    assert worst_panel.entry_bps.max() == 20.0
    applied = book.apply([_trade()], session_tz="UTC")
    assert applied.trades[0].r_cost == pytest.approx(0.20)
    assert applied.trades[0].r_net == pytest.approx(0.30)
    assert applied.worst_account in {"A", "B"}


def test_target_usa_solo_la_cuenta_declarada() -> None:
    book = costs.CostBook(
        [_fake("CFD-006", _panel([4.0, 4.0, 4.0]))],
        mode="target",
        session_tz="UTC",
    )
    bars = pd.DataFrame(
        {"open": [100.0] * 3, "high": [101.0] * 3, "low": [99.0] * 3, "close": [100.0] * 3},
        index=pd.date_range("2024-01-10 15:00", periods=3, freq="5min", tz="UTC"),
    )
    book.panel(bars)
    applied = book.apply([_trade()], session_tz="UTC")
    assert applied.worst_account == "CFD-006"
    assert applied.trades[0].r_cost == pytest.approx(0.08)


def _hourly_cost(mapping: dict[int, float]) -> fastbt.CfdHourlyCosts:
    profile = CostProfile(
        account="TEST",
        symbol="US100",
        market=Market.CFD,
        commission_type="zero",
        slippage_price=0.0,
        spread_price=1.0,
        spread_p75_price=1.0,
    )
    return fastbt.CfdHourlyCosts(
        profile,
        spread_bps_by_local_hour=mapping,
        session_tz="America/New_York",
    )


def test_hora_sin_medicion_usa_el_maximo() -> None:
    cost = _hourly_cost({10: 1.0, 15: 3.0})
    index = pd.DatetimeIndex(
        [
            pd.Timestamp("2024-01-10 17:00", tz="UTC"),  # 12:00 NY, sin medición
            pd.Timestamp("2024-01-10 20:00", tz="UTC"),  # 15:00 NY
        ]
    )
    bars = pd.DataFrame(
        {"open": [100.0, 100.0], "high": [101.0, 101.0], "low": [99.0, 99.0], "close": [100.0, 100.0]},
        index=index,
    )
    panel = cost.panel(bars)
    assert panel.spread_bps.tolist() == pytest.approx([3.0, 3.0])


def test_dst_no_desplaza_la_hora_local(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE broker_spreads (symbol TEXT, hour_utc INTEGER, median_bps REAL,"
            " p75_bps REAL, n_ticks INTEGER, from_ts TEXT, to_ts TEXT, source TEXT,"
            " PRIMARY KEY(symbol, hour_utc, source))"
        )
        con.executemany(
            "INSERT INTO broker_spreads VALUES (?,?,?,?,?,?,?,?)",
            [
                ("US100.CASH", 19, 1.0, 1.0, 10, "2026-07-15T19:00:00+00:00", "2026-07-15T19:59:59+00:00", "broker"),
                ("US100.CASH", 20, 2.0, 2.0, 10, "2026-12-15T20:00:00+00:00", "2026-12-15T20:59:59+00:00", "broker"),
            ],
        )
    spread = costs.load_local_hour_spreads(
        "CFD-001", "US100", db_path=db, session_tz="America/New_York"
    )
    assert 15 in spread.p75_bps
    assert spread.p75_bps[15] == pytest.approx(2.0)
    assert 15 not in spread.missing_hours


def test_slippage_sin_datos_rechaza_registro(tmp_path: Path, monkeypatch) -> None:
    config = load_engine_config()
    config = config.model_copy(
        update={
            "assumed_slippage": AssumedSlippageConfig(
                source="assumption",
                instruments={
                    "US100": 1.0,
                    "US500": None,
                    "US30": 2.5,
                    "XAUUSD": 0.15,
                    "EURUSD": 0.00005,
                    "GBPUSD": 0.00005,
                    "USDJPY": 0.005,
                },
            )
        }
    )
    monkeypatch.setattr(costs, "load_engine_config", lambda: config)
    frame = __import__("tradinglab.discovery.engine", fromlist=["x"]).synthetic_frame(
        years=0.5, seed=7
    )
    with pytest.raises(campaigns.CampaignError, match="slippage asumido"):
        campaigns.register(
            "US500",
            "M5",
            "ny_open_vol_filter",
            "small",
            segments=SEGMENTS,
            frame=frame,
            campaign_id="sin-slippage",
            cost_accounts=["CFD-006"],
            cost_mode="target",
            dry_run=True,
            db_path=tmp_path / "discovery.db",
        )


def test_config_hash_incluye_cost_accounts_y_modo(tmp_path: Path) -> None:
    frame = __import__("tradinglab.discovery.engine", fromlist=["x"]).synthetic_frame(
        years=0.5, seed=11
    )
    one = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="one",
        cost_accounts=["CFD-001"],
        cost_mode="target",
        dry_run=True,
        db_path=tmp_path / "discovery.db",
    )
    two = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="two",
        cost_accounts=["CFD-001", "CFD-006"],
        cost_mode="worst",
        dry_run=True,
        db_path=tmp_path / "discovery.db",
    )
    assert one["config_hash"] != two["config_hash"]
    assert one["config"]["cost"]["accounts"] == ["CFD-001"]
    assert one["config"]["cost"]["mode"] == "target"
    assert two["config"]["cost"]["accounts"] == ["CFD-001", "CFD-006"]
    assert two["config"]["cost"]["mode"] == "worst"


def test_campana_antigua_conserva_hash(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    databank.add_campaign(
        "old",
        {
            "instrument": "US100",
            "timeframe": "M5",
            "cost": {"account": "CFD-001", "firm": "ftmo", "use_p75": True},
        },
        instrument="US100",
        timeframe="M5",
        status="registered",
        n_total=10,
        config_hash="hash-viejo",
        db_path=db,
    )
    before = databank.get_campaign("old", db_path=db)
    assert before is not None
    after = databank.get_campaign("old", db_path=db)
    assert after is not None
    assert after["config_hash"] == "hash-viejo"
    assert after["config"] == before["config"]
    assert "accounts" not in after["config"]["cost"]


def test_draft_con_costes_no_cuenta_hasta_aprobar(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    lab = tmp_path / "lab.db"
    databank.init_databank(db)
    frame = __import__("tradinglab.discovery.engine", fromlist=["x"]).synthetic_frame(
        years=0.5, seed=13
    )
    baseline = count_tests(lab, discovery_db=db)
    campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="cost-draft",
        cost_accounts=["CFD-001", "CFD-006"],
        cost_mode="worst",
        db_path=db,
    )
    assert count_tests(lab, discovery_db=db) == baseline
    campaigns.approve("cost-draft", db_path=db, verify=False)
    assert count_tests(lab, discovery_db=db) == baseline + 440


def test_sync_spreads_daily_es_attach_only() -> None:
    script = (ROOT / "scripts" / "sync_spreads_daily.ps1").read_text(
        encoding="utf-8"
    )
    assert "CFD-001" in script
    assert "CFD-006" in script
    assert "--measure" in script
    assert "--write" in script
    assert "mt5.login" not in script
    assert ".shutdown" not in script
    assert "RunLevel Highest" not in script


def test_show_muestra_coste_por_cuenta(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from tradinglab.cli import app
    from tradinglab.discovery import genetic

    monkeypatch.setenv("COLUMNS", "240")
    db = tmp_path / "discovery.db"
    databank.add_campaign(
        "show-cost",
        {
            "instrument": "US100",
            "timeframe": "M5",
            "cost": {
                "account": "CFD-001",
                "accounts": ["CFD-001", "CFD-006"],
                "mode": "worst",
            },
        },
        instrument="US100",
        timeframe="M5",
        status="registered",
        n_total=1,
        db_path=db,
    )
    strategy_id = databank.add_strategy(
        "show-cost",
        genetic.template_strategy("ny_open_vol_filter"),
        db_path=db,
    )
    databank.add_evaluation(
        strategy_id,
        segment="fitness_is",
        cost_profile="worst:CFD-001+CFD-006:US100",
        metrics={
            "cost_r": 0.03,
            "cost_by_account": {"CFD-001": 0.03, "CFD-006": 0.027},
            "cost_viable_by_account": {"CFD-001": True, "CFD-006": True},
            "worst_account": "CFD-001",
            "worst_share": 1.0,
            "best_account": "CFD-006",
            "best_share": 1.0,
            "selected_account": "CFD-006",
            "selected_share": 1.0,
            "cost_accounts": ["CFD-001", "CFD-006"],
            "cost_mode": "best",
            "slippage_assumption": {
                "US100": {"value": 1.0, "source": "assumption"}
            },
        },
        trades_count=10,
        db_path=db,
    )
    result = CliRunner().invoke(
        app, ["discovery", "show", str(strategy_id), "--db", str(db)]
    )
    assert result.exit_code == 0
    assert "Coste por cuenta" in result.output
    assert "CFD-001" in result.output
    assert "CFD-006" in result.output
    assert "Más barata" in result.output
    assert "sí" in result.output


