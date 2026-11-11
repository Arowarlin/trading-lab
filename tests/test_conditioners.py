from __future__ import annotations

from datetime import date

import pandas as pd

from tradinglab.conditioners import (
    boundary_flags,
    business_days_around,
    flags_series,
    fomc_dates,
)
from tradinglab.strategies.base import exposure_multiplier


def _close(values):
    index = pd.bdate_range("2023-01-02", periods=len(values))
    return pd.Series(values, index=index, dtype=float)


def test_exposure_multiplier_multiplica_los_flags_activos():
    assert exposure_multiplier({}, {"pre_fomc": 0.5}) == 1.0
    assert exposure_multiplier({"pre_fomc": True}, {"pre_fomc": 0.5}) == 0.5
    assert (
        exposure_multiplier(
            {"pre_fomc": True, "boundary_extreme": True},
            {"pre_fomc": 1.5, "boundary_extreme": 0.5},
        )
        == 0.75
    )
    assert exposure_multiplier({"pre_fomc": True}, None) == 1.0


def test_boundary_extreme_es_causal():
    close = _close([100.0] * 260 + [130.0, 131.0])
    flags = boundary_flags(close, window=252, k=2.0)
    # el día del salto todavía no se marca: la estadística va con t-1
    assert bool(flags.iloc[-2]) is False
    assert bool(flags.iloc[-1]) is True


def test_truncado_vs_completo_no_miran_al_futuro():
    close = _close([100.0] * 250 + [120.0, 118.0, 121.0])
    completo = boundary_flags(close, window=100, k=2.0)
    corte = close.index[-2]
    truncado = boundary_flags(close.loc[:corte], window=100, k=2.0)
    assert completo.loc[corte] == truncado.loc[corte]


def test_flags_series_sin_datos_de_calendario():
    close = _close([100.0 + index * 0.1 for index in range(300)])
    frame, warnings = flags_series("SPY", close, db_path=None)
    assert set(["pre_fomc", "tom_window", "month_end_selloff", "monday_overnight"]).issubset(
        frame.columns
    )
    assert not frame["pre_fomc"].any()
    assert warnings


def test_dias_habiles_alrededor():
    dias = business_days_around(date(2026, 11, 11), 2, 1)
    assert date(2026, 11, 11) in dias
    assert date(2026, 11, 10) in dias
    assert date(2026, 11, 12) in dias
    assert all(dia.weekday() < 5 for dia in dias)


def test_fomc_sin_tabla_devuelve_error(tmp_path):
    fechas, error = fomc_dates(str(tmp_path / "no-existe.db"))
    assert fechas == []
    assert error


def test_tabla_por_bot_desde_conditioners_yaml(tmp_path, monkeypatch):
    from tradinglab import conditioners

    (tmp_path / "conditioners.yaml").write_text(
        "bots:\n  bot-a:\n    pre_fomc: 0.5\n"
        "default:\n  monday_overnight: 0.75\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(conditioners, "CONFIG_DIR", tmp_path)
    assert conditioners.bot_multiplier_table("bot-a") == {"pre_fomc": 0.5}
    assert conditioners.bot_multiplier_table("otro") == {"monday_overnight": 0.75}


def test_la_propuesta_no_afecta_a_produccion(tmp_path, monkeypatch):
    from tradinglab import conditioners

    (tmp_path / "conditioners.yaml").write_text(
        "default: {}\nbots: {}\nproposal:\n  pre_fomc: 0.5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(conditioners, "CONFIG_DIR", tmp_path)
    assert conditioners.bot_multiplier_table("bot-a") == {}
    assert conditioners.proposal_table("bot-a") == {"pre_fomc": 0.5}


def test_la_configuracion_real_no_tiene_multiplicadores():
    """Con `default: {}` y `bots: {}` nada cambia en producción."""
    from tradinglab.conditioners import bot_multiplier_table

    for bot_id in ("qqq-trend-f13", "trend-spy", "meanrev-large"):
        assert bot_multiplier_table(bot_id) == {}
