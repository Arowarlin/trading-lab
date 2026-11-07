from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_backup_no_incluye_env():
    script = (ROOT / "scripts" / "backup.ps1").read_text(encoding="utf-8")
    assert re.search(r'"\.env"', script) is None
    assert ".env.example" in script
    assert "restore_test.ps1" in script
    assert "NO incluye .env" in script


def test_restore_test_existe_y_verifica():
    script = (ROOT / "scripts" / "restore_test.ps1").read_text(encoding="utf-8")
    assert "Expand-Archive" in script
    assert ".env" in script
    assert "ALPACA_API_KEY" in script
    assert "integrity_check" in script
    assert "PASS" in script


def test_migrate_secrets_no_imprime_valores():
    script = (ROOT / "scripts" / "migrate_secrets.py").read_text(encoding="utf-8")
    assert "keyring.set_password" in script
    assert "get_password" in script
    assert "print(f\"OK   {key}\")" in script
    assert "print(f\"OK   {key}: {value}\")" not in script
