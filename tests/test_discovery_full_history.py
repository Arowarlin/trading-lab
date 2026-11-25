"""T32 · Historia completa en specs D1."""

from __future__ import annotations

from pathlib import Path

import yaml

from tradinglab.discovery import campaigns, spec


def test_usable_from_d1():
    assert (
        campaigns.d1_usable_start("turn_of_month", "US100", "D1", "dukascopy")
        == "2014-01-01"
    )
    assert campaigns.d1_usable_start("turn_of_month", "US500", "D1", "dukascopy") == "2018-01-01"
    assert campaigns.d1_usable_start("ny_open_vol_filter", "US100", "M5", "broker") is None


def test_spec_d1_usa_usable_from_en_lugar_de_2018(tmp_path: Path):
    source = Path(".orquestador/specs/q1-rebote-us500-d1.yaml")
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    data["campaign_id"] = "t32-usable"
    data["instrument"] = "US100"
    data["segments"]["is"] = ["2018-01-01", "2024-06-30"]
    path = tmp_path / "t32.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    campaign = spec.load_spec(path)
    assert campaign["config"]["segments"]["is"][0] == "2014-01-01"
