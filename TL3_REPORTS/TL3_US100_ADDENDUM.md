# TL3 · Addendum US100 v3.2 (T6)

Réplica exacta del EA v3.2 sobre `data/cache/ea/US100_CASH_M5_NY.parquet`,
con el setfile sin cambios y calentamiento desde 2017-12-28. Operaciones
filtradas por entrada ≥ 2021-09-14.

## Comprobación de réplica

| Métrica | T41 | Réplica TL3 | Diferencia |
|---|---:|---:|---:|
| Operaciones | 478 | **479** | +1 |
| Expectativa | +0,3104 R | **+0,3104 R** | 0,0000 |
| Total | +148,4 R | **+148,7 R** | +0,3 |
| Desviación | 1,9193 | 1,9173 | −0,0020 |

La única diferencia es la operación nueva del 2026-11-24 (barras añadidas
después de T41). **La réplica reproduce**; no se marca bloqueada.

`TL3_REPORTS/ea_trades_v32.parquet`: 479 filas con entrada, salida, lado, R,
MAE/MFE en R, hora de entrada y año.

## Largo/corto por año

| Año | Largos | Exp R largo | Cortos | Exp R corto |
|---|---:|---:|---:|---:|
| 2021 (desde sep) | 18 | +0,4879 | 16 | −0,2625 |
| 2022 | 28 | +0,2907 | 56 | +0,8675 |
| 2023 | 66 | +0,1104 | 28 | **−0,1368** |
| 2024 | 69 | +0,2831 | 27 | +0,3229 |
| 2025 | 55 | +0,3984 | 31 | +0,0503 |
| 2026 | 37 | +0,5887 | 48 | +0,2165 |

**Hipótesis de `TL3_US100_CASE_STUDY.md §3.3`:** el lado corto pierde en
2023: **28 operaciones, −0,1368 R**. Se confirma de forma descriptiva.

## MAE/MFE y hora de entrada

- MAE medio: **−1,0537 R**; MFE medio: **+1,6614 R**.
- R por hora de entrada:

| Hora NY | Ops | Exp R |
|---:|---:|---:|
| 09 | 195 | +0,4014 |
| 10 | 273 | +0,2239 |
| 11 | 11 | +0,8428 |

Solo descriptivo: **no** se proponen filtros ni parámetros a partir de esta
tabla. No se tocó el EA, el setfile ni el motor.
