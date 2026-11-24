# R2g · cierre e historia completa

Comparación y calidad desde 2021-10-01 hasta 2026-11-20.

## Cobertura de la caché M1

| Símbolo | Primer dato | Último dato | Meses | Filas | Meses sin fichero |
|---|---|---|---:|---:|---|
| US100 | 2011-09-18T21:53:00+00:00 | 2026-11-20T21:14:00+00:00 | 178 | 4,275,591 | 2011-10, 2011-11, 2011-12, 2013-03, 2013-04 |
| US500 | 2011-09-18T21:53:00+00:00 | 2026-11-20T21:14:00+00:00 | 178 | 4,109,488 | 2011-10, 2011-11, 2011-12, 2013-03, 2013-04 |
| US30 | 2013-09-30T13:34:00+00:00 | 2026-11-20T21:14:00+00:00 | 159 | 4,059,094 | ninguno |
| XAUUSD | 2003-05-05T00:01:00+00:00 | 2026-11-20T21:59:00+00:00 | 283 | 8,010,604 | ninguno |
| EURUSD | 2003-05-04T21:00:00+00:00 | 2026-11-20T21:59:00+00:00 | 283 | 8,801,267 | ninguno |
| GBPUSD | 2003-05-04T21:00:00+00:00 | 2026-11-20T21:59:00+00:00 | 283 | 8,797,879 | ninguno |
| USDJPY | 2003-05-04T21:00:00+00:00 | 2026-11-20T21:59:00+00:00 | 283 | 8,797,677 | ninguno |

## Comparación con el bróker (M5, 2021-10 → última semana cerrada)

| Símbolo | Velas | Corr | Δnivel | Δbps | Lag | Coincidencia | Veredicto |
|---|---:|---:|---:|---:|---:|---:|---|
| US100 | 350,589 | 0.9855 | +0.895219 | +0.47 | +0 | 32.1% | apta |
| US500 | 350,561 | 0.9902 | +0.300109 | +0.56 | +0 | 19.5% | apta |
| US30 | 350,601 | 0.9813 | +0.934436 | +0.23 | +0 | 28.4% | apta |
| XAUUSD | 360,717 | 0.9976 | +0.114191 | +0.42 | +0 | 79.1% | apta |
| EURUSD | 381,154 | 0.9913 | +0.000006 | +0.05 | +0 | 81.8% | apta |
| GBPUSD | 381,088 | 0.9889 | +0.000014 | +0.11 | +0 | 70.2% | apta |
| USDJPY | 381,086 | 0.9933 | +0.000047 | +0.00 | +0 | 76.9% | apta |

## Calidad Dukascopy por TF

