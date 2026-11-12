from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml
from typer.testing import CliRunner

from tradinglab import cli as cli_mod
from tradinglab.guardian import (
    GUARDIAN_FILENAME,
    GuardianError,
    build_config,
    export_config,
    guardian_sessions,
    guardian_terminal_path,
    read_exported,
    resolve_target,
    terminal_data_path,
)


def _accounts_file(tmp_path: Path, accounts: dict) -> Path:
    path = tmp_path / "accounts.yaml"
    path.write_text(
        yaml.safe_dump({"accounts": accounts}, sort_keys=False), encoding="utf-8"
    )
    return path


def _forward_file(
    tmp_path: Path, *, magics: tuple[int, int] = (20261151, 20261152)
) -> Path:
    bots = []
    for index, magic in enumerate(magics):
        bots.append(
            {
                "id": f"forward-{index}",
                "canonical_symbol": "EURUSD",
                "strategy": "london_pullback",
                "timeframe": "M15",
                "account": "ftmo_demo",
                "params": {
                    "fast": 50,
                    "slow": 100,
                    "pullback_atr": 0.5,
                    "max_hold": 16,
                },
                "entry_start": "07:00",
                "entry_end": "16:00",
                "force_exit": "16:00",
                "stop_atr": 2.0,
                "max_trades_per_day": 1,
                "magic": magic,
                "enabled": True,
            }
        )
    path = tmp_path / "intraday_forward.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "account": "ftmo_demo",
                "defense": "report",
                "bots": bots,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _ftmo_account(account_size: float = 100_000) -> dict:
    return {
        "type": "fondeo",
        "firm": "ftmo",
        "phase": "challenge",
        "account_size": account_size,
        "status": "demo",
        "limits": {"daily_loss_pct": 0.05, "max_drawdown_pct": 0.10},
    }


def test_build_config_ftmo_demo():
    cfg = build_config("ftmo_demo")
    assert cfg["account"] == "ftmo_demo"
    assert cfg["account_size"] == pytest.approx(100_000)
    assert cfg["daily_loss_pct"] == pytest.approx(0.045)
    assert cfg["max_drawdown_pct"] == pytest.approx(0.09)
    assert cfg["reset_tz"] == "Europe/Prague"
    expected = int(
        datetime.now(ZoneInfo("Europe/Prague")).utcoffset().total_seconds() // 60
    )
    assert cfg["reset_utc_offset_minutes"] == expected
    assert cfg["magics"] == [20261151, 20261152, 20261153]
    assert cfg["version"] == 1
    assert cfg["limits_source"].startswith("prop.yaml:ftmo/challenge")


def test_build_config_usa_magics_del_forward(tmp_path):
    accounts = _accounts_file(tmp_path, {"ftmo_demo": _ftmo_account()})
    forward = _forward_file(tmp_path, magics=(111, 222))
    cfg = build_config("ftmo_demo", accounts_path=accounts, forward_path=forward)
    assert cfg["magics"] == [111, 222]
    assert cfg["bots"] == ["forward-0", "forward-1"]


def test_cuenta_propia_usa_limits_del_yaml(tmp_path):
    accounts = _accounts_file(
        tmp_path,
        {
            "paper_test": {
                "type": "capital_propio",
                "account_size": 50_000,
                "limits": {"daily_loss_pct": 0.02, "max_drawdown_pct": 0.07},
            }
        },
    )
    forward = _forward_file(tmp_path)
    cfg = build_config("paper_test", accounts_path=accounts, forward_path=forward)
    assert cfg["daily_loss_pct"] == pytest.approx(0.02)
    assert cfg["max_drawdown_pct"] == pytest.approx(0.07)
    assert cfg["limits_source"] == "accounts.yaml:limits"


def test_cuenta_desconocida_aborta():
    with pytest.raises(GuardianError, match="no existe"):
        build_config("no_existe")


def test_fondeo_sin_firm_aborta(tmp_path):
    accounts = _accounts_file(
        tmp_path,
        {
            "fund": {
                "type": "fondeo",
                "account_size": 100_000,
                "limits": {"daily_loss_pct": 0.05, "max_drawdown_pct": 0.10},
            }
        },
    )
    forward = _forward_file(tmp_path)
    with pytest.raises(GuardianError, match="sin firm/phase"):
        build_config("fund", accounts_path=accounts, forward_path=forward)


def test_cuenta_propia_sin_limits_aborta(tmp_path):
    accounts = _accounts_file(
        tmp_path,
        {"paper_test": {"type": "capital_propio", "account_size": 50_000}},
    )
    forward = _forward_file(tmp_path)
    with pytest.raises(GuardianError, match="falta 'limits'"):
        build_config("paper_test", accounts_path=accounts, forward_path=forward)


