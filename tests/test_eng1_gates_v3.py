"""ENG-1 S1: puertas v3 opcionales (docs/engineering/STATS_REDESIGN.md).

Por defecto ``gates_version = 2``: todo sigue igual. Con 3:
- WF y PBO sobre una muestra fija de la población evaluada (no el frontier) y
  ventanas WF por TF del prerregistro WF-TF;
- confirmación OOS-2 con PSR contra 0 >= 1 - alpha/m (Bonferroni).
Todo sintético; sin datos de mercado.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import decisions, levels, robustness
from tradinglab.discovery.config import load_engine_config


def _config(version: int):
    base = load_engine_config()
    return base.model_copy(update={"robustness": base.robustness.model_copy(update={"gates_version": version})})


class _FakeEvaluations:
    def __init__(self, n: int, days: int = 1300, seed: int = 0):
        rng = np.random.default_rng(seed)
        dates = [d.date().isoformat() for d in pd.bdate_range("2015-01-05", periods=days)]
        self.rows = []
        for sid in range(1, n + 1):
            active = rng.random(days) < 0.1
            values = np.where(active, rng.normal(-0.05, 1.0, days), 0.0)
            keep = np.flatnonzero(active)
            self.rows.append(
                {
                    "id": sid,
                    "returns": values[keep],
                    "dates": [dates[i] for i in keep],
                }
            )

    def list_strategies(self, **kwargs):
        return [{"id": row["id"]} for row in self.rows]

    def list_evaluations(self, strategy_id, **kwargs):
        row = self.rows[int(strategy_id) - 1]
        return [
            {
                "segment": "fitness_is",
                "returns": np.asarray(row["returns"], dtype=float),
                "metrics": {"return_dates": row["dates"]},
            }
        ]

    def frontier(self, campaign_id, **kwargs):
        return [
            {"strategy_id": row["id"], "returns": list(row["returns"]), "dates": row["dates"]}
            for row in self.rows[:10]
        ]

    def get_campaign(self, campaign_id, **kwargs):
        return {"id": campaign_id, "timeframe": "H1"}


def _patch(monkeypatch, fake, version):
    for name in ("list_strategies", "list_evaluations", "frontier", "get_campaign"):
        monkeypatch.setattr(robustness.databank, name, getattr(fake, name))
    monkeypatch.setattr(robustness, "load_engine_config", lambda: _config(version))


def test_engine_yaml_activa_v3():
    # Activado por el operador el 2026-11-26 (docs/engineering/DECISIONS.md).
    assert load_engine_config().robustness.gates_version == 3


def test_v2_usa_el_frontier(monkeypatch):
    _patch(monkeypatch, _FakeEvaluations(60), 2)
    pbo, wf = robustness._pbo_wf("camp", None)
    assert pbo["gates_version"] == 2 and pbo["matrix"] == "frontier"
    assert pbo["n_variants_matrix"] == 10
    assert wf["wf_windows"] == [60, 20]


def test_v3_usa_una_muestra_fija_de_la_poblacion_y_ventanas_por_tf(monkeypatch):
    fake = _FakeEvaluations(60)
    _patch(monkeypatch, fake, 3)
    monkeypatch.setattr(
        robustness,
        "load_engine_config",
        lambda: _config(3).model_copy(
            update={"robustness": _config(3).robustness.model_copy(update={"v3_population_sample": 40})}
        ),
    )
    pbo, wf = robustness._pbo_wf("camp", None)
    assert pbo["gates_version"] == 3 and pbo["matrix"] == "population_sample"
    assert pbo["n_variants_matrix"] == 40
    assert wf["wf_windows"] == [180, 60]
    again, _ = robustness._pbo_wf("camp", None)
    assert again["n_variants_matrix"] == 40
    assert again.get("pbo") == pbo.get("pbo")  # misma muestra: semilla por campaña


def test_level4_usa_el_umbral_del_resultado():
    common = dict(
        level3=True, enough_oos2=True, oos2=0.2, pbo=0.1, wf_ok=True, regime_ok=True,
        slip2=0.1, challenge_ok=True, random_oos2=99.0,
    )
    assert decisions.level4_ok(dsr_confirm=0.95, **common) is True
    assert decisions.level4_ok(dsr_confirm=0.95, dsr_threshold=0.999, **common) is False
    assert decisions.level4_ok(dsr_confirm=0.9995, dsr_threshold=0.999, **common) is True


def test_psr_bonferroni_v3(tmp_path):
    rng = np.random.default_rng(3)
    strong = rng.normal(0.08, 1.0, 756)
    out = levels._psr_bonferroni_v3(
        strong, base={"k_finalists": 2, "dsr": 0.5}, n_trials=4, alpha=0.05,
        db_path=tmp_path / "vacia.db",
    )
    assert out["kind"] == "psr_bonferroni_v3"
    assert out["m_oos2_reads"] == 4  # sin lecturas registradas: m = n_trials
    assert out["threshold"] == pytest.approx(1 - 0.05 / 4)
    assert out["dsr_v2_reference"] == 0.5 and out["k_finalists"] == 2
    noise = rng.normal(0.0, 1.0, 756)
    weak = levels._psr_bonferroni_v3(noise, base={}, n_trials=4, alpha=0.05, db_path=tmp_path / "vacia.db")
    assert (weak["dsr"] or 0.0) < weak["threshold"]


def test_d06_potencia_con_v3_cuenta_solo_el_oos2(monkeypatch):
    from tradinglab.discovery import power

    segments = {"is": ["2015-01-01", "2019-12-31"], "oos1": ["2020-01-01", "2022-12-31"],
                "oos2": ["2023-01-01", "2025-12-31"]}
    counts = power.counts_from_is(150, segments)
    assert counts["trades_holdout"] == pytest.approx(180, abs=2)  # OOS-1 + OOS-2: 6 años
    assert counts["trades_oos2"] == pytest.approx(90, abs=2)  # solo OOS-2: 3 años
    assert power.power_count_key() == "trades_oos2"  # engine.yaml usa v3
    monkeypatch.setattr("tradinglab.discovery.config.load_engine_config", lambda: _config(2))
    assert power.power_count_key() == "trades_holdout"


def test_v3_conserva_los_metadatos_de_la_confirmacion(tmp_path):
    # Regresión: el PSR se calcula con n_trials = 1 y pisaba el n_trials real.
    rng = np.random.default_rng(5)
    out = levels._psr_bonferroni_v3(
        rng.normal(0.05, 1.0, 400),
        base={"n_trials": 4, "k_finalists": 2, "n_accounts": 2, "dsr": 0.4},
        n_trials=4,
        alpha=0.05,
        db_path=tmp_path / "vacia.db",
    )
    assert out["n_trials"] == 4 and out["k_finalists"] == 2 and out["n_accounts"] == 2
    assert out["psr_n_trials"] == 1
