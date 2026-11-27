"""E-02 (ENG-1): mínimo opcional de operaciones en OOS-1 para elegir finalistas.

Con ruido puro el GA dejaba finalistas con 1-3 operaciones en OOS-1 y
expectativa positiva (docs/engineering/AUDIT_FINDINGS.md §8). El mínimo es
opcional: ``None`` mantiene el comportamiento de siempre.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from tradinglab.discovery import engine
from tradinglab.discovery.config import load_engine_config


def _candidate(name: str) -> engine.Individual:
    return engine.Individual(strategy={"name": name}, strategy_hash=name, complexity=1)


def _oos1(items: list[engine.Individual], trades: list[int]) -> dict[int, dict]:
    out = {}
    for seed, (item, n) in enumerate(zip(items, trades)):
        rng = np.random.default_rng(seed)
        dates = [d.date().isoformat() for d in pd.bdate_range("2021-01-04", periods=60)]
        out[id(item)] = {
            "metrics": {"trades": n, "expectancy_r": 0.4, "profit_factor": 2.0},
            "returns": list(rng.normal(0.0, 1.0, len(dates))),
            "return_dates": dates,
        }
    return out


def test_sin_minimo_el_comportamiento_es_el_de_siempre():
    items = [_candidate("a"), _candidate("b")]
    selected, _ = engine._select_finalists(
        items, _oos1(items, [1, 40]), finalists_max=5, corr_cluster=0.99
    )
    assert {item.strategy_hash for item in selected} == {"a", "b"}


def test_con_minimo_se_descarta_el_finalista_de_pocas_operaciones():
    items = [_candidate("a"), _candidate("b")]
    selected, discarded = engine._select_finalists(
        items, _oos1(items, [1, 40]), finalists_max=5, corr_cluster=0.99, min_trades_oos1=30
    )
    assert [item.strategy_hash for item in selected] == ["b"]
    reasons = {item.strategy_hash: reason for item, reason in discarded}
    assert "1 operaciones < 30" in reasons["a"]


def test_engine_yaml_activa_el_minimo_de_30():
    # Activado por el operador el 2026-11-26 con el valor del banco S2.
    assert load_engine_config().validation.min_trades_oos1 == 30
