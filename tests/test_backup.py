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
    assert "MANIFEST.json" in script
    assert "PASS" in script


def test_migrate_secrets_no_imprime_valores():
    script = (ROOT / "scripts" / "migrate_secrets.py").read_text(encoding="utf-8")
    assert "keyring.set_password" in script
    assert "get_password" in script
    assert "print(f\"OK   {key}\")" in script
    assert "print(f\"OK   {key}: {value}\")" not in script

def test_backup_usa_api_sqlite_y_manifiesto():
    backup = (ROOT / "scripts" / "backup.ps1").read_text(encoding="utf-8")
    helper = (ROOT / "scripts" / "backup_db.py").read_text(encoding="utf-8")
    assert "backup_db.py" in backup
    assert "MANIFEST.json" in backup
    assert "integrity_check" in backup
    assert "fills" in backup and "strategy_trials" in backup and "ai_decisions" in backup
    assert 'Copy-Item "data\\lab.db"' not in backup
    assert "source_con.backup(dest_con)" in helper
    assert "PRAGMA integrity_check" in helper
    assert "wal_checkpoint(TRUNCATE)" in helper
    assert "journal_mode=DELETE" in helper


def test_backup_offsite_cifra_y_restore_descifra():
    backup = (ROOT / "scripts" / "backup.ps1").read_text(encoding="utf-8")
    assert "-Offsite" in backup
    assert "backup.offsite_dir" in backup
    assert "backup_crypto.ps1" in backup
    assert "0.5 * $drive.Free" in backup
    assert "14" in backup and "8" in backup
    restore = (ROOT / "scripts" / "restore_test.ps1").read_text(encoding="utf-8")
    assert "backup_crypto.ps1" in restore
    assert "decrypt" in restore
    assert "BACKUP_PASSWORD" in restore


def test_backup_crypto_ida_y_vuelta(tmp_path):
    import os
    import shutil
    import subprocess

    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        import pytest

        pytest.skip("PowerShell no disponible")
    source = tmp_path / "plain.txt"
    source.write_bytes(b"TradingLab backup de prueba")
    encrypted = tmp_path / "plain.enc"
    decrypted = tmp_path / "plain.out"
    env = dict(os.environ)
    env["TRADINGLAB_BACKUP_PASSWORD"] = "clave-de-test"
    for mode, origin, target in (
        ("encrypt", source, encrypted),
        ("decrypt", encrypted, decrypted),
    ):
        result = subprocess.run(
            [
                powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "scripts" / "backup_crypto.ps1"),
                "-Mode", mode, "-Path", str(origin), "-Out", str(target),
            ],
            env=env, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
    assert decrypted.read_bytes() == source.read_bytes()
    assert b"TradingLab" not in encrypted.read_bytes()
