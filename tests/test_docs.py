from __future__ import annotations

from pathlib import Path

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


def test_readme_menciona_propfund():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Prop Fund" in readme
