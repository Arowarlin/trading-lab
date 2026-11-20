from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tradinglab.config import Settings
from tradinglab.db import connect
from tradinglab.f13 import (
    config_check,
    config_hash,
    config_payload,
    freeze,
    migrate_account,
    refreeze_history,
    status,
)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    config = root / "config"
    config.mkdir(parents=True)
    (config / "bots.yaml").write_text(
        "bots:\n"
        "  - id: other-bot\n"
        "    enabled: false\n"
        "    account: paper_main\n"
        "  - id: qqq-trend-f13\n"
        "    type: deterministic\n"
        "    enabled: true\n"
        "    account: paper_main\n"
        "    params: {fast: 50, slow: 200, regime: 200}\n",
        encoding="utf-8",
    )
    (config / "f13.yaml").write_text(
        "bot: qqq-trend-f13\n"
        "symbol: QQQ\n"
        "status: paper\n"
        "criteria:\n"
        "  window_weeks: 8\n"
        "  min_cycles_pct: 0.95\n",
        encoding="utf-8",
    )
    (config / "accounts.yaml").write_text(
        "accounts:\n"
        "  paper_main:\n"
        "    name: Paper interno\n"
        "    type: capital_propio\n"
        "    broker: paper\n"
        "    platform: internal\n"
        "    status: active\n"
        "    account_size: 100000\n"
        "  alpaca_paper:\n"
        "    name: Alpaca paper\n"
        "    type: capital_propio\n"
        "    broker: alpaca\n"
        "    platform: alpaca\n"
        "    status: active\n"
        "    account_size: 100000\n",
        encoding="utf-8",
    )
    (config / "lab.yaml").write_text(
        "mode: paper\nexecution:\n  broker: paper\n", encoding="utf-8"
    )
    (config / "prop.yaml").write_text("rules: {}\n", encoding="utf-8")
    return root


def _settings() -> Settings:
    return Settings(mode="paper")


def test_migracion_cambia_cuenta_y_reinicia_ventana(tmp_path):
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    before = status(db)
    assert before is not None

    result = migrate_account(
        db,
        bot="qqq-trend-f13",
        new_account="alpaca_paper",
        start_date="2026-11-13",
        reason="migración a bróker real (alpaca_paper)",
        root=root,
        settings=_settings(),
    )

    assert result["old_account"] == "paper_main"
    assert result["new_account"] == "alpaca_paper"
    assert result["start_date"] == "2026-11-13"
    assert result["previous_hash"] == before["config_hash"]
    assert result["new_hash"] == config_hash(root)
    assert result["new_hash"] != before["config_hash"]

    row = status(db)
    assert row["start_date"] == "2026-11-13"
    assert row["previous_hash"] == before["config_hash"]
    assert row["refreeze_reason"] == "migración a bróker real (alpaca_paper)"
    assert row["refrozen_at"]
    assert config_check(db, root)["ok"] is True

    payload = config_payload(root)
    assert payload["account"]["name"] == "Alpaca paper"
    assert payload["account"]["platform"] == "alpaca"
    assert payload["f13"]["start_date"] == "2026-11-13"

    bots = yaml.safe_load((root / "config" / "bots.yaml").read_text(encoding="utf-8"))
    f13_bot = next(item for item in bots["bots"] if item["id"] == "qqq-trend-f13")
    other = next(item for item in bots["bots"] if item["id"] == "other-bot")
    assert f13_bot["account"] == "alpaca_paper"
    assert other["account"] == "paper_main"
    assert other["enabled"] is False

    f13_yaml = yaml.safe_load((root / "config" / "f13.yaml").read_text(encoding="utf-8"))
    assert f13_yaml["start_date"] == "2026-11-13"
    assert f13_yaml["criteria"]["window_weeks"] == 8

    history = refreeze_history(db)
    assert history[0]["reason"] == "migración a bróker real (alpaca_paper)"
    assert history[0]["changed_files"] == '["bots.yaml", "f13.yaml"]'
    with connect(db) as con:
        audit = con.execute(
            "SELECT action, params FROM console_actions "
            "WHERE action = 'f13_migrate_account' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert audit is not None
    assert "alpaca_paper" in audit["params"]


def test_migracion_rechaza_live_sin_tocar_archivos(tmp_path):
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    before = (root / "config" / "bots.yaml").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="live"):
        migrate_account(
            db,
            bot="qqq-trend-f13",
            new_account="alpaca_paper",
            start_date="2026-11-13",
            reason="prueba live",
            root=root,
            settings=Settings(mode="live"),
        )
    assert (root / "config" / "bots.yaml").read_text(encoding="utf-8") == before
    assert status(db)["start_date"] == "2026-11-09"


def test_migracion_rechaza_cuenta_no_paper(tmp_path):
    root = _repo(tmp_path)
    path = root / "config" / "accounts.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "  alpaca_live:\n"
        "    name: Alpaca live\n"
        "    broker: alpaca\n"
        "    platform: alpaca\n"
        "    status: live\n"
        "    account_size: 100000\n",
        encoding="utf-8",
    )
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    # La cuenta nueva forma parte del freeze; el rechazo debe ser por estado.
    with pytest.raises(ValueError, match="no paper"):
        migrate_account(
            db,
            bot="qqq-trend-f13",
            new_account="alpaca_live",
            start_date="2026-11-13",
            reason="prueba",
            root=root,
            settings=_settings(),
        )


def test_migracion_rechaza_config_ya_cambiada(tmp_path):
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    (root / "config" / "prop.yaml").write_text("rules: {changed: true}\n", encoding="utf-8")
    before = (root / "config" / "bots.yaml").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="ya cambió"):
        migrate_account(
            db,
            bot="qqq-trend-f13",
            new_account="alpaca_paper",
            start_date="2026-11-13",
            reason="prueba",
            root=root,
            settings=_settings(),
        )
    assert (root / "config" / "bots.yaml").read_text(encoding="utf-8") == before
    assert status(db)["start_date"] == "2026-11-09"


def test_migracion_rechaza_misma_cuenta(tmp_path):
    root = _repo(tmp_path)
    db = tmp_path / "lab.db"
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-11-09",
        root=root,
    )
    with pytest.raises(ValueError, match="ya usa"):
        migrate_account(
            db,
            bot="qqq-trend-f13",
            new_account="paper_main",
            start_date="2026-11-13",
            reason="prueba",
            root=root,
            settings=_settings(),
        )
