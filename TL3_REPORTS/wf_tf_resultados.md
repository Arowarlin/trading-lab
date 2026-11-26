# WF-TF — walk-forward con ventanas por timeframe

**Prerregistro aplicado:** `TL3_REPORTS/robust1_wf_windows.md`, commit `ccf27cb`, SHA-256 `f8ad4e9e30c2b4aa3dd26f2831e102163c8001467ae5d6147deb311ac6f75238` (comprobado antes de empezar).

**Declaración (literal, COLA-WF-TF §1):**

> Esta evaluación es una **segunda oportunidad** para los finalistas de EDGE-1. La propuesta de ventanas se escribió a partir de la **frecuencia** de operaciones, no de resultados, pero se aplica sabiendo que tres finalistas de `edge1-11` (USDJPY H1; 5178, 5309 y 5385) solo fallaban por un WF "no informativo". Se aplica **igual a los 22**, una sola vez y con los mismos umbrales. El juez final sigue siendo el OOS-2 (2023-2026), **sin abrir**, que solo el operador puede autorizar a leer una vez.

Una sola pasada por finalista, los mismos umbrales y ninguna lectura del OOS-2 ni llamada a `confirm`. El juez final sigue siendo el OOS-2.

<!-- WF-TF:EDGE-1:START -->
## EDGE-1 — 22 finalistas, 11 campañas

**Generado:** 2026-11-26T14:28:04.238178+00:00
**Pasan las 4 puertas con WF-TF:** 0 de 22.

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
