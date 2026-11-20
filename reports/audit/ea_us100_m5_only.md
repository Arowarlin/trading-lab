# Auditoría M5-only · EA `us100-ftmo1`

Generado: 2026-11-20T02:55:32+00:00 · **solo lectura, sin trials nuevos**

- Caché: `E:\trading-lab\data\cache\ea\US100_CASH_M5_NY.parquet`
- Setfile: `E:\trading-lab\integrations\mt5\us100_ftmo1\US100_FTMO_v3_challenge.set`
- Ventana auditada: **2021-10-01 → 2026-11-13 16:45**
- `count_tests`: **1060** antes y después (sin cambios; 0 escrituras propias en `data/lab.db`)
- Cambios externos en `data/lab.db` durante la ejecución: **ninguno**
- Motor: `ea_us100_engine.py` actual (v3.2, incluye filtro de festivos NYSE)

## 1. Granularidad de la caché

| Segmento | Fechas | Filas | Δ mínimo | Δ máximo | Δ dominante | % 5 min |
|---|---|---|---|---|---|---|
| D1 2017-12-28..2020-12-30 | 2017-12-28 18:00:00 → 2020-12-30 18:00:00 | 777 | 1 days 00:00:00 | 4 days 00:00:00 | 1 days 00:00:00 (616), 3 days 00:00:00 (152), 4 days 00:00:00 (5), 2 days 00:00:00 (3) | 0.0 |
| H1 2021-01-03..2021-09-13 | 2021-01-03 18:00:00 → 2021-09-13 23:00:00 | 3840 | 0 days 01:00:00 | 3 days 00:00:00 | 0 days 01:00:00 (3657), 0 days 02:00:00 (130), 2 days 02:00:00 (33), 1 days 00:00:00 (11), 0 days 06:00:00 (3) | 0.0 |
| M5 2021-09-14..2026-11-13 | 2021-09-14 00:00:00 → 2026-11-13 16:45:00 | 362230 | 0 days 00:05:00 | 3 days 01:20:00 | 0 days 00:05:00 (360872), 0 days 01:20:00 (1018), 2 days 01:20:00 (248), 0 days 05:10:00 (31), 3 days 01:20:00 (8) | 1.0 |

- Duplicados: **0** · OHLC inválidas en M5: **0** · OHLC ausentes en M5: **0**
- En el tramo M5, el **99.6 %** de los saltos son de 5 min; el mínimo es **0 days 00:05:00**. La caché mezcla D1 (2018-2020), H1 (ene-sep 2021) y M5 (desde 2021-09-14). `ea_us100_engine.run` no detecta granularidad.

## 2. Comparación de escenarios

| Escenario | Barras | Días RTH | n_obs | Ops | Win % | PF | Exp R | Total R | DD R | DSR local |
|---|---|---|---|---|---|---|---|---|---|---|
| v3 registrado | 366847 | 1.500 | 1.500 | 480 | 33.8 | 1.45 | +0.298 | +143.2 | -24.8 | 0.999362 |
| Caché mixta completa (motor actual) | 366847 | 1500 | 1500 | 476 | 34.2 | 1.48 | +0.316 | +150.4 | -24.8 | 0.999675 |
| M5 real desde 2021-10-01 | 358708 | 1321 | 1321 | 475 | 34.1 | 1.47 | +0.307 | +145.9 | -24.8 | 0.999481 |
| M5 real desde 2021-09-14, ops desde 2021-10-01 | 362230 | 1321 | 1321 | 472 | 34.1 | 1.47 | +0.311 | +146.9 | -24.8 | 0.999577 |

> El v3 registrado usa el motor anterior al filtro de festivos v3.2; por eso no es directamente comparable con las otras filas. La fila `Caché mixta completa (motor actual)` es la referencia reproducible del motor que corre hoy.

### Operaciones y R por año

| Año | v3 ops | v3 R | full ops | full R | strict ops | strict R | warm ops | warm R |
|---|---|---|---|---|---|---|---|---|
| 2021 | 34 | +4.6 | 34 | +4.6 | 33 | +0.1 | 30 | +1.1 |
| 2022 | 84 | +56.7 | 84 | +56.7 | 84 | +56.7 | 84 | +56.7 |
| 2023 | 94 | +3.5 | 94 | +3.5 | 94 | +3.5 | 94 | +3.5 |
| 2024 | 96 | +28.3 | 96 | +28.3 | 96 | +28.3 | 96 | +28.3 |
| 2025 | 87 | +19.4 | 86 | +23.5 | 86 | +23.5 | 86 | +23.5 |
| 2026 | 85 | +30.8 | 82 | +33.9 | 82 | +33.9 | 82 | +33.9 |

### DD máximo por año (R)

| Año | v3 DD | full DD | strict DD | warm DD |
|---|---|---|---|---|
| 2021 | -7.2 | -7.2 | -7.1 | -7.1 |
| 2022 | -7.0 | -7.0 | -7.0 | -7.0 |
| 2023 | -16.5 | -16.5 | -16.5 | -16.5 |
| 2024 | -10.8 | -10.8 | -10.8 | -10.8 |
| 2025 | -14.1 | -14.1 | -14.1 | -14.1 |
| 2026 | -10.1 | -9.0 | -9.0 | -9.0 |

