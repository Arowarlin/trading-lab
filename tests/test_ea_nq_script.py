"""NQ-B · El script corre con datos sintéticos y controles de la enmienda."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ea_nq_out_of_period.py"


def _run(*args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )


@pytest.mark.requires_local("data/cache/ea/US100_CASH_M5_NY.parquet")
def test_script_nq_sintetico(tmp_path):
    report = tmp_path / "nq_sintetico.md"
    result = _run("--synthetic", "--report", str(report))

    assert result.returncode == 0, result.stderr
    text = report.read_text(encoding="utf-8")
    assert "SINTÉTICO" in text
    assert "A-2 · Validez NQ 2018" in text
    assert "¿Válida?" in text
    assert "Veredicto" in text


@pytest.mark.requires_local("data/cache/ea/US100_CASH_M5_NY.parquet")
def test_puente_no_imprime_rendimiento(tmp_path):
    report = tmp_path / "puente.md"
    result = _run("--synthetic", "--bridge", "--report", str(report))

    assert result.returncode == 0, result.stderr
    text = report.read_text(encoding="utf-8")
    assert "A-1" in text
    assert "Emparejadas" in text
    assert "Correlación" in text
    assert "| Expectativa |" not in text
    assert "| PF |" not in text
    assert "Total R |" not in text


@pytest.mark.requires_local("data/cache/ea/US100_CASH_M5_NY.parquet")
def test_granularidad_d1_responde_sin_datos(tmp_path):
    index = pd.date_range("2022-01-03", "2022-12-30", freq="B")
    d1 = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "tickvol": 1.0,
            "spread": 10.0,
        },
        index=index,
    )
    path = tmp_path / "us100_d1.parquet"
    d1.to_parquet(path)
    report = tmp_path / "granularidad.md"
    result = _run(
        "--bridge",
        "--m1",
        str(ROOT / "data" / "cache" / "databento" / "US100_M1.parquet"),
        "--reference-m1",
        str(ROOT / "data" / "cache" / "dukascopy" / "US100_M1.parquet"),
        "--us100",
        str(path),
        "--report",
        str(report),
    )

    assert result.returncode == 2
    text = report.read_text(encoding="utf-8")
    assert "Sin datos: granularidad" in text


def test_exclusion_de_rolls_en_ambos_lados():
    spec = importlib.util.spec_from_file_location("nq_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "t": [
                pd.Timestamp("2026-01-15 10:00"),
                pd.Timestamp("2026-01-16 10:00"),
            ],
            "t_exit": [
                pd.Timestamp("2026-01-15 11:00"),
                pd.Timestamp("2026-01-16 11:00"),
            ],
            "d": [1, 1],
            "r": [1.0, 2.0],
        }
    )
    sessions = [pd.Timestamp("2026-01-15")]

    nq, nq_counts = module.exclude_roll_sessions(frame, sessions)
    ref, ref_counts = module.exclude_roll_sessions(frame, sessions)

    assert len(nq) == 1 and len(ref) == 1
    assert nq_counts == {2026: 1}
    assert ref_counts == {2026: 1}
    assert nq.iloc[0]["t"] == pd.Timestamp("2026-01-16 10:00")


def test_festivos_y_cierres_especiales_se_excluyen():
    spec = importlib.util.spec_from_file_location("nq_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    sessions = module.holiday_sessions(2012, 2012)

    assert pd.Timestamp("2012-07-04") in sessions
    assert pd.Timestamp("2012-11-23") in sessions
    assert pd.Timestamp("2012-10-29") in sessions

