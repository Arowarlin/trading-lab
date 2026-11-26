# WF-TF — walk-forward con ventanas por timeframe

**Prerregistro aplicado:** `TL3_REPORTS/robust1_wf_windows.md`, commit `ccf27cb`, SHA-256 `f8ad4e9e30c2b4aa3dd26f2831e102163c8001467ae5d6147deb311ac6f75238` (comprobado antes de empezar).

**Declaración (literal, COLA-WF-TF §1):**

> Esta evaluación es una **segunda oportunidad** para los finalistas de EDGE-1. La propuesta de ventanas se escribió a partir de la **frecuencia** de operaciones, no de resultados, pero se aplica sabiendo que tres finalistas de `edge1-11` (USDJPY H1; 5178, 5309 y 5385) solo fallaban por un WF "no informativo". Se aplica **igual a los 22**, una sola vez y con los mismos umbrales. El juez final sigue siendo el OOS-2 (2023-2026), **sin abrir**, que solo el operador puede autorizar a leer una vez.

Una sola pasada por finalista, los mismos umbrales y ninguna lectura del OOS-2 ni llamada a `confirm`. El juez final sigue siendo el OOS-2.

<!-- WF-TF:EDGE-1:START -->
## EDGE-1 — 22 finalistas, 11 campañas

**Generado:** 2026-11-26T16:33:19.906736+00:00
**Pasan las 4 puertas con WF-TF:** 0 de 22.

Las columnas de eficiencia y `stitched_sharpe` se muestran aunque el veredicto sea `Sin datos` (menos de 3 pliegues); en ese caso no aprueban nada.

### WF antiguo (60/20) frente a WF-TF

| Estrategia | Campaña | Activo | TF | Pliegues | Mediana ops/ventana | WF-TF eff | WF-TF stitched | WF-TF veredicto | Motivo | WF viejo eff | WF viejo etiqueta |
|---:|---|---|---|---:|---:|---:|---:|---|---|---:|---|
| 936 | `edge1-01-trend-pullback-mtf-usdjpy-h4` | USDJPY | H4 | 13 | 6.0 | 0.416 | 0.070 | fallido | estabilidad 0.250 < 0,300 | 0.000 | WF no informativo (baja frecuencia) |
| 1038 | `edge1-01-trend-pullback-mtf-usdjpy-h4` | USDJPY | H4 | 13 | 6.0 | 0.416 | 0.070 | fallido | estabilidad 0.250 < 0,300 | 0.000 | WF no informativo (baja frecuencia) |
| 1348 | `edge1-02-vol-squeeze-breako-usdjpy-h4` | USDJPY | H4 | 14 | 22.0 | -0.596 | -0.020 | fallido | stitched -0.020 <= 0.00 | 0.000 | informativo |
| 2801 | `edge1-05-vol-squeeze-breako-eurusd-h4` | EURUSD | H4 | 14 | 8.0 | -0.101 | -0.164 | fallido | stitched -0.164 <= 0.00 | 0.000 | informativo |
| 3228 | `edge1-06-donchian-vol-h4-gbpusd-h4` | GBPUSD | H4 | 14 | 9.5 | 0.000 | -0.087 | fallido | stitched -0.087 <= 0.00 | 0.000 | informativo |
| 3583 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 13 | 2.0 | 0.000 | 0.353 | fallido | pliegues positivos 0.385 < 0,500 | 0.000 | WF no informativo (baja frecuencia) |
| 3585 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 13 | 2.0 | 0.000 | 0.353 | fallido | pliegues positivos 0.385 < 0,500 | 0.000 | WF no informativo (baja frecuencia) |
| 3625 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 13 | 2.0 | 0.000 | 0.353 | fallido | pliegues positivos 0.385 < 0,500 | 0.000 | WF no informativo (baja frecuencia) |
| 3669 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 13 | 2.0 | 0.000 | 0.353 | fallido | pliegues positivos 0.385 < 0,500 | 0.000 | WF no informativo (baja frecuencia) |
| 3675 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 13 | 2.0 | 0.000 | 0.353 | fallido | pliegues positivos 0.385 < 0,500 | 0.000 | WF no informativo (baja frecuencia) |
| 4114 | `edge1-08-vol-squeeze-breako-gbpusd-h4` | GBPUSD | H4 | 14 | 6.0 | 0.071 | 0.349 | fallido | eficiencia 0.071 < 0.30 | 0.000 | informativo |
| 5178 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | USDJPY | H1 | 29 | 2.0 | 0.000 | -0.488 | fallido | stitched -0.488 <= 0.00 | 0.000 | WF no informativo (baja frecuencia) |
| 5309 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | USDJPY | H1 | 29 | 2.0 | 0.000 | -0.488 | fallido | stitched -0.488 <= 0.00 | 0.000 | WF no informativo (baja frecuencia) |
| 5385 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | USDJPY | H1 | 29 | 2.0 | 0.000 | -0.488 | fallido | stitched -0.488 <= 0.00 | 0.000 | WF no informativo (baja frecuencia) |
| 5566 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | USDJPY | H1 | 31 | 16.0 | -0.225 | -0.279 | fallido | stitched -0.279 <= 0.00 | -0.249 | informativo |
| 5775 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | USDJPY | H1 | 31 | 16.0 | -0.225 | -0.279 | fallido | stitched -0.279 <= 0.00 | -0.249 | informativo |
| 5854 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | USDJPY | H1 | 31 | 16.0 | -0.225 | -0.279 | fallido | stitched -0.279 <= 0.00 | -0.249 | informativo |
| 7855 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | GBPUSD | H1 | 31 | 0.0 | 0.000 | 0.217 | fallido | pliegues positivos 0.226 < 0,500 | 0.000 | WF no informativo (baja frecuencia) |
| 7966 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | GBPUSD | H1 | 31 | 0.0 | 0.000 | 0.217 | fallido | pliegues positivos 0.226 < 0,500 | 0.000 | WF no informativo (baja frecuencia) |
| 8011 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | GBPUSD | H1 | 31 | 0.0 | 0.000 | 0.217 | fallido | pliegues positivos 0.226 < 0,500 | 0.000 | WF no informativo (baja frecuencia) |
| 9111 | `edge1-21-asia-range-reversi-usdjpy-m30` | USDJPY | M30 | 49 | 5.0 | 0.000 | 0.150 | fallido | pliegues positivos 0.490 < 0,500 | -0.212 | informativo |
| 9611 | `edge1-22-trend-pullback-mtf-usdjpy-m30` | USDJPY | M30 | 45 | 0.0 | 0.000 | -0.226 | fallido | stitched -0.226 <= 0.00 | 0.000 | WF no informativo (baja frecuencia) |

