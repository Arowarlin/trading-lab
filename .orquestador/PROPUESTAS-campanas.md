# PROPUESTAS · campañas R2k (solo papel)

Fecha: 2026-11-22. Coste DSR cero: no se registró ninguna campaña ni borrador.
No se ejecutó `approve/run/confirm/supersede`, no se leyó OOS-1/OOS-2 y no se
tocó ninguna tarea programada.

## Qué se corrigió antes de proponer

- **R típico**: mediana de ATR(14) de los **últimos 12 meses** de Dukascopy
  (mismo régimen de precio que el spread medido), no desde `usable_from` a 2003.
  Se muestra también ATR en % del precio.
- **Cost_R de cribado** (ATR 12m) y **cost_R de operaciones** (mediana de
  `trade.r_cost` de la plantilla) son columnas separadas. La factibilidad usa la
  de operaciones; la viabilidad cuenta×símbolo×TF usa la de cribado.
- **Compatibilidad plantilla × TF**: `valid_timeframes` en cada plantilla. Asia
  18:00-03:00 no es representable en H4/D1; se excluyen de suggest y preflight.
- **Preflight/feasibility en seco**: `lab discovery preflight --spec` y
  `lab discovery feasibility --spec` sobre YAML, sin registrar campaña.

## Edge Map (resumen)

- inválida: 1 (`intraday_momentum_close` US100 M5).
- sin edge bruto: 1 (`intraday_momentum_close_v2` US100 M5, bruto -0.0112,
  neto -0.0778, cost_R operaciones 0.0523).
- sobreajustada: 1 (`ny_open_vol_filter` US100 M5, neto 0.0292, cost_R 0.0470).
- candidata nivel 3: 0; confirmada nivel 4: 0.

Por eso se excluyen `intraday_momentum_close`, `intraday_momentum_close_v2` y
`ny_open_vol_filter US100 M5`. Las propuestas usan familias distintas:
`asia_range_reversion`, `ny_open_vol_filter` (M15, no M5) y
`session_breakout_htf`.

## Compatibilidad plantilla × TF

| Plantilla | M1 | M5 | M15 | M30 | H1 | H4 | D1 |
|---|---|---|---|---|---|---|---|
| asia_range_reversion | — | SÍ | SÍ | SÍ | SÍ | NO (declarada, no representable) | NO (declarada, no representable) |
| intraday_momentum_close | — | SÍ | SÍ | SÍ | NO (declarada, no representable) | — | — |
| intraday_momentum_close_v2 | — | SÍ | SÍ | SÍ | NO (declarada, no representable) | — | — |
| ny_open_vol_filter | SÍ | SÍ | SÍ | — | — | — | — |
| session_breakout_htf | — | SÍ | SÍ | SÍ | — | — | — |

## Propuestas (3 familias distintas)

Todas: modo GA `small`, **n_total estimado 440** (40 × (10+1)); si van en grid
se recalcula al registrar. IS **2021-10-01 → 2024-06-30**, dentro de
`usable_from` (USDJPY H1 2003-05-04; US100 M15 2015-01-02). Sin OOS.

| # | Hipótesis de mercado | Símbolo | TF | Plantilla | n_total | Cuentas viables (T2) | Cribado cost_R (ATR 12m) | Operaciones cost_R | Preflight | Feasibility seco |
|---|---|---|---|---|---|---:|---|---|---|---|---|
| 1 | El USDJPY concentra el flujo asiático; los extremos del rango 18:00-03:00 actúan como liquidez y el precio revierte. H1 captura el ciclo sin el spread de M1-M5. | USDJPY | H1 | asia_range_reversion | 440 | CFD-001 y CFD-006 | 0.0982 / 0.0857 | 0.0506 / 0.0422 | 40/40 válidos | 38/40 factibles (95,0 %) · PASA |
| 2 | Apertura NY: la ruptura del rango 09:35-11:30 con volatilidad alta tiene continuación; M15 filtra el ruido de M1/M5 y mantiene coste de operaciones 0.048-0.055 R. | US100 | M15 | ny_open_vol_filter | 440 | CFD-001 y CFD-006 | 0.0925 / 0.0961 | 0.0548 / 0.0479 | 40/40 válidos | 38/40 factibles (95,0 %) · PASA |
| 3 | Ruptura del rango de apertura con confirmación de la última vela H1; M15 permite entrar tras el OR de 15 min y el filtro HTF evita falsos breaks. | US100 | M15 | session_breakout_htf | 440 | CFD-001 y CFD-006 | 0.0925 / 0.0961 | 0.0631 / 0.0555 | 40/40 válidos | 31/40 factibles (77,5 %) · PASA |

Evidencia de `suggest` (ops IS y pliegues):
- USDJPY H1 asia: 257 ops; pliegues 51/45/64/52.
- US100 M15 ny_open: 614 ops CFD-001 (615 CFD-006); pliegues 123/123/129/115.
- US100 M15 session_breakout: 335 ops; pliegues 60/66/76/74.

Los dos cost_R son distintos por diseño: el de cribado mide el coste contra el
ATR típico del TF; el de operaciones mide el coste real de las entradas/salidas
de la plantilla. La factibilidad usa el de operaciones (como antes); el cribado
cuenta×símbolo×TF usa el de ATR 12m.

## Salida de preflight y feasibility en seco

Comandos (sin registrar campaña):

```text
lab discovery preflight --spec .orquestador/specs/asia-usdjpy-h1.yaml
lab discovery feasibility --spec .orquestador/specs/asia-usdjpy-h1.yaml
lab discovery preflight --spec .orquestador/specs/ny-open-us100-m15.yaml
lab discovery feasibility --spec .orquestador/specs/ny-open-us100-m15.yaml
lab discovery preflight --spec .orquestador/specs/session-breakout-us100-m15.yaml
lab discovery feasibility --spec .orquestador/specs/session-breakout-us100-m15.yaml
```

Resultados:
- Preflight: 40 generados / 40 válidos / 0 rechazados / 0 duplicadas en las tres.
- Feasibility: 38/40 (95,0 %), 38/40 (95,0 %) y 31/40 (77,5 %); las tres pasan
  el gate ≥50 %.
- `count_tests` y el número de filas de `disc_campaigns` no cambian (test
  `tests/test_discovery_spec.py`).

## Impacto en el DSR

- Contador actual: **1676**.
- Si se aprobaran las 3 campañas: 1676 + 3×440 = **2996**. Cada `n_total` entra
  completo al aprobar/registrar; no se ejecutó ninguna.

## Excluidas

- `ny_open_vol_filter` US100 M5: prohibida expresamente y Edge Map la marca
  sobreajustada.
- `intraday_momentum_close`: inválida en Edge Map y prohibida expresamente.
- `intraday_momentum_close_v2`: sin edge bruto en Edge Map.
- Asia H4/D1: incompatibles con el rango 18:00-03:00.
- M1/M5 en general: sin cost_R de cribado viable en T2.
- US30 CFD-006: Sin datos de spread; US500/US30 no los permite CFD-001.

## Cierre

- Ninguna campaña registrada; ningún DSR consumido; sin OOS; sin push.
- Specs en `.orquestador/specs/` (no se registran).
- `git status --short` antes de R2k: solo `?? tl2-edge-map.patch`.
