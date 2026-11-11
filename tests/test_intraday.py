from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.intraday import (
    BARS_PER_SESSION,
    _bars_per_year,
    asian_range_reversal,
    backtest_intraday,
    break_even_cost_bps,
    cache_metadata,
    families_for_symbol,
    fix_flow,
    load_bars,
    london_pullback,
    opening_range_breakout,
    orb_ny,
    overlap_breakout,
    range_reversal,
    render_markdown,
    run_intraday,
    save_bars,
    session_hold,
    session_trend,
    tokyo_breakout,
    trend_intraday,
    trend_pullback,
    write,
)
from tradinglab.intraday_costs import asset_costs


def _bars(days: int = 60, spread: bool = True) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=days * 96, freq="15min", tz="UTC")
    rng = np.random.default_rng(5)
    drift = np.sin(np.arange(len(idx)) / 120.0) * 0.0004
    close = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.0008, len(idx)) + drift))
    frame = pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.0001, len(idx))),
            "high": close * 1.0004,
            "low": close * 0.9996,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )
    if spread:
        frame["spread"] = 10.0
    return frame


@pytest.mark.parametrize(
    ("timeframe", "bars_per_session", "bars_per_year"),
    [
        ("M1", 1440, 252 * 1440),
        ("M5", 288, 252 * 288),
        ("M15", 96, 252 * 96),
        ("M30", 48, 252 * 48),
        ("H1", 24, 252 * 24),
        ("H4", 6, 252 * 6),
        ("D1", 1, 252),
    ],
)
def test_bars_per_year_por_timeframe(
    timeframe: str, bars_per_session: int, bars_per_year: int
) -> None:
    assert BARS_PER_SESSION[timeframe] == bars_per_session
    assert _bars_per_year(timeframe) == bars_per_year
    assert _bars_per_year(timeframe.lower()) == bars_per_year


@pytest.mark.parametrize("timeframe", ["M7", "1d", "W1", "", "D"])
def test_bars_per_year_timeframe_desconocido_falla(timeframe: str) -> None:
    with pytest.raises(ValueError, match="timeframe desconocido"):
        _bars_per_year(timeframe)


def test_cache_roundtrip(tmp_path):
    df = _bars(days=3)
    path = save_bars(df, tmp_path, "EURUSD", "M15")
    assert path.exists()
    loaded = load_bars(tmp_path, "EURUSD", "M15")
    assert len(loaded) == len(df)
    meta = cache_metadata(loaded, "M15")
    assert meta["rows"] == len(df)
    assert meta["years"] > 0


def test_backtest_intraday_costes_y_spread():
    df = _bars()
    target = opening_range_breakout(df).target
    result = backtest_intraday(df, target, timeframe="M15")
    assert result["metrics"]["bars"] == len(df)
    assert result["metrics"]["num_trades"] >= 0
    assert "returns" in result and "equity" in result
    assert result["spread_reliable"] is True
    no_spread = df.drop(columns=["spread"])
    assert backtest_intraday(no_spread, target, timeframe="M15")["spread_reliable"] is False


def test_backtest_usa_spread_de_ticks_por_hora():
    df = _bars(days=2).drop(columns=["spread"])
    target = opening_range_breakout(df).target
    hourly = pd.Series({hour: 2.0 for hour in range(24)})
    result = backtest_intraday(
        df,
        target,
        timeframe="M15",
        tick_spread_bps=hourly,
    )
    assert result["spread_source"] == "ticks"
    assert result["spread_tick_hours"] == 24
    assert result["spread_bps_median"] == pytest.approx(2.0)
    assert result["spread_reliable"] is True


def test_backtest_spread_override_label_y_reliable():
    df = _bars(days=2).drop(columns=["spread"])
    target = opening_range_breakout(df).target
    result = backtest_intraday(
        df,
        target,
        timeframe="M15",
        spread_override_bps=2.0,
        spread_override_reliable=True,
        spread_label="broker: MT5 ticks p75",
    )
    assert result["spread_source"] == "broker: MT5 ticks p75"
    assert result["spread_reliable"] is True
    assert result["spread_bps_median"] == pytest.approx(2.0)


def test_run_intraday_atribuye_spread_de_ticks():
    df = _bars(days=30).drop(columns=["spread"])
    hourly = pd.Series({hour: 1.5 for hour in range(24)})
    report = run_intraday(df, paths=5, tick_spread_bps=hourly)
    assert "Dukascopy" in report["cost_model"]["spread"]["source"]
    assert report["cost_model"]["spread"]["tick_hours"] == 24


