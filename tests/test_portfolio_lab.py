"""Tests sintéticos del Portfolio Lab: unidades R, solape, reglas y CLI."""

from __future__ import annotations

import json
import sqlite3
import zlib
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from tradinglab import cli as cli_mod
from tradinglab import portfolio_lab as pl


def _scaled(series, factor: float = 8.0):
    values = tuple(float(value) * factor for value in series.daily_r)
    trades = tuple(replace(trade, r=None if trade.r is None else trade.r * factor) for trade in series.trades)
    return replace(
        series,
        daily_r=values,
        trade_r=tuple(value * factor for value in series.trade_r),
        trades=trades,
    )


@pytest.mark.parametrize("rho", [0.0, 0.5, 0.9])
def test_correlacion_conocida(rho):
    series = pl.synthetic_preset(rho, days=1500, seed=11)
    _, matrix = pl.align(series)
    active = pl.active_matrix(series, None)
    corr = pl.correlation_matrix(matrix, active)
    assert corr.shape == (3, 3)
    for i in range(3):
        for j in range(i + 1, 3):
            assert corr[i, j] == pytest.approx(rho, abs=0.06)


def test_correlacion_alta_no_reduce_riesgo():
    series = [_scaled(item) for item in pl.synthetic_preset(0.9, days=600, seed=3)]
    names = [item.name for item in series]
    _, matrix = pl.align(series)
    active = pl.active_matrix(series, None)
    weights = {"equal": pl.allocate(names, matrix, "equal")}
    context = pl.account_context("CFD-001")
    report = pl.challenge_report(series, weights, context, matrix=matrix, paths=400, seed=5)
    results = report["results"]
    individual = [float(results[f"solo:{name}"]["p_pasar_fase1"]) for name in names]
    portfolio = float(results["cartera:equal"]["p_pasar_fase1"])
    assert portfolio <= max(individual) + 0.03
    assert all(value["ratio"] > 1 for value in pl.loss_coincidence(matrix, active).values())
    assert all(value["operaciones_solapadas"] > 0 for value in pl.overlap_by_pair(series).values())


def test_dias_sin_operacion_no_inflan_perdidas():
    days = tuple(date(2024, 1, 1) + timedelta(days=index) for index in range(70))
    active = days[::5]  # 14 días con una operación; el resto, 0 R sin operar.
    assert len(active) == 14
    left = [-1.0 if i < 7 else 1.0 for i in range(14)]
    right = [-1.0 if i in {0, 1, 2, 7, 8, 9, 10} else 1.0 for i in range(14)]
    series = []
    for label, values in (("A", left), ("B", right)):
        daily = {day: 0.0 for day in days}
        daily.update(dict(zip(active, values)))
        series.append(
            pl.StrategySeries(
                name=label,
                source="synthetic",
                symbol="SYN",
                daily_r=tuple(daily[day] for day in days),
                dates=days,
                trade_r=tuple(values),
                trade_dates=active,
                granularity="operacion_R",
                risk_source="sintetico",
            )
        )
    _, matrix = pl.align(series)
    flags = pl.active_matrix(series, days)
    assert flags.sum() == 28
    correcto = next(iter(pl.loss_coincidence(matrix, flags).values()))
    inflado = next(iter(pl.loss_coincidence(matrix).values()))
    assert correcto["dias_ambas_operan"] == 14
    assert correcto["dias_ambos_negativos"] == 3
    assert correcto["ratio"] == pytest.approx(0.86, abs=0.01)
    assert inflado["ratio"] > 4.0  # el error que se está corrigiendo


def test_perdidas_fuera_de_dias_comunes_no_cuentan():
    left = np.zeros((10, 2))
    active = np.zeros((10, 2), dtype=bool)
    left[:5, 0] = -1.0
    active[:5, 0] = True
    left[5:, 1] = -1.0
    active[5:, 1] = True
    result = next(iter(pl.loss_coincidence(left, active).values()))
    assert result["dias_ambas_operan"] == 0
    assert result["esperado_independiente"] == 0.0
    assert result["ratio"] is None


def test_reglas_de_firma_respetadas():
    c1 = pl.account_context("CFD-001")
    c6 = pl.account_context("CFD-006")
    r1, r6 = c1["rules"], c6["rules"]
    assert (r1.profit_target_pct, r1.max_daily_loss_pct, r1.max_loss_pct) == pytest.approx(
        (0.10, 0.05, 0.10)
    )
    assert (r6.profit_target_pct, r6.max_daily_loss_pct, r6.max_loss_pct) == pytest.approx(
        (0.08, 0.05, 0.10)
    )
    assert r6.buffer_pct == pytest.approx(0.20)
    series = pl.synthetic_preset(0.5, days=200, seed=1)
    names = [item.name for item in series]
    _, matrix = pl.align(series)
    weights = pl.allocate(names, matrix, "capped", cap_pct=0.4)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert all(0.0 <= value <= 0.4 + 1e-9 for value in weights.values())
    with pytest.raises(ValueError, match="inviable"):
        pl.allocate(names, matrix, "capped", cap_pct=0.2)
    firm_cap = pl.allocate(names, matrix, "capped", cap_pct=0.02, risk_pct=0.005)
    assert firm_cap == pl.allocate(names, matrix, "inverse_vol")
    assert all(0.005 * value <= 0.02 for value in firm_cap.values())


def test_parse_strategies():
    assert pl.parse_strategies(" ftmo-eurusd, 3, , ftmo-eurusd ") == ("ftmo-eurusd", "3")
    with pytest.raises(ValueError, match="desconocida"):
        pl.load_series(["no-existe"], db_path=None)


