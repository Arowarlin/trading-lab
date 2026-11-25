"""T24 · SPRT de confirmación forward."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from tradinglab.discovery import sprt


def test_sprt_acepta_ventaja_real():
    returns = np.full(2000, 0.1)
    result = sprt.sprt(returns, delta=0.1, sigma=1.0)
    assert result["decision"] == "aceptar_ventaja"
    assert 20 < result["n_stopped"] < 1500
    assert result["llr"] >= result["A"]


def test_sprt_rechaza_nulo():
    returns = np.random.default_rng(7).normal(0.0, 1.0, 3000)
    result = sprt.sprt(returns, delta=0.1, sigma=1.0)
    assert result["decision"] == "rechazar"
    assert result["llr"] <= result["B"]


def test_wald_formulas():
    assert sprt.wald_expected_n(0.1) == pytest.approx(381.29, abs=0.5)
    assert sprt.wald_expected_n_null(0.1) == pytest.approx(268.32, abs=0.5)


def test_sprt_potencia_estadistica():
    rng = np.random.default_rng(2026)
    accepted = 0
    stops: list[int] = []
    for _ in range(1000):
        values = rng.normal(0.1, 1.0, 5000)
        result = sprt.sprt(values, delta=0.1, sigma=1.0)
        if result["decision"] == "aceptar_ventaja":
            accepted += 1
        stops.append(int(result["n_stopped"] or result["n"]))
    assert 0.76 <= accepted / 1000 <= 0.84
    assert 330 <= sum(stops) / len(stops) <= 450


def test_sprt_falso_positivo_nulo():
    rng = np.random.default_rng(99)
    accepted = 0
    for _ in range(1000):
        values = rng.normal(0.0, 1.0, 5000)
        result = sprt.sprt(values, delta=0.1, sigma=1.0)
        if result["decision"] == "aceptar_ventaja":
            accepted += 1
    assert accepted / 1000 <= 0.07


def test_carga_forward_coincidencia_exacta(monkeypatch):
    from tradinglab import journal

    trades = [
        SimpleNamespace(bot="us100", r_multiple=0.5),
        SimpleNamespace(bot="us100-ftmo1", r_multiple=9.0),
        SimpleNamespace(bot="forward:us100", r_multiple=-0.2),
    ]
    monkeypatch.setattr(
        journal, "load_closed_trades", lambda db_path: (trades, {})
    )
    values, reason = sprt.load_forward_returns("us100", db_path="ignored")
    assert reason == "OK"
    assert values == [0.5, -0.2]


def test_carga_forward_filtra_por_bot(monkeypatch):
    from tradinglab import journal

    trades = [
        SimpleNamespace(bot="forward:eurusd-london-pullback-forward", r_multiple=0.5),
        SimpleNamespace(bot="forward:eurusd-london-pullback-forward", r_multiple=-0.2),
        SimpleNamespace(bot="otro", r_multiple=9.0),
        SimpleNamespace(bot="forward:eurusd-london-pullback-forward", r_multiple=None),
    ]
    monkeypatch.setattr(
        journal, "load_closed_trades", lambda db_path: (trades, {})
    )
    values, reason = sprt.load_forward_returns(
        "eurusd-london-pullback-forward", db_path="ignored"
    )
    assert reason == "OK"
    assert values == [0.5, -0.2]


def test_cli_forward_sprt(monkeypatch):
    from typer.testing import CliRunner

    from tradinglab import cli

    monkeypatch.setattr(
        sprt, "load_forward_returns", lambda strategy, db_path=None: ([0.1] * 2000, "OK")
    )
    result = CliRunner().invoke(
        cli.app,
        ["forward", "sprt", "estrategia", "--delta", "0.1", "--sigma", "1"],
    )
    assert result.exit_code == 0, result.output
    assert "aceptar_ventaja" in result.output
