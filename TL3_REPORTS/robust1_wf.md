# ROBUST-1 R3 - Walk-forward en baja frecuencia

**Generado:** 2026-11-26T13:06:19.089150+00:00
**Finalistas:** 22 · **WF no informativo:** 14

Ventanas actuales: `train=60` días, `test=20` días (`engine.yaml::robustness`), sin cambios. Matriz diaria ordenada (R2). Se cuentan los **cierres de la variante elegida por el WF en cada pliegue**, que es la que el walk-forward evalúa; el detalle por pliegue queda en `robust1_wf.json`.

| Estrategia | Campaña | Activo | TF | WF eff | Pliegues | Mediana ops/pliegue | Rango ops | Etiqueta |
|---:|---|---|---|---:|---:|---:|---|---|
| 936 | `edge1-01-trend-pullback-mtf-usdjpy-h4` | USDJPY | H4 | 0.000 | 95 | 0.0 | 0-40 | WF no informativo (baja frecuencia) |
| 1038 | `edge1-01-trend-pullback-mtf-usdjpy-h4` | USDJPY | H4 | 0.000 | 95 | 0.0 | 0-40 | WF no informativo (baja frecuencia) |
| 1348 | `edge1-02-vol-squeeze-breako-usdjpy-h4` | USDJPY | H4 | 0.000 | 100 | 3.0 | 0-10 | informativo |
| 2801 | `edge1-05-vol-squeeze-breako-eurusd-h4` | EURUSD | H4 | 0.000 | 100 | 3.0 | 0-39 | informativo |
| 3228 | `edge1-06-donchian-vol-h4-gbpusd-h4` | GBPUSD | H4 | 0.000 | 100 | 2.0 | 0-7 | informativo |
| 3583 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 0.000 | 95 | 0.0 | 0-7 | WF no informativo (baja frecuencia) |
| 3585 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 0.000 | 95 | 0.0 | 0-7 | WF no informativo (baja frecuencia) |
| 3625 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 0.000 | 95 | 0.0 | 0-7 | WF no informativo (baja frecuencia) |
| 3669 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 0.000 | 95 | 0.0 | 0-7 | WF no informativo (baja frecuencia) |
| 3675 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | GBPUSD | H4 | 0.000 | 95 | 0.0 | 0-7 | WF no informativo (baja frecuencia) |
| 4114 | `edge1-08-vol-squeeze-breako-gbpusd-h4` | GBPUSD | H4 | 0.000 | 100 | 2.0 | 0-10 | informativo |
| 5178 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | USDJPY | H1 | 0.000 | 95 | 0.0 | 0-32 | WF no informativo (baja frecuencia) |
| 5309 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | USDJPY | H1 | 0.000 | 95 | 0.0 | 0-32 | WF no informativo (baja frecuencia) |
| 5385 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | USDJPY | H1 | 0.000 | 95 | 0.0 | 0-32 | WF no informativo (baja frecuencia) |
| 5566 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | USDJPY | H1 | -0.249 | 100 | 9.0 | 0-40 | informativo |
| 5775 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | USDJPY | H1 | -0.249 | 100 | 9.0 | 0-40 | informativo |
| 5854 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | USDJPY | H1 | -0.249 | 100 | 9.0 | 0-40 | informativo |
| 7855 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | GBPUSD | H1 | 0.000 | 99 | 0.0 | 0-40 | WF no informativo (baja frecuencia) |
| 7966 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | GBPUSD | H1 | 0.000 | 99 | 0.0 | 0-40 | WF no informativo (baja frecuencia) |
| 8011 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | GBPUSD | H1 | 0.000 | 99 | 0.0 | 0-40 | WF no informativo (baja frecuencia) |
| 9111 | `edge1-21-asia-range-reversi-usdjpy-m30` | USDJPY | M30 | -0.212 | 101 | 4.0 | 0-26 | informativo |
| 9611 | `edge1-22-trend-pullback-mtf-usdjpy-m30` | USDJPY | M30 | 0.000 | 93 | 0.0 | 0-39 | WF no informativo (baja frecuencia) |

## Lectura

- La puerta WF **sigue sin pasar** cuando la eficiencia es < 0,3; la
  etiqueta solo explica que la ventana de 20 días no contiene
  operaciones suficientes para medirla.
- No se tocaron `wf_train_days`/`wf_test_days` ni ningún umbral.
- Propuesta de ventanas por TF para una cola futura, prerregistrada en
  `TL3_REPORTS/robust1_wf_windows.md`; no se aplica en esta cola.
