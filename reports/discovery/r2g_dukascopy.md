# R2g · Dukascopy M1 y temporalidades

Comparación M5 desde 2021-10-01. Sin campañas ni OOS.

## Comparación con el bróker

| Símbolo | Velas bróker | Velas Dukascopy | Solape | Corr | Δnivel | Δnivel bps | Lag | Coincidencia | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| US100 | 70,158 | 68,799 | 68,430 | 0.9817 | +4.786348 | 3.45 | +0 | 16.0% | apta |
| US500 | 70,157 | 68,811 | 68,442 | 0.9814 | +1.685494 | 3.93 | +0 | 7.7% | apta |
| US30 | 70,158 | 68,811 | 68,442 | 0.9804 | +5.932340 | 1.76 | +0 | 7.7% | apta |
| XAUUSD | 70,327 | 71,172 | 70,307 | 0.9982 | +0.105034 | 0.58 | +0 | 84.3% | apta |
| EURUSD | 74,483 | 75,128 | 74,481 | 0.9833 | +0.000007 | 0.07 | +0 | 79.9% | apta |
| GBPUSD | 74,489 | 75,090 | 74,458 | 0.9892 | +0.000024 | 0.18 | +0 | 73.7% | apta |
| USDJPY | 74,485 | 75,113 | 74,476 | 0.9918 | +0.001216 | 0.10 | +0 | 78.1% | apta |

Criterio: correlación ≥ 0,95 y lag 0 → apta. Lag +1 = Dukascopy va una vela por detrás. Coincidencia = OHLC dentro del 10 % del rango mediano del bróker tras quitar la diferencia media de nivel.

## Verificación reciente (2026-10)

| Símbolo | Velas | Corr | Δnivel | Δnivel bps | Lag | Coincidencia | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---|
| US100 | 5,811 | 0.9995 | -1.652878 | -0.55 | +0 | 47.3% | apta |
| US500 | 5,809 | 0.9984 | -0.206254 | -0.27 | +0 | 34.7% | apta |
| US30 | 5,811 | 0.9987 | -2.240480 | -0.43 | +0 | 34.0% | apta |
| XAUUSD | 5,965 | 0.9991 | +0.072733 | 0.18 | +0 | 95.9% | apta |
| EURUSD | 6,232 | 0.9943 | +0.000006 | 0.05 | +0 | 89.5% | apta |
| GBPUSD | 6,224 | 0.9804 | +0.000001 | 0.01 | +0 | 73.9% | apta |
| USDJPY | 6,225 | 0.9937 | -0.001493 | -0.09 | +0 | 83.0% | apta |

## Calidad Dukascopy (7 TF)

