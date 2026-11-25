"""Tests sinteticos del registro diario (F5), sin resultados."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJ = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "forward_daily", PROJ / "tools" / "forward_daily.py"
)
fd = importlib.util.module_from_spec(SPEC)
sys.modules["forward_daily"] = fd
SPEC.loader.exec_module(fd)

DAY = "2026-12-01"


def _frame() -> pd.DataFrame:
    """9:30-9:44 en 100; 9:45-9:59 en 102; desde 10:00 en 108 (rompe el 2R)."""
    idx = pd.date_range(f"{DAY} 09:30", periods=390, freq="1min", tz="America/New_York")
    close = np.full(390, 100.0)
    close[15:30] = 102.0
    close[30:] = 108.0
    open_ = np.concatenate([[100.0], close[:-1]])
    open_[15:30] = 102.0
    open_[30:] = 108.0
    high = np.maximum(open_, close) + 0.5
    low = np.minimum(open_, close) - 0.5
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 100.0},
        index=idx.tz_convert("UTC"),
    )
    df.index.name = "time"
    return df


def test_sesion_sintetica_produce_la_fila_esperada():
    session = fd.session_from_frame(_frame(), DAY)
    assert session is not None
    result = fd.build_day([session], fd.Costs(1.0, 0.0), variants=["NQF-A"])
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["variant"] == "NQF-A" and row["side"] == 1
    assert row["stop"] == pytest.approx(99.5)
    assert row["target"] == pytest.approx(107.0)  # 2R desde 102 con stop 99.5
    assert row["contracts"] == 21  # 150 // (2.5*2 + 2*1)
    assert row["exit_reason"] == "target"
    assert row["exit_price"] == pytest.approx(107.0)
    assert "r_net" not in fd.FIELDS


def test_ledger_append_es_idempotente(tmp_path, monkeypatch):
    monkeypatch.setattr(fd, "LEDGER", tmp_path / "ledger.csv")
    session = fd.session_from_frame(_frame(), DAY)
    result = fd.build_day([session], fd.Costs(1.0, 0.0), variants=["NQF-A"])
    assert fd.append_ledger(result.rows, "test", "hash") == 1
    assert fd.append_ledger(result.rows, "test", "hash") == 0
    text = (tmp_path / "ledger.csv").read_text(encoding="utf-8")
    assert text.count("NQF-A") == 1
    assert "r_net" not in text


def test_main_no_imprime_metricas(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fd, "LEDGER", tmp_path / "ledger.csv")
    csv_path = tmp_path / "dia.csv"
    _frame().reset_index().to_csv(csv_path, index=False)
    code = fd.main([
        "--source", "csv", "--csv", str(csv_path), "--date", DAY,
        "--commission-side-usd", "1.0",
    ])
    assert code == 0
    out = capsys.readouterr().out.lower()
    for token in ("r_net", "p&l", "pf ", "win rate", "expect", "media"):
        assert token not in out
    assert "nqf-a: n=1" in out


def test_sin_comision_bloquea(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fd, "LEDGER", tmp_path / "ledger.csv")
    assert fd.main(["--dry-run"]) == 2
    err = capsys.readouterr().err.lower()
    assert "bloqueado: falta comision" in err
