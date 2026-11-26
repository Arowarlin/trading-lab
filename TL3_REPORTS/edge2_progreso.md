# EDGE-2 - progreso

Plan Y1: `6ffd14ae2998a37ee9d6ab7cdff73b0fb2f1e3728f65c45f684ba531d85d360d` (18 campanas, n_total 7.920).
Iniciado Y2: 2026-11-26 08:30 -04:00.

**Estado:** Y2 en espera. `edge1` presente; falta el tag `robust-1` (ROBUST-1 R6). Si ROBUST-1 publica
Y1b, se usa el plan recongelado. Comprobacion cada 10 min; sin lanzar campanas hasta que exista `robust-1`.

## Espera

- 2026-11-26 08:30 -04:00: `edge1` = si, `robust-1` = no. 18 borradores `edge2-*` en `draft`, ninguno ejecutado.
- 2026-11-26 08:33 -04:00: ROBUST-1 arranco en paralelo (`robust1: cola`, tag `robust-pre`, lock
  `proyecto-robust`). `count_tests` antes de EDGE-2 = **12.694**.

## Pasada 1

| # | Campana | Activo | TF | Plantilla | Eval | Efect | Finalistas | Estado | Consola | Tiempo |
|---:|---|---|---|---|---:|---:|---:|---|---|---:|
| 1 | `edge2-01-donchian-vol-h4-us100-h4` | US100 | H4 | donchian_vol_h4 | 434 | 22 | 0 | done | si | 6.4 min |
| 2 | `edge2-02-trend-pullback-mtf-us100-h4` | US100 | H4 | trend_pullback_mtf | 435 | 53 | 5 | done | si | 6.7 min |
| 3 | `edge2-03-vol-squeeze-breako-us100-h4` | US100 | H4 | vol_squeeze_breakout | 432 | 39 | 1 | done | si | 6.7 min |
| 4 | `edge2-04-st-reversal-idx-us100-h1` | US100 | H1 | st_reversal_idx | 440 | 30 | 0 | done | si | 6.7 min |
| 5 | `edge2-05-trend-pullback-mtf-us100-h1` | US100 | H1 | trend_pullback_mtf | 440 | 73 | 2 | done | si | 8.3 min |
| 6 | `edge2-06-vol-squeeze-breako-us100-h1` | US100 | H1 | vol_squeeze_breakout | 438 | 75 | 1 | done | si | 8.0 min |
| 7 | `edge2-07-donchian-vol-h4-us500-h4` | US500 | H4 | donchian_vol_h4 | 435 | 49 | 0 | done | si | 7.3 min |
| 8 | `edge2-08-trend-pullback-mtf-us500-h4` | US500 | H4 | trend_pullback_mtf | 435 | 58 | 2 | done | si | 7.2 min |
| 9 | `edge2-09-vol-squeeze-breako-us500-h4` | US500 | H4 | vol_squeeze_breakout | 437 | 38 | 0 | done | si | 6.7 min |
| 10 | `edge2-10-st-reversal-idx-us500-h1` | US500 | H1 | st_reversal_idx | Sin datos | Sin datos | Sin datos | bloqueado: CalledProcessError: Command '['E:\\trading-lab\\.venv\\Scripts\\lab.exe', 'discovery', 'approve', 'edge2-10-st-reversal-idx-us500-h1', '--approved-by-operator']' returned non-zero exit status 1. | si | 0.4 min |
| 11 | `edge2-11-trend-pullback-mtf-us500-h1` | US500 | H1 | trend_pullback_mtf | 440 | 80 | 1 | done | si | 9.4 min |
| 12 | `edge2-12-vol-squeeze-breako-us500-h1` | US500 | H1 | vol_squeeze_breakout | 438 | 78 | 0 | done | si | 10.5 min |
| 13 | `edge2-13-st-reversal-idx-us100-m30` | US100 | M30 | st_reversal_idx | Sin datos | Sin datos | Sin datos | bloqueado: CalledProcessError: Command '['E:\\trading-lab\\.venv\\Scripts\\lab.exe', 'discovery', 'approve', 'edge2-13-st-reversal-idx-us100-m30', '--approved-by-operator']' returned non-zero exit status 1. | si | 0.8 min |
| 14 | `edge2-14-trend-pullback-mtf-us100-m30` | US100 | M30 | trend_pullback_mtf | 437 | 84 | 0 | done | si | 19.7 min |
| 15 | `edge2-15-vol-squeeze-breako-us100-m30` | US100 | M30 | vol_squeeze_breakout | Sin datos | Sin datos | Sin datos | bloqueado: CalledProcessError: Command '['E:\\trading-lab\\.venv\\Scripts\\lab.exe', 'discovery', 'approve', 'edge2-15-vol-squeeze-breako-us100-m30', '--approved-by-operator']' returned non-zero exit status 1. | si | 0.5 min |
| 16 | `edge2-16-st-reversal-idx-us100-m15` | US100 | M15 | st_reversal_idx | Sin datos | Sin datos | Sin datos | bloqueado: CalledProcessError: Command '['E:\\trading-lab\\.venv\\Scripts\\lab.exe', 'discovery', 'approve', 'edge2-16-st-reversal-idx-us100-m15', '--approved-by-operator']' returned non-zero exit status 1. | si | 0.8 min |
| 17 | `edge2-17-trend-pullback-mtf-us100-m15` | US100 | M15 | trend_pullback_mtf | Sin datos | Sin datos | Sin datos | bloqueado: CalledProcessError: Command '['E:\\trading-lab\\.venv\\Scripts\\lab.exe', 'discovery', 'approve', 'edge2-17-trend-pullback-mtf-us100-m15', '--approved-by-operator']' returned non-zero exit status 1. | si | 0.6 min |
| 18 | `edge2-18-vol-squeeze-breako-us100-m15` | US100 | M15 | vol_squeeze_breakout | Sin datos | Sin datos | Sin datos | bloqueado: CalledProcessError: Command '['E:\\trading-lab\\.venv\\Scripts\\lab.exe', 'discovery', 'approve', 'edge2-18-vol-squeeze-breako-us100-m15', '--approved-by-operator']' returned non-zero exit status 1. | si | 0.6 min |