def test_cuenta_propia_con_limits_invalidos_aborta(tmp_path):
    accounts = _accounts_file(
        tmp_path,
        {
            "paper_test": {
                "type": "capital_propio",
                "account_size": 50_000,
                "limits": {"daily_loss_pct": 0.0, "max_drawdown_pct": 0.07},
            }
        },
    )
    forward = _forward_file(tmp_path)
    with pytest.raises(GuardianError, match="daily_loss_pct inválido"):
        build_config("paper_test", accounts_path=accounts, forward_path=forward)


def test_forward_sin_magics_aborta(tmp_path):
    accounts = _accounts_file(tmp_path, {"ftmo_demo": _ftmo_account()})
    path = tmp_path / "empty_forward.yaml"
    path.write_text(
        yaml.safe_dump(
            {"version": 1, "account": "ftmo_demo", "bots": []}, sort_keys=False
        ),
        encoding="utf-8",
    )
    with pytest.raises(GuardianError, match="magics"):
        build_config("ftmo_demo", accounts_path=accounts, forward_path=path)


def test_terminal_data_path(tmp_path):
    lab = tmp_path / "lab.yaml"
    lab.write_text(
        yaml.safe_dump({"mt5": {"data_path": str(tmp_path / "terminal")}}),
        encoding="utf-8",
    )
    assert terminal_data_path(lab) == tmp_path / "terminal"

    lab.write_text(yaml.safe_dump({"mt5": {"terminal_path": None}}), encoding="utf-8")
    assert terminal_data_path(lab) is None


def test_resolve_target_fallback(tmp_path):
    lab = tmp_path / "lab.yaml"
    lab.write_text(yaml.safe_dump({"mt5": {}}), encoding="utf-8")
    target, fallback, warning = resolve_target(
        lab_path=lab, fallback_dir=tmp_path / "data"
    )
    assert target == tmp_path / "data" / "guardian.json"
    assert fallback is True
    assert warning and "mt5.data_path" in warning


def test_export_escribe_json_atomico(tmp_path):
    target = tmp_path / "terminal" / "MQL5" / "Files" / GUARDIAN_FILENAME
    result = export_config("ftmo_demo", target_path=target)
    assert Path(result["path"]) == target
    assert target.exists()
    assert not target.with_suffix(".json.tmp").exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["account"] == "ftmo_demo"
    assert payload["magics"] == [20261151, 20261152, 20261153]


def test_export_usa_data_path_del_terminal(tmp_path):
    lab = tmp_path / "lab.yaml"
    lab.write_text(
        yaml.safe_dump({"mt5": {"data_path": str(tmp_path / "terminal")}}),
        encoding="utf-8",
    )
    result = export_config("ftmo_demo", lab_path=lab)
    assert result["fallback"] is False
    assert Path(result["path"]) == (
        tmp_path / "terminal" / "MQL5" / "Files" / GUARDIAN_FILENAME
    )
    assert Path(result["path"]).exists()


def test_export_fallback_sin_data_path(tmp_path):
    lab = tmp_path / "lab.yaml"
    lab.write_text(yaml.safe_dump({"mt5": {}}), encoding="utf-8")
    result = export_config(
        "ftmo_demo", lab_path=lab, fallback_dir=tmp_path / "data"
    )
    assert result["fallback"] is True
    assert "mt5.data_path" in result["warning"]
    assert Path(result["path"]) == tmp_path / "data" / "guardian.json"
    assert Path(result["path"]).exists()


def test_read_exported_sin_datos(tmp_path):
    state = read_exported(target_path=tmp_path / "missing.json")
    assert state["exists"] is False
    assert state["config"] is None


def test_read_exported_tras_export(tmp_path):
    target = tmp_path / "guardian.json"
    export_config("ftmo_demo", target_path=target)
    state = read_exported(target_path=target)
    assert state["exists"] is True
    assert state["config"]["account"] == "ftmo_demo"
    assert state["age_s"] is not None
    assert state["age_s"] >= 0


def test_read_exported_json_invalido(tmp_path):
    target = tmp_path / "guardian.json"
    target.write_text("{", encoding="utf-8")
    with pytest.raises(GuardianError, match="JSON inválido"):
        read_exported(target_path=target)


def _write_log(base: Path, lines: list[str]) -> Path:
    log = base / "MQL5" / "Files" / "tradinglab_guardian.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


def test_sesiones_alert_cuentan_dias_del_log(tmp_path: Path) -> None:
    base = tmp_path / "terminal"
    _write_log(
        base,
        [
            "2026.11.10 23:42:39 INIT mode=ALERT account=ftmo_demo daily=0.0450",
            "2026.11.11 00:00:12 START day=20261111 equity=100000.00",
            "2026.11.11 23:59:01 INIT mode=ALERT account=ftmo_demo daily=0.0450",
        ],
    )
    state = guardian_sessions(required=5, data_path=base)
    assert state["ok"] is True
    assert state["sessions"] == 2
    assert state["session_days"] == ["2026.11.10", "2026.11.11"]
    assert state["triggers"] == 0
    assert state["gate_ok"] is False
    assert "faltan 3" in state["reason"]


