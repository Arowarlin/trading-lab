# RESULTADO TL3 · Ciclo 1

- **Fecha:** 2026-11-25
- **Rama:** `feature/prop-fund-multifirm`
- **count_tests al empezar y al cerrar:** **1895**

## Bloques

| Bloque | Estado | Detalle |
|---|---|---|
| T0 | Hecho | `tl3: T0 - auditoria y colas` (`c9c0d12`); `TL3_REPORTS` y colas versionadas. |
| T1 | Hecho | `tl3/data.py`: manifiesto de 14 archivos, cargador con granularidad/clase; 5 tests. |
| T2 | Hecho | 8 copias en `data/tl3/futures/`; originales intactos; hashes en el manifiesto. |
| T3 | Hecho | `tl3_research.db` con 11 hipótesis, `thresholds.yaml`, candados y edge map; 4 tests. |
| T4 | Hecho | `tl3/report.py`: escalera bruto → neto con test a mano; 1 test. |
| T5 | Hecho | `ai_trader` vs gemela recalculada: IA 0,2953 R, gemela 0,2594 R, tendencia 0,3179 R; Δ vs tendencia −0,0225 R, IC95 [−0,1833; +0,1206], n=48 → **no concluyente**. |
| T6 | Hecho | Réplica EA v3.2: 479 ops, +0,3104 R, total 148,7 R; reproduce T41 ±1 op nueva. |
| T7 | **Bloqueado** | Falta la fila `TL3-T7` de `record-informal`; no se ejecutó. |
| T8 | **Bloqueado** | Falta la fila `TL3-T8` de `record-informal`; no se ejecutó. |
| T9 | Hecho | H1: swap 7,33 %/365 = 2,01-2,81 bps + spread 0,69 + slippage 0,38 ≈ 3,1-3,9 bps; 2× > 3,5 → **`rejected: cost_gate`**. H3: 207 días, MDE 0,1731 > 0,12 → `no_power`. |
| T10 | Hecho | `TL3_REPORTS/TL3_RESULTS_CICLO1.md`. |
| T11 | Hecho | ruff limpio; pytest **1976 passed, 1 skipped** (29:49); `lab doctor` OK; `lab propfund verify` 4/4; README/PLAN; tag `tl3-ciclo1c`. |

## T5 · `ai_trader`

48 operaciones cerradas, M1 de MT5 attach-only, gemela recalculada con
`shadow_seed`, regla de tendencia y "siempre tomar":
IA 0,2953 R, gemela 0,2594 R, tendencia 0,3179 R, siempre tomar = IA.
Δ vs gemela +0,0360 R, IC95 [−0,0843; +0,1462]; Δ vs tendencia −0,0225 R,
IC95 [−0,1833; +0,1206]. Veredicto: **no concluyente**; no se cambia
`ai_trader`.

## T6 · Réplica EA

479 ops, +0,3104 R, total 148,7 R, sd 1,9173. T41: 478 / +0,3104 / 148,4.
La diferencia es la operación nueva del 2026-11-24. **Réplica reproduce.**
Corto 2023: 28 ops, −0,1368 R (confirma la hipótesis descriptiva).
MAE −1,0537 R; MFE +1,6614 R.

## T7/T8 · Bloqueo

Las filas de `informal_trials` con textos `TL3-T7` y `TL3-T8` **no existen**;
`count_tests` sigue en 1895, no en 1897. Se aplica la regla §1: bloqueado,
no se ejecuta y se sigue. El operador puede registrarlas y relanzar solo
esos bloques.

**H-2026-009b invalidada** por error de unidades del swap (TL3-C H-a). La fila v?lida es H-2026-009c (C3), creada con hora actual.

## T9

- **H1 corregida:** `swap_mode: 5` de CFD-006 = interés anual; 7,33 %/365 =
  2,01 bps/noche (2,81 de media con día triple), + spread 0,69 bps +
  slippage 0,38 bps ≈ **3,1-3,9 bps**. 2 × coste > 3,5 →
  **H-2026-010 = `rejected: cost_gate`** (fila append-only H-2026-010b).
  CFD-001 sigue `blocked: swap sin datos fiables`.
- H3: 655 sesiones válidas, 207 con señal; MDE 0,1731 > 0,12 →
  `rejected: no_power`.

## T10/T11

- `TL3_REPORTS/TL3_RESULTS_CICLO1.md` con estados y recomendaciones.
- `ruff check`: limpio.
- `pytest -q`: **1976 passed, 1 skipped** (29:49).
- `lab doctor`: OK (avisos preexistentes de plantilla FTMO).
- `lab propfund verify`: 4/4 grupos OK.
- README §11 y PLAN actualizados.
- Commit `tl3: cierre ciclo 1c`, tag `tl3-ciclo1c`. Telegram enviado.

## Cumplimiento

Sin campañas, OOS, `confirm`, `record-informal`, push, borrado ni órdenes.
No se tocó el EA, el setfile, `ea_us100_engine.py`, `ea_lab/`, `ai_trader.py`,
Prop Fund, riesgo FTMO, forward, `config/schedule.yaml` ni las tareas.
