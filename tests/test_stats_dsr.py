from __future__ import annotations

import math

import numpy as np
import pytest

from tradinglab.stats import (
    METRIC_VERSION,
    StatsError,
    deflated_sharpe,
    dsr_from_returns,
    dsr_local_global,
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


def test_local_y_global_no_mezclan_n_con_dispersion():
    rng = np.random.default_rng(19)
    returns = rng.normal(0.008, 0.01, 500)
    payload = dsr_local_global(
        returns,
        [0.0, 0.5],
        list(np.linspace(-0.9, 0.9, 60)),
        2,
        1_000,
    )
    assert payload["local"]["dsr"] is not None
    assert payload["local"]["dsr"] > 0.95
    assert payload["local"]["n_trials"] == 2
    assert payload["global"]["dsr"] is not None
    assert payload["global"]["dsr"] < 0.95
    assert payload["global"]["n_trials"] == 1_000
    assert payload["global"]["n_series"] == 60

    missing = dsr_local_global(
        returns, [0.0, 0.5], [0.1] * 29, 2, 1_000
    )
    assert missing["global"]["dsr"] is None
    assert missing["global"]["status"] == "Sin datos"
    assert "29" in missing["global"]["reason"]


def test_psr_vs_cero_para_un_solo_finalista():
    rng = np.random.default_rng(13)
    returns = rng.normal(0.004, 0.01, 400)
    without = dsr_from_returns(returns, [], 1)
    assert without["dsr"] is None
    assert without["status"] == "Sin datos"

    payload = dsr_from_returns(returns, [], 1, benchmark_sr=0.0)
    assert payload["status"] == "ok"
    assert payload["dsr"] is not None
    assert payload["sr0_period"] == 0.0
    direct = deflated_sharpe(
        period_sharpe(returns),
        len(returns),
        payload["skew"],
        payload["kurt"],
        0.0,
        1,
        benchmark_sr=0.0,
    )
    assert payload["dsr"] == pytest.approx(direct)


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
