from __future__ import annotations

import pytest

from tradinglab.config import ROOT
from tradinglab.ea_lab.candidate import (
    SETFILE,
    load_base_setfile,
    point_values,
    pre_registration,
    pre_registration_hash,
    scaled_params,
    scaled_values,
)


def test_reescalado_solo_toca_los_cuatro_parametros_en_puntos():
    values = load_base_setfile(SETFILE)
    ratio = 0.25
    scaled = scaled_values(values, ratio)
    assert scaled["InpSlBufAtr"] == pytest.approx(values["InpSlBufAtr"] * ratio)
    assert scaled["InpMinSlPts"] == pytest.approx(values["InpMinSlPts"] * ratio)
    assert scaled["InpMaxSpreadPts"] == pytest.approx(values["InpMaxSpreadPts"] * ratio)
    assert scaled["InpRR"] == values["InpRR"]
    assert scaled["InpSlAtr"] == values["InpSlAtr"]

    base = scaled_params(values, 1.0)
    params = scaled_params(values, ratio)
    assert params["slip"] == pytest.approx(base["slip"] * ratio)
    assert params["rr"] == base["rr"]
    assert params["sl_atr"] == base["sl_atr"]
    assert params["max_sl_atr"] == base["max_sl_atr"]
    assert params["gap_min"] == base["gap_min"]
    assert params["min_score"] == base["min_score"]
    assert params["max_consec"] == base["max_consec"]
    assert base["slip"] == pytest.approx(0.5)

    rows = point_values(values, ratio)
    assert rows["ratio"] == pytest.approx(ratio)
    assert rows["slip"]["scaled"] == pytest.approx(0.125)


def test_pre_registro_tiene_tres_veredictos_y_hash_estable():
    payload = pre_registration()
    assert set(payload["verdict"]) == {"PASA", "PASA SALVO DSR GLOBAL", "NO PASA"}
    assert payload["thresholds"]["min_dsr"] == pytest.approx(0.90)
    assert payload["thresholds"]["max_pbo"] == pytest.approx(0.30)
    assert payload["window"]["start"] == "2021-09-15"
    first = pre_registration_hash()
    assert first == pre_registration_hash()
    doc = (ROOT / "docs" / "ea_lab" / "us500_nyopen.md").read_text(encoding="utf-8")
    assert first in doc


def test_hash_cambia_si_cambia_un_termino(monkeypatch):
    import tradinglab.ea_lab.candidate as candidate

    before = pre_registration_hash()
    original = candidate.validation_thresholds

    def relajado():
        data = original()
        data["min_dsr"] = 0.80
        return data

    monkeypatch.setattr(candidate, "validation_thresholds", relajado)
    assert candidate.pre_registration_hash() != before
