"""Añade una entrada de ENG-1 a docs/CHANGELOG-produccion.md bajo el lock ``changelog-produccion``.

Lo ejecuta el operador **después** del merge. Si el lock está ocupado, no
escribe nada. Si la entrada ya existe, no la duplica. No borra nada.

    .venv\\Scripts\\python.exe docs\\engineering\\tools\\eng_changelog.py F0-09
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

ENTRIES: dict[str, tuple[str, str]] = {
    "F0-09": (
        "ENG-1 F0-09 · Hash del forward del EA independiente de los finales de línea",
        """- **Autorización del operador (literal):** «si a ambas preguntas» y «tienes permiso para todo»
  (2026-11-26, sesión de Claude Code), en respuesta a corregir F0-09.
- **Qué:** `ea_forward._sha256` y `_code_sha256` normalizan CRLF → LF antes de calcular el hash.
  `ensure_forward` acepta el hash congelado anterior `f490642ba7a1f71b` como alias de
  `71ee2cabe6aa9aef` (`LEGACY_CRITERIA_HASHES`); cualquier otro hash distinto sigue bloqueando.
- **Por qué:** el hash solo se reproducía si en la copia de Windows `US100_EA.mq5`,
  `US100_ExitManager.mqh`, `US100_RiskManager.mqh` y `ea_us100_engine.py` tenían CRLF. El día que git
  los reescribiera con LF, el forward fallaría con "criterios ya congelados" aunque el EA fuera el
  mismo (docs/engineering/AUDIT_FINDINGS.md §10).
- **Prueba:** `tests/test_eng1_ea_hash.py` reconstruye la copia del operador desde git y demuestra que
  el cálculo anterior da `f490642ba7a1f71b` y el nuevo `71ee2cabe6aa9aef` sobre el mismo contenido; el
  forward con el hash antiguo sigue funcionando y con otro hash sigue bloqueado. `test_ea_forward`
  pasa ahora también en CI (antes fallaba 5 tests).
- **Sin cambio en el forward en marcha:** la fila de `lifecycle_bots` no se reescribe.
- **Baseline:** `lab propfund baseline --reason "ENG-1 F0-09 …"` antes y después del merge
  (`ea_forward.py` está en el grupo protegido `ea_us100_ftmo1`).
- **Vuelta atrás:** tag `tl2-eng1-f009-pre`.
""",
    ),
    "B-14": (
        "ENG-1 B-14 · Huecos de la TCA v2 (MT5 y paper)",
        """- **Autorización del operador (literal):** «tienes permiso para todo» y «hacer» (2026-11-26/27,
  sesión de Claude Code), en respuesta a la lista de pendientes que incluía B-14.
- **Qué:** solo cambia lo que se **graba** en `tca`; el envío de órdenes (`request`, SL/TP, volumen,
  reintentos de filling) es idéntico.
  1. `execution/mt5.py`: sin `signal_price`, `slippage_bps` va nulo (antes medía tick → fill y se
     guardaba como decisión → fill). `ai_trader` y `forward_intraday` ya pasan `signal_price`.
  2. `execution/mt5.py`: `expected_cost_bps` nulo cuando el bróker no tiene coste supuesto (antes 0).
  3. `execution/mt5.py`: `bid`/`ask` del tick del envío (`submit_tick`), el mismo que `requested_price`.
  4. `execution/paper.py`: el paper graba `origin="paper"`; `slippage_measured` (T12) lo excluye,
     porque su slippage es el supuesto, no una medición.
- **No incluido (diseño aparte):** salidas SL/TP del servidor (reconciliar con `history_deals`) y
  `ts_utc` del fill (`deal.time_msc`). Ver docs/engineering/WORKER_REPORTS/B-costs.md, "Diseño de
  medición TCA".
- **Prueba:** `tests/test_eng1_b14_tca.py` (valor anterior frente al nuevo); `test_mt5_tca` y
  `test_mt5` actualizados con el valor anterior anotado.
- **Baseline:** `lab propfund baseline --reason "ENG-1 B-14 …"` antes y después del merge
  (`execution/mt5.py` está en el grupo protegido `ftmo_risk`).
- **Vuelta atrás:** tag `tl2-eng1-b14-pre`.
""",
    ),
}

DATES = {"F0-09": "2026-11-26", "B-14": "2026-11-27"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("entry", choices=sorted(ENTRIES))
    parser.add_argument("--root", default=str(REPO))
    parser.add_argument("--locks-dir", default=None)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(REPO / "src"))
    from tradinglab import orq_lock

    title, body = ENTRIES[args.entry]
    target = Path(args.root) / "docs" / "CHANGELOG-produccion.md"
    if not target.exists():
        print(f"Sin datos: no existe {target}")
        return 1
    if title in target.read_text(encoding="utf-8"):
        print("La entrada ya existe; no se toca nada.")
        return 0
    owner = "eng1-operador"
    try:
        orq_lock.acquire("changelog-produccion", owner, cola="ENG-1", locks_dir=args.locks_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"No se escribe: el lock changelog-produccion no está libre ({exc}).")
        return 2
    try:
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"\n### {DATES.get(args.entry, '2026-11-26')} · {title}\n{body}")
        print(f"Entrada añadida a {target}")
    finally:
        orq_lock.release("changelog-produccion", owner, locks_dir=args.locks_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