## Bloqueos Y2 (approve)

Las 6 no aprobadas siguen en `draft` y **no** cuentan en el DSR. Motivo literal de feasibility:

| # | Campana | Factibles | Motivo |
|---:|---|---:|---|
| 10 | `edge2-10-st-reversal-idx-us500-h1` | 14/40 (35,0 %) | feasibility < 50 % |
| 13 | `edge2-13-st-reversal-idx-us100-m30` | 14/40 (35,0 %) | feasibility < 50 % |
| 15 | `edge2-15-vol-squeeze-breako-us100-m30` | 18/40 (45,0 %) | feasibility < 50 % |
| 16 | `edge2-16-st-reversal-idx-us100-m15` | 17/40 (42,5 %) | feasibility < 50 % |
| 17 | `edge2-17-trend-pullback-mtf-us100-m15` | 14/40 (35,0 %) | feasibility < 50 % |
| 18 | `edge2-18-vol-squeeze-breako-us100-m15` | 3/40 (7,5 %) | feasibility < 50 % |

## Y2 cierre

- 12/18 `done`; 6 bloqueadas en `approve` por feasibility (no suman). 12 finalistas.
- `count_tests` 12.694 → esperado 17.974 (12 x 440 tras comprobar).

## Y3 - robustez

- Inicio: 2026-11-26 11:47 -04:00. 12 finalistas, script `scripts/edge2_x3.py` (solo IS+OOS-1).

## Y3 resultado

- 12 finalistas; **0 pasan Y3**. Puerta 2: WF 0,000-0,028 y PBO 0,314-0,863 en todos. Puerta 3 (spread p75 y slippage x2) pasa en los 12.
- Incidencia resuelta: el perfil CFD-006 (US500) no trae slippage; `edge2_x3.py` usa el asumido de `engine.yaml` (0,5), el mismo de la campana. No se toco el motor ni `fastbt.py`.

## Y4-Y6

- Y4 = **sin pasada 2** (0 finalistas pasaron Y3). Y5 = **0 confirmadas** (OOS-2 no leido). Y6 = **0 EAs**.

## Y7 - consola y ESTADO

- Consola: 18 campanas `edge2-` visibles (12 `done`); `/api/discovery/campaign/edge2-02-...` devuelve `costs_by_account` con spread, spread p75, comision, swap long/short y slippage.
- US500: el perfil muestra slippage Sin datos; las campanas usaron el asumido 0,5 de `engine.yaml`.
- `ESTADO.md`: seccion 10 "Campanas EDGE-2"; `count_tests` 12.694 -> 17.974.

## Y8 - cierre (en curso)

- `ruff check .`: limpio.
- `lab doctor`: exit 0; Frescura WARN 0/17; Reglas fondeo WARN (entorno).
- `lab propfund verify`: exit 0; 4 OK.
- `pytest -q`: en ejecucion (log `TL3_REPORTS/edge2_pytest.log`).
- Pendiente: README/PLAN (lock `readme-plan` tomado), tag `edge2`, Telegram y liberar locks.