## 3. Sharpes de las 8 variantes del EA

Las 8 variantes se recalcularon con la misma matriz diaria del DSR local. `strategy_trials` no guardó `sr_period` para estas filas, así que la referencia es el recálculo sobre la caché completa con el motor actual.

| # | RR | gap | consec | SR full | SR strict | Δ strict | SR warmup |
|---|---|---|---|---|---|---|---|
| 0 | 3.00 | 0.5 | 1 | 1.210 | 1.244 | +0.033 | 1.266 |
| 1 | 3.00 | 0.5 | 2 | 1.003 | 1.013 | +0.010 | 1.045 |
| 2 | 3.00 | 0.7 | 1 | 1.327 | 1.367 | +0.040 | 1.379 |
| 3 | 3.00 | 0.7 | 2 | 1.191 | 1.211 | +0.020 | 1.235 |
| 4 | 3.50 | 0.5 | 1 | 1.312 | 1.360 | +0.048 | 1.381 |
| 5 | 3.50 | 0.5 | 2 | 1.076 | 1.099 | +0.022 | 1.129 |
| 6 | 3.50 | 0.7 | 1 | 1.441 | 1.497 | +0.056 | 1.508 |
| 7 | 3.50 | 0.7 | 2 | 1.270 | 1.304 | +0.034 | 1.326 |

- Serie base (`ea_report`, 1 serie): SR anual **1.441** (full) → **1.497** (strict) → **1.508** (warmup). v3 registrado: **1.372**.

## 4. DSR global antes y después

| Escenario | n_obs | SR anual | Series | N trials | DSR global |
|---|---|---|---|---|---|
| Registrado v3 (histórico) | 1500 | 1.372 | 653 | 1042 | 0.634293 |
| v3 reproducido (SR ajustada al v3) | 1500 | 1.372 | 653 | 1042 | 0.634287 |
| Actual antes (motor v3.2, caché mixta) | 1500 | 1.441 | 661 | 1060 | 0.706211 |
| Después strict (M5 desde 2021-10-01) | 1321 | 1.497 | 661 | 1060 | 0.740171 |
| Después warmup (M5 desde 2021-09-14) | 1321 | 1.508 | 661 | 1060 | 0.749774 |
| Sensibilidad strict + 653 series + N=1042 | 1321 | 1.497 | 653 | 1042 | 0.737699 |

### Descomposición del cambio

| Paso | DSR global | Δ |
|---|---|---|
| v3 registrado | 0.634293 | — |
| + filtro de festivos v3.2 (653 series, N=1042) | 0.703417 | +0.069125 |
| + 8 series US500 y N=1060 | 0.706211 | +0.002794 |
| + M5-only strict (661 series, N=1060) | 0.740171 | +0.033959 |

- El v3 registrado (**0.634293**) se reproduce como **0.634287** si se fija la SR de la serie base al valor v3 (Δ -0.000005). La mayor parte de la diferencia con el DSR actual (0.706211) es el filtro de festivos v3.2; la granularidad añade el resto (ver descomposición).
- Reemplazar solo la SR de `ea_report` en la dispersión mueve el global **0.704219** (Δ -0.001992): las otras 32 series US100 son D1 nativas.
- Limpiar la caché y acortar la serie base lleva el global a **0.740171** (strict) o **0.749774** (warmup). Sigue por debajo de 0,90: el gate global falla.

## 5. Trials US100 con ventana anterior a 2021-10-01

