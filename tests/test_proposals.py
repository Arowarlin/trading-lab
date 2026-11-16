from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _proposal() -> dict:
    path = ROOT / "config" / "proposals" / "disable_fx_forward.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_propuesta_desactiva_solo_los_dos_forwards_fx():
    proposal = _proposal()
    assert proposal["id"] == "disable_fx_forward"
    assert proposal["target"] == "config/intraday_forward.yaml"
    assert proposal["requires_confirmation"] is True
    changes = proposal["changes"]
    assert len(changes) == 2
    assert {item["magic"] for item in changes} == {20261151, 20261152}
    assert all(item["from"] is True and item["to"] is False for item in changes)
    assert proposal["not_changed"][0]["magic"] == 20261153


def test_propuesta_de_cementerio_no_toca_enabled():
    path = ROOT / "config" / "proposals" / "us100-trend-d1-cemetery.yaml"
    proposal = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert proposal["action"] == "move_to_cemetery"
    assert proposal["changes"][0]["bot"] == "us100-trend-d1"
    assert proposal["changes"][0]["from"] is True
    assert proposal["changes"][0]["to"] is False
    forward = yaml.safe_load(
        (ROOT / "config" / "intraday_forward.yaml").read_text(encoding="utf-8")
    )
    bot = next(item for item in forward["bots"] if item["id"] == "us100-trend-d1")
    assert bot["enabled"] is True


def test_la_propuesta_no_esta_aplicada():
    path = ROOT / "config" / "intraday_forward.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert all(bot["enabled"] is True for bot in config["bots"])
    assert {bot["magic"] for bot in config["bots"]} == {
        20261151,
        20261152,
        20261153,
    }
