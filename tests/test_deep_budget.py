from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tradinglab import cli as cli_mod
from tradinglab.agents import bridge


def test_el_bridge_manda_el_presupuesto_al_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capturado: dict = {}
    script = tmp_path / "run_tradingagents.py"
    script.write_text("# test", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        capturado["cmd"] = cmd
        capturado["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    monkeypatch.setattr(bridge, "TA_PYTHON", Path(sys.executable))
    monkeypatch.setattr(bridge, "TA_SCRIPT", script)
    monkeypatch.setattr(bridge, "ROOT", tmp_path)

    with pytest.raises(Exception):
        bridge.run_tradingagents("SPY", "2026-01-05", "market", save=False)

    cmd = capturado["cmd"]
    assert "--timeout-s" in cmd
    index = cmd.index("--timeout-s")
    assert int(cmd[index + 1]) > 0
    # el padre mata el proceso poco después que el script se corte solo
    assert capturado["timeout"] == int(cmd[index + 1]) + 60


def test_el_presupuesto_por_defecto_es_de_30_minutos() -> None:
    assert bridge.run_tradingagents.__defaults__ is not None
    assert "timeout" in bridge.run_tradingagents.__kwdefaults__
    assert bridge.run_tradingagents.__kwdefaults__["timeout"] == 1800


def test_el_cli_avisa_cuando_el_deep_no_se_completo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fila = {
        "ticker": "SPY",
        "lite_rating": "Hold",
        "lite_confidence": 0.5,
        "lite_target": None,
        "lite_analysts": ["lite"],
        "lite_duration_s": 90.0,
        "lite_error": None,
        "deep_rating": None,
        "deep_confidence": None,
        "deep_target": None,
        "deep_analysts": [],
        "deep_duration_s": None,
        "deep_error": "TradingAgents excedió el presupuesto de 1800s para SPY",
        "retrospective": False,
    }

    monkeypatch.setattr(
        "tradinglab.agent_compare.run_comparison", lambda *a, **k: fila
    )
    monkeypatch.setattr(
        "tradinglab.agent_compare.report",
        lambda *a, **k: {
            "n": 0,
            "agreement_rate": None,
            "matrix": {},
            "mean_target_diff": None,
            "insufficient": True,
            "sample_warning": "muestra insuficiente",
            "by_source": [],
        },
    )
    result = CliRunner().invoke(cli_mod.app, ["agent-compare", "SPY"])
    assert result.exit_code == 0
    assert "El deep no se completó" in result.output
    assert "presupuesto" in result.output
