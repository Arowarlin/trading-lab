"""Ayuda a backup.ps1: lee config y keyring sin imprimir secretos por error.

Uso interno:
  python scripts/backup_config.py dir
  python scripts/backup_config.py password
"""
from __future__ import annotations

import sys
from pathlib import Path

import keyring
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 1 or args[0] not in {"dir", "password"}:
        print("uso: backup_config.py dir|password", file=sys.stderr)
        return 2
    if args[0] == "password":
        value = keyring.get_password("tradinglab", "BACKUP_PASSWORD") or ""
        if value:
            print(value)
        return 0
    data = yaml.safe_load(
        (ROOT / "config" / "lab.yaml").read_text(encoding="utf-8")
    ) or {}
    value = ((data.get("backup") or {}).get("offsite_dir") or "")
    print(str(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
