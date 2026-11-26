# Motor flat_mode · inventario de campañas afectadas

- Fecha: 2026-11-26.
- Base: `E:\trading-lab\data\discovery.db` (solo lectura).
- Campañas totales: **64**; afectadas con `legacy`: **52**.
- De las afectadas: **48** son de 24 h (varios días por diseño) y **4** son intradía con TF no alineado (fallo real).
- No se ha modificado ninguna campaña, estrategia ni plantilla.

## Por plantilla y TF

| Plantilla | TF | Campañas |
|---|---|---|
| d1_extension_reversion | D1 | 2 |
| donchian_vol_h4 | H4 | 6 |
| fix_reversal | H1 | 5 |
| st_reversal_idx | H1 | 2 |
| st_reversal_idx | M15 | 1 |
| st_reversal_idx | M30 | 1 |
| trend_pullback_mtf | H1 | 6 |
| trend_pullback_mtf | H4 | 6 |
| trend_pullback_mtf | M15 | 2 |
| trend_pullback_mtf | M30 | 2 |
| turn_of_month | D1 | 4 |
| vol_squeeze_breakout | H1 | 5 |
| vol_squeeze_breakout | H4 | 6 |
| vol_squeeze_breakout | M15 | 2 |
| vol_squeeze_breakout | M30 | 2 |

## Campañas afectadas

