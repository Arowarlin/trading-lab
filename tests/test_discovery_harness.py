"""T01 · Arnés de autoevaluación: nulo, potencia, barras y CLI."""

from __future__ import annotations

from datetime import date

import pytest
from typer.testing import CliRunner

from tradinglab.cli import app
from tradinglab.discovery import harness


@pytest.fixture(scope="module")
def years() -> dict[str, float]:
    return harness.segment_years(today=date(2026, 11, 24))


def test_nulo_no_aprueba_en_ninguna_frecuencia(years):
    for frequency in (12, 50, 250, 1000):
        row = harness.simulate_gates(
            frequency=frequency,
            edge=0.0,
            simulations=1000,
            seed=7,
            years=years,
        )
        assert row.p_approve < 0.05, (frequency, row)
        assert row.ci_high < 0.05, (frequency, row)


def test_ventaja_alta_aprueba(years):
    row = harness.simulate_gates(
        frequency=1000,
        edge=0.5,
        simulations=1000,
        seed=7,
        years=years,
    )
    assert row.p_approve > 0.90, row


def test_arnes_reproducible(years):
    first = harness.simulate_gates(
        frequency=250, edge=0.1, simulations=300, seed=11, years=years
    )
    second = harness.simulate_gates(
        frequency=250, edge=0.1, simulations=300, seed=11, years=years
    )
    assert first == second


def test_bars_recupera_la_ventaja(years):
    row = harness.simulate_bars(edge=0.2, trades=500, seed=11)
    assert row.trades == 500
    assert row.passed, row
    assert row.recovered_mean_r == pytest.approx(row.expected_r, abs=0.10)
    assert row.cost_r == pytest.approx(0.0002 * 10_000 / 300, rel=1e-9)


@pytest.mark.parametrize("edge", [0.0, 0.05, 0.1, 0.2])
def test_bars_sin_ruido_recupera_delta_menos_coste(edge):
    row = harness.simulate_bars(
        edge=edge, trades=200, seed=7, sigma_pct=0.0
    )
    assert row.recovered_mean_r == pytest.approx(edge - row.cost_r, abs=1e-9)
    assert row.passed


def test_bars_cinco_semillas_oscilan_alrededor_del_esperado():
    rows = [
        harness.simulate_bars(edge=0.1, trades=300, seed=seed)
        for seed in (1, 2, 3, 4, 5)
    ]
    expected = 0.1 - rows[0].cost_r
    for row in rows:
        assert row.recovered_mean_r == pytest.approx(expected, abs=0.12)
        assert row.passed
    assert len({round(row.recovered_mean_r, 6) for row in rows}) == 5


def test_cli_harness_escribe_el_informe(tmp_path):
    destination = tmp_path / "harness.md"
    result = CliRunner().invoke(
        app,
        [
            "discovery",
            "harness",
            "--mode",
            "bars",
            "--edge",
            "0.2",
            "--sims",
            "60",
            "--seed",
            "7",
            "--output",
            str(destination),
        ],
    )
    assert result.exit_code == 0, result.output
    assert destination.exists()
    text = destination.read_text(encoding="utf-8")
    assert "Recuperación de la ventaja" in text
    assert "0.2" in text