### Las 4 puertas

Gate 1 y Gate 3 salen de la tabla ya calculada; PBO, ruido y ejecución no se recalculan. Gate 2 exige además WF-TF `ok` (eficiencia ≥ 0,3, `stitched_sharpe` > 0, ≥ 3 pliegues y el resto del veredicto).

| Estrategia | Campaña | TF | Gate 1 | PBO | Ruido | Ejec | WF-TF | Gate 2 | Gate 3 | Puerta 4 | 4 puertas |
|---:|---|---|---:|---:|---:|---:|---|---|---|---|---|
| 936 | `edge1-01-trend-pullback-mtf-usdjpy-h4` | H4 | si | 0.743 | 0.742 | 0.944 | no | no | si | no | NO |
| 1038 | `edge1-01-trend-pullback-mtf-usdjpy-h4` | H4 | si | 0.743 | 0.825 | 0.958 | no | no | si | no | NO |
| 1348 | `edge1-02-vol-squeeze-breako-usdjpy-h4` | H4 | si | 0.957 | 0.861 | 0.493 | no | no | si | no | NO |
| 2801 | `edge1-05-vol-squeeze-breako-eurusd-h4` | H4 | si | 0.245 | 0.403 | 0.969 | no | no | si | no | NO |
| 3228 | `edge1-06-donchian-vol-h4-gbpusd-h4` | H4 | si | 0.578 | 0.758 | 0.976 | no | no | si | no | NO |
| 3583 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | H4 | si | 0.789 | 0.736 | 0.911 | no | no | si | no | NO |
| 3585 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | H4 | si | 0.789 | 0.739 | 0.925 | no | no | si | no | NO |
| 3625 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | H4 | si | 0.789 | 0.727 | 0.919 | no | no | si | no | NO |
| 3669 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | H4 | si | 0.789 | 0.847 | 0.923 | no | no | si | no | NO |
| 3675 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | H4 | si | 0.789 | 0.736 | 0.911 | no | no | si | no | NO |
| 4114 | `edge1-08-vol-squeeze-breako-gbpusd-h4` | H4 | si | 0.398 | 1.031 | 0.999 | no | no | si | no | NO |
| 5178 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | H1 | si | 0.198 | 0.652 | 0.933 | no | no | si | no | NO |
| 5309 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | H1 | si | 0.198 | 0.927 | 0.980 | no | no | si | no | NO |
| 5385 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | H1 | si | 0.198 | 0.742 | 0.988 | no | no | si | no | NO |
| 5566 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | H1 | si | 0.023 | 0.719 | 0.935 | no | no | si | no | NO |
| 5775 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | H1 | si | 0.023 | -0.971 | -0.199 | no | no | no | no | NO |
| 5854 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | H1 | si | 0.023 | 0.819 | 0.918 | no | no | si | no | NO |
| 7855 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | H1 | si | 0.689 | -0.014 | 1.008 | no | no | si | no | NO |
| 7966 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | H1 | si | 0.689 | 0.426 | 1.101 | no | no | si | no | NO |
| 8011 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | H1 | si | 0.689 | 0.118 | 1.034 | no | no | si | no | NO |
| 9111 | `edge1-21-asia-range-reversi-usdjpy-m30` | M30 | si | 0.257 | 0.087 | 0.974 | no | no | si | no | NO |
| 9611 | `edge1-22-trend-pullback-mtf-usdjpy-m30` | M30 | si | 0.298 | 0.232 | 0.816 | no | no | si | no | NO |