| Campaña | Activo | TF | Plantilla | Estado | Sesión | flat_at | Tipo |
|---|---|---|---|---|---|---|---|
| n2-donchian-xauusd-h4 | XAUUSD | H4 | donchian_vol_h4 | done | 00:00-23:59 | 23:59 | 24 h |
| n2-donchian-usdjpy-h4 | USDJPY | H4 | donchian_vol_h4 | done | 00:00-23:59 | 23:59 | 24 h |
| q2-fix-usdjpy-h1 | USDJPY | H1 | fix_reversal | done | 00:00-23:59 | 23:59 | 24 h |
| q2-fix-eurusd-h1 | EURUSD | H1 | fix_reversal | done | 00:00-23:59 | 23:59 | 24 h |
| q2-fix-gbpusd-h1 | GBPUSD | H1 | fix_reversal | done | 00:00-23:59 | 23:59 | 24 h |
| r9-tom-us500-d1 | US500 | D1 | turn_of_month | done | 00:00-23:59 | 23:59 | 24 h |
| r9-tom-us100-d1 | US100 | D1 | turn_of_month | done | 00:00-23:59 | 23:59 | 24 h |
| q1-rebote-us500-d1 | US500 | D1 | d1_extension_reversion | done | 00:00-23:59 | 23:59 | 24 h |
| q1-rebote-us100-d1 | US100 | D1 | d1_extension_reversion | done | 00:00-23:59 | 23:59 | 24 h |
| r9b-tom-us500-d1 | US500 | D1 | turn_of_month | done | 00:00-23:59 | 23:59 | 24 h |
| r9b-tom-us100-d1 | US100 | D1 | turn_of_month | done | 00:00-23:59 | 23:59 | 24 h |
| v2-fix-londres-eurgbp-h1 | EURUSD | H1 | fix_reversal | done | 00:00-23:59 | 23:59 | 24 h |
| edge1-01-trend-pullback-mtf-usdjpy-h4 | USDJPY | H4 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-02-vol-squeeze-breako-usdjpy-h4 | USDJPY | H4 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-03-donchian-vol-h4-eurusd-h4 | EURUSD | H4 | donchian_vol_h4 | done | 00:00-23:59 | 23:59 | 24 h |
| edge1-04-trend-pullback-mtf-eurusd-h4 | EURUSD | H4 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-05-vol-squeeze-breako-eurusd-h4 | EURUSD | H4 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-06-donchian-vol-h4-gbpusd-h4 | GBPUSD | H4 | donchian_vol_h4 | done | 00:00-23:59 | 23:59 | 24 h |
| edge1-07-trend-pullback-mtf-gbpusd-h4 | GBPUSD | H4 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-08-vol-squeeze-breako-gbpusd-h4 | GBPUSD | H4 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-09-trend-pullback-mtf-xauusd-h4 | XAUUSD | H4 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-10-vol-squeeze-breako-xauusd-h4 | XAUUSD | H4 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-11-trend-pullback-mtf-usdjpy-h1 | USDJPY | H1 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-12-vol-squeeze-breako-usdjpy-h1 | USDJPY | H1 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-13-fix-reversal-xauusd-h1 | XAUUSD | H1 | fix_reversal | draft | 00:00-23:59 | 23:59 | 24 h |
| edge1-15-trend-pullback-mtf-eurusd-h1 | EURUSD | H1 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-16-vol-squeeze-breako-eurusd-h1 | EURUSD | H1 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-18-trend-pullback-mtf-gbpusd-h1 | GBPUSD | H1 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-19-vol-squeeze-breako-gbpusd-h1 | GBPUSD | H1 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-22-trend-pullback-mtf-usdjpy-m30 | USDJPY | M30 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-23-vol-squeeze-breako-usdjpy-m30 | USDJPY | M30 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-25-trend-pullback-mtf-xauusd-h1 | XAUUSD | H1 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-27-trend-pullback-mtf-usdjpy-m15 | USDJPY | M15 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge1-28-vol-squeeze-breako-usdjpy-m15 | USDJPY | M15 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge2-13-st-reversal-idx-us100-m30 | US100 | M30 | st_reversal_idx | draft | 09:35-15:55 | 15:55 | intradía |
| edge2-14-trend-pullback-mtf-us100-m30 | US100 | M30 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge2-15-vol-squeeze-breako-us100-m30 | US100 | M30 | vol_squeeze_breakout | draft | 00:00-23:59 | 23:55 | 24 h |
| edge2-16-st-reversal-idx-us100-m15 | US100 | M15 | st_reversal_idx | draft | 09:35-15:55 | 15:55 | intradía |
| edge2-17-trend-pullback-mtf-us100-m15 | US100 | M15 | trend_pullback_mtf | draft | 00:00-23:59 | 23:55 | 24 h |
| edge2-18-vol-squeeze-breako-us100-m15 | US100 | M15 | vol_squeeze_breakout | draft | 00:00-23:59 | 23:55 | 24 h |
| edge2-01-donchian-vol-h4-us100-h4 | US100 | H4 | donchian_vol_h4 | done | 00:00-23:59 | 23:59 | 24 h |
| edge2-02-trend-pullback-mtf-us100-h4 | US100 | H4 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge2-03-vol-squeeze-breako-us100-h4 | US100 | H4 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge2-04-st-reversal-idx-us100-h1 | US100 | H1 | st_reversal_idx | done | 09:35-15:55 | 15:55 | intradía |
| edge2-05-trend-pullback-mtf-us100-h1 | US100 | H1 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge2-06-vol-squeeze-breako-us100-h1 | US100 | H1 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge2-07-donchian-vol-h4-us500-h4 | US500 | H4 | donchian_vol_h4 | done | 00:00-23:59 | 23:59 | 24 h |
| edge2-08-trend-pullback-mtf-us500-h4 | US500 | H4 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge2-09-vol-squeeze-breako-us500-h4 | US500 | H4 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |
| edge2-10-st-reversal-idx-us500-h1 | US500 | H1 | st_reversal_idx | draft | 09:35-15:55 | 15:55 | intradía |
| edge2-11-trend-pullback-mtf-us500-h1 | US500 | H1 | trend_pullback_mtf | done | 00:00-23:59 | 23:55 | 24 h |
| edge2-12-vol-squeeze-breako-us500-h1 | US500 | H1 | vol_squeeze_breakout | done | 00:00-23:59 | 23:55 | 24 h |

## EDGE-1 · finalistas

