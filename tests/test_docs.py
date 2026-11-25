from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_estado_real():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Discovery TL2" in text
    assert "us100-ftmo1" in text
    assert "INCIERTO" in text
    assert "docs/README-historico.md" in text


def test_readme_historico_existe():
    assert (ROOT / "docs" / "README-historico.md").exists()


def test_plan_existe():
    assert (ROOT / "PLAN.md").exists()


def test_readme_menciona_propfund():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Prop Fund" in readme