### Puerta 4 — grupos de correlación

- Sin candidatos que pasen las puertas 1 a 3 con WF-TF: no hay grupos de correlación.

<!-- WF-TF:EDGE-1:END -->

<!-- WF-TF:EDGE-2:START -->
## EDGE-2 — 12 finalistas, 6 campañas

**Generado:** 2026-11-26T16:33:20.966816+00:00
**Pasan las 4 puertas con WF-TF:** 0 de 12.

**EDGE-2:** misma declaración, ventanas y umbrales que EDGE-1; una sola pasada sobre sus finalistas, sin tocar la cola de EDGE-2. OOS-2 sin leer.

Las columnas de eficiencia y `stitched_sharpe` se muestran aunque el veredicto sea `Sin datos` (menos de 3 pliegues); en ese caso no aprueban nada.

### WF antiguo (60/20) frente a WF-TF

| Estrategia | Campaña | Activo | TF | Pliegues | Mediana ops/ventana | WF-TF eff | WF-TF stitched | WF-TF veredicto | Motivo | WF viejo eff | WF viejo etiqueta |
|---:|---|---|---|---:|---:|---:|---:|---|---|---:|---|
| 12719 | `edge2-02-trend-pullback-mtf-us100-h4` | US100 | H4 | 1 | 10.0 | 5.871 | 3.540 | Sin datos | folds insuficientes (1 < 3) | 0.000 | Sin datos |
| 12864 | `edge2-02-trend-pullback-mtf-us100-h4` | US100 | H4 | 1 | 10.0 | 5.871 | 3.540 | Sin datos | folds insuficientes (1 < 3) | 0.000 | Sin datos |
| 12892 | `edge2-02-trend-pullback-mtf-us100-h4` | US100 | H4 | 1 | 10.0 | 5.871 | 3.540 | Sin datos | folds insuficientes (1 < 3) | 0.000 | Sin datos |
| 12911 | `edge2-02-trend-pullback-mtf-us100-h4` | US100 | H4 | 1 | 10.0 | 5.871 | 3.540 | Sin datos | folds insuficientes (1 < 3) | 0.000 | Sin datos |
| 12992 | `edge2-02-trend-pullback-mtf-us100-h4` | US100 | H4 | 1 | 10.0 | 5.871 | 3.540 | Sin datos | folds insuficientes (1 < 3) | 0.000 | Sin datos |
| 13484 | `edge2-03-vol-squeeze-breako-us100-h4` | US100 | H4 | 1 | 32.0 | 0.407 | 0.389 | Sin datos | folds insuficientes (1 < 3) | 0.000 | Sin datos |
| 14046 | `edge2-05-trend-pullback-mtf-us100-h1` | US100 | H1 | 5 | 82.0 | -1.181 | -0.840 | fallido | stitched -0.840 <= 0.00 | 0.000 | Sin datos |
| 14325 | `edge2-05-trend-pullback-mtf-us100-h1` | US100 | H1 | 5 | 82.0 | -1.181 | -0.840 | fallido | stitched -0.840 <= 0.00 | 0.000 | Sin datos |
| 14736 | `edge2-06-vol-squeeze-breako-us100-h1` | US100 | H1 | 5 | 12.0 | 0.694 | 0.647 | fallido | estabilidad 0.000 < 0,300 | 0.028 | Sin datos |
| 15371 | `edge2-08-trend-pullback-mtf-us500-h4` | US500 | H4 | 1 | 4.0 | 0.972 | 1.334 | Sin datos | folds insuficientes (1 < 3) | 0.000 | Sin datos |
| 15631 | `edge2-08-trend-pullback-mtf-us500-h4` | US500 | H4 | 1 | 4.0 | 0.972 | 1.334 | Sin datos | folds insuficientes (1 < 3) | 0.000 | Sin datos |
| 16545 | `edge2-11-trend-pullback-mtf-us500-h1` | US500 | H1 | 5 | 13.0 | -1.971 | -2.406 | fallido | stitched -2.406 <= 0.00 | 0.000 | Sin datos |