| Símbolo | TF | Filas | Inicio útil | Huecos | Pausa | Calendario | Sesiones sin datos | Estado |
|---|---|---:|---|---:|---|---|---:|---|
| US100 | M1 | 4,040,843 | 2013-11-01T00:00:00+00:00 | 2857 | 16:15 (1939×) | nyse | 433 | WARN |
| US100 | M5 | 815,048 | 2013-11-01T00:00:00+00:00 | 414 | 16:15 (1711×) | nyse | 433 | WARN |
| US100 | M15 | 272,859 | 2013-11-01T00:00:00+00:00 | 21 | 16:15 (1714×) | nyse | 433 | WARN |
| US100 | M30 | 138,181 | 2013-11-01T00:00:00+00:00 | 11 | ninguna | nyse | 433 | WARN |
| US100 | H1 | 70,667 | 2013-11-01T00:00:00+00:00 | 870 | ninguna | nyse | 433 | FAIL |
| US100 | H4 | 19,105 | 2013-06-02T21:00:00+00:00 | 814 | ninguna | nyse | 432 | FAIL |
| US100 | D1 | 3,479 | 2013-06-02T21:00:00+00:00 | 8 | ninguna | nyse | 189 | WARN |
| US500 | M1 | 3,878,419 | 2013-11-01T00:00:00+00:00 | 8949 | 16:15 (1953×) | nyse | 459 | WARN |
| US500 | M5 | 810,206 | 2013-11-01T00:00:00+00:00 | 454 | 16:15 (1710×) | nyse | 459 | WARN |
| US500 | M15 | 271,730 | 2013-11-01T00:00:00+00:00 | 36 | 16:15 (1710×) | nyse | 459 | WARN |
| US500 | M30 | 137,664 | 2013-11-01T00:00:00+00:00 | 14 | ninguna | nyse | 459 | WARN |
| US500 | H1 | 70,407 | 2013-11-01T00:00:00+00:00 | 872 | ninguna | nyse | 459 | FAIL |
| US500 | H4 | 19,042 | 2013-06-02T21:00:00+00:00 | 814 | ninguna | nyse | 457 | FAIL |
| US500 | D1 | 3,468 | 2013-06-02T21:00:00+00:00 | 18 | ninguna | nyse | 209 | FAIL |
| US30 | M1 | 4,048,072 | 2013-11-01T00:00:00+00:00 | 2018 | 16:15 (1920×) | nyse | 191 | WARN |
| US30 | M5 | 816,529 | 2013-11-01T00:00:00+00:00 | 360 | 16:15 (1710×) | nyse | 191 | WARN |
| US30 | M15 | 273,047 | 2013-11-01T00:00:00+00:00 | 18 | 16:15 (1709×) | nyse | 191 | WARN |
| US30 | M30 | 138,231 | 2013-11-01T00:00:00+00:00 | 8 | ninguna | nyse | 191 | WARN |
| US30 | H1 | 70,680 | 2013-11-01T00:00:00+00:00 | 867 | ninguna | nyse | 191 | FAIL |
| US30 | H4 | 18,614 | 2013-09-30T13:00:00+00:00 | 806 | ninguna | nyse | 190 | FAIL |
| US30 | D1 | 3,393 | 2013-09-29T21:00:00+00:00 | 9 | ninguna | nyse | 37 | WARN |
| XAUUSD | M1 | 7,921,315 | 2003-12-01T00:00:00+00:00 | 26549 | 17:00 (2241×) | sin calendario | 29 | WARN |
| XAUUSD | M5 | 1,679,641 | 2003-05-05T00:00:00+00:00 | 2417 | 17:00 (2339×) | sin calendario | 29 | WARN |
| XAUUSD | M15 | 567,203 | 2003-05-05T00:00:00+00:00 | 122 | 17:00 (2333×) | sin calendario | 29 | WARN |
| XAUUSD | M30 | 284,892 | 2003-05-05T00:00:00+00:00 | 45 | ninguna | sin calendario | 29 | WARN |
| XAUUSD | H1 | 142,817 | 2003-05-05T00:00:00+00:00 | 171 | ninguna | sin calendario | 29 | WARN |
| XAUUSD | H4 | 36,588 | 2003-05-04T21:00:00+00:00 | 28 | ninguna | sin calendario | 28 | WARN |
| XAUUSD | D1 | 6,108 | 2003-05-04T21:00:00+00:00 | 17 | ninguna | sin calendario | 37 | WARN |
| EURUSD | M1 | 8,801,267 | 2003-05-04T21:00:00+00:00 | 597 | ninguna | sin calendario | 4 | WARN |
| EURUSD | M5 | 1,764,230 | 2003-05-04T21:00:00+00:00 | 35 | ninguna | sin calendario | 4 | WARN |
| EURUSD | M15 | 588,175 | 2003-05-04T21:00:00+00:00 | 6 | ninguna | sin calendario | 4 | WARN |
| EURUSD | M30 | 294,109 | 2003-05-04T21:00:00+00:00 | 1 | ninguna | sin calendario | 4 | WARN |
| EURUSD | H1 | 147,067 | 2003-05-04T21:00:00+00:00 | 3 | ninguna | sin calendario | 4 | WARN |
| EURUSD | H4 | 36,779 | 2003-05-04T21:00:00+00:00 | 0 | ninguna | sin calendario | 4 | WARN |
| EURUSD | D1 | 6,138 | 2003-05-04T21:00:00+00:00 | 0 | ninguna | sin calendario | 7 | WARN |
| GBPUSD | M1 | 8,797,879 | 2003-05-04T21:00:00+00:00 | 840 | ninguna | sin calendario | 4 | WARN |
| GBPUSD | M5 | 1,763,914 | 2003-05-04T21:00:00+00:00 | 36 | ninguna | sin calendario | 4 | WARN |
| GBPUSD | M15 | 588,130 | 2003-05-04T21:00:00+00:00 | 8 | ninguna | sin calendario | 4 | WARN |
| GBPUSD | M30 | 294,083 | 2003-05-04T21:00:00+00:00 | 3 | ninguna | sin calendario | 4 | WARN |
| GBPUSD | H1 | 147,054 | 2003-05-04T21:00:00+00:00 | 3 | ninguna | sin calendario | 4 | WARN |
| GBPUSD | H4 | 36,776 | 2003-05-04T21:00:00+00:00 | 0 | ninguna | sin calendario | 4 | WARN |
| GBPUSD | D1 | 6,137 | 2003-05-04T21:00:00+00:00 | 0 | ninguna | sin calendario | 8 | WARN |
| USDJPY | M1 | 8,797,677 | 2003-05-04T21:00:00+00:00 | 701 | ninguna | sin calendario | 4 | WARN |
| USDJPY | M5 | 1,763,864 | 2003-05-04T21:00:00+00:00 | 33 | ninguna | sin calendario | 4 | WARN |
| USDJPY | M15 | 588,062 | 2003-05-04T21:00:00+00:00 | 7 | ninguna | sin calendario | 4 | WARN |
| USDJPY | M30 | 294,050 | 2003-05-04T21:00:00+00:00 | 1 | ninguna | sin calendario | 4 | WARN |
| USDJPY | H1 | 147,037 | 2003-05-04T21:00:00+00:00 | 4 | ninguna | sin calendario | 4 | WARN |
| USDJPY | H4 | 36,777 | 2003-05-04T21:00:00+00:00 | 2 | ninguna | sin calendario | 4 | WARN |
| USDJPY | D1 | 6,142 | 2003-05-04T21:00:00+00:00 | 0 | ninguna | sin calendario | 9 | WARN |
