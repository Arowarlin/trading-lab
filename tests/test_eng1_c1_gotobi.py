"""Tests sintéticos del script C1 (fix de Tokio en días gotobi). Sin datos de mercado."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parents[1] / "docs" / "engineering" / "tools" / "c1_tokyo_fix_gotobi.py"
_SPEC = importlib.util.spec_from_file_location("c1_tokyo_fix_gotobi", _PATH)
c1 = importlib.util.module_from_spec(_SPEC)
sys.modules["c1_tokyo_fix_gotobi"] = c1
_SPEC.loader.exec_module(c1)

HOLIDAYS = {date(2010, 1, 1), date(2010, 11, 3), date(2010, 11, 23)}


def _frame(drift_pips: float, seed: int, *, extra_stamp: str | None = None) -> pd.DataFrame:
    """Velas M1 00:00-00:59 UTC en días hábiles 2003-2022, con deriva en días gotobi."""

    rng = np.random.default_rng(seed)
    gotobi = set(c1.gotobi_days("2003-01-01", "2022-12-31", HOLIDAYS))
    rows, stamps = [], []
    for day in pd.bdate_range("2003-01-01", "2022-12-31"):
        move = rng.normal(0.0, 5.0) + (drift_pips if day.date() in gotobi else 0.0)
        path = np.linspace(0.0, move, 60) * c1.PIP + 100.0
        for minute in range(60):
            stamps.append(day.tz_localize("UTC") + pd.Timedelta(minutes=minute))
            rows.append((path[minute] + 0.005, path[minute]))  # ASK = BID + 0,5 pips
    if extra_stamp:
        stamps.append(pd.Timestamp(extra_stamp, tz="UTC"))
        rows.append((100.005, 100.0))
    return pd.DataFrame(rows, columns=["ask_open", "close"], index=pd.DatetimeIndex(stamps))


def test_gotobi_se_adelanta_al_habil_anterior():
    days = c1.gotobi_days("2010-06-01", "2010-06-30", set())
    # 5-jun-2010 es sábado: pasa al viernes 4. El último hábil de junio es el 30 (miércoles).
    assert date(2010, 6, 4) in days and date(2010, 6, 5) not in days
    assert date(2010, 6, 30) in days
    # Un gotobi que cae en festivo japonés se adelanta: 2010-11-05 (viernes) es hábil y se queda;
    # con el 5 declarado festivo, pasa al jueves 4.
    november = c1.gotobi_days("2010-11-01", "2010-11-30", {date(2010, 11, 5)})
    assert date(2010, 11, 4) in november and date(2010, 11, 5) not in november
    assert date(2010, 11, 25) in november


def test_detecta_una_deriva_sembrada():
    result = c1.evaluate(_frame(drift_pips=3.0, seed=1), HOLIDAYS, commission_pips_rt=0.75)
    assert result.n_events > 1400
    assert result.t_hac > c1.T_CRIT
    assert result.verdict == "candidate"
    assert abs(result.placebo["mean_net_pips"] + 0.5 + 0.75) < 0.5  # placebo ≈ −coste


def test_sin_deriva_no_es_candidato():
    result = c1.evaluate(_frame(drift_pips=0.0, seed=2), HOLIDAYS, commission_pips_rt=0.75)
    assert result.verdict == "rejected"


def test_se_niega_a_leer_el_tramo_sellado():
    frame = _frame(drift_pips=0.0, seed=3, extra_stamp="2023-01-04 00:00")
    with pytest.raises(c1.SealedDataError):
        c1.evaluate(frame, HOLIDAYS, commission_pips_rt=0.75)


def test_cli_exige_aprobacion(tmp_path):
    with pytest.raises(SystemExit):
        c1.main(["--cache", "x", "--jp-holidays", "y", "--commission-pips-rt", "0.75", "--out",
                 str(tmp_path / "o.json")])
