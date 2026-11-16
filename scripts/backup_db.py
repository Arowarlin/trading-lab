"""Copia consistente de SQLite con la API de backup.

La base origen se abre en modo lectura y ``sqlite3.Connection.backup()`` copia
tambien las paginas confirmadas que siguen en el WAL. El destino se verifica
con ``PRAGMA integrity_check`` y se cuentan ``fills``, ``strategy_trials`` y
``ai_decisions``. El resultado se escribe como JSON en stdout.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

TABLES = ("fills", "strategy_trials", "ai_decisions")
TIME_COLUMNS = {
    "fills": "ts_utc",
    "strategy_trials": "ts",
    "ai_decisions": "ts",
}


def _open_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def _remove_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        try:
            Path(str(path) + suffix).unlink()
        except FileNotFoundError:
            pass


def _counts(con: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in TABLES
    }


def backup(source: Path, dest: Path) -> dict:
    """Copia ``source`` a ``dest`` y devuelve el manifiesto del backup."""
    if not source.is_file():
        raise FileNotFoundError(f"no existe la base: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.unlink()
    except FileNotFoundError:
        pass
    _remove_sidecars(dest)

    backup_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_con = _open_readonly(source)
    dest_con = sqlite3.connect(dest, timeout=30)
    try:
        source_con.backup(dest_con)
        dest_con.commit()
        dest_con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dest_con.execute("PRAGMA journal_mode=DELETE")
        dest_con.commit()
        integrity = str(dest_con.execute("PRAGMA integrity_check").fetchone()[0])
        counts = _counts(dest_con)
    finally:
        source_con.close()
        dest_con.close()
    _remove_sidecars(dest)

    result = {
        "ok": integrity.lower() == "ok",
        "source": str(source),
        "dest": str(dest),
        "backup_at": backup_at,
        "integrity_check": integrity,
        "counts": counts,
        "time_columns": TIME_COLUMNS,
    }
    if not result["ok"]:
        try:
            dest.unlink()
        except FileNotFoundError:
            pass
        raise RuntimeError(f"integrity_check fallo: {integrity}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup consistente de SQLite")
    parser.add_argument("--source", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()
    try:
        result = backup(Path(args.source), Path(args.dest))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
