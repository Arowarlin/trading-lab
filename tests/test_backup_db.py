from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("fills", "strategy_trials", "ai_decisions")
TIME_COLUMNS = {
    "fills": "ts_utc",
    "strategy_trials": "ts",
    "ai_decisions": "ts",
}


def _wal_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    for table in TABLES:
        con.execute(
            f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, {TIME_COLUMNS[table]} TEXT)"
        )
    return con


def test_backup_db_incluye_wal_sin_volcar(tmp_path):
    db = tmp_path / "lab.db"
    con = _wal_db(db)
    for table in TABLES:
        con.execute(
            f"INSERT INTO {table}({TIME_COLUMNS[table]}) VALUES (?)",
            ("2026-11-16T13:00:00+00:00",),
        )
    con.commit()

    wal = Path(str(db) + "-wal")
    assert wal.exists() and wal.stat().st_size > 0

    dest = tmp_path / "backup.db"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "backup_db.py"),
            "--source",
            str(db),
            "--dest",
            str(dest),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["integrity_check"] == "ok"
    assert payload["counts"] == {
        "fills": 1,
        "strategy_trials": 1,
        "ai_decisions": 1,
    }
    con.close()

    restored = sqlite3.connect(dest)
    try:
        for table in TABLES:
            count = restored.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 1
        assert restored.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        restored.close()
    assert not Path(str(dest) + "-wal").exists()
