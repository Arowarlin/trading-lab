from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T09A = (
    "src/tradinglab/costs.py",
    "src/tradinglab/optimize.py",
    "src/tradinglab/reporting.py",
    "src/tradinglab/web.py",
)
NAIVE = re.compile(r"(?:datetime|dt)\.now\(\s*\)|(?:date|dt\.date)\.today\(\s*\)")


def test_t09a_sin_llamadas_naive():
    for name in T09A:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not NAIVE.search(text), name


def test_ruff_mantiene_dtz_en_tests():
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "DTZ" in config
    assert '"tests/**" = ["DTZ"]' in config
    assert '"src/tradinglab/f13.py" = ["DTZ"]' not in config
    assert '"src/tradinglab/cli.py" = ["DTZ"]' not in config