| Símbolo | TF | Filas | Inicio útil | Huecos | Pausa | Calendario | Días sin datos | Estado |
|---|---|---:|---|---:|---|---|---:|---|
| US100 | M1 | 402,378 | 2021-09-01T00:00:00+00:00 | 3 | 16:15 (233×) | nyse | 1253 | WARN |
| US100 | M5 | 80,484 | 2021-09-01T00:00:00+00:00 | 1 | 16:15 (233×) | nyse | 1253 | WARN |
| US100 | M15 | 26,829 | 2021-09-01T00:00:00+00:00 | 1 | 16:15 (233×) | nyse | 1253 | WARN |
| US100 | M30 | 13,563 | 2021-09-01T00:00:00+00:00 | 0 | 16:30 (233×) | nyse | 1253 | OK |
| US100 | H1 | 6,930 | 2021-09-01T00:00:00+00:00 | 0 | 17:00 (233×) | nyse | 1253 | OK |
| US100 | H4 | 131 | 2026-10-01T01:00:00+00:00 | 0 | ninguna | nyse | 1253 | FAIL |
| US100 | D1 | 21 | 2026-10-01T21:00:00+00:00 | 0 | ninguna | nyse | 1045 | FAIL |
| US500 | M1 | 399,131 | 2021-09-01T00:00:00+00:00 | 91 | 16:15 (233×) | nyse | 1253 | WARN |
| US500 | M5 | 80,494 | 2021-09-01T00:00:00+00:00 | 0 | 16:15 (233×) | nyse | 1253 | OK |
| US500 | M15 | 26,832 | 2021-09-01T00:00:00+00:00 | 0 | 16:15 (233×) | nyse | 1253 | OK |
| US500 | M30 | 13,564 | 2021-09-01T00:00:00+00:00 | 0 | 16:30 (233×) | nyse | 1253 | OK |
| US500 | H1 | 6,930 | 2021-09-01T00:00:00+00:00 | 0 | 17:00 (233×) | nyse | 1253 | OK |
| US500 | H4 | 131 | 2026-10-01T01:00:00+00:00 | 0 | ninguna | nyse | 1253 | FAIL |
| US500 | D1 | 21 | 2026-10-01T21:00:00+00:00 | 0 | ninguna | nyse | 1045 | FAIL |
| US30 | M1 | 402,339 | 2021-09-01T00:00:00+00:00 | 2 | 16:15 (233×) | nyse | 1253 | WARN |
| US30 | M5 | 80,496 | 2021-09-01T00:00:00+00:00 | 0 | 16:15 (233×) | nyse | 1253 | OK |
| US30 | M15 | 26,832 | 2021-09-01T00:00:00+00:00 | 0 | 16:15 (233×) | nyse | 1253 | OK |
| US30 | M30 | 13,564 | 2021-09-01T00:00:00+00:00 | 0 | 16:30 (233×) | nyse | 1253 | OK |
| US30 | H1 | 6,930 | 2021-09-01T00:00:00+00:00 | 0 | 17:00 (233×) | nyse | 1253 | OK |
| US30 | H4 | 131 | 2026-10-01T01:00:00+00:00 | 0 | ninguna | nyse | 1253 | FAIL |
| US30 | D1 | 21 | 2026-10-01T21:00:00+00:00 | 0 | ninguna | nyse | 1045 | FAIL |
| XAUUSD | M1 | 416,181 | 2021-09-01T00:00:00+00:00 | 5 | 17:00 (233×) | sin calendario | 1253 | WARN |
| XAUUSD | M5 | 83,244 | 2021-09-01T00:00:00+00:00 | 5 | 17:00 (233×) | sin calendario | 1253 | WARN |
| XAUUSD | M15 | 27,748 | 2021-09-01T00:00:00+00:00 | 5 | 17:00 (233×) | sin calendario | 1253 | WARN |
| XAUUSD | M30 | 13,875 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 1253 | WARN |
| XAUUSD | H1 | 6,940 | 2021-09-01T00:00:00+00:00 | 5 | 17:00 (233×) | sin calendario | 1253 | WARN |
| XAUUSD | H4 | 131 | 2026-10-01T01:00:00+00:00 | 0 | ninguna | sin calendario | 1253 | FAIL |
| XAUUSD | D1 | 21 | 2026-10-01T21:00:00+00:00 | 0 | ninguna | sin calendario | 1045 | FAIL |
| EURUSD | M1 | 1,520,766 | 2021-09-01T00:00:00+00:00 | 459 | ninguna | sin calendario | 339 | WARN |
| EURUSD | M5 | 305,659 | 2021-09-01T00:00:00+00:00 | 7 | ninguna | sin calendario | 339 | WARN |
| EURUSD | M15 | 101,914 | 2021-09-01T00:00:00+00:00 | 1 | ninguna | sin calendario | 339 | WARN |
| EURUSD | M30 | 50,959 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 339 | WARN |
| EURUSD | H1 | 25,480 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 339 | WARN |
| EURUSD | H4 | 131 | 2026-10-01T01:00:00+00:00 | 0 | ninguna | sin calendario | 339 | FAIL |
| EURUSD | D1 | 21 | 2026-10-01T21:00:00+00:00 | 0 | ninguna | sin calendario | 284 | FAIL |
| GBPUSD | M1 | 436,506 | 2021-09-01T00:00:00+00:00 | 139 | ninguna | sin calendario | 1251 | WARN |
| GBPUSD | M5 | 87,719 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | WARN |
| GBPUSD | M15 | 29,255 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | WARN |
| GBPUSD | M30 | 14,628 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | WARN |
| GBPUSD | H1 | 7,314 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | WARN |
| GBPUSD | H4 | 131 | 2026-10-01T01:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | FAIL |
| GBPUSD | D1 | 21 | 2026-10-01T21:00:00+00:00 | 0 | ninguna | sin calendario | 1043 | FAIL |
| USDJPY | M1 | 436,581 | 2021-09-01T00:00:00+00:00 | 130 | ninguna | sin calendario | 1251 | WARN |
| USDJPY | M5 | 87,746 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | WARN |
| USDJPY | M15 | 29,253 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | WARN |
| USDJPY | M30 | 14,627 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | WARN |
| USDJPY | H1 | 7,314 | 2021-09-01T00:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | WARN |
| USDJPY | H4 | 131 | 2026-10-01T01:00:00+00:00 | 0 | ninguna | sin calendario | 1251 | FAIL |
| USDJPY | D1 | 21 | 2026-10-01T21:00:00+00:00 | 0 | ninguna | sin calendario | 1043 | FAIL |

## Calidad bróker (M5)

| Símbolo | Filas | Inicio útil | Huecos | Pausa | Calendario | Estado |
|---|---:|---|---:|---|---|---|
| US100 | 363,802 | 2021-09-01T00:00:00+00:00 | 205 | 16:50 (1020×) | nyse | WARN |
| US500 | 363,760 | 2021-09-01T00:00:00+00:00 | 224 | 16:50 (1019×) | sin calendario | WARN |
| US30 | 366,103 | 2021-09-01T00:00:00+00:00 | 21 | 16:50 (1020×) | nyse | WARN |
| XAUUSD | 366,784 | 2021-09-01T00:00:00+00:00 | 56 | 16:50 (1012×) | sin calendario | WARN |
| EURUSD | 387,510 | 2021-09-01T00:00:00+00:00 | 41 | ninguna | sin calendario | WARN |
| GBPUSD | 387,468 | 2021-09-01T00:00:00+00:00 | 48 | ninguna | sin calendario | WARN |
| USDJPY | 387,451 | 2021-09-01T00:00:00+00:00 | 49 | ninguna | sin calendario | WARN |

## Cobertura de la caché

- Común a los 7 símbolos: 2021-09-01 → 2022-09-30 (12 meses) y spot-check 2026-10.
- EURUSD además: 2021-09-01 → 2025-08-31.
- El feed público limitó las ráfagas con 429/503; la descarga es reanudable por meses.
- No se ejecutaron campañas ni se leyó OOS-1/OOS-2.
