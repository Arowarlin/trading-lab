# RESULTADO TL3 · Ciclo 1 (revisión C)

- **Fecha:** 2026-11-25
- **Rama:** `feature/prop-fund-multifirm`
- **count_tests:** **1897**

## Bloques

| Bloque | Estado | Detalle |
|---|---|---|
| T0 | Hecho | Auditoría y colas versionadas. |
| T1 | Hecho | Manifiesto y cargador; 5 tests. |
| T2 | Hecho | 8 copias de futuros. |
| T3 | Hecho | Registro append-only; 11 hipótesis. |
| T4 | Hecho | Escalera bruto → neto. |
| T5 | Hecho | IA vs tendencia: Δ −0,0225 R (IC95 −0,1833; +0,1206) → no concluyente. |
| T5-bis | Hecho (C1) | 48 de T5: gap −0,2475 R (IC95 −0,5362; +0,0484); sin posibles no ejecutadas −0,2278. Entrada +0,0661, costes −0,0089, salida/resto −0,3047. |
| T6 | Hecho | 479 ops, +0,3104 R; corto 2023 −0,1368 R. |
| T7 | Hecho | 374 ops, −0,0296 R, LCB −0,1753 → no confirma. Muestra efectiva 2013-2014 y 2018-2021. |
| T8 | Hecho (C3) | 117 eventos; σ bruta 94,06 bps; MDE 21,65; t 1,909; neto 8,04 bps; LCB −0,60 → no confirma. |
| T9 | Hecho | H1 `rejected: cost_gate`; H3 `rejected: no_power`. |
| T10 | Hecho | `TL3_RESULTS_CICLO1.md`. |
| T11 | Hecho | Cierres `tl3-ciclo1b`, `tl3-ciclo1c`; cierre 1d en C5. |

## T5-bis · Simulación vs real

Conjunto exacto de T5 = 48 operaciones (todas menos #52 y #54). Agregados de
control: IA 0,2953, gemela 0,2594, tendencia 0,3179, real 0,0479.

| Conjunto | n | R real | R sim | Gap | IC95 |
|---|---:|---:|---:|---:|---|
| Todas | 48 | 0,0479 | 0,2953 | **−0,2475** | [−0,5362; +0,0484] |
| Sin posibles no ejecutadas | 46 | 0,0500 | 0,2777 | −0,2278 | [−0,5118; +0,0644] |

El gap se concentra en entrada y salida/resto; los costes del modelo no lo
explican. Posibles no ejecutadas: #3 y #5. No se tocó `ai_trader`.

## T7 · EA Dukascopy

374 ops, expectativa −0,0296 R, LCB95 −0,1753, `slip_eq` 0,26 pt → **no
confirma**. La regla del prerregistro deja 1127 sesiones válidas de 2334
(frente a 1077 del script); 2012, 2016 y 2017 no tienen sesiones válidas y
2015 solo 37, así que la muestra efectiva es 2013-2014 y 2018-2021. La cota
de ~2,8 R por operación añadida impide que el veredicto cambie.

## T8 · FOMC corregido

La fila **H-2026-009b es inválida** por error de unidades del swap (200,8
bps/noche en vez de 2,008). La fila válida es **H-2026-009c**, con
`created_at` actual.

- 117 eventos válidos; exclusiones evento×índice: US100 4, US500 4, US30 17.
- σ bruta 94,06 bps; σ neta 94,10; MDE 21,65 < 30.
- Criterio (a): t Welch bruto 1,909 ≥ 1,645 → pasa.
- Criterio (b): neto 8,04 bps, LCB95 −0,60 → **no pasa**.
- **Veredicto: no confirma.** No se reinterpreta.

## T9

H1: swap 7,33 %/365 = 2,008 bps/noche (2,81 con día triple) + spread 0,69 +
slippage 0,38 ≈ 3,1-3,9 bps; 2× > 3,5 → **rejected: cost_gate**.
H3: 207 días con señal, MDE 0,1731 > 0,12 → **rejected: no_power**.

## Cumplimiento

Sin campañas, OOS, `confirm`, `record-informal`, push, borrado ni órdenes.
No se tocó el EA, el setfile, `ea_us100_engine.py`, `ea_lab/`, `ai_trader.py`,
Prop Fund, riesgo FTMO, forward, `config/schedule.yaml` ni las tareas.
