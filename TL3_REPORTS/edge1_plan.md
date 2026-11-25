# EDGE-1 X1 - plan de campanas congelado

**Congelado:** 2026-11-25T23:04:30.081083+00:00
**Hash del plan:** `8026de6dc2407ff8f56a6ebb09078be8e547dc0649f0e33346c29371abc5c509`
**Campanas:** 28 · **n_total esperado:** 12,320

## 1. Reglas congeladas

- Fuente unica: `dukascopy`; perfil `small`; modo `ga`; semilla = indice de la matriz.
- Coste: `--cost-account CFD-001 --cost-account CFD-006 --cost-mode worst`.
- IS: `max(2012-01-01, inicio util, usable_from)` por activo/TF (excepcion congelada).
- OOS-1: `2020-01-01:2022-12-31`; OOS-2: `2023-01-01:` (sellado).
- Matriz: combinaciones que la plantilla admite, X0.4 viable (`cost_r <= 0,10`) y sin campana previa con la misma terna.
- Cobertura: 1 por plantilla nueva viable, 1 por activo permitido, >=3 por TF; el resto por menor `cost_r`.

## 2. Activos bloqueados en X0

- **US100**: swap CFD-001 6,24 bps/noche > 5 (coste fuera de magnitud).
- **US30**: spread Sin datos en CFD-001 y CFD-006.
- **US500**: CFD-001 no permite US500; la regla de dos cuentas (CFD-001 + CFD-006) lo excluye.
- **`st_reversal_idx`**: sin combinacion viable (US500 M30 cost_r 0,1088 > 0,10); plantilla creada, sin campana.

## 3. Matriz

| # | Campana | Plantilla | Activo | TF | Semilla | IS | OOS-1 | cost_r |
|---:|---|---|---|---|---:|---|---|---:|
| 1 | `edge1-01-trend-pullback-mtf-usdjpy-h4` | trend_pullback_mtf | USDJPY | H4 | 1 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0121 |
| 2 | `edge1-02-vol-squeeze-breako-usdjpy-h4` | vol_squeeze_breakout | USDJPY | H4 | 2 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0121 |
| 3 | `edge1-03-donchian-vol-h4-eurusd-h4` | donchian_vol_h4 | EURUSD | H4 | 3 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0127 |
| 4 | `edge1-04-trend-pullback-mtf-eurusd-h4` | trend_pullback_mtf | EURUSD | H4 | 4 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0127 |
| 5 | `edge1-05-vol-squeeze-breako-eurusd-h4` | vol_squeeze_breakout | EURUSD | H4 | 5 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0127 |
| 6 | `edge1-06-donchian-vol-h4-gbpusd-h4` | donchian_vol_h4 | GBPUSD | H4 | 6 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0139 |
| 7 | `edge1-07-trend-pullback-mtf-gbpusd-h4` | trend_pullback_mtf | GBPUSD | H4 | 7 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0139 |
| 8 | `edge1-08-vol-squeeze-breako-gbpusd-h4` | vol_squeeze_breakout | GBPUSD | H4 | 8 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0139 |
| 9 | `edge1-09-trend-pullback-mtf-xauusd-h4` | trend_pullback_mtf | XAUUSD | H4 | 9 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0185 |
| 10 | `edge1-10-vol-squeeze-breako-xauusd-h4` | vol_squeeze_breakout | XAUUSD | H4 | 10 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0185 |
| 11 | `edge1-11-trend-pullback-mtf-usdjpy-h1` | trend_pullback_mtf | USDJPY | H1 | 11 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0256 |
| 12 | `edge1-12-vol-squeeze-breako-usdjpy-h1` | vol_squeeze_breakout | USDJPY | H1 | 12 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0256 |
| 13 | `edge1-13-fix-reversal-xauusd-h1` | fix_reversal | XAUUSD | H1 | 13 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0261 |
| 14 | `edge1-14-asia-range-reversi-eurusd-h1` | asia_range_reversion | EURUSD | H1 | 14 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0271 |
| 15 | `edge1-15-trend-pullback-mtf-eurusd-h1` | trend_pullback_mtf | EURUSD | H1 | 15 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0271 |
| 16 | `edge1-16-vol-squeeze-breako-eurusd-h1` | vol_squeeze_breakout | EURUSD | H1 | 16 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0271 |
| 17 | `edge1-17-asia-range-reversi-gbpusd-h1` | asia_range_reversion | GBPUSD | H1 | 17 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0294 |
| 18 | `edge1-18-trend-pullback-mtf-gbpusd-h1` | trend_pullback_mtf | GBPUSD | H1 | 18 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0294 |
| 19 | `edge1-19-vol-squeeze-breako-gbpusd-h1` | vol_squeeze_breakout | GBPUSD | H1 | 19 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0294 |
| 20 | `edge1-20-london-breakout-eurusd-h1` | london_breakout | EURUSD | H1 | 20 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0361 |
| 21 | `edge1-21-asia-range-reversi-usdjpy-m30` | asia_range_reversion | USDJPY | M30 | 21 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0374 |
| 22 | `edge1-22-trend-pullback-mtf-usdjpy-m30` | trend_pullback_mtf | USDJPY | M30 | 22 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0374 |
| 23 | `edge1-23-vol-squeeze-breako-usdjpy-m30` | vol_squeeze_breakout | USDJPY | M30 | 23 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0374 |
| 24 | `edge1-24-asia-range-reversi-xauusd-h1` | asia_range_reversion | XAUUSD | H1 | 24 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0391 |
| 25 | `edge1-25-trend-pullback-mtf-xauusd-h1` | trend_pullback_mtf | XAUUSD | H1 | 25 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0391 |
| 26 | `edge1-26-asia-range-reversi-usdjpy-m15` | asia_range_reversion | USDJPY | M15 | 26 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0548 |
| 27 | `edge1-27-trend-pullback-mtf-usdjpy-m15` | trend_pullback_mtf | USDJPY | M15 | 27 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0548 |
| 28 | `edge1-28-vol-squeeze-breako-usdjpy-m15` | vol_squeeze_breakout | USDJPY | M15 | 28 | 2012-01-01:2019-12-31 | 2020-01-01:2022-12-31 | 0.0548 |

