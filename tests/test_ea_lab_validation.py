from __future__ import annotations

import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from tradinglab import ea_us100_engine as engine
from tradinglab.ea_lab.candidate import SETFILE, load_base_setfile, scaled_params
from tradinglab.ea_lab.validation import (
    AlreadyValidated,
    _patched_ea_us100,
    _record_us500_trials,
    validate_candidate,
    verdict_from_filters,
)


def _filters(*, dsr_ok: bool = True, dsr_value: float | None = 0.95, other_ok: bool = True) -> dict:
    return {
        "trades": {"value": 480, "ok": other_ok},
        "dsr": {"value": dsr_value, "ok": dsr_ok},
        "dsr_local": {"value": 0.99, "ok": True},
        "pbo": {"value": 0.24, "ok": other_ok},
        "walk_forward": {"value": "ok", "ok": other_ok},
        "regimen": {"value": True, "ok": other_ok},
        "spread": {"value": 50.0, "ok": other_ok},
        "coste_2pts": {"value": 0.1, "ok": other_ok},
    }


def _synthetic_m5(days: int = 5) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(7)
    price = 6000.0
    index = []
    for day in range(days):
        start = pd.Timestamp("2026-11-02 09:30") + pd.Timedelta(days=day)
        for step in range(78):
            change = float(rng.normal(0, 0.8))
            open_ = price
            close = price + change
            high = max(open_, close) + abs(float(rng.normal(0, 0.3)))
            low = min(open_, close) - abs(float(rng.normal(0, 0.3)))
            rows.append(
                {
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "tickvol": float(rng.integers(500, 5000)),
                    "spread": 50.0,
                }
            )
            price = close
            index.append(start + pd.Timedelta(minutes=5 * step))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index))


def test_veredicto_pasa():
    assert verdict_from_filters(_filters())[0] == "PASA"


def test_veredicto_pasa_salvo_dsr_global():
    verdict, reasons = verdict_from_filters(_filters(dsr_ok=False, dsr_value=0.63))
    assert verdict == "PASA SALVO DSR GLOBAL"
    assert reasons == ["dsr"]


def test_veredicto_no_pasa_por_otro_criterio():
    verdict, reasons = verdict_from_filters(_filters(other_ok=False))
    assert verdict == "NO PASA"
    assert "pbo" in reasons


def test_veredicto_no_pasa_si_dsr_sin_datos():
    verdict, reasons = verdict_from_filters(_filters(dsr_ok=False, dsr_value=None))
    assert verdict == "NO PASA"
    assert "dsr_sin_datos" in reasons


def test_patch_reescala_slip_y_registra_familia_us500(tmp_path):
    values = load_base_setfile(SETFILE)
    with _patched_ea_us100(0.5):
        from tradinglab.ea_us100 import params_from_set

        params = params_from_set(values)
        assert params["slip"] == pytest.approx(0.25)

    db = tmp_path / "lab.db"
    rows = [
        {
            "index": 0,
            "min_score": 55,
            "rr": 3.5,
            "gap_min": 0.7,
            "max_consec": 1,
            "n": 10,
            "win": 30.0,
            "pf": 1.2,
            "expR": 0.1,
            "totR": 1.0,
            "maxDD_R": 2.0,
        }
    ]
    _record_us500_trials(
        db, rows, baseline_index=0, run_id="test", symbol="US500.cash", srs=[0.05]
    )
    with sqlite3.connect(db) as con:
        family, symbol, counted = con.execute(
            "select family, symbol, counted from strategy_trials"
        ).fetchone()
    assert (family, symbol, counted) == ("US500_NYOPEN_CONFLUENCE", "US500.CASH", 1)


def _fake_payload() -> dict:
    return {
        "baseline": {"n": 480, "win": 33.8, "pf": 1.45, "expR": 0.298, "totR": 143.2, "maxDD_R": 24.8},
        "filters": _filters(dsr_ok=False, dsr_value=0.63),
        "bars": {"rows": 100, "start": "2021-09-15", "end": "2026-11-13"},
        "rows": [],
        "dsr_local": 0.99,
        "dsr_global": 0.63,
        "dsr_local_meta": {"metric_version": "dsr_v2"},
        "dsr_global_meta": {"n_series": 653, "frequency": "daily"},
        "pbo": 0.241,
        "walk_forward": {"verdict": "ok", "stitched_sharpe": 1.3, "efficiency": 0.9, "n_folds": 5},
        "regime": {"passed": True, "years": {"2021": {"total_return": 0.01, "sharpe": 0.4, "max_drawdown": -0.02}}},
        "monte_carlo": {"pass_rate": 0.1, "breach_rate": 0.0, "timeout_rate": 0.9},
        "dynamic_risk": {"return": 0.1, "equity": 110000, "max_drawdown": -0.05, "killed": False},
        "costs": {"2.0": {"expR": 0.1, "pf": 1.1, "totR": 10.0}},
        "n_trials": 1052,
        "n_trials_local": 8,
    }


def test_validate_candidate_escribe_informes_y_veredicto(monkeypatch, tmp_path):
    fake = _fake_payload()
    monkeypatch.setattr("tradinglab.ea_us100.validate", lambda *a, **k: dict(fake))
    payload = validate_candidate(
        None,
        ratio=0.20662301,
        data={
            "us500": {"measured_bps": 0.8104, "last_close": 6000, "atr_median": 5.0553},
            "us100": {"measured_bps": 0.7061, "last_close": 26785, "atr_median": 24.4662},
        },
        db_path=tmp_path / "lab.db",
        record=False,
        output_dir=tmp_path / "out",
        single_shot=False,
    )
    assert payload["verdict"] == "PASA SALVO DSR GLOBAL"
    assert payload["ea"] == "us500-nyopen"
    assert payload["relative_cost"]["us500"]["spread_over_atr"] == pytest.approx(0.0962, rel=1e-3)
    assert (tmp_path / "out" / "validation.md").exists()
    assert (tmp_path / "out" / "verdict.md").exists()
    assert "PASA SALVO DSR GLOBAL" in (tmp_path / "out" / "verdict.md").read_text(encoding="utf-8")


def test_validacion_no_se_repite(tmp_path):
    (tmp_path / ".validated").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    with pytest.raises(AlreadyValidated):
        validate_candidate(
            None,
            ratio=0.2,
            data={},
            output_dir=tmp_path,
            single_shot=True,
        )


def test_llamada_al_motor_con_parametros_reescalados_sin_mt5():
    frame = _synthetic_m5()
    values = load_base_setfile(SETFILE)
    params = scaled_params(values, 0.2066)
    snapshot = dict(params)

    trades = engine.run(frame, params)

    assert isinstance(trades, pd.DataFrame)
    assert params == snapshot
    assert params["slip"] != 0.5
    stats = engine.stats(trades)
    assert set(stats) >= {"n", "win", "pf", "expR", "totR", "maxDD_R"}
    assert trades.index.is_monotonic_increasing
    assert len(trades) == int(stats["n"])

