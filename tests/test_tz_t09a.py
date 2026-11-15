from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T09A = (
    "src/tradinglab/costs.py",
    "src/tradinglab/optimize.py",
    "src/tradinglab/readiness.py",
    "src/tradinglab/reporting.py",
    "src/tradinglab/web.py",
    "scripts/build_qqq_trend_cfd_artifact.py",
)
NAIVE = re.compile(r"(?:datetime|dt)\.now\(\s*\)|(?:date|dt\.date)\.today\(\s*\)")


def test_t09a_sin_llamadas_naive():
    for name in T09A:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not NAIVE.search(text), name


def test_t09b_sigue_excluido_en_ruff():
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "DTZ" in config
    for name in (
        "src/tradinglab/f13.py",
        "src/tradinglab/cli.py",
        "src/tradinglab/lifecycle.py",
        "src/tradinglab/orchestrator.py",
        "src/tradinglab/premarket.py",
        "src/tradinglab/telegram.py",
    ):
        assert f'"{name}" = ["DTZ"]' in config
