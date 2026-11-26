# TASK_QUEUE · Programa ENG-1

Estados: `PENDING` · `READY` · `RUNNING` · `BLOCKED` · `REVIEW` · `FAILED` · `COMPLETED` · `REJECTED`.
Dónde: **N** = nube (Claude), **L** = equipo del operador (OpenCode u operador).
Un fichero de la columna *Archivos* tiene un solo dueño a la vez.

| ID | Tarea | Dónde | Responsable | Archivos (escritura) | Depende de | Estado | Criterio de aceptación | Evidencia |
|---|---|---|---|---|---|---|---|---|
| ENG-00 | Baseline Fase 0 | N | Claude | `docs/engineering/BASELINE_REPORT.md` | — | COMPLETED | SHA, entorno, campañas y CI identificados | `BASELINE_REPORT.md` |
| ENG-A1 | Auditoría motor `fastbt` (solo lectura) | N | Worker A | `WORKER_REPORTS/A-engine.md` | ENG-00 | RUNNING | Hallazgos con reproducción sintética, NUEVO/CONOCIDO | — |
| ENG-B1 | Auditoría de costes y TCA (solo lectura) | N | Worker B | `WORKER_REPORTS/B-costs.md` | ENG-00 | RUNNING | Ídem + diseño de medición TCA | — |
| ENG-C1 | Auditoría de datos (solo lectura) | N | Worker C | `WORKER_REPORTS/C-data.md` | ENG-00 | RUNNING | Ídem + qué falta para NQ/MNQ | — |
| ENG-D1 | Auditoría estadística (solo lectura) | N | Worker D | `WORKER_REPORTS/D-stats.md` | ENG-00 | RUNNING | Ídem + respuestas 1-8 con simulación | — |
| ENG-F1 | Suite `pytest` en el contenedor (marcadores de CI) | N | Claude | `TASK_STATUS.md` | ENG-00 | RUNNING | Lista de fallos clasificada: entorno vs regresión | — |
| ENG-F2 | Aislar los 43 tests que dependen del equipo del operador (marcador `local_data` o `skipif` por recurso ausente), sin tocar su lógica | N→L | Claude propone, operador aprueba | `tests/test_ea_registry.py`, `test_guardian.py`, `test_tl3_data.py`, `test_ea_nq_script.py`, `test_portfolio_lab.py`, `test_wf_tf_eval.py`, `test_research.py`, `test_optimize.py`, `test_export_signals.py`, `pyproject.toml` (markers), `ci.yml` | ENG-F1 | PENDING | CI verde **sin** desactivar tests que sí pueden correr en CI; en local siguen pasando los 2073 | — |
| ENG-F3 | Fijar numba en `uv.lock` (extra `discovery`) | L | operador | `uv.lock` | — | BLOCKED (operador: `uv lock` cambia el lock de producción) | `uv sync --frozen --extra discovery` funciona y la versión queda registrada | F0-01 |
| ENG-G1 | Consolidar `AUDIT_FINDINGS.md` | N | Claude | `docs/engineering/AUDIT_FINDINGS.md` | A1, B1, C1, D1 | PENDING | Cada hallazgo verificado por Claude (no solo copiado) | — |
| ENG-E1 | Auditoría de discovery/edge research (`engine.py`, `edge_map.py`, EDGE-1/2) y lista de hipótesis ya rechazadas | N | Worker E | `WORKER_REPORTS/E-edge.md` | ENG-G1 | PENDING | Lista de "no repetir" con su motivo y documento | — |
| ENG-P1 | Prompts de OpenCode para reproducir con datos los hallazgos HIGH+ | N | Claude | `docs/engineering/OPENCODE_PROMPTS.md` | ENG-G1 | PENDING | Un prompt por tarea L, con ficheros cerrados y PARA | — |
| ENG-M1 | Parches del motor (tests que fallan + parche en rama `eng/motor-*`), **sin integrar** | N | Claude | rama aparte | ENG-G1 | BLOCKED (EDGE-2 en marcha; MOTOR-FLAT ya cubre `flat_at`) | Tests rojos antes / verdes después; identidad bit a bit en modo `legacy` | — |
| ENG-R1 | Prerregistros de las 4 líneas de investigación (Fase 6) | N | Claude | `docs/engineering/EDGE_RESEARCH_PLAN.md` | ENG-E1, ENG-C1 | PENDING | Mecanismo, datos, entradas, salidas, costes y criterio de rechazo **antes** de ver resultados | — |
| ENG-R2 | Lanzar cualquier campaña de ENG-R1 | L | operador | — | ENG-R1 | BLOCKED (aprobación explícita; AGENTS.md) | — | — |