def test_backtest_zero_costs_es_diagnostico():
    df = _bars()
    target = opening_range_breakout(df).target
    normal = backtest_intraday(df, target, timeframe="M15")
    zero = backtest_intraday(
        df,
        target,
        timeframe="M15",
        commission_bps=0.0,
        slippage_bps=0.0,
        spread_override_bps=0.0,
    )
    assert zero["spread_reliable"] is True
    assert zero["spread_bps_median"] == 0.0
    assert zero["spread_observed_bps_median"] > 0
    assert zero["metrics"]["sharpe"] >= normal["metrics"]["sharpe"]


def test_run_intraday_marca_costes_cero():
    df = _bars(days=30)
    report = run_intraday(
        df,
        paths=10,
        commission_bps=0.0,
        slippage_bps=0.0,
        slippage_optimistic_bps=0.0,
        spread_override_bps=0.0,
    )
    assert report["costs"]["diagnostic_zero_costs"] is True
    assert "Diagnóstico zero-cost" in render_markdown(report)


def test_costes_eurusd_oficiales():
    cost = asset_costs("EURUSD")
    assert cost.verified is True
    assert cost.commission_per_lot_usd == pytest.approx(2.50)
    assert cost.commission_side == "per_side"
    assert "2025-09-25" in (cost.source_date or "")
    bps = cost.commission_bps(pd.Series([1.10]))
    assert float(bps.iloc[0]) == pytest.approx(2.50 / 110_000 * 10_000, rel=1e-6)


def test_costes_por_tipo_de_activo():
    usdjpy = asset_costs("USDJPY")
    assert usdjpy.verified is True
    assert float(usdjpy.commission_bps(pd.Series([150.0])).iloc[0]) == pytest.approx(
        2.50 / 100_000 * 10_000, rel=1e-6
    )
    xau = asset_costs("XAUUSD")
    assert xau.verified is True
    assert float(xau.commission_bps(pd.Series([2400.0])).iloc[0]) == pytest.approx(
        0.07, rel=1e-6
    )
    nasdaq = asset_costs("US100.CASH")
    assert nasdaq.verified is True
    assert float(nasdaq.commission_bps(pd.Series([20_000.0])).iloc[0]) == 0.0


def test_familias_por_activo():
    assert families_for_symbol("US100.CASH") == (
        "orb_ny",
        "trend_intraday",
        "caja_ny",
    )
    assert families_for_symbol("XAUUSD") == ("asian_rev", "overlap_breakout")
    assert families_for_symbol("EURUSD") == (
        "range_reversal",
        "london_pullback",
        "session_hold",
        "fix_flow",
    )
    assert families_for_symbol("USDJPY") == (
        "session_trend",
        "tokyo_breakout",
        "session_hold",
        "fix_flow",
    )


def test_nuevas_familias_generan_targets():
    df = _bars(days=45)
    for fn in (
        range_reversal,
        orb_ny,
        trend_intraday,
        overlap_breakout,
        london_pullback,
        session_trend,
        tokyo_breakout,
        session_hold,
        fix_flow,
    ):
        result = fn(df)
        assert len(result.target) == len(df)
        assert result.target.abs().max() <= 1.0


def test_session_hold_el_stop_atreve_una_sesion():
    """Con un stop muy corto la posición se cierra antes del cierre de sesión."""
    df = _bars(days=45)
    abierto = session_hold(df, session="LDN", direction=1, atr_k=0.01).target
    ancho = session_hold(df, session="LDN", direction=1, atr_k=50.0).target
    assert float(abierto.abs().sum()) < float(ancho.abs().sum())
    assert float(ancho.abs().sum()) > 0.0


def test_fix_flow_solo_opera_en_la_ventana_del_fix():
    df = _bars(days=45)
    target = fix_flow(df, window_min=60, side="long_usd", fix="ecb").target
    assert float(target.abs().sum()) > 0.0
    assert set(target.unique().tolist()) <= {-1.0, 0.0, 1.0}


def test_write_guarda_informe_por_activo(tmp_path):
    df = _bars(days=30)
    report = run_intraday(df, symbol="EURUSD", paths=10)
    files = write(report, tmp_path)
    assert Path(files["json"]).exists()
    assert Path(files["asset_json"]).exists()
    assert "EURUSD" in Path(files["asset_json"]).name
    assert "EURUSD" in Path(files["asset_md"]).name