**Suma n_total:** 12,320 (28 x 440).

## 4. Reparto

- Por TF: {'H1': 12, 'H4': 10, 'M15': 3, 'M30': 3}
- Por activo: {'EURUSD': 7, 'GBPUSD': 6, 'USDJPY': 10, 'XAUUSD': 5}
- Por plantilla: {'asia_range_reversion': 5, 'donchian_vol_h4': 2, 'fix_reversal': 1, 'london_breakout': 1, 'trend_pullback_mtf': 10, 'vol_squeeze_breakout': 9}

## 5. Pasada 2 (regla fijada ahora)

Se repiten con perfil `medium` y semilla nueva (`1000 + indice`) las campanas de la pasada 1 con al menos 1 finalista que paso X3 completo. Maximo 6, por orden de mas finalistas que pasaron y, a igualdad, menor `cost_r`. Se registran antes de ejecutar y sus finalistas pasan por X3. Si ninguna cumple, X4 = `sin pasada 2`.

## 6. Confirmacion OOS-2

Una sola lectura por finalista que pase las 4 puertas de COLA-EDGE-1 §4. Las plantillas de apertura NY en indices quedan marcadas `a forward, OOS-2 no valido`; en esta matriz no hay ninguna campana de esas plantillas.

## 7. Contaminacion declarada

US100/US500/US30 ORB (`ny_open_vol_filter`, `session_breakout_htf` y cualquier ORB) tienen el OOS-2 dentro del diseno del EA `us100-ftmo1`. En esta matriz no se registran esas plantillas.

## 8. Registro

- Dry-run: **28/28 OK** (`TL3_REPORTS/edge1_register_dry.log`).
- Registro real: **28/28 `draft`** (`TL3_REPORTS/edge1_register_real.log`); suma `n_total` en `disc_campaigns` = **12.320**.
- Dataset por activo/TF verificado en el registro; calidad `warn` en 20 campanas (huecos ya anotados en X0) y `ok` en 8. Ninguna `fail`.

