from __future__ import annotations

from tradinglab.config import DEFAULT_DB
from tradinglab.execution_model import build_report, collect_variants
from tradinglab.learning import count_tests


def test_execution_model_no_cambia_contador_dsr(tmp_path):
    """El informe es medición: mismas variantes, otro modelo, sin trials nuevos."""
    before = count_tests(DEFAULT_DB)
    rows = collect_variants()
    assert len(rows) == 84

    path = build_report(tmp_path)
    after = count_tests(DEFAULT_DB)

    assert after == before
    text = path.read_text(encoding="utf-8")
    assert "84" in text
    assert "no se registraron trials" in text.lower()
    assert "Eventos" in text