def test_simbolo_sin_comision_verificada_no_inventa():
    cost = asset_costs("BTCUSD")
    assert cost.verified is False
    with pytest.raises(RuntimeError, match="sin verificar"):
        run_intraday(_bars(days=3), symbol="BTCUSD", paths=5)


def test_break_even_cost_bps_sintetico():
    gross = pd.Series([0.002 if index % 2 == 0 else 0.001 for index in range(200)])
    turnover = pd.Series(1.0, index=gross.index)
    # media 0.0015 => 15 bps de coste uniforme llevan el Sharpe a 0
    assert break_even_cost_bps(gross, turnover, "M15") == pytest.approx(15.0, abs=0.1)


def test_curva_de_costes_y_modelo():
    df = _bars(days=30)
    report = run_intraday(df, paths=10)
    model = report["cost_model"]
    assert model["commission"]["verified"] is True
    assert model["commission"]["source_date"] == "2025-09-25"
    assert model["slippage"]["optimistic_bps"] == pytest.approx(0.5)
    assert model["slippage"]["conservative_bps"] == pytest.approx(2.0)
    row = report["outcomes"][0]
    assert set(row["cost_curve_bps"]) == {"0.0", "0.5", "1.0", "2.0", "3.0"}
    assert row["calibrated_cost_bps"] > 0
    assert "Coste de equilibrio" in render_markdown(report)


def test_run_intraday_registra_las_variantes_probadas(tmp_path):
    from tradinglab.trials import list_trials

    db = tmp_path / "lab.db"
    df = _bars(days=30)
    report = run_intraday(df, paths=10, db_path=db)
    assert report["trials_recorded"] == len(report["outcomes"])
    rows = list_trials(db, limit=500)
    assert len(rows) == report["trials_recorded"]
    assert {row["outcome"] for row in rows} <= {"passed", "failed"}
    assert all(row["reason"] for row in rows if row["outcome"] == "failed")
    assert all(row["hypothesis"] for row in rows)
    assert all(row["run_id"] == report["run_id"] for row in rows)


def test_recalculo_no_cambia_contador_dsr(tmp_path):
    from tradinglab.learning import count_tests
    from tradinglab.trials import record_trial

    db = tmp_path / "lab.db"
    record_trial(
        db,
        family="seed",
        hypothesis="seed",
        symbol="EURUSD",
        outcome="failed",
        source="sweep",
    )
    before = count_tests(db)
    df = _bars(days=30).drop(columns=["spread"])
    report = run_intraday(
        df,
        symbol="EURUSD",
        paths=5,
        families=("range_reversal",),
        db_path=db,
        record=False,
        dsr_n_trials=before,
        spread_override_bps=2.0,
        spread_override_reliable=True,
        spread_label="broker: MT5 ticks p75",
        recalculation={"enabled": True, "reason": "test sintético"},
    )
    assert report["trials_recorded"] == 0
    assert report["dsr_n_trials"] == before
    assert report["recalculation"]["dsr_counter_unchanged"] is True
    assert report["recalculation"]["strategy_trials_before"] == before
    assert report["recalculation"]["strategy_trials_after"] == before
    assert count_tests(db) == before
    assert report["cost_model"]["spread"]["source"] == "broker: MT5 ticks p75"
    assert report["cost_model"]["spread"]["stat"] == "p75"
    markdown = render_markdown(report)
    assert "Recálculo de coste" in markdown
    assert "no se crearon trials nuevos" in markdown


def test_tres_estrategias_generan_targets():
    df = _bars()
    for fn in (opening_range_breakout, trend_pullback, asian_range_reversal):
        result = fn(df)
        assert len(result.target) == len(df)
        assert result.target.abs().max() <= 1.0


def test_run_intraday_controles_y_tabla():
    df = _bars(days=90)
    report = run_intraday(df, paths=20)
    assert report["n_trials"] > 0
    assert report["pbo"] is not None
    assert report["walk_forward"] is not None
    assert "outcomes" in report and "monte_carlo" in report
    assert report["passed"] == 0  # sin regímenes históricos 2018/2020/2022
    md = render_markdown(report)
    assert "Investigación intradía" in md
    assert "Monte Carlo" in md
