# RESULTADO TL3 · Ciclo 1 (revisión C)

- **Fecha:** 2026-11-25
- **Tag de cierre:** `tl3-ciclo1d`
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
| T11 | Hecho | Cierres `tl3-ciclo1b`, `tl3-ciclo1c` y `tl3-ciclo1d` (C5); pytest 1980 passed + 1 skipped. |

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

## TL3-D · Estado de la cadena (2026-11-25)

| Bloque | Estado | Detalle |
|---|---|---|
| D0 | Hecho | `29459cf` cola TL3-D. |
| D1 | Hecho | `4ecafaa` swap, codificación y registro. |
| D2 | Hecho | `b2d980b` línea base sin ventaja. FundingPips marcado no fiable (simulador anterior); corregido en TL2-DIARIO `020b41b`. |
| D3 | Hecho | `e68936b` cobertura: 270 filas; US100 2012-2021 = 1116 vs ~1128 (−12), 0 en 2012/2016/2017; `data_coverage.md` y `coverage.json`. |
| D3b | Hecho | `db760c7` T5-bis: 12 TP / 13 SL / 23 otro, 23/48 coincidencias, opuestas #27 y #51; `nights(fecha)`; FundingPips: 30.672/45.000 (68,2 %) caminos afectados con el código anterior, 0 con el corregido. |
| D4 | Hecho | Plan de potencia: sd Δ_t 0,5341 → n 177, redondeo 180; Δ_g 0,4059 → 103; R real 0,9871 → 605. Ritmo 5,33 ops/día hábil; evaluación única a 180 (~2027-01-04). H-2026-012 `draft`. |
| D5 | Hecho | Forward EA: 3 cerradas (2026-11-16, 11-18, 11-24), solo conteo. T6: 479 ops, +0,3104 R, sd 1,9173 → n 237 (real 0) y 515 (real 0,10); puntos 30/60/515 (~2027-03-16, ~2027-07-13, ~2032-06-14). `drift.py` citado. |
| D5b | Hecho | TCA: 68 filas, 66 con slippage 0, 2 sin `fill_px`, 68 sin latencia, 58 pre-migración. Causa confirmada en `mt5.py:772-783` y `paper.py:140-155`. Decisión→fill real (45/48, ≤20 s): mediana 0,440 bps / p95 2,263 bps; media +0,0114 R. `fill_px` de TCA difiere del fill real (mediana 0,426 bps; máx 2,899). Propuesta no aplicada. |
| D6 | Bloqueado (contador) | `ruff` OK; pytest **2000 passed + 1 skipped** (34m37s); `lab doctor` Frescura FAIL 7/17 (aviso), resto OK; `lab propfund verify` OK. `count_tests` **1926**, no 1897: +29 por `informal_trials` 6 (n=7) y 7 (n=22) de NASDAQ EDGE, 20:49Z, ajenas a TL3-D; `bloqueado: contador cambiado`. Tag `tl3-ciclo1e`. |
| D7 | Hecho | Resumen enviado a Telegram (`lab telegram send --file`), mensaje confirmado: protecciones, P(financiada), sesiones por índice, n/fechas de ai_trader y EA, TCA y bloqueo de contador. |

## TL3-E · Estado de la cadena (2026-11-25)

- **Arranque:** `count_tests` = **1926**; solo `reports/discovery/edge_map.md` modificado (externo permitido) y la propia cola. Sin otro `pytest -q`.
- **E0:** cola versionada con `git add -f`.
- **E1:** `orq_lock` (acquire/release/status/held), CLI `scripts/orq_lock.py`, 6 tests, sección de `AGENTS.md` y plantilla de cola. Locks viejos se informan, no se roban.
- **E2:** `docs/VERIFICACION.md`, `tl3/verify.py`, tabla `verifications` y `require_verified`; verificación NQF-A/B/C **Conforma** (29 comprobaciones, 0 defectos, 1 aviso documental: ejemplo `1.25` en `forward_daily.py`). Informe `TL3_REPORTS/verificacion_nqf.md`; hash del modelo `cb7ee5a9…`.
- **E3:** tabla `warnings`, `add_warning`/`warnings_for`/`render`, CLI `scripts/tl3_warnings.py`, siembra idempotente de **12 avisos** (ea 4, ai_trader 4, cuenta:CFD-006 1, prop.simulator 2, nqedge 1) y columna "Avisos" en `report.status_table`.
- **Siguiente paso anotado:** mostrar los avisos en Prop Fund, la web o `lab propfund` es **producción**: no se hace en esta cola.
- **E4:** `ruff` limpio; pytest **2017 passed + 1 skipped** (31m28s); `lab propfund verify` OK; `lab doctor` con Frescura FAIL 6/17 e IA sesiones WARN (entorno); `count_tests` **1926** sin cambios; tag `tl3-ciclo1f`.
- **E5:** resumen enviado a Telegram (`lab telegram send --file`), mensaje confirmado: locks, verificaciones, avisos y bloqueos.

## TL3-F · Estado de la cadena (2026-11-25/26)

- **Arranque F1:** `count_tests` **5446**; locks `proyecto-tl3-f` y `tl3-registry`. F1 auditó `scripts/tl3_warnings.py` (12 avisos), los huecos D3 de US100 y archivó `tl2-edge-map.patch` en `legacy/`; informe `reports/tl3/saneamiento-f1.md`.
- **F2:** H-2026-013 `draft` (US100 H1, `Close_D1 > SMA50_D1`, entrada al open de la vela siguiente a la señal de 09:00 NY, stop 2,0×ATR(14), target 2R, flat 15:00). Plantilla `h1_sma50_session_long`; feasibility **799 ops** IS 2019-2023, pliegues 207/202/77/199, `cost_r` 0,05388 (CFD-001 0,05368; CFD-006 0,04751); **21/799 cruzan día** en festivos/cierres NYSE. Informe `reports/tl3/h-2026-013-draft.md`.
- **F3 · verificación independiente** (`sesion-tl3-f3-audit`, commit `c4ec579`): 35 comprobaciones → **Defectos** (3 defectos, 3 avisos). Defectos: (1) el encabezado del spec conserva 15:55 y la plantilla+fila usan 15:00 (documental); (2) el spec deriva 415 minutos y la plantilla+fila usan 360 (documental); (3) 21/799 (2,63 %) noches >0 por falta de la barra de las 15:00 en festivos/cierres, así que `nights == 0` no se cumple. Avisos: 2 señales de Viernes Santo sin barra posterior, hash estructural no reproducible y benchmark no ejecutado. Informe `TL3_REPORTS/verificacion_h-2026-013.md`; fila en `verifications` con hash `9605ebc8…` y veredicto `Defectos`. **H-2026-013 no se aprueba**; no se corrige el código congelado: decide el operador.
- **Cierre:** `ruff` limpio en las rutas de F3 (`ruff check .` solo marca `scripts/edge2_x0.py`, sin seguimiento y de EDGE2); pytest **2050 passed + 1 skipped** (34:05); `lab doctor` Frescura FAIL 5/17 y Reglas fondeo WARN (entorno); `lab propfund verify` OK; `count_tests` **7206** al empezar → **9846** al cerrar (+2640 por 6 campañas `edge1-` aprobadas en paralelo; los 18 borradores `edge2-` no cuentan); sin filas nuevas en `informal_trials` (7, id 7) ni campañas fuera de `edge1-`/`edge2-` (46 → 64, 28 `edge1-` y 18 `edge2-`). Tag `tl3-ciclo1g`.

