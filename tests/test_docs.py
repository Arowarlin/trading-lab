from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_readme_sin_duplicado_lm_studio():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert text.count("Con 16 GB de VRAM") == 1


def test_readme_numeracion_f15():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "| F15 |" in text
    assert "**F15** datos de ticks" in text
    assert "**F14** datos de ticks" not in text


def test_plan_existe():
    assert (ROOT / "PLAN.md").exists()


def test_readme_f13_coherente_con_bots_yaml():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    bots = yaml.safe_load((ROOT / "config" / "bots.yaml").read_text(encoding="utf-8"))
    f13 = next(item for item in bots["bots"] if item["id"] == "qqq-trend-f13")
    if not f13["enabled"]:
        return
    lines = readme.splitlines()
    for index, line in enumerate(lines):
        if "qqq-trend-f13" not in line:
            continue
        window = "\n".join(lines[index : index + 3]).lower()
        assert not re.search(r"enabled\s*:\s*false", window), window
    assert "congelado, sin activar" not in readme.lower()
    f13_row = next(line for line in lines if line.startswith("| F13 |"))
    assert "activo" in f13_row.lower()
    assert "paper" in f13_row.lower()
    assert "tradinglab-f13" in f13_row.lower()
