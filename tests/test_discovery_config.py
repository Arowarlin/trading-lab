from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from tradinglab.discovery.config import ENGINE_PATH, load_engine_config


def _base() -> dict:
    return {
        "engine": {"workers": 12, "ram_limit_gb": 8},
        "profiles": {
            "small": {"population": 40, "generations": 10},
            "medium": {"population": 100, "generations": 25},
            "large": {"population": 200, "generations": 60},
        },
        "genetics": {"mutation_rate": 0.3, "crossover_rate": 0.6, "elite_frac": 0.1},
        "limits": {"max_nodes": 12, "max_depth": 4},
        "validation": {
            "min_trades_is": 100,
            "min_trades_fold": 15,
            "folds": 4,
            "finalists_max": 5,
            "corr_cluster": 0.7,
        },
        "data_quality": {
            "gap_factor": 3,
            "max_gap_hours": 4,
            "scheduled_gap_share": 0.2,
            "warn_if_gaps_gt": 0,
            "fail_if_gap_pct_gt": 0.005,
        },
    }


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "engine.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_config_real_tiene_los_valores_de_la_fase_0() -> None:
    config = load_engine_config()
    assert config.workers == 12
    assert config.ram_limit_gb == 8
    assert config.profile("small").population == 40
    assert config.profile("medium").generations == 25
    assert config.profile("large").population == 200
    assert config.genetics.mutation_rate == pytest.approx(0.3)
    assert config.genetics.crossover_rate == pytest.approx(0.6)
    assert config.genetics.elite_frac == pytest.approx(0.1)
    assert config.limits.max_nodes == 12
    assert config.limits.max_depth == 4
    assert config.validation.min_trades_is == 100
    assert config.validation.min_trades_fold == 15
    assert config.validation.folds == 4
    assert config.validation.finalists_max == 5
    assert config.validation.corr_cluster == pytest.approx(0.7)
    assert config.data_quality.gap_factor == pytest.approx(3)
    assert config.data_quality.max_gap_hours == pytest.approx(4)
    assert config.data_quality.scheduled_gap_share == pytest.approx(0.2)
    assert config.data_quality.warn_if_gaps_gt == 0
    assert config.data_quality.fail_if_gap_pct_gt == pytest.approx(0.005)
    assert ENGINE_PATH.exists()


def test_config_rechaza_perfil_faltante(tmp_path: Path) -> None:
    payload = _base()
    del payload["profiles"]["large"]
    with pytest.raises(ValidationError, match="large"):
        load_engine_config(_write(tmp_path, payload))


def test_config_rechaza_workers_y_tasas_fuera_de_rango(tmp_path: Path) -> None:
    payload = _base()
    payload["engine"]["workers"] = 0
    with pytest.raises(ValidationError):
        load_engine_config(_write(tmp_path, payload))
    payload = _base()
    payload["genetics"]["mutation_rate"] = 1.5
    with pytest.raises(ValidationError):
        load_engine_config(_write(tmp_path, payload))
    payload = _base()
    payload["validation"]["corr_cluster"] = 2
    with pytest.raises(ValidationError):
        load_engine_config(_write(tmp_path, payload))


def test_config_rechaza_profundidad_incoherente(tmp_path: Path) -> None:
    payload = _base()
    payload["limits"] = {"max_nodes": 4, "max_depth": 3}
    with pytest.raises(ValidationError, match="max_depth"):
        load_engine_config(_write(tmp_path, payload))


def test_config_rechaza_yaml_roto(tmp_path: Path) -> None:
    path = tmp_path / "engine.yaml"
    path.write_text("engine: [", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML"):
        load_engine_config(path)


def test_config_perfil_desconocido() -> None:
    with pytest.raises(KeyError, match="perfil"):
        load_engine_config().profile("inexistente")
