# Calidad de datos · auditoría del 2026-11-25

Generado con `tools/phase_b.py` (solo lectura). Resultados completos en
`phase_b_results.json`.

La auditoría de calidad (conteos, huecos, duplicados) recorre todo el rango. No
mira precios ni retornos del tramo sellado.

## 1. Resumen

| Serie | Filas | Rango (ET) | Duplicados | OHLC incoherente | Precio ≤ 0 | Sesiones RTH | Completas (≥ 380 barras, sin cierre corto) |
|---|---:|---|---:|---:|---:|---:|---:|
| NQ CME (Databento `NQ.c.0`) | 2.720.203 | 2010-06-06 20:00 → 2018-12-31 16:59 | 0 | 0 | 0 | 2.160 | 2.080 |
| Dukascopy USA100 | 4.275.591 | 2011-09-18 17:53 → 2026-11-20 16:14 | 0 | 0 | 0 | 3.752 | 3.434 |

## 2. Hallazgos

1. **Alineación horaria correcta en NQ.**
   - Volumen mediano por barra de 9:30–9:34 ET: 1.596 con horario de verano y 1.529 en horario estándar.
   - A las 10:00–10:04: 879 y 833.
   - El pico de la apertura cae en las 9:30 ET en los dos regímenes de DST, así que el índice UTC y la etiqueta "hora de apertura de la barra" son correctos.
2. **Dukascopy no tiene volumen útil.**
   - Su "volumen" es tick volume fraccional, sin pico en la apertura (0,162 frente a 0,141).
   - VWAP, RVOL y el perfil calculados con él son, en la práctica, promedios temporales.
   - Consecuencia: el modelo E y el filtro RVOL **solo** con NQ.
3. **Dukascopy no tiene ask.**
   - Las columnas `ask_*` están vacías en el 100 % de las filas, en todos los años.
   - El informe R2g del laboratorio la trató como serie bid+ask; en esta caché solo hay bid.
   - El spread de Dukascopy queda como **Sin datos** y los costes de US100 tendrán que salir del bróker (MT5).
4. **Sesiones parciales en Dukascopy 2013–2014.**
   - 74 y 95 sesiones con menos de 380 barras en RTH (frente a 0–10 en los demás años).
   - Se excluyen. Ese tramo tiene menos muestra efectiva.
5. **Huecos de más de 5 min dentro de Globex en NQ.**
   - Entre 800 y 1.150 por año en 2010–2015; 104 en 2018.
   - Son minutos nocturnos sin operaciones: el feed no emite barra si no hay trades.
   - En RTH, en sesiones completas, falta < 0,12 % de minutos en todos los años.
   - No afecta a ONH/ONL: un minuto sin trade no tiene precio que pueda ser un extremo.
6. **Medias sesiones:** 3–10 por año en las dos series. Se excluyen de las descriptivas.
7. **Rolls de NQ.c.0.**
   - La caché no trae `instrument_id`.
   - Se detectan 58 sesiones candidatas por salto a las 18:00 ET en meses de vencimiento. Algunas son festivos o gaps de noticias, no rolls.
   - Política adoptada:
     - excluir la ventana fija de cada trimestre (3er viernes −9 días → +1 día);
     - excluir también los días con salto detectado (más 3 días);
     - no usar PDH/PDL cuando la víspera está excluida.
   - Resultado: 1.733 sesiones NQ útiles en DEV de 2.080 completas.
8. **Contaminación declarada.** Las familias A–F son componentes de confluencia del EA `us100-ftmo1` (`src/tradinglab/ea_us100_engine.py`):

   | EA `us100-ftmo1` | Familia de este proyecto |
   |---|---|
   | `trade_start=935`, `trade_end=1130` | misma ventana de entrada (9:35–11:30 ET) |
   | `or_end=945`, modo `ORB_RETEST`, `fb_window=6` | A · NY Open Breakout (retest en ≤ 6 velas) |
   | `use_pd` / `use_on`, `sweep_window=12` | B · Liquidity Sweep |
   | `vwap_ext_sd=2.0` | C · VWAP ± 2σ |
   | FVG con `htf_min=15` | D · Displacement + FVG |
   | RVOL, `rr=2.0`, BE a 1R | E/F y reglas comunes |
   | SL primero si SL y TP caen en la misma barra | regla común de ejecución |

   Usos previos de la historia:
   - NQ 2010–2017 con el EA: `reports/ea/us100-ftmo1-nq-2010-2017.md`.
   - Dukascopy 2012–2021 con T7: `TL3_REPORTS/ea_oop_dukascopy.md`; **no confirma**.
   - US100 2021–2026: periodo de diseño del EA.

   **OOS-1 y OOS-2 no son fuera de muestra para estas familias.**

9. **Fase C histórica: ejecutada y registrada, contaminada.** La Fase C **sí se ejecutó** en `03_BACKTEST` (16:43-16:51) y el operador la **registró** en `informal_trials` (fila 7, n=22; fila 6, n=7). Esos resultados históricos están **contaminados por el EA** `us100-ftmo1` (ver §2.8 y `COLA-NQEDGE-FORWARD §1`, bloque F1): no son una prueba limpia ni fuera de muestra. El forward NQF-A/B/C sigue siendo el prerregistrado, sin cambios.

## 3. Cobertura por año (sesiones RTH completas)

| Año | NQ | Dukascopy |
|---|---:|---:|
| 2010 | 140 | — |
| 2011 | 244 | 3 |
| 2012 | 238 | 226 |
| 2013 | 239 | 103 |
| 2014 | 237 | 152 |
| 2015 | 246 | 244 |
| 2016 | 247 | 250 |
| 2017 | 245 | 249 |
| 2018 | 244 | 246 |
| 2019 | — | 249 |
| 2020 | — | 247 |
| 2021 | — | 251 |
| 2022–2023 (OOS-1) | — | 497 |
| 2024–2026 (sellado) | — | 717 |

## 4. Calendario de noticias histórico

`news_calendar_history.csv`: 1.408 eventos, 2010–2026.

- **Primer intento descartado:** `release/dates` de FRED mezcla fechas de
  revisión.
  - El CPI salía con 13 fechas al año (revisión estacional de febrero).
  - "FOMC Press Release" daba 250 fechas al año.
- **Método final:** primera publicación ALFRED (`output_type=4`) de CPIAUCSL,
  PAYEMS, PPIFIS/PPIFGS, PCE, GDP, RSAFS y JTSJOL, más fechas FOMC de
  federalreserve.gov (`fomc_dates.csv`).
- **Resultado:** 12 al año en series mensuales, 4 en GDP avance y 8 en FOMC.
  2020 tiene 9 FOMC: 2 extraordinarias y la de marzo cancelada.
- **ISM y Jobless Claims no están** (no hay fuente oficial abierta leída).
  Quedan fuera del estudio de eventos.
