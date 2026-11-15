from __future__ import annotations

import math

import numpy as np
import pytest

from tradinglab.stats import (
    METRIC_VERSION,
    StatsError,
    deflated_sharpe,
    dsr_from_returns,
    period_sharpe,
)


def test_ejemplo_publicado_bailey_lopez_de_prado():
    # SR anual 2,5 -> SR por periodo 2,5/sqrt(250); V[SR] = 0,5/250.
    dsr = deflated_sharpe(
        2.5 / math.sqrt(250),
        1_250,
        -3.0,
        10.0,
        math.sqrt(0.5 / 250),
        100,
    )
    assert dsr == pytest.approx(0.9004, abs=0.001)


def test_mejor_de_500_series_de_ruido_no_pasa_el_filtro():
    rng = np.random.default_rng(7)
    returns = [rng.normal(0.0, 0.01, 750) for _ in range(500)]
    trial_srs = [period_sharpe(series) for series in returns]
    best = max(range(len(returns)), key=lambda index: trial_srs[index])
    payload = dsr_from_returns(returns[best], trial_srs, 500, periods_per_year=252)
    assert payload["metric_version"] == METRIC_VERSION
    assert payload["dsr"] is not None
    assert payload["dsr"] < 0.95


def test_media_positiva_clara_con_dos_pruebas():
    rng = np.random.default_rng(11)
    returns = rng.normal(0.008, 0.01, 500)
    payload = dsr_from_returns(returns, [0.0, 0.5], 2)
    assert payload["dsr"] is not None
    assert payload["dsr"] > 0.95


def test_sharpe_por_periodo_mayor_que_uno_es_error_de_unidades():
    rng = np.random.default_rng(3)
    returns = rng.normal(0.03, 0.01, 300)
    assert period_sharpe(returns) > 1.0
    with pytest.raises(StatsError, match="anualizada"):
        dsr_from_returns(returns, [0.1, 0.2], 10)


def test_periods_per_year_solo_anualiza_para_el_informe():
    rng = np.random.default_rng(5)
    returns = rng.normal(0.001, 0.01, 400)
    without = dsr_from_returns(returns, [0.01, 0.02], 10)
    with_year = dsr_from_returns(
        returns, [0.01, 0.02], 10, periods_per_year=252
    )
    assert without["dsr"] == pytest.approx(with_year["dsr"])
    assert without["annualized_sr"] is None
    assert with_year["annualized_sr"] == pytest.approx(
        with_year["sr_period"] * math.sqrt(252)
    )
