# 08 · Roadmap de implementación

**Cuándo:** después de las fases 0–5b de la migración CFD/futuros. **TradingLab 2.0 sustituye la FASE 5c**
de `TradingLab_migracion_CFD_futuros.md`.
Cada fase termina con: tests verdes, `lab propfund verify` OK, commit y **tag** `tl2-fN`.
**Rollback** = `git reset --hard tl2-f(N-1)`, siempre en local y solo con tu aprobación.

| Fase | Entrega | Archivos nuevos (principales) | Criterio de aceptación | Riesgo |
|---|---|---|---|---|
| 0 | Línea base y aislamiento | `tests/test_discovery_isolation.py`, `config/discovery/engine.yaml` | pytest completo igual que antes; verify OK | Bajo |
| 1 | Calidad de datos CFD | `discovery/data_quality.py`, `lab discovery data-check` | Informe ok/warn/fail con hash para US100/US500 | Bajo |
| 2 | DSL + bloques + compilador | `discovery/dsl.py`, `blocks.py`, `indicators_ext.py`, `compiler.py` | Validación semántica; test de no look-ahead en todos los bloques | Medio |
| 3 | Motor rápido + paridad | `discovery/fastbt.py`, `tests/test_discovery_parity.py` | Paridad con `backtest_intraday` y `run_event_backtest`; ≥ 2.000 backtests/min en US100 M5 de 3 años con 12 workers (medido, no prometido) | **Alto** |
| 4 | Databank + cola de jobs | tablas `disc_*`, `discovery/databank.py`, `jobs.py` | Reanudación tras matar el proceso; dedupe por hash | Medio |
| 5 | Campañas y segmentación IS/OOS-1/OOS-2 | `discovery/campaigns.py`, `lab discovery register` | GA no puede leer OOS (test); N_total previo; `count_tests` incluye la campaña | **Alto** |
| 6 | NSGA-II + genealogía | `discovery/nsga2.py`, `genetic.py`, `fitness.py`, `lab discovery run` | Tests de dominancia/crowding; perfil `small` termina y guarda genealogía | Medio |
| 7 | Optimizer, Retester, Robustness Lab, niveles | `optimizer.py`, `retester.py`, `robustness.py`, `levels.py` | Reutiliza DSR/PBO/WF existentes (sin copiarlos); finalistas ≤ 5 | Medio |
| 8 | Consola Discovery Lab | `web.py` (rutas nuevas), `webui/index.html` (vista nueva) | Todas las pantallas leen la API real; sin botones falsos | Bajo |
| 9 | Agentes IA (hipótesis → AST) | `discovery/agents/` | Salida JSON validada; agentes sin permisos de escritura de métricas (test) | Medio |
| 10 | Futuros (Databento) | `discovery/data_databento.py` | Estimación de coste antes de descargar; continuo con tabla de rolls | Medio |
| 11 | Portfolio + Prop Intelligence | `discovery/portfolio_view.py` | Matriz estrategia × cuenta | Bajo |
| 12 | Exportador MQL5 | `discovery/export/mql5.py` | `.mq5` compila en MetaEditor (verificación manual) + CSV de señales | Medio |

Orden mínimo viable (MVP): **0 → 1 → 2 → 3 → 4 → 5 → 6 → 7** (descubrimiento honesto de punta a punta en
US100 M5). Consola, IA, futuros, cartera y exportación vienen después.

## Qué NO hacer

- No ejecutar `lab discovery run` real (campaña registrada) sin tu aprobación en la misma sesión:
  suma pruebas al DSR global como cualquier campaña (regla de `AGENTS.md`).
- No tocar los archivos protegidos ni el forward demo.
- No subir (push) sin tu autorización.
