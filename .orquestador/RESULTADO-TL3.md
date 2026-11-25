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
| T5 | Hecho | `ai_trader` vs gemela: Δ +0,1675 R, IC95 [−0,209; +0,541], n=48 → **Sin datos**. |
| T6 | Hecho | Réplica EA v3.2: 479 ops, +0,3104 R, total 148,7 R; reproduce T41 ±1 op nueva. |
| T7 | **Bloqueado** | Falta la fila `TL3-T7` de `record-informal`; no se ejecutó. |
| T8 | **Bloqueado** | Falta la fila `TL3-T8` de `record-informal`; no se ejecutó. |
| T9 | Hecho | H1: coste 0,724 bps, pasa en CFD-006; CFD-001 bloqueado por swap. H3: 207 días, MDE 0,1731 > 0,12 → `no_power`. |
| T10 | Hecho | `TL3_REPORTS/TL3_RESULTS_CICLO1.md`. |
| T11 | Hecho | ruff limpio; pytest **1976 passed, 1 skipped** (32:23); `lab doctor` OK; `lab propfund verify` 4/4; README/PLAN; commit y tag. |

## T5 · `ai_trader`

48 operaciones cerradas: IA +0,0479 R, gemela −0,1196 R, Δ +0,1675 R,
sd 1,3379, IC95 [−0,2090; +0,5411]. Compras 13 → −0,4454; ventas 35 →
+0,3952. La regla de tendencia y el "siempre tomar" quedan **Sin datos**.
Veredicto: **Sin datos**; no se cambia `ai_trader`.

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

## T9

- H1: coste 0,724 bps/noche en CFD-006, 2× = 1,449 < 3,5 declarado → pasa;
  CFD-001 `blocked: swap sin datos fiables`.
- H3: 655 sesiones válidas, 207 con señal; MDE 0,1731 > 0,12 →
  `rejected: no_power`.

## T10/T11

- `TL3_REPORTS/TL3_RESULTS_CICLO1.md` con estados y recomendaciones.
- `ruff check`: limpio.
- `pytest -q`: **1976 passed, 1 skipped** (32:23); aviso de `psutil`.
- `lab doctor`: OK (avisos preexistentes de plantilla FTMO).
- `lab propfund verify`: 4/4 grupos OK.
- README §11 y PLAN actualizados.
- Commit `tl3: ciclo 1`, tag `tl3-ciclo1`.

## Cumplimiento

Sin campañas, OOS, `confirm`, `record-informal`, push, borrado ni órdenes.
No se tocó el EA, el setfile, `ea_us100_engine.py`, `ea_lab/`, `ai_trader.py`,
Prop Fund, riesgo FTMO, forward, `config/schedule.yaml` ni las tareas.