Finalistas EDGE-1: **22**. Con `legacy`: **21** mantienen varios días y **1** son intradía correctos.

| Campaña | ID | Activo | TF | Plantilla | Veredicto | Lectura |
|---|---|---|---|---|---|---|
| edge1-01-trend-pullback-mtf-usdjpy-h4 | 936 | USDJPY | H4 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-01-trend-pullback-mtf-usdjpy-h4 | 1038 | USDJPY | H4 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-02-vol-squeeze-breako-usdjpy-h4 | 1348 | USDJPY | H4 | vol_squeeze_breakout | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-05-vol-squeeze-breako-eurusd-h4 | 2801 | EURUSD | H4 | vol_squeeze_breakout | FRÁGIL | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-06-donchian-vol-h4-gbpusd-h4 | 3228 | GBPUSD | H4 | donchian_vol_h4 | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-07-trend-pullback-mtf-gbpusd-h4 | 3583 | GBPUSD | H4 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-07-trend-pullback-mtf-gbpusd-h4 | 3585 | GBPUSD | H4 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-07-trend-pullback-mtf-gbpusd-h4 | 3625 | GBPUSD | H4 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-07-trend-pullback-mtf-gbpusd-h4 | 3669 | GBPUSD | H4 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-07-trend-pullback-mtf-gbpusd-h4 | 3675 | GBPUSD | H4 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-08-vol-squeeze-breako-gbpusd-h4 | 4114 | GBPUSD | H4 | vol_squeeze_breakout | FRÁGIL | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-11-trend-pullback-mtf-usdjpy-h1 | 5178 | USDJPY | H1 | trend_pullback_mtf | FRÁGIL | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-11-trend-pullback-mtf-usdjpy-h1 | 5309 | USDJPY | H1 | trend_pullback_mtf | FRÁGIL | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-11-trend-pullback-mtf-usdjpy-h1 | 5385 | USDJPY | H1 | trend_pullback_mtf | FRÁGIL | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-12-vol-squeeze-breako-usdjpy-h1 | 5566 | USDJPY | H1 | vol_squeeze_breakout | FRÁGIL | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-12-vol-squeeze-breako-usdjpy-h1 | 5775 | USDJPY | H1 | vol_squeeze_breakout | FRÁGIL | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-12-vol-squeeze-breako-usdjpy-h1 | 5854 | USDJPY | H1 | vol_squeeze_breakout | FRÁGIL | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-18-trend-pullback-mtf-gbpusd-h1 | 7855 | GBPUSD | H1 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-18-trend-pullback-mtf-gbpusd-h1 | 7966 | GBPUSD | H1 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-18-trend-pullback-mtf-gbpusd-h1 | 8011 | GBPUSD | H1 | trend_pullback_mtf | SOBREAJUSTADA | mantiene varios días (swap; revisar las reglas de fin de semana) |
| edge1-21-asia-range-reversi-usdjpy-m30 | 9111 | USDJPY | M30 | asia_range_reversion | FRÁGIL | intradía correcto |
| edge1-22-trend-pullback-mtf-usdjpy-m30 | 9611 | USDJPY | M30 | trend_pullback_mtf | FRÁGIL | mantiene varios días (swap; revisar las reglas de fin de semana) |

## EDGE-1 · EAs exportados

**Sin datos**: `exports/edge1/` no contiene EAs exportados.

## Lectura

- Las plantillas de 24 h (`trend_pullback_mtf`, `vol_squeeze_breakout`, `donchian_vol_h4`, `fix_reversal`, `turn_of_month`, `d1_extension_reversion`) conservan `legacy`: su `flat_at` no dispara en TF ≥ M15 y por diseño mantienen posiciones varios días (con swap).
- `st_reversal_idx` en M15/M30/H1 es un fallo real de sesión intradía: la posición puede dormir. La plantilla nueva `_v3` usa `no_overnight`; las campañas ya registradas no se tocan.
- EDGE-1 no dejó EAs en `exports/edge1/`; no se inventan ficheros.
