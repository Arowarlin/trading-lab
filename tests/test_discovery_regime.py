"""Regímenes sobre retorno de cuenta y sin años fuera del tramo."""

from __future__ import annotations

import pandas as pd

from tradinglab.discovery.robustness import account_regime


def _series(start: str, end: str, value: float = 0.2) -> pd.Series:
    index = pd.bdate_range(start, end, tz="UTC")
    return pd.Series(value, index=index, dtype=float)


def test_regimen_2021_2025_pasa_sin_exigir_2018_2020() -> None:
    report = account_regime(_series("2021-10-04", "2025-06-27"), 0.005)

    assert report["passed"] is True
    assert report["missing"] == []
    assert set(report["years"]) == {"2021", "2022", "2023", "2024", "2025"}


def test_regimen_2022_negativo_falla_por_2022() -> None:
    daily = _series("2021-10-04", "2025-06-27")
    daily[daily.index.year == 2022] = -0.2
    report = account_regime(daily, 0.005)

    assert report["passed"] is False
    assert any("2022" in reason for reason in report["reasons"])
    assert not any("2018" in reason or "2020" in reason for reason in report["reasons"])


def test_regimen_solo_exige_anos_presentes() -> None:
    report = account_regime(_series("2021-10-04", "2023-12-29"), 0.005)

    assert report["passed"] is True
    assert set(report["years"]) == {"2021", "2022", "2023"}
    assert not {"2024", "2025"} & set(report["years"])


def test_regimen_escala_r_por_riesgo_de_cuenta() -> None:
    daily = _series("2022-01-03", "2022-12-30", value=0.1)
    low = account_regime(daily, 0.005)
    high = account_regime(daily, 0.01)

    low_return = low["years"]["2022"]["total_return"]
    high_return = high["years"]["2022"]["total_return"]
    assert high_return > low_return > 0.0
    assert low["risk_per_trade_pct"] == 0.005
    assert high["risk_per_trade_pct"] == 0.01


def test_regimen_riesgo_ausente_es_sin_datos() -> None:
    from tradinglab.discovery import robustness

    report = robustness._regime(_series("2022-01-03", "2022-12-30"), None)
    assert report["status"] == "Sin datos"
    assert report["passed"] is False