| Grupo | Filas | Ventana | TF | counted | ¿Dispersión diaria? | ¿Caché EA? | Acción |
|---|---|---|---|---|---|---|---|
| `CALENDAR` | 4 | 2017-12-28 00:00:00+00:00 → 2026-04-13 00:00:00+00:00 | D1 | 0 | sí | no | D1 nativo construido desde H4 (campaign.py); no usa la caché M5 del EA |
| `CALENDAR` | 4 | 2017-12-28 00:00:00+00:00 → 2024-08-07 00:00:00+00:00 | D1 | 0 | sí | no | D1 nativo construido desde H4 (campaign.py); no usa la caché M5 del EA |
| `ORB_NY` | 8 | 2017-12-28 → 2026-11-11 | — | 1 | no | no | sin timeframe/sr_period: global_srs lo excluye de la dispersión diaria |
| `ST_REVERSAL` | 4 | 2017-12-28 00:00:00+00:00 → 2026-04-13 00:00:00+00:00 | D1 | 0 | sí | no | D1 nativo construido desde H4 (campaign.py); no usa la caché M5 del EA |
| `ST_REVERSAL` | 4 | 2017-12-28 00:00:00+00:00 → 2024-08-07 00:00:00+00:00 | D1 | 0 | sí | no | D1 nativo construido desde H4 (campaign.py); no usa la caché M5 del EA |
| `TREND` | 15 | 2017-12-28 → 2026-11-11 | H4 | 1 | no | no | H4: frecuencia intraday; no entra en la dispersión diaria |
| `TREND_DAILY_ATR` | 2 | 2017-12-28 → 2026-11-12 | — | 0 | no | no | counted=0 y sin sharpe de primer nivel; excluido |
| `TREND_INTRADAY` | 16 | 2017-12-28 → 2026-11-11 | — | 1 | no | no | sin timeframe/sr_period: global_srs lo excluye de la dispersión diaria |
| `TSMOM` | 4 | 2017-12-28 00:00:00+00:00 → 2026-04-13 00:00:00+00:00 | D1 | 0 | sí | no | D1 nativo construido desde H4 (campaign.py); no usa la caché M5 del EA |
| `TSMOM` | 4 | 2017-12-28 00:00:00+00:00 → 2024-08-07 00:00:00+00:00 | D1 | 0 | sí | no | D1 nativo construido desde H4 (campaign.py); no usa la caché M5 del EA |
| `US100_FTMO_CONFLUENCE` | 8 | 2021-09-15 → 2026-11-13 | M5 | 1 | no | sí | 8 variantes M5 del EA; SR recalculados en la auditoría |
| `US100_FTMO_CONFLUENCE` | 2 | 2021-09-15 → 2026-11-13 | M5 | 0 | no | sí | resumen/informe de robustez; no añade una serie al DSR |
| `US100_FTMO_CONFLUENCE` | 1 | 2021-09-15 → 2026-11-13 | M5 | 1 | no | sí | resumen/informe de robustez; no añade una serie al DSR |
| `VOL_BREAKOUT` | 4 | 2017-12-28 00:00:00+00:00 → 2026-04-13 00:00:00+00:00 | D1 | 0 | sí | no | D1 nativo construido desde H4 (campaign.py); no usa la caché M5 del EA |
| `VOL_BREAKOUT` | 4 | 2017-12-28 00:00:00+00:00 → 2024-08-07 00:00:00+00:00 | D1 | 0 | sí | no | D1 nativo construido desde H4 (campaign.py); no usa la caché M5 del EA |
| `ea_report` | 1 | 2017-12-28 → 2026-11-13 | M5 mixta | — | sí | sí | SR recalculado; única serie US100 de la dispersión que usa la caché mixta |

- Filas US100 con ventana anterior a 2021-10-01: **84**; en la dispersión diaria: **33**; recalculadas sobre M5: **9**.
- Las 32 celdas `campaign` D1 se construyen desde H4 (`campaign.py`), no desde la caché M5 del EA. Las filas `ORB_NY`/`TREND_INTRADAY`/`TREND` H4 no entran en la dispersión diaria por falta de `timeframe`/`sr_period` o por ser H4.

## 6. Conclusiones

1. **La caché no es M5 homogénea.** 2018-2020 son D1, enero-septiembre 2021 son H1 y el M5 real empieza el 2021-09-14. El motor no detecta granularidad; las velas D1/H1 se procesan como si fueran M5.
2. **El DSR local no cambia de conclusión.** 0,999362 (v3) → 0,999481 (strict) → 0,999577 (warmup). Sigue aprobando el criterio informativo local.
3. **El total R cambia poco.** v3 +143,2 R; motor actual full +150,4 R; strict +145,9 R; warmup +146,9 R. Entre full, strict y warmup, 2022-2025 son idénticos; el año 2021 es el sensible al corte del 2021-10-01 (+4,6 R → +0,1 R) y 2026 coincide al mismo corte. La diferencia v3 vs full en 2025-2026 son las 4 operaciones de festivos que filtra v3.2.
4. **El DSR global sigue fallando.** Actual 0,706211 → strict 0,740171 → warmup 0,749774, todos < 0,90. El 0,634293 registrado se reproduce exactamente (0,634287) fijando la SR v3; la diferencia es el filtro de festivos v3.2, no la granularidad.
5. **Solo 1 de las 33 series US100 diarias usa la caché mixta.** Las 32 `campaign` D1 son nativas. Los trials `ORB_NY`/`TREND_INTRADAY`/`TREND` H4 no entran en la dispersión diaria. Por eso reemplazar los Sharpes US100 apenas mueve el global (−0,002): el cambio viene de la serie base, no de la dispersión.
6. **Veredicto:** la auditoría no rescata el EA. El gate global sigue fallando y el local sigue aprobando; la conclusión `NO PASA` se mantiene.

## Aviso

- El motor actual ya no reproduce el v3 registrado (480 ops, +143,2 R, 0,634293): el filtro de festivos v3.2 elimina 4 operaciones y sube la SR. La comparación limpia es contra la fila `Caché mixta completa (motor actual)`.
- No se ha ejecutado `lab campaign run`, `research`, `research-intraday` ni `research-swing`; no se ha insertado nada en `strategy_trials`, `optimization_trials`, `holdout_reads` ni `campaign_registry`.
- Todas las conexiones a `data/lab.db` son `mode=ro` con `PRAGMA query_only=ON`; `total_changes=0` en cada una. `count_tests` sigue en **1060** y las tablas auditadas no cambiaron. Si el SHA-256 del archivo cambió, fue por un proceso externo (se registra arriba).
