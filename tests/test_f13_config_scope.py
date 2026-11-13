from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from tradinglab.config import Settings
from tradinglab.f13 import config_hash


def _copy_config(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "config"
    for name in (
        "lab.yaml", "ops.yaml", "bots.yaml", "prop.yaml",
        "f13.yaml", "accounts.yaml",
    ):
        shutil.copy2(source / name, root / "config" / name)
    return root


def test_ops_no_cambia_hash_y_bot_si(tmp_path):
    root = _copy_config(tmp_path)
    before = config_hash(root)
    ops = root / "config" / "ops.yaml"
    ops.write_text(
        ops.read_text(encoding="utf-8") + "\n# cambio operativo ajeno\n",
        encoding="utf-8",
    )
    assert config_hash(root) == before

    bots = root / "config" / "bots.yaml"
    data = yaml.safe_load(bots.read_text(encoding="utf-8"))
    for bot in data["bots"]:
        if bot["id"] == "qqq-trend-f13":
            bot["exposure"] = 0.36
    bots.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    assert config_hash(root) != before


def test_settings_mezcla_ops_y_lab(tmp_path):
    root = _copy_config(tmp_path)
    settings = Settings.load(root / "config" / "lab.yaml")
    assert settings.mode == "paper"
    assert settings.llm.model == "qwen/qwen3-30b-a3b"
    assert settings.daytrader.enabled is True
    assert settings.mt5.default_symbol == "EURUSD"
    assert settings.risk.per_trade_risk_pct == 0.01

def test_hash_usa_la_cuenta_real_del_bot(tmp_path):
    root = _copy_config(tmp_path)
    before = config_hash(root)
    path = root / "config" / "accounts.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["accounts"]["alpaca_paper"]["limits"]["daily_loss_pct"] = 0.99
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    assert config_hash(root) == before
    data["accounts"]["paper_main"]["limits"]["daily_loss_pct"] = 0.99
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    assert config_hash(root) != before
