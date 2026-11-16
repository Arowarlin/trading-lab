# OPENCODE_MASTER_PLAN — Cómo ejecutar el plan con OpenCode

## Reglas para cada sesión

1. Modelo: **DeepSeek V4.1 Flash**. Una tarea de `OPENCODE_TASKS.md` por sesión, con prompts cortos y numerados.
2. Lee primero AGENTS.md y los archivos que nombra la tarea. No toques nada fuera de ellos.
3. Prohibido: ejecutar campañas, barridos u Optuna; leer el holdout; cambiar `enabled` en cualquier yaml; tocar `.env` o las tareas programadas; hacer push; borrar.
4. Al terminar, ejecuta `uv run ruff check . && uv run pytest -q && uv run lab doctor && uv run lab f13 config-check`, añade una entrada en PLAN.md y haz el commit.
5. Resumen: Hecho / 1..N / Aviso / Siguiente.

## Plantilla de prompt (DeepSeek V4.1 Flash)

```
Lee AGENTS.md y docs/audit_2026/OPENCODE_TASKS.md. Ejecuta SOLO la tarea <ID>.
1. Lee los archivos que nombra.
2. Implementa el diseño indicado, sin dependencias nuevas.
3. Escribe los tests indicados.
4. ruff, pytest, lab doctor, lab f13 config-check.
5. PLAN.md y commit. Sin push.
Si algo del diseño choca con el código real, para y explícalo en Aviso en vez de improvisar.
Resumen: Hecho / 1..N / Aviso / Siguiente.
```

## Fases

| Fase | Tareas | Resultado verificable |
|---|---|---|
| 0. Integridad | T01, T03, T04, T05 y después T02 | El DSR reproduce 0,9004; el guardián ve el EA; informe dsr_v2.md |
| 1. Costes | T06, T07, T08, T09 | Los tests de swap, spread de limitadas, contabilidad y DST pasan |
| 2. Honestidad estadística | T10, T11 | Informe de robustez del EA |
| 3. Riesgo | T12 | `lab doctor` muestra el riesgo por símbolo y por clúster |
| 4. IA y mantenimiento | T13, T14 | Replay separado del forward |
| 5. Investigación nueva | S2 y S3 de STRATEGY_DEVELOPMENT_PLAN | **Solo con pre-registro y aprobación explícita** |

## Qué comprobar en cada push

- El número de tests no baja.
- `count_tests` no sube salvo en la fase 5.
- El hash de F13 no cambia.
- Ningún diff en `config/intraday_forward.yaml`, `accounts.yaml` (límites) ni `ai_trader.yaml` (riesgo) sin aprobación.
