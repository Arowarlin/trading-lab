from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tradinglab.cli import app
from tradinglab.db import connect, init_db
from tradinglab.drill import DrillError, run_drill, simulate_drill


class _Settings:
    def __init__(self, mode: str = "paper") -> None:
        self.mode = mode
        self.timezone = "UTC"
        self.risk = {"daily_loss_pct": 0.05}


def test_el_simulacro_rechaza_live():
    with pytest.raises(DrillError):
        run_drill("data/lab.db", _Settings("live"), confirm=True, armed=True)
    with pytest.raises(DrillError):
        simulate_drill("data/lab.db", _Settings("live"))


def test_el_simulacro_exige_operador_armado_y_confirmacion(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with pytest.raises(DrillError):
        run_drill(db, _Settings(), confirm=True, armed=False)
    with pytest.raises(DrillError):
        run_drill(db, _Settings(), confirm=False, armed=True)


def test_la_simulacion_no_toca_nada_y_deja_rastro(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO orders(ts, ticker, side, qty, status) "
            "VALUES('2026-11-11T00:00:00+00:00', 'AAPL', 'buy', 5, 'pending')"
        )
    before = _counts(db)
    result = simulate_drill(db, _Settings())
    assert result["pending_orders"] == 1
    assert result["mode"] == "paper"
    assert result["killswitch_active"] is False
    # no se cancela nada ni se cierra nada
    assert _counts(db) == before
    with connect(db) as con:
        rows = con.execute(
            "SELECT action, actor FROM console_actions WHERE action = 'drill_simulacion'"
        ).fetchall()
    assert rows and rows[0]["actor"] == "drill"


def test_la_simulacion_por_cli_no_pide_pin(tmp_path, monkeypatch):
    import tradinglab.cli as cli_mod

    monkeypatch.setattr(cli_mod, "DEFAULT_DB", tmp_path / "lab.db")
    init_db(tmp_path / "lab.db")
    runner = CliRunner()
    result = runner.invoke(app, ["drill", "--dry-run"])
    assert result.exit_code == 0
    assert "Simulación" in result.output


def _counts(db: Path) -> tuple[int, int]:
    with connect(db) as con:
        orders = int(
            con.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0]
        )
        positions = int(con.execute("SELECT COUNT(*) FROM positions").fetchone()[0])
    return orders, positions


def test_el_drill_puede_comprobar_el_backup(tmp_path, monkeypatch):
    import tradinglab.drill as drill_mod

    db = tmp_path / "lab.db"
    init_db(db)
    monkeypatch.setattr(
        drill_mod,
        "verify_latest_backup",
        lambda live_db: {"ok": True, "detail": "OK backup"},
    )
    result = simulate_drill(db, _Settings(), check_backup=True)
    assert result["backup_ok"] is True
    assert result["backup"]["detail"] == "OK backup"
    assert any(step["step"] == "backup" and step["ok"] for step in result["steps"])


def test_el_drill_falla_si_el_backup_no_tiene_filas_anteriores(tmp_path, monkeypatch):
    import tradinglab.drill as drill_mod

    db = tmp_path / "lab.db"
    init_db(db)
    monkeypatch.setattr(
        drill_mod,
        "verify_latest_backup",
        lambda live_db: {"ok": False, "detail": "fills: backup 0 < vivas 1"},
    )
    result = simulate_drill(db, _Settings(), check_backup=True)
    assert result["backup_ok"] is False
    assert any(step["step"] == "backup" and not step["ok"] for step in result["steps"])


def test_el_cli_drill_check_backup_sale_1_si_falla(tmp_path, monkeypatch):
    import tradinglab.cli as cli_mod
    import tradinglab.drill as drill_mod

    monkeypatch.setattr(cli_mod, "DEFAULT_DB", tmp_path / "lab.db")
    init_db(tmp_path / "lab.db")
    monkeypatch.setattr(
        drill_mod,
        "verify_latest_backup",
        lambda live_db: {"ok": False, "detail": "falta fills anterior"},
    )
    runner = CliRunner()
    result = runner.invoke(app, ["drill", "--dry-run", "--check-backup"])
    assert result.exit_code == 1
    assert "Backup FAIL" in result.output


def test_el_simulacro_real_avisa_por_los_dos_canales(tmp_path, monkeypatch):
    enviados: list[str] = []

    import tradinglab.alerts as alerts_mod
    import tradinglab.telegram as telegram_mod

    monkeypatch.setattr(
        alerts_mod, "send", lambda event, message, **kwargs: enviados.append(f"ntfy:{event}")
    )
    monkeypatch.setattr(
        telegram_mod, "send_configured", lambda text: enviados.append("telegram")
    )
    db = tmp_path / "lab.db"
    init_db(db)
    result = run_drill(db, _Settings(), confirm=True, armed=True)
    assert result["cancelled_orders"] == 0
    assert "ntfy:drill" in enviados
    assert "telegram" in enviados
    with connect(db) as con:
        row = con.execute(
            "SELECT actor FROM console_actions WHERE action = 'drill' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None and row["actor"] == "drill"
    detail = json.dumps(result, ensure_ascii=False)
    assert "steps" in detail
