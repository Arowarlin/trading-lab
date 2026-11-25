Hecho
- TL3-E E0-E3 completos: coordinación entre sesiones, verificación previa y avisos que viajan.
- E4: ruff limpio, pytest 2017 passed + 1 skipped, lab doctor y lab propfund verify; count_tests 1926; tag tl3-ciclo1f.

1. Locks y regla
- `orq_lock` con acquire/release/status/held; CLI `scripts/orq_lock.py`; locks viejos se informan y no se roban.
- `AGENTS.md` §Coordinación entre sesiones y `.orquestador/PLANTILLA-COLA.md`.
- `pytest-full` y `readme-plan` usados en este cierre.

2. Verificación «lo habría cazado»
- `docs/VERIFICACION.md`, `tl3/verify.py`, tabla `verifications` y `require_verified`.
- Tests: swap 200,8 bps, tolerancia 2×90 puntos, 371 vs 357 y huella de las 48 primeras vs T5.
- NQF-A/B/C: **Conforma** (29 comprobaciones, 0 defectos, 1 aviso documental: ejemplo 1.25 en forward_daily). Hash del modelo `cb7ee5a9…`.

3. Avisos
- 12 avisos sembrados: ea:us100-ftmo1 4, ai_trader 4, cuenta:CFD-006 1, prop.simulator 2, nqedge 1.
- Columna «Avisos» en `report.status_table` y CLI `scripts/tl3_warnings.py`.
- Mostrarlos en Prop Fund, web o `lab propfund` es producción: siguiente paso, no ejecutado.

Aviso
- `lab doctor`: Frescura FAIL 6/17 e IA sesiones WARN (entorno); el resto OK.
- `count_tests` 1926 sin cambios desde el arranque; sin bloqueos.
- No se tocó producción ni `forward_models.py`; no se leyó `03_BACKTEST`.

Siguiente
- Llevar los avisos a Prop Fund/web/lab propfund en otra cola con aprobación.
- Fin de TL3-E.
