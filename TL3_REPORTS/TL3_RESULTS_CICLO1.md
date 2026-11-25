# TL3 · Resultados del ciclo 1 (revisión C)

## Bloques

| Bloque | Estado | Cifra / veredicto |
|---|---|---|
| T0 | Hecho | Auditoría y colas versionadas. |
| T1 | Hecho | Manifiesto de 14 archivos; cargador rechaza granularidad/clase. |
| T2 | Hecho | 8 copias de futuros en `data/tl3/futures/`. |
| T3 | Hecho | Registro append-only con 11 hipótesis y candados. |
| T4 | Hecho | Escalera bruto → neto con test a mano. |
| T5 | Hecho | IA 0,2953 R, gemela 0,2594 R, tendencia 0,3179 R; Δ vs tendencia −0,0225 R (IC95 −0,1833; +0,1206) → **no concluyente**. |
| **T5-bis** | Hecho (C1) | 48 de T5: real 0,0479 R, simulado 0,2953 R, **gap −0,2475 R**, IC95 [−0,5362; +0,0484]. Sin posibles no ejecutadas: gap −0,2278 R. Entrada +0,0661; costes −0,0089; salida/resto −0,3047. |
| T6 | Hecho | Réplica EA: 479 ops, +0,3104 R; corto 2023 −0,1368 R. |
| T7 | Hecho | 374 ops, exp **−0,0296 R**, LCB95 −0,1753, `slip_eq` 0,26 pt → **no confirma**. Muestra efectiva 2013-2014 y 2018-2021 (2015 solo 37 sesiones; 2012, 2016 y 2017 sin sesiones válidas). |
| T8 | Hecho (C3) | 117 eventos, σ bruta 94,06 bps, MDE 21,65 < 30; t bruto 1,909 ≥ 1,645; neto 8,04 bps, LCB95 −0,60 → **no confirma**. |
| T9 | Hecho | H1 **rejected: cost_gate** (coste 3,1-3,9 bps; 2× > 3,5). H3 **rejected: no_power** (MDE 0,1731 > 0,12). |
| T10 | Hecho | Este informe. |
| T11 | Hecho | Cierres 1b (`tl3-ciclo1b`) y 1c (`tl3-ciclo1c`); cierre 1d en C5. |

## Hipótesis

| ID | Hipótesis | Estado | Motivo |
|---|---|---|---|
| H-2026-001 | Fix FX | `rejected` | `gross_lt_cost` |
| H-2026-002 | Asia USDJPY | `rejected` | `no_gross_edge` |
| H-2026-003 | Cambio de mes | `inconclusive` | `no_power_cost_v1` |
| H-2026-004 | Rebote D1 | `inconclusive` | `no_power_cost_v1` |
| H-2026-005 | Donchian | `inconclusive` | `no_power_cost_v1` |
| H-2026-006 | Momentum intradía | `inconclusive` | `no_power_cost_v1` |
| H-2026-007 | NY open GA | `inconclusive` | `no_power_cost_v1` |
| H-2026-008 | EA OOP (T7) | `rejected` | `holdout_fail` (374 ops, −0,0296 R, LCB −0,1753) |
| H-2026-009 | H2 FOMC (T8) | `rejected` | `holdout_fail` en H-2026-009c (t 1,909; LCB neto −0,60). H-2026-009b invalidada por swap 100×. |
| H-2026-010 | H1 nocturna | `rejected` | `cost_gate` (H-2026-010b) |
| H-2026-011 | H3 OR | `rejected` | `no_power` |

## Recomendaciones

1. **EA:** T7 **no confirma** en 2013-2014 y 2018-2021 con el coste prerregistrado. Según la lectura fijada, alta probabilidad de ajuste a 2021-2026 o dependencia de régimen. No se cambia el EA ni el riesgo.
2. **`ai_trader`:** no concluyente frente a la tendencia (Δ −0,0225 R, IC95 incluye 0); el gap simulación-real es −0,2475 R y se explica por ejecución. No se cambia.
3. **T8:** no confirma (criterio b, LCB neto −0,60). No se reinterpreta; no se prueba otra versión.
4. **H1/H3:** H1 rechazada por coste; H3 sin potencia. Medir swap ≥ 20 sesiones antes de reabrir H1.

## Contador

`count_tests` = **1897**. T7 y T8 suman 1 cada uno; T5-bis no suma.
