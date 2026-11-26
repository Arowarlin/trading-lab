"""Tests de ``scripts/wf_tf_eval.py`` (WF-TF, solo lectura)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import wf_tf_eval  # noqa: E402

from tradinglab.discovery import databank, robustness  # noqa: E402


def _frame(rows: int, variants: int = 4, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2020-01-01", periods=rows)
    values = rng.normal(0.0, 0.01, size=(rows, variants))
    return pd.DataFrame(values, index=index)


def test_ventanas_preregistradas() -> None:
    assert wf_tf_eval.WINDOWS == {
        "M5": (60, 20),
        "M15": (60, 20),
        "M30": (120, 40),
        "H1": (180, 60),
        "H4": (360, 120),
        "D1": (504, 126),
    }
    assert wf_tf_eval.windows_for("h1") == (180, 60)
    with pytest.raises(KeyError):
        wf_tf_eval.windows_for("W1")


def test_menos_de_tres_pliegues_es_sin_datos() -> None:
    # H4 exige 360+120=480 filas; 200 no alcanza ni un pliegue.
    result = wf_tf_eval.evaluate_matrix(_frame(200), "H4")
    assert result["status"] == "Sin datos"
    assert result["verdict"] == "Sin datos"
    assert result["ok"] is False
    assert result["efficiency"] is None
    assert "muestra insuficiente" in result["reason"]

    # 600 filas -> 2 pliegues: tampoco aprueba.
    result = wf_tf_eval.evaluate_matrix(_frame(600), "H4")
    assert result["n_folds"] == 2
    assert result["status"] == "Sin datos"
    assert result["verdict"] == "Sin datos"
    assert result["ok"] is False
    assert "folds insuficientes" in result["reason"]


def test_ventanas_del_tf_se_aplican() -> None:
    frame = _frame(2000)
    h4 = wf_tf_eval.evaluate_matrix(frame, "H4")
    assert h4["train_len"] == 360
    assert h4["test_len"] == 120
    assert h4["n_folds"] == len(range(0, 2000 - 480 + 1, 120))
    h1 = wf_tf_eval.evaluate_matrix(frame, "H1")
    assert h1["train_len"] == 180
    assert h1["test_len"] == 60


def test_identidad_60_20_con_robustness() -> None:
    campaign = "edge1-11-trend-pullback-mtf-usdjpy-h1"
    real_db = ROOT / "data" / "discovery.db"
    new = wf_tf_eval.evaluate_campaign(
        campaign,
        "H1",
        db_path=real_db,
        with_frequency=False,
        train_len=60,
        test_len=20,
    )
    with wf_tf_eval.readonly_databank(real_db):
        _pbo, old = robustness._pbo_wf(campaign, real_db)  # noqa: SLF001
    assert new["n_folds"] == old["n_folds"]
    assert new["efficiency"] == old["efficiency"]
    assert new["stitched_sharpe"] == old["stitched_sharpe"]
    assert new["ok"] == old["ok"]
    assert new["n_variants"] == old["n_variants"]


def test_lectura_sin_escritura() -> None:
    with wf_tf_eval.readonly_databank(None):
        with databank.connect(databank.DEFAULT_DISCOVERY_DB) as con:
            with pytest.raises(sqlite3.OperationalError):
                con.execute("CREATE TABLE wf_tf_no_debe_crearse (x INTEGER)")
        # init_databank no hace nada dentro del contexto.
        assert databank.init_databank() == databank.DEFAULT_DISCOVERY_DB


def test_matriz_diaria_ordenada() -> None:
    real_db = ROOT / "data" / "discovery.db"
    with wf_tf_eval.readonly_databank(real_db):
        frame, ids = robustness._frontier_frame(  # noqa: SLF001
            "edge1-11-trend-pullback-mtf-usdjpy-h1", real_db
        )
    assert frame is not None
    assert ids
    assert isinstance(frame.index, pd.DatetimeIndex)
    expected = pd.bdate_range(frame.index.min(), frame.index.max())
    assert frame.index.equals(expected)
    assert not frame.isna().any().any()
