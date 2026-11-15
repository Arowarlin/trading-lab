from __future__ import annotations

from pathlib import Path

import yaml

from tradinglab.ea_registry import as_bot_row, ea_magic_map, get_ea, load_eas
from tradinglab.ea_us100 import load_setfile, params_from_set
from tradinglab.mt5_fills import lab_magic_map


def test_ea_registrado_y_mapeado():
    eas = load_eas()
    assert [ea.id for ea in eas] == ["us100-ftmo1"]
    ea = get_ea("us100-ftmo1")
    assert ea is not None
    assert ea.symbol == "US100.cash"
    assert ea.magic == 93010001
    assert ea.setfile.exists()
    assert ea.files()["ex5"] is True
    assert ea_magic_map()[93010001] == "ea:us100-ftmo1"
    assert lab_magic_map()[93010001] == "ea:us100-ftmo1"


def test_el_ea_se_puede_mover_a_la_cuenta_del_trial(tmp_path: Path):
    source = yaml.safe_load(Path("config/mt5_eas.yaml").read_text(encoding="utf-8"))
    source["eas"][0]["account"] = "ftmo_trial_ea"
    target = tmp_path / "mt5_eas.yaml"
    target.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    eas = load_eas(target)
    assert eas[0].account == "ftmo_trial_ea"


def test_fila_de_consola_es_solo_lectura():
    ea = get_ea("us100-ftmo1")
    assert ea is not None
    row = as_bot_row(ea)
    assert row["external"] is True
    assert row["type"] == "external_mt5"
    assert row["universe"] == ["US100.cash"]
    assert row["enabled"] is True


def test_setfile_v3_se_traduce_al_motor():
    ea = get_ea("us100-ftmo1")
    assert ea is not None
    values = load_setfile(ea.setfile)
    params = params_from_set(values)
    assert params["min_score"] == 55
    assert params["rr"] == 3.5
    assert params["max_consec"] == 1
    assert params["trade_end"] == 1100
    assert params["mode"] == "agg"
    assert params["sl_mode"] == "atr"
    assert params["gap_min"] == 0.7
    assert params["ny_offset_h"] == 0
    assert params["max_spread"] == 3.0
