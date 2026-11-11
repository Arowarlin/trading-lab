from __future__ import annotations

import json

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from tradinglab import cli as cli_mod
from tradinglab.backtest import run as run_backtest
from tradinglab.export_signals import build_export, effective_target, export_signals


def frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(closes), freq="D", tz="UTC")
    values = np.array(closes, dtype=float)
    return pd.DataFrame(
        {
            "open": values,
            "high": values * 1.002,
            "low": values * 0.998,
            "close": values,
            "volume": 1_000.0,
        },
        index=index,
    )


def test_effective_target_aplaza_una_barra():
    df = frame([100.0] * 5)
    target = pd.Series([1.0, 1.0, 0.0, 0.0, 0.0], index=df.index)
    effective = effective_target(df, target)
    assert effective.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]


def test_effective_target_fuera_de_sesion_es_cero():
    df = frame([100.0] * 5)
    target = pd.Series([1.0] * 5, index=df.index)
    effective = effective_target(df, target, session=("23:00", "23:30"), session_tz="UTC")
    assert effective.tolist() == [0.0] * 5


def test_export_escribe_parquet_con_primitivas(tmp_path):
    df = frame([100.0, 101.0, 102.0, 101.5, 100.5, 99.0])
    target = pd.Series([1.0, 1.0, 1.0, 0.0, 0.0, 0.0], index=df.index)
    bt = run_backtest(df, target, starting_cash=100_000.0, commission_bps=1.0, slippage_bps=5.0)
    out = tmp_path / "signals.parquet"
    export = export_signals(
        df,
        target,
        bt,
        out,
        symbol="TEST",
        strategy="trend test",
        commission_bps=1.0,
        slippage_bps=5.0,
        exposure=1.0,
    )
    assert out.exists()
    assert export.rows == len(bt.equity)

    frame_out = pd.read_parquet(out)
    assert frame_out.index.name == "date"
    for column in (
        "symbol",
        "target",
        "exec_price",
        "commission",
        "spread",
        "slippage",
    ):
        assert column in frame_out.columns

    traded = frame_out["qty"].abs() > 0
    assert traded.any()
    assert frame_out.loc[traded, "exec_price"].notna().all()
    assert (frame_out.loc[traded, "commission"] > 0).all()
    assert (frame_out.loc[~traded, "commission"] == 0).all()
    assert (frame_out.loc[traded, "slippage"] == 5.0).all()
    assert (frame_out.loc[~traded, "slippage"] == 0).all()
    assert (frame_out.loc[~traded, "exec_price"].isna()).all()

    # la equity exportada es la del motor
    pd.testing.assert_series_equal(
        frame_out["equity"].astype(float),
        bt.equity.astype(float),
        check_names=False,
    )

    meta = json.loads(export.meta_path.read_text(encoding="utf-8"))
    assert meta["symbol"] == "TEST"
    assert meta["executions"] == int(traded.sum())
    assert meta["engine_metrics"]["num_trades"] == len(meta["trade_pnls"])


def test_build_export_respeta_exposicion(tmp_path):
    df = frame([100.0, 101.0, 102.0])
    target = pd.Series([0.5, 0.5, 0.5], index=df.index)
    bt = run_backtest(df, target, starting_cash=100_000.0)
    built = build_export(
        df,
        target,
        bt,
        symbol="TEST",
        strategy="trend",
        commission_bps=1.0,
        slippage_bps=5.0,
        exposure=0.5,
    )
    assert (built["exposure"] == 0.5).all()
    assert built["target"].max() <= 0.5


def test_cli_backtest_expone_export_signals():
    result = CliRunner().invoke(cli_mod.app, ["backtest", "--help"])
    assert result.exit_code == 0
    assert "--export-signals" in result.output
    assert "--family" in result.output


def test_cli_backtest_rechaza_params_invalidos():
    result = CliRunner().invoke(
        cli_mod.app, ["backtest", "SPY", "--params", "{no-json}", "--export-signals", "x.parquet"]
    )
    assert result.exit_code == 2
