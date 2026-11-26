# ROBUST-1 · R2 · PBO de `edge1-01` y `edge1-11`

**Fecha:** 2026-11-26 · **Solo lectura** (IS; sin OOS-2).

## Comprobación inicial

Se recalcularon las matrices de entrada de `robustness._pbo_wf` con
`databank.frontier(campaign_id)` y `cscv_pbo(n_slices=16, seed=0)`. Las
matrices eran distintas (40 estrategias cada una; 886 y 850 filas), pero el
PBO salía casi idéntico al mostrarlo con 3 decimales:

| Campaña | Filas | `strategy_id` ajenos | PBO (3 decimales) |
|---|---:|---:|---:|
| `edge1-01-trend-pullback-mtf-usdjpy-h4` | 886 | 0 | 0.634 |
| `edge1-11-trend-pullback-mtf-usdjpy-h1` | 850 | 0 | 0.634 |

La diferencia real era 0,00047, no un valor cacheado ni una matriz compartida.

## Causa: matriz desordenada y no diaria

`databank.frontier` devuelve el R diario **solo de los días con operación**.
`_pbo_wf` los unía con `pd.concat(..., sort=False)`: el índice quedaba
desordenado (había pliegues que empezaban en 2018 y terminaban en 2012) y cada
fila era un "día con operación", no un día de calendario. Eso hacía que el PBO
y el walk-forward cortaran por posición sobre una serie no temporal.

**Corrección (R2/R3):** `_frontier_frame` ordena el índice, lo normaliza a
fechas y lo reindexa a días hábiles (lunes-viernes) rellenando con 0 los días
sin operación. No se toca ningún umbral.

## Resultado tras la corrección

| Campaña | Filas | Matriz SHA-256 (32) | PBO recalculado |
|---|---:|---|---:|
| `edge1-01-trend-pullback-mtf-usdjpy-h4` | 1971 | `f20ff32a57e592844d5174d876e7a7ab` | 0.7429681430 |
| `edge1-11-trend-pullback-mtf-usdjpy-h1` | 1971 | `b8cf37f7052e780a89be60263c5d5ace` | 0.1979797980 |

* Las matrices siguen siendo distintas y ahora son series diarias regulares.
* El PBO ya **no coincide**: `edge1-01` empeora a 0,743 (falla ≤ 0,30) y
  `edge1-11` mejora a 0,198 (pasa el PBO, pero sigue fallando el WF y las demás
  puertas).
* No hay caché global: el PBO es global a la campaña y se guarda por estrategia.

## Resolución

**H-2 confirmado como error de matriz, no como casualidad.** Corregido con
`_frontier_frame` y un test sintético que exige índice monótono, calendario de
días hábiles y ceros en los días sin operación. Los PBO guardados antes de esta
cola quedan obsoletos; R4 los recalcula para los 22 finalistas.
