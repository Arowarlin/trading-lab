# ROBUST-1 · R2 · PBO de `edge1-01` y `edge1-11`

**Fecha:** 2026-11-26 · **Solo lectura** (IS; sin OOS-2).

## Comprobación

Se recalcularon las matrices de entrada de `robustness._pbo_wf` con
`databank.frontier(campaign_id)` y `cscv_pbo(n_slices=16, seed=0)`.

| Campaña | Estrategias | Filas | Matriz SHA-256 (32) | `rows_used` | PBO recalculado | PBO almacenado |
|---|---:|---:|---|---:|---:|---:|
| `edge1-01-trend-pullback-mtf-usdjpy-h4` | 40 | 886 | `743cf9989e53742940ce2fbbe4012888` | 880 | 0.6335664336 | 0.6335664336 |
| `edge1-11-trend-pullback-mtf-usdjpy-h1` | 40 | 850 | `2fa0dba84ccaaee7af303f8c8887dfa5` | 848 | 0.6340326340 | 0.6340326340 |

* Las matrices **no son la misma**: distinto número de filas, distinto hash y
  distinto conjunto de `strategy_id` (comprobado: las 40 filas de cada matriz
  pertenecen a su campaña, 0 ajenas).
* Los PBO **no son idénticos**: difieren en 0,00047 (≈ 6 combinaciones de
  12.870). La tabla de EDGE-1 los muestra a 3 decimales y ambos redondean a
  0,634, que es lo que parecía un valor repetido.
* No hay caché global ni matriz compartida: `_pbo_wf` consulta
  `databank.frontier(campaign_id)` y el PBO es global a la campaña (por eso
  todos los finalistas de una misma campaña comparten su PBO).

## Resolución

**Casualidad numérica por redondeo, no error de matriz ni de caché.** No se
cambia código ni umbrales. El PBO completo se conserva en
`disc_validations.result_json` para evitar decisiones sobre la cifra
redondeada.