def test_retornos_de_subyacente_se_rechazan(tmp_path):
    oracle = tmp_path / "reports" / "research" / "oracles"
    oracle.mkdir(parents=True)
    index = pd.date_range("2024-01-01", periods=288, freq="15min", tz="UTC")
    pd.DataFrame({"returns": np.linspace(0.001, 0.002, 288)}, index=index).to_parquet(
        oracle / "signals_eurusd-london-pullback.parquet"
    )
    with pytest.raises(ValueError, match="Sin datos") as exc:
        pl.load_forward("ftmo-eurusd", root=tmp_path)
    assert "riesgo inicial por operación" in str(exc.value)
    with pytest.raises(ValueError, match="Sin datos"):
        pl.load_series(["ftmo-eurusd", "syn-0"], root=tmp_path)


def test_ai_forward_usa_r_por_operacion(tmp_path):
    db = tmp_path / "lab.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE ai_trades (ts TEXT, symbol TEXT, setup TEXT, exit_ts TEXT, "
        "risk_usd REAL, pnl REAL, r_multiple REAL, status TEXT, source TEXT)"
    )
    con.executemany(
        "INSERT INTO ai_trades VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("2026-01-01T10:00:00+00:00", "XAUUSD", "orb_5m", "2026-01-01T10:05:00+00:00", 250.0, 250.0, 1.0, "closed", "forward"),
            ("2026-01-01T11:00:00+00:00", "XAUUSD", "orb_5m", "2026-01-01T11:05:00+00:00", 250.0, -125.0, -0.5, "closed", "forward"),
            ("2026-01-02T11:00:00+00:00", "XAUUSD", "orb_5m", "2026-01-02T11:05:00+00:00", 250.0, 500.0, 2.0, "closed", "forward"),
            ("2026-01-03T11:00:00+00:00", "XAUUSD", "orb_5m", None, 250.0, None, None, "proposed", "forward"),
        ],
    )
    con.commit()
    before = db.read_bytes()
    con.close()
    series = pl.load_ai_trades("XAUUSD", "orb_5m", db_path=db)
    assert series.trade_r == (1.0, -0.5, 2.0)
    assert series.daily_r == pytest.approx((0.5, 2.0))
    assert series.trade_dates == (date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 2))
    assert series.dates == (date(2026, 1, 1), date(2026, 1, 2))
    assert series.granularity == "operacion_R"
    assert "riesgo_usd declarado" in series.source
    assert db.read_bytes() == before


def test_carga_discovery_solo_tramos_permitidos(tmp_path):
    db = tmp_path / "discovery.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE disc_strategies (id INTEGER, instrument TEXT, level INTEGER, "
        "status TEXT, verdict TEXT)"
    )
    con.execute(
        "INSERT INTO disc_strategies VALUES (1, 'US100.CASH', 3, 'finalist', 'MODERADA')"
    )
    con.execute(
        "CREATE TABLE disc_evaluations (id INTEGER, strategy_id INTEGER, segment TEXT, "
        "metrics_json TEXT, returns_blob BLOB)"
    )
    values = np.array([0.5, -0.25, 0.75, -0.5], dtype=np.float32)
    blob = zlib.compress(values.tobytes())
    stamps = [f"2024-01-0{day}T00:00:00" for day in range(2, 6)]
    metrics = json.dumps({"return_dates": stamps})
    con.executemany(
        "INSERT INTO disc_evaluations VALUES (?, ?, ?, ?, ?)",
        [(1, 1, "fitness_is", metrics, blob), (2, 1, "oos1", metrics, blob)],
    )
    con.commit()
    before = db.read_bytes()
    con.close()
    series = pl.load_discovery(1, db_path=db)
    assert len(series.daily_r) == 8
    assert series.source.startswith("discovery:nivel=3")
    assert series.granularity == "dia_R_agregado_por_cierre"
    assert series.trade_r == ()
    assert db.read_bytes() == before


def test_discovery_sin_operaciones_marca_breach_sin_datos(tmp_path):
    discovery = pl.load_discovery(94)
    synthetic = pl.synthetic_preset(0.0, days=300, seed=7)[0]
    report = pl.challenge_report(
        [discovery, synthetic],
        {"equal": pl.allocate([discovery.name, synthetic.name], pl.align([discovery, synthetic])[1], "equal")},
        pl.account_context("CFD-001"),
        paths=100,
        seed=1,
    )
    for row in report["results"].values():
        assert row["p_romper_cualquiera"] is None
        assert "Sin datos" in row["trade_basis"]


def test_cli_analyze_json():
    result = CliRunner().invoke(
        cli_mod.app,
        [
            "portfolio",
            "analyze",
            "--strategies",
            "syn-50",
            "--account",
            "CFD-001",
            "--paths",
            "60",
            "--seed",
            "1",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["members"]) == 3
    assert "cartera:equal" in payload["challenge"]["results"]
    assert payload["verdict"]["equal"]
    assert payload["members"][0]["granularity"] == "operacion_R"


def test_cli_cuenta_desconocida():
    result = CliRunner().invoke(
        cli_mod.app,
        ["portfolio", "analyze", "--strategies", "syn-0", "--account", "NO-EXiste"],
    )
    assert result.exit_code == 1
    assert "cuenta desconocida" in result.output


def test_cli_rechaza_backtest_congelado():
    result = CliRunner().invoke(
        cli_mod.app,
        ["portfolio", "analyze", "--strategies", "us100-trend-d1,syn-0", "--account", "CFD-001"],
    )
    assert result.exit_code == 1
    assert "Sin datos" in result.output
