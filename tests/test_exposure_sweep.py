from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

import tradinglab.exposure_sweep as sweep_mod
from tradinglab.cli import app
from tradinglab.exposure_sweep import (
    SweepError,
    _horizon_blocks,
    artifact_file,
    funded_month_payout,
    load_artifact,
    recommendation,
    run_sweep,
    save_artifact,
    sweep,
)
from tradinglab.prop.rules import ftmo


def _returns(
    n: int = 400,
    *,
    mean: float = 0.0,
    vol: float = 0.001,
    seed: int = 5,
) -> pd.Series:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2023-01-02", periods=n, tz="UTC")
    return pd.Series(rng.normal(mean, vol, n), index=index)


def test_k_escala_el_maxdd_sin_reventar():
    returns = _returns(300, mean=0.0, vol=0.001)
    rules = ftmo(100_000.0, "challenge")
    low = sweep(
        returns, rules, k_values=(0.5, 1.0), paths=400, oracle=False, eurusd=1.1
    )
    medians = {
        row["k"]: row["sin_limite"]["median_max_drawdown"] for row in low["rows"]
    }
    assert medians[0.5] < 0
    assert medians[1.0] < 0
    ratio = medians[0.5] / medians[1.0]
    assert 0.4 <= ratio <= 0.6, ratio
    # y el peor 5 % también se escala
    p5 = {row["k"]: row["sin_limite"]["p5_max_drawdown"] for row in low["rows"]}
    assert p5[0.5] > p5[1.0]


def test_el_horizonte_sin_limite_termina():
    returns = _returns(300, mean=0.01, vol=0.002)
    rules = ftmo(100_000.0, "challenge")
    payload = sweep(
        returns, rules, k_values=(1.0,), paths=200, oracle=False, eurusd=1.1
    )
    row = payload["rows"][0]["sin_limite"]
    assert row["pass_rate"] > 0.9
    assert row["timeout_rate"] <= 0.01
    assert row["pass_rate"] + row["breach_rate"] + row["timeout_rate"] == pytest.approx(1.0)


def test_el_horizonte_se_pasa_en_bloques():
    assert _horizon_blocks(120, 5) == 24
    assert _horizon_blocks(750, 5) == 150
    assert _horizon_blocks(7, 5) == 2


def test_el_artefacto_va_y_vuelve(tmp_path):
    returns = _returns(200)
    saved = save_artifact(
        "bot-x", tmp_path, returns, meta={"run_id": "abc", "symbol": "XAUUSD"}
    )
    assert Path(saved["path"]).exists()
    loaded = load_artifact("bot-x", tmp_path)
    assert loaded["meta"]["run_id"] == "abc"
    assert len(loaded["returns"]) == len(returns)
    assert loaded["returns"].iloc[0] == pytest.approx(float(returns.iloc[0]))


def test_sin_artefacto_falla(tmp_path):
    with pytest.raises(SweepError, match="falta el artefacto"):
        load_artifact("no-existe", tmp_path)


def test_el_mes_fondeado_paga_cero_si_revienta():
    returns = _returns(200, mean=-0.05, vol=0.001)
    rules = ftmo(100_000.0, "challenge")
    month = funded_month_payout(
        returns, k=1.0, account=100_000.0, split=0.8, rules=rules, paths=100
    )
    assert month["breach_rate"] == 1.0
    assert month["expected_payout_usd"] == 0.0


