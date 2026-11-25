# TL3 · Edge Map (ciclo 1)

Etiquetas tomadas de `TL3_DISCOVERY_FAILURE_ANALYSIS.md` y de los cierres
NQ/E2/T41. **No** se toca `reports/discovery/edge_map.md`.

| ID | Hipótesis | TF | Estado | Motivo / evidencia |
|---|---|---|---|---|
| H-2026-001 | Fix FX (EURUSD/GBPUSD) | H1 | `rejected` | `gross_lt_cost`: 7.527 ops v2, el coste elimina el bruto |
| H-2026-002 | Asia USDJPY | H1 | `rejected` | `no_gross_edge` |
| H-2026-003 | Cambio de mes | D1 | `inconclusive` | `no_power_cost_v1`: 0 finalistas; US500 OOS-1 negativo, US100 deriva < 90 |
| H-2026-004 | Rebote D1 | D1 | `inconclusive` | `no_power_cost_v1`: US500 sin edge bruto; US100 muestra insuficiente |
| H-2026-005 | Donchian | H4 | `inconclusive` | `no_power_cost_v1` |
| H-2026-006 | Momentum intradía | M5 | `inconclusive` | `no_power_cost_v1` |
| H-2026-007 | NY open GA | M5 | `inconclusive` | `no_power_cost_v1` |
| H-2026-008 | EA v3.2 fuera de periodo (T7) | M5 | `rejected` | `holdout_fail`: 374 ops, exp ?0,0296 R, LCB ?0,1753 |
| H-2026-009 | H2 deriva pre-FOMC (T8) | D1 | `rejected` | `no_power`: MDE 43,76 > 30 bps |
| H-2026-010 | H1 deriva nocturna (T9) | D1 | `rejected` | `cost_gate` (H-2026-010b) |
| H-2026-011 | H3 impulso de apertura (T9) | M5 | `draft` | Solo conteo/MDE; no se ejecuta |

A-1/A-2 de NQ-B son controles de **paridad**, no pruebas; no suman al
contador.
