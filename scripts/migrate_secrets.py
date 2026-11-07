"""Migra los secretos de .env a Windows Credential Manager (keyring).

Nunca imprime valores: solo nombres de claves y el resultado de la verificación.
El .env se conserva como fallback local; los backups ya no lo incluyen.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import keyring
from dotenv import dotenv_values

from tradinglab.config import KEYRING_SERVICE, ROOT, SECRET_KEYS


def _status() -> int:
    found = 0
    for key in SECRET_KEYS:
        if keyring.get_password(KEYRING_SERVICE, key):
            print(f"OK   {key}")
            found += 1
        else:
            print(f"--   {key}")
    print(f"{found}/{len(SECRET_KEYS)} secretos en {KEYRING_SERVICE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrar secretos de .env a keyring")
    parser.add_argument("--status", action="store_true", help="Solo mostrar qué claves existen")
    parser.add_argument("--dry-run", action="store_true", help="No escribir; solo listar")
    parser.add_argument(
        "--dotenv",
        default=str(ROOT / ".env"),
        help="Ruta del .env (por defecto E:\\trading-lab\\.env)",
    )
    args = parser.parse_args()

    if args.status:
        return _status()

    path = Path(args.dotenv)
    if not path.exists():
        print(f"No existe {path}; no hay nada que migrar.")
        return 1

    values = dotenv_values(path)
    migrated = 0
    for key in SECRET_KEYS:
        value = values.get(key) or os.getenv(key)
        if not value or not str(value).strip():
            print(f"--   {key} (vacío, se omite)")
            continue
        if args.dry_run:
            print(f"PLAN {key}")
            continue
        try:
            keyring.set_password(KEYRING_SERVICE, key, str(value))
            check = keyring.get_password(KEYRING_SERVICE, key)
        except Exception as exc:
            print(f"ERROR {key}: {exc}")
            return 1
        if check != str(value):
            print(f"ERROR {key}: la verificación no coincide")
            return 1
        print(f"OK   {key}")
        migrated += 1

    if args.dry_run:
        print("Dry-run: no se escribió nada.")
    else:
        print(f"Migrados {migrated} secretos a {KEYRING_SERVICE}.")
        print("El .env sigue como fallback; no se imprime ningún valor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
