"""NQ-A · El script de la parte B corre con datos sintéticos."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_script_nq_sintetico(tmp_path):
    report = tmp_path / "nq_sintetico.md"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ea_nq_out_of_period.py"),
            "--synthetic",
            "--report",
            str(report),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )

    assert result.returncode == 0, result.stderr
    text = report.read_text(encoding="utf-8")
    assert "SINTÉTICO" in text
    assert "## Validez 2018" in text
    assert "¿Válida?" in text
    assert "Veredicto" in text
