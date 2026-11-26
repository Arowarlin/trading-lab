"""Añade la entrada de ENG-1 F5 a docs/CHANGELOG-produccion.md bajo el lock ``changelog-produccion``.

Lo ejecuta el operador **después** del merge (ver INTEGRACION_PENDIENTE.md). Si el
lock está ocupado por otra sesión, no escribe nada y lo dice. Si la entrada ya
existe, no la duplica. No borra nada.

    .venv\\Scripts\\python.exe docs\\engineering\\tools\\eng_changelog_f5.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MARK = "ENG-1 F5 · `DEFAULT_DB` configurable solo para la suite de tests"
AUTH = (
    "- **Autorización del operador (literal):** «apruebo todo» (2026-11-26, sesión de Claude Code),\n"
    "  en respuesta a: aprobar ENG-F5 (`DEFAULT_DB` configurable; toca `config.py`) y ENG-F3 (`uv lock`).\n"
)
ENTRY = f"""
### 2026-11-26 · {MARK}
{AUTH}- **Qué:** `config.DEFAULT_DB` lee `TRADINGLAB_DB` si existe; `telegram.STATE_PATH` y
  `task_health.STATE_FILE` van junto a `DEFAULT_DB`. `tests/conftest.py` define la variable con una
  carpeta temporal y quita `.env`/keyring a los tests sin marcador de red/credenciales.
- **Por qué:** cada `pytest` escribía alertas de test en `data/lab.db` real y las **enviaba por ntfy**
  (1.210 envíos entre el 2026-11-09 y el 2026-11-26, incluida una crítica "missing_sl BTCUSD"),
  además de filas de `data_freshness` y `telegram_state.json`
  (docs/engineering/AUDIT_FINDINGS.md, F0-08 y §6).
- **Sin cambio en producción:** sin la variable las rutas son idénticas
  (`tests/test_eng1_default_db.py::test_sin_variable_las_rutas_son_las_de_siempre`).
- **Mismo merge:** C-02 (reanudación de Dukascopy), C-04 (`register` no mezcla futuros y CFD),
  `uv.lock` con `arch` y `numba`, y 3 regresiones `xfail` del motor.
- **Baseline:** `lab propfund baseline --reason "ENG-1 F5 …"` antes del merge.
- **Vuelta atrás:** tag `tl2-eng1-f5-pre`.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(REPO))
    parser.add_argument("--locks-dir", default=None)
    args = parser.parse_args(argv)
    root = Path(args.root)
    sys.path.insert(0, str(REPO / "src"))
    from tradinglab import orq_lock

    target = root / "docs" / "CHANGELOG-produccion.md"
    if not target.exists():
        print(f"Sin datos: no existe {target}")
        return 1
    text = target.read_text(encoding="utf-8")
    if MARK in text and AUTH in text:
        print("La entrada ya existe y está completa; no se toca nada.")
        return 0
    owner = "eng1-operador"
    try:
        orq_lock.acquire("changelog-produccion", owner, cola="ENG-1", locks_dir=args.locks_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"No se escribe: el lock changelog-produccion no está libre ({exc}).")
        return 2
    try:
        text = target.read_text(encoding="utf-8")
        if MARK in text:
            # Entrada escrita por la versión anterior del script: solo falta la autorización.
            heading = f"### 2026-11-26 · {MARK}\n"
            new_text = text.replace(heading, heading + AUTH, 1)
            target.write_text(new_text, encoding="utf-8", newline="\n")
            print(f"Autorización añadida a la entrada existente en {target}")
        else:
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(ENTRY)
            print(f"Entrada añadida a {target}")
    finally:
        orq_lock.release("changelog-produccion", owner, locks_dir=args.locks_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