def test_puerta_cumple_con_cinco_sesiones_sin_disparos(tmp_path: Path) -> None:
    base = tmp_path / "terminal"
    _write_log(
        base,
        [
            f"2026.11.{day:02d} 00:00:12 INIT mode=ALERT account=ftmo_demo daily=0.0450"
            for day in (10, 11, 12, 13, 16)
        ],
    )
    state = guardian_sessions(required=5, data_path=base)
    assert state["sessions"] == 5
    assert state["triggers"] == 0
    assert state["gate_ok"] is True
    assert "puerta cumplida" in state["reason"]


def test_un_disparo_bloquea_la_puerta(tmp_path: Path) -> None:
    base = tmp_path / "terminal"
    _write_log(
        base,
        [
            f"2026.11.{day:02d} 00:00:12 INIT mode=ALERT account=ftmo_demo daily=0.0450"
            for day in (10, 11, 12, 13, 16)
        ]
        + ["2026.11.16 12:00:00 TRIGGER daily loss 5.00% >= 4.50%"],
    )
    state = guardian_sessions(required=5, data_path=base)
    assert state["sessions"] == 5
    assert state["triggers"] == 1
    assert state["gate_ok"] is False
    assert "falsos positivos" in state["reason"]


def test_sesiones_sin_log_no_inventan_datos(tmp_path: Path) -> None:
    state = guardian_sessions(required=5, data_path=tmp_path / "terminal")
    assert state["ok"] is True
    assert state["sessions"] == 0
    assert state["gate_ok"] is False
    assert state["exists"] is False


def test_el_log_se_busca_en_otro_terminal_de_mt5(tmp_path: Path, monkeypatch) -> None:
    """Si el terminal configurado no tiene log, se usa el del EA en otro."""
    otro = tmp_path / "otro"
    log = _write_log(
        otro,
        [
            f"2026.11.{day:02d} 00:00:12 INIT mode=ALERT account=ftmo_demo daily=0.0450"
            for day in (10, 11, 12, 13, 16)
        ],
    )
    monkeypatch.setattr(
        "tradinglab.guardian._terminal_data_path", lambda: tmp_path / "terminal"
    )
    monkeypatch.setattr(
        "tradinglab.guardian._other_terminal_logs", lambda: [log]
    )
    state = guardian_sessions(required=5)
    assert state["exists"] is True
    assert state["sessions"] == 5
    assert state["gate_ok"] is True
    assert "otro terminal" in state["source"]


def test_el_terminal_del_guardian_viene_de_su_config(tmp_path: Path) -> None:
    path = tmp_path / "guardian.yaml"
    path.write_text(
        yaml.safe_dump({"terminal_path": str(tmp_path / "terminal")}), encoding="utf-8"
    )
    assert guardian_terminal_path(path) == tmp_path / "terminal"
    assert guardian_terminal_path(tmp_path / "no-existe.yaml") is None


def test_la_configuracion_real_apunta_a_un_terminal():
    path = guardian_terminal_path()
    assert path is not None
    assert path.exists()


def test_cli_guardian_export(monkeypatch, tmp_path):
    cfg = build_config("ftmo_demo")
    synthetic = {
        "path": str(tmp_path / "guardian.json"),
        "fallback": True,
        "warning": "falta mt5.data_path en config/lab.yaml",
        "config": cfg,
    }
    monkeypatch.setattr(
        "tradinglab.guardian.export_config", lambda *a, **k: synthetic
    )
    result = CliRunner().invoke(cli_mod.app, ["guardian", "export"])
    assert result.exit_code == 0
    assert "Guardián" in result.output
    assert "20261151" in result.output
    assert "falta mt5.data_path" in result.output


def test_cli_guardian_status_sin_datos(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tradinglab.guardian.resolve_target",
        lambda **kwargs: (tmp_path / "missing.json", False, None),
    )
    result = CliRunner().invoke(cli_mod.app, ["guardian", "status"])
    assert result.exit_code == 0
    assert "Sin datos" in result.output


def test_cli_guardian_status_con_datos(monkeypatch, tmp_path):
    target = tmp_path / "guardian.json"
    export_config("ftmo_demo", target_path=target)
    monkeypatch.setattr(
        "tradinglab.guardian.resolve_target",
        lambda **kwargs: (target, False, None),
    )
    result = CliRunner().invoke(cli_mod.app, ["guardian", "status"])
    assert result.exit_code == 0
    assert "ftmo_demo" in result.output
    assert "20261151" in result.output


@pytest.mark.mt5
@pytest.mark.skipif(
    os.environ.get("TRADINGLAB_MT5_TESTS") != "1",
    reason="requiere terminal MT5; activa TRADINGLAB_MT5_TESTS=1",
)
def test_export_al_terminal_real():
    result = export_config("ftmo_demo")
    assert Path(result["path"]).exists()