### Las 4 puertas

Gate 1 y Gate 3 salen de la tabla ya calculada; PBO, ruido y ejecución no se recalculan. Gate 2 exige además WF-TF `ok` (eficiencia ≥ 0,3, `stitched_sharpe` > 0, ≥ 3 pliegues y el resto del veredicto).

| Estrategia | Campaña | TF | Gate 1 | PBO | Ruido | Ejec | WF-TF | Gate 2 | Gate 3 | Puerta 4 | 4 puertas |
|---:|---|---|---:|---:|---:|---:|---|---|---|---|---|
| 12719 | `edge2-02-trend-pullback-mtf-us100-h4` | H4 | si | 0.526 | 0.708 | 0.959 | no | no | si | no | NO |
| 12864 | `edge2-02-trend-pullback-mtf-us100-h4` | H4 | si | 0.526 | 0.401 | 0.934 | no | no | si | no | NO |
| 12892 | `edge2-02-trend-pullback-mtf-us100-h4` | H4 | si | 0.526 | 0.727 | 0.969 | no | no | si | no | NO |
| 12911 | `edge2-02-trend-pullback-mtf-us100-h4` | H4 | si | 0.526 | 0.268 | 0.845 | no | no | si | no | NO |
| 12992 | `edge2-02-trend-pullback-mtf-us100-h4` | H4 | si | 0.526 | 0.755 | 0.991 | no | no | si | no | NO |
| 13484 | `edge2-03-vol-squeeze-breako-us100-h4` | H4 | si | 0.863 | 0.576 | 0.930 | no | no | si | no | NO |
| 14046 | `edge2-05-trend-pullback-mtf-us100-h1` | H1 | si | 0.499 | 0.808 | 0.929 | no | no | si | no | NO |
| 14325 | `edge2-05-trend-pullback-mtf-us100-h1` | H1 | si | 0.499 | 0.986 | 0.947 | no | no | si | no | NO |
| 14736 | `edge2-06-vol-squeeze-breako-us100-h1` | H1 | si | 0.543 | 0.617 | 0.830 | no | no | si | no | NO |
| 15371 | `edge2-08-trend-pullback-mtf-us500-h4` | H4 | si | 0.314 | 0.923 | 0.966 | no | no | si | no | NO |
| 15631 | `edge2-08-trend-pullback-mtf-us500-h4` | H4 | si | 0.314 | -0.721 | 0.544 | no | no | si | no | NO |
| 16545 | `edge2-11-trend-pullback-mtf-us500-h1` | H1 | si | 0.560 | 0.972 | 0.798 | no | no | si | no | NO |

### Puerta 4 — grupos de correlación

- Sin candidatos que pasen las puertas 1 a 3 con WF-TF: no hay grupos de correlación.

<!-- WF-TF:EDGE-2:END -->
