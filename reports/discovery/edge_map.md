# Edge Map · TradingLab 2.0

Solo lectura del databank. Sin OOS-2, sin campañas y sin DSR nuevo.

## Hipótesis probadas (2026-11-24)

Estas tres hipótesis ya se probaron. `suggest` no vuelve a proponer las
combinaciones plantilla × mercado × TF de la tabla; las propuestas de la misma
plantilla en **otros** mercados siguen siendo "por probar", no una
re-optimización de lo ya visto.

| # | Hipótesis | Plantilla | Mercados · TF | Campañas | Estado |
|---|---|---|---|---|---|
| 1 | Cambio de mes | `turn_of_month` | US500, US100 · D1 | `r9b-tom-us500-d1`, `r9b-tom-us100-d1`; `r9-tom-*` archivadas por anclaje | Probada; 0 finalistas. US500: OOS-1 negativo; US100: deriva < 90 |
| 2 | Reversión en los fix | `fix_reversal` | USDJPY, EURUSD, GBPUSD · H1 | `q2-fix-usdjpy-h1`, `q2-fix-eurusd-h1`, `q2-fix-gbpusd-h1` | Probada; edge bruto que el coste elimina |
| 4 | Rebote tras ventas fuertes | `d1_extension_reversion` | US500, US100 · D1 | `q1-rebote-us500-d1`, `q1-rebote-us100-d1` | Probada; US500 sin edge bruto; US100 muestra insuficiente (OOS-1 con 0 ops) |

La hipótesis 3 (momentum de serie temporal en cesta) **no** se marca como
probada: la infraestructura de ejecución está lista, pero la campaña
`q3-tsmom-cesta-d1` está pausada por la enmienda de auditoría del 2026-11-24 y
no se ha registrado ni ejecutado.

La tabla de abajo es la exportación anterior (2026-11-22); se conserva como
histórico. Los informes de cada campaña están en `reports/discovery/`.

## Resumen

- sin probar: 0
- solo viabilidad: 0
- inválida: 1
- sin edge bruto: 2
- edge bruto que el coste elimina: 0
- sobreajustada: 1
- candidata nivel 3: 0
- confirmada nivel 4: 0
- no verificable: 0

## Mapa

| Hipótesis | Instrumento | TF | Fuente | Estado | Bruto mediana | Bruto mejor | Neto mediana | Cost_R | Ops+ | Candidatas | Confirmadas |
|---|---|---|---|---|---|---|---|---|---|---|---|
| intraday_momentum_close | US100 | M5 | broker | inválida | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 0 | 0 |
| intraday_momentum_close_v2 | US100 | M5 | broker | sin edge bruto | -0.0112 | 0.0184 | -0.0778 | 0.0523 | 8/32 | 0 | 0 |
| ny_open_vol_filter | US100 | M5 | broker | sobreajustada | Sin datos | Sin datos | 0.0292 | 0.0470 | Sin datos | 0 | 0 |
| asia_range_reversion | USDJPY | H1 | dukascopy | sin edge bruto | -0.0533 | -0.0291 | -0.1170 | 0.0422 | 0/27 | 0 | 0 |

## Cuentas sin conectar

- CFD-002 · ftmo · ftmo_2step · DISCONNECTED · fuera de la capa de firma

La etiqueta usa la mediana de la rejilla (grid) o de la frontera de rango 1 (GA). El mejor valor es informativo y no decide.