def test_economia_lee_prop_yaml_si_existe(tmp_path, monkeypatch):
    path = tmp_path / "prop.yaml"
    path.write_text(
        yaml.safe_dump({"economics": {"challenge_fee_eur": 300, "profit_split": 0.9}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sweep_mod, "PROP_CONFIG", path)
    economics = sweep_mod._economics(None, None)
    assert economics["fee_eur"] == 300
    assert economics["profit_split"] == 0.9
    # los parámetros explícitos mandan
    override = sweep_mod._economics(540, 0.8)
    assert override["fee_eur"] == 540
    assert override["profit_split"] == 0.8


def test_recomendacion_negativa_y_positiva():
    negative = {
        "rows": [
            {"k": 0.5, "ev_eur": -10.0},
            {"k": 1.0, "ev_eur": -1.0},
        ]
    }
    rec = recommendation(negative)
    assert rec["positive"] is False
    assert rec["text"] == "no es EV positivo a ninguna k"
    positive = {"rows": [{"k": 0.5, "ev_eur": 5.0}, {"k": 1.0, "ev_eur": 50.0}]}
    rec = recommendation(positive)
    assert rec["positive"] is True
    assert rec["k"] == 1.0


def test_el_barrido_escribe_informe_y_lee_el_artefacto(tmp_path, monkeypatch):
    returns = _returns(300, mean=0.002, vol=0.004)
    save_artifact(
        "bot-x",
        tmp_path,
        returns,
        meta={
            "run_id": "run-1",
            "symbol": "US100.CASH",
            "params": {"fast": 50, "slow": 200, "stop_atr": 3.0},
            "source": "test",
        },
    )
    monkeypatch.setattr(
        sweep_mod,
        "eurusd_rate",
        lambda cache_dir: {"rate": 1.1, "timeframe": "H1", "as_of": "test", "source": "test"},
    )
    payload = run_sweep(
        "bot-x",
        out_dir=tmp_path,
        paths=100,
        oracle=False,
        bootstrap=0,
    )
    assert payload["bot"] == "bot-x"
    assert payload["variant"]["fast"] == 50
    assert payload["recommendation"]["positive"] in (True, False)
    markdown = Path(payload["files"]["markdown"]).read_text(encoding="utf-8")
    assert "Barrido de exposición" in markdown
    assert "k óptima" in markdown or "no es EV positivo" in markdown
    saved = json.loads(Path(payload["files"]["json"]).read_text(encoding="utf-8"))
    assert saved["artifact"] == str(artifact_file(tmp_path, "bot-x"))


def test_cli_muestra_la_tabla(tmp_path, monkeypatch):
    returns = _returns(300, mean=0.002, vol=0.004)
    save_artifact("bot-cli", tmp_path, returns, meta={"run_id": "r", "symbol": "X"})
    monkeypatch.setattr(
        sweep_mod,
        "eurusd_rate",
        lambda cache_dir: {"rate": 1.1, "timeframe": "H1", "as_of": "test", "source": "test"},
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "prop",
            "exposure-sweep",
            "--bot",
            "bot-cli",
            "--out",
            str(tmp_path),
            "--paths",
            "50",
            "--bootstrap",
            "0",
            "--no-oracle",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "P(pasar)" in result.output
    assert "EV neto" in result.output


def test_el_reembolso_cambia_el_ev():
    returns = _returns(300, mean=0.002, vol=0.004)
    rules = ftmo(100_000.0, "challenge")
    with_refund = sweep(
        returns,
        rules,
        k_values=(0.5, 1.0),
        paths=500,
        oracle=False,
        eurusd=1.1,
        fee_refund_on_pass=True,
    )
    without = sweep(
        returns,
        rules,
        k_values=(0.5, 1.0),
        paths=500,
        oracle=False,
        eurusd=1.1,
        fee_refund_on_pass=False,
    )
    fee = with_refund["economics"]["fee_eur"]
    for row, old in zip(with_refund["rows"], without["rows"]):
        expected = row["sin_limite"]["pass_rate"] * fee
        assert row["ev_eur"] - old["ev_eur"] == pytest.approx(expected, abs=1e-6)
        assert row["ev_no_refund_eur"] == pytest.approx(old["ev_eur"], abs=1e-9)


def _sparse_series(days: int, trades: int, seed: int = 11) -> pd.Series:
    """Serie diaria con `trades` días de movimiento y el resto planos."""
    rng = np.random.default_rng(seed)
    values = np.zeros(days)
    positions = rng.choice(days - 1, size=trades, replace=False)
    values[positions] = rng.normal(0.02, 0.03, size=trades)
    index = pd.bdate_range("2010-01-04", periods=days, tz="UTC")
    return pd.Series(values, index=index)


def test_el_ic_se_estrecha_con_mas_operaciones():
    rules = ftmo(100_000.0, "challenge")
    short = sweep(
        _sparse_series(300, 6),
        rules,
        k_values=(1.0,),
        paths=400,
        oracle=False,
        eurusd=1.1,
        bootstrap=60,
        bootstrap_paths=400,
    )
    long = sweep(
        _sparse_series(3000, 60),
        rules,
        k_values=(1.0,),
        paths=400,
        oracle=False,
        eurusd=1.1,
        bootstrap=60,
        bootstrap_paths=400,
    )
    short_ci = short["rows"][0]["ci90"]
    long_ci = long["rows"][0]["ci90"]
    assert short_ci["low"] is not None and long_ci["low"] is not None
    width_short = short_ci["high"] - short_ci["low"]
    width_long = long_ci["high"] - long_ci["low"]
    assert width_long < width_short, (width_short, width_long)
