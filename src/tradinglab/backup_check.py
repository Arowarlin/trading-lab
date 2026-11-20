"""Verifica el ultimo backup restaurandolo y comparando conteos.

El backup antiguo copiaba solo ``lab.db``. Si la base estaba en WAL, el zip
podia pasar ``PRAGMA integrity_check`` y aun asi perder las transacciones que
seguian en ``lab.db-wal``: el archivo restaurado es valido, solo es mas viejo.
Por eso el drill ahora restaura el ultimo zip y compara los conteos con las
filas de la base viva anteriores a ``backup_at``. Las filas posteriores al
backup son tolerables; las anteriores que falten son un FAIL.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

DEFAULT_BACKUP_DIR = Path(r"F:\TradingLabBackups")
TABLES = ("fills", "strategy_trials", "ai_decisions")
TIME_COLUMNS = {
    "fills": "ts_utc",
    "strategy_trials": "ts",
    "ai_decisions": "ts",
}


def _backup_dir(directory: str | Path | None = None) -> Path:
    if directory is not None:
        return Path(directory)
    env = os.environ.get("TRADINGLAB_BACKUP_DIR")
    return Path(env) if env else DEFAULT_BACKUP_DIR


def latest_backup(directory: str | Path | None = None) -> Path | None:
    root = _backup_dir(directory)
    if not root.is_dir():
        return None
    files = sorted(
        root.glob("trading-lab_*.zip"),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    return files[0] if files else None


def _counts(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(db_path, timeout=30)
    try:
        return {
            table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in TABLES
        }
    finally:
        con.close()


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})")}


def _live_before(db_path: Path, backup_at: str) -> dict[str, int]:
    con = sqlite3.connect(db_path, timeout=30)
    try:
        counts: dict[str, int] = {}
        for table in TABLES:
            columns = _table_columns(con, table)
            column = TIME_COLUMNS.get(table, "ts")
            if column not in columns:
                column = "ts"
            if column not in columns:
                raise RuntimeError(f"{table} no tiene columna de tiempo")
            counts[table] = int(
                con.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE {column} IS NULL OR {column} <= ?",
                    (backup_at,),
                ).fetchone()[0]
            )
        return counts
    finally:
        con.close()


def _parse_manifest(manifest: dict) -> tuple[str, dict[str, int]]:
    backup_at = str(manifest.get("backup_at") or "")
    if not backup_at:
        raise RuntimeError("MANIFEST.json sin backup_at")
    try:
        datetime.fromisoformat(backup_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"backup_at invalido: {backup_at}") from exc
    database = manifest.get("database") or {}
    counts = database.get("counts") or {}
    parsed: dict[str, int] = {}
    for table in TABLES:
        if table not in counts:
            raise RuntimeError(f"MANIFEST.json sin conteo de {table}")
        parsed[table] = int(counts[table])
    return backup_at, parsed


def verify_backup(zip_path: str | Path, live_db: str | Path) -> dict:
    """Restaura ``zip_path`` y compara sus conteos con la base viva."""
    archive = Path(zip_path)
    live = Path(live_db)
    problems: list[str] = []
    result: dict = {
        "ok": False,
        "backup": str(archive),
        "backup_at": "",
        "integrity_check": "",
        "restored": {},
        "live_before": {},
        "manifest": {},
        "problems": problems,
        "detail": "",
    }
    if not archive.is_file():
        result["detail"] = f"no existe el backup: {archive}"
        return result
    if not live.is_file():
        result["detail"] = f"no existe la base viva: {live}"
        return result

    with tempfile.TemporaryDirectory(prefix="tradinglab-drill-") as temp:
        root = Path(temp)
        try:
            with zipfile.ZipFile(archive) as zf:
                for name in ("MANIFEST.json", "data/lab.db"):
                    try:
                        zf.extract(name, root)
                    except KeyError:
                        problems.append(f"falta {name} en el zip")
        except zipfile.BadZipFile as exc:
            result["detail"] = f"zip invalido: {exc}"
            return result

        manifest_path = root / "MANIFEST.json"
        db_path = root / "data" / "lab.db"
        if not manifest_path.is_file() or not db_path.is_file():
            result["detail"] = "; ".join(problems) or "backup incompleto"
            return result

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            backup_at, manifest_counts = _parse_manifest(manifest)
        except Exception as exc:
            result["detail"] = f"manifiesto invalido: {exc}"
            return result
        result["backup_at"] = backup_at
        result["manifest"] = manifest_counts

        con = sqlite3.connect(db_path, timeout=30)
        try:
            integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
            restored = {
                table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in TABLES
            }
        except sqlite3.Error as exc:
            result["detail"] = f"no se pudo leer el backup: {exc}"
            return result
        finally:
            con.close()

        result["integrity_check"] = integrity
        result["restored"] = restored
        if integrity.lower() != "ok":
            problems.append(f"integrity_check={integrity}")
        for table in TABLES:
            if restored[table] != manifest_counts[table]:
                problems.append(
                    f"{table}: manifiesto {manifest_counts[table]} != restaurado {restored[table]}"
                )

        try:
            live_before = _live_before(live, backup_at)
        except Exception as exc:
            result["detail"] = f"no se pudo leer la base viva: {exc}"
            return result
        result["live_before"] = live_before

        for table in TABLES:
            if restored[table] < live_before[table]:
                problems.append(
                    f"{table}: backup {restored[table]} < vivas antes de {backup_at} "
                    f"{live_before[table]}"
                )

    if problems:
        result["detail"] = "; ".join(problems)[:400]
        return result
    result["ok"] = True
    result["detail"] = (
        f"OK {archive.name}: fills {result['restored']['fills']} / "
        f"trials {result['restored']['strategy_trials']} / "
        f"decisions {result['restored']['ai_decisions']}"
    )
    return result


def verify_latest_backup(
    live_db: str | Path,
    directory: str | Path | None = None,
) -> dict:
    archive = latest_backup(directory)
    if archive is None:
        return {
            "ok": False,
            "backup": "",
            "backup_at": "",
            "integrity_check": "",
            "restored": {},
            "live_before": {},
            "manifest": {},
            "problems": ["no hay backups"],
            "detail": f"no hay backups en {_backup_dir(directory)}",
        }
    return verify_backup(archive, live_db)


__all__ = [
    "DEFAULT_BACKUP_DIR",
    "TABLES",
    "TIME_COLUMNS",
    "latest_backup",
    "verify_backup",
    "verify_latest_backup",
]
