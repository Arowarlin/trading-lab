# RESULTADO · R2j-b — calendario completo, tramos y usable_from

Fecha: 2026-11-22. Sin campañas, sin OOS, sin push. Sin tocar umbrales numéricos
(`gap_factor`, `max_gap_hours`, `fail_if_gap_pct_gt`, densidad 50 %, estabilidad 60 %).

## Hecho

- Sin sesión configurada, `_calendar_gap` y la ruta intraday usan
  `discovery/calendars.py` (2003-2030, festivos + cierres especiales) y ya no
  `nyse_calendar` (2021-2027). Los cierres tempranos solo excusan lo posterior a
  las 13:00 NY; un hueco de mañana cuenta.
- `derive-sessions` escribe un tramo por bloque de años consecutivos estables con
  valores idénticos. Un año inestable corta el bloque y queda sin tramo; una pausa
  no estable no se hereda del vecino. Las 14 claves están en `engine.yaml`.
- Nuevo `lab discovery usable-from [--write]`: calcula por fuente:símbolo:TF la
  primera fecha con todos los años cubiertos por tramo o sin huecos reales y cuyo
  data-check recortado no es FAIL. `--write` lo guarda en
  `data_quality.usable_from`.
- `campaigns.register` rechaza una campaña nueva cuyo `is` empiece antes de
  `usable_from`; `supersede` no aplica la regla para no tocar campañas ya
  registradas.
- Commit `8a121d0` · `tl2: R2j-b - calendario completo, tramos y usable_from`.
- Tag `tl2-r2j-b`.

## 1. Calendario completo también sin sesión

- NYSE 2021-2027: `nyse_holidays` y `nyse_early_closes` siguen coincidiendo
  exactamente con `nyse_calendar.FULL_HOLIDAYS`/`EARLY_CLOSES` (test de regresión).
- Los cierres especiales salen del calendario nuevo: Reagan, Ford, Sandy, Bush y
  Carter. El 2025-01-09 (Carter) pasa a programado; Dukascopy tiene barras ese día,
  pero el hueco H1 de las 10:00 deja de contar. Es un cierre real, no una regresión.
- `US500 D1` 2019-04-18 (Viernes Santo) pasa a programado; antes no se reconocía
  porque `nyse_calendar` solo cubre 2021-2027.
- Cierre temprano: un hueco de la mañana del 3-jul, Black Friday o 24-dic cuenta;
  solo lo posterior a las 13:00 es programado. Esto añade 9 huecos reales nuevos
  que antes se ocultaban al tratar el día entero como festivo (detalle en §5).

## 2. Sesiones por tramos

YAML generado de las 14 claves, tal cual:

```yaml
"dukascopy:US100":
    segments:
      - start: "2015-01-01"
        end: "2015-12-31"
        friday_close: "16:00"
        sunday_open: "18:00"
        pause_start: null
        pause_end: null
        short_close: "13:00"
      - start: "2018-01-01"
        end: "2023-12-31"
        friday_close: "16:15"
        sunday_open: "18:00"
        pause_start: "16:15"
        pause_end: "18:00"
        short_close: null
      - start: "2024-01-01"
        end: "2025-12-31"
        friday_close: "16:15"
        sunday_open: "18:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2026-01-01"
        end: "2026-12-31"
        friday_close: "16:15"
        sunday_open: "18:00"
        pause_start: "16:15"
        pause_end: "18:00"
        short_close: null
  "dukascopy:US500":
    segments:
      - start: "2015-01-01"
        end: "2015-12-31"
        friday_close: "16:00"
        sunday_open: "18:00"
        pause_start: null
        pause_end: null
        short_close: "13:00"
      - start: "2018-01-01"
        end: "2026-12-31"
        friday_close: "16:15"
        sunday_open: "18:00"
        pause_start: "16:15"
        pause_end: "18:00"
        short_close: null
  "dukascopy:US30":
    segments:
      - start: "2013-01-01"
        end: "2013-12-31"
        friday_close: "17:00"
        sunday_open: "19:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2015-01-01"
        end: "2015-12-31"
        friday_close: "16:00"
        sunday_open: "18:00"
        pause_start: "16:15"
        pause_end: "16:30"
        short_close: "13:00"
      - start: "2018-01-01"
        end: "2026-12-31"
        friday_close: "16:15"
        sunday_open: "18:00"
        pause_start: "16:15"
        pause_end: "18:00"
        short_close: null
  "dukascopy:XAUUSD":
    segments:
      - start: "2005-01-01"
        end: "2012-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2013-01-01"
        end: "2026-12-31"
        friday_close: "17:00"
        sunday_open: "18:00"
        pause_start: "17:00"
        pause_end: "18:00"
        short_close: null
  "dukascopy:EURUSD":
    segments:
      - start: "2003-01-01"
        end: "2018-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2019-01-01"
        end: "2019-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: "17:00"
        pause_end: "18:00"
        short_close: null
      - start: "2020-01-01"
        end: "2024-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2025-01-01"
        end: "2025-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: "17:10"
        pause_end: "17:25"
        short_close: null
      - start: "2026-01-01"
        end: "2026-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
  "dukascopy:GBPUSD":
    segments:
      - start: "2003-01-01"
        end: "2010-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2011-01-01"
        end: "2011-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: "17:05"
        pause_end: "17:20"
        short_close: null
      - start: "2012-01-01"
        end: "2017-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2018-01-01"
        end: "2018-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: "17:30"
        pause_end: "18:15"
        short_close: null
      - start: "2019-01-01"
        end: "2019-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: "17:00"
        pause_end: "18:00"
        short_close: null
      - start: "2020-01-01"
        end: "2026-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
  "dukascopy:USDJPY":
    segments:
      - start: "2003-01-01"
        end: "2011-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2012-01-01"
        end: "2012-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: "17:20"
        pause_end: "17:50"
        short_close: null
      - start: "2013-01-01"
        end: "2018-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2019-01-01"
        end: "2019-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: "17:00"
        pause_end: "18:00"
        short_close: null
      - start: "2020-01-01"
        end: "2020-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
      - start: "2021-01-01"
        end: "2021-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: "17:15"
        pause_end: "17:25"
        short_close: null
      - start: "2022-01-01"
        end: "2026-12-31"
        friday_close: "17:00"
        sunday_open: "17:00"
        pause_start: null
        pause_end: null
        short_close: null
  "broker:US100":
    segments:
      - start: "2022-01-01"
        end: "2026-12-31"
        friday_close: "16:50"
        sunday_open: "18:00"
        pause_start: "16:50"
        pause_end: "18:05"
        short_close: null
  "broker:US500":
    segments:
      - start: "2022-01-01"
        end: "2026-12-31"
        friday_close: "16:50"
        sunday_open: "18:00"
        pause_start: "16:50"
        pause_end: "18:05"
        short_close: null
  "broker:US30":
    segments:
      - start: "2022-01-01"
        end: "2026-12-31"
        friday_close: "16:50"
        sunday_open: "18:00"
        pause_start: "16:50"
        pause_end: "18:05"
        short_close: null
  "broker:XAUUSD":
    segments:
      - start: "2022-01-01"
        end: "2026-12-31"
        friday_close: "16:50"
        sunday_open: "18:00"
        pause_start: "16:50"
        pause_end: "18:05"
        short_close: null
  "broker:EURUSD":
    segments:
      - start: "2022-01-01"
        end: "2026-12-31"
        friday_close: "16:55"
        sunday_open: "17:00"
        pause_start: "16:55"
        pause_end: "17:05"
        short_close: null
  "broker:GBPUSD":
    segments:
      - start: "2022-01-01"
        end: "2026-12-31"
        friday_close: "16:55"
        sunday_open: "17:00"
        pause_start: "16:55"
        pause_end: "17:05"
        short_close: null
  "broker:USDJPY":
    segments:
      - start: "2022-01-01"
        end: "2026-12-31"
        friday_close: "16:55"
        sunday_open: "17:00"
        pause_start: "16:55"
        pause_end: "17:05"
        short_close: null
```

Tramos y años sin tramo:

| Clave | Tramos estables | Años sin tramo |
|---|---|---|
| dukascopy:US100 | 2015-2015 (V 16:00, D 18:00, P —); 2018-2023 (V 16:15, D 18:00, P 16:15→18:00); 2024-2025 (V 16:15, D 18:00, P —); 2026-2026 (V 16:15, D 18:00, P 16:15→18:00) | 2013, 2014, 2016, 2017 |
| dukascopy:US500 | 2015-2015 (V 16:00, D 18:00, P —); 2018-2026 (V 16:15, D 18:00, P 16:15→18:00) | 2013, 2014, 2016, 2017 |
| dukascopy:US30 | 2013-2013 (V 17:00, D 19:00, P —); 2015-2015 (V 16:00, D 18:00, P 16:15→16:30); 2018-2026 (V 16:15, D 18:00, P 16:15→18:00) | 2014, 2016, 2017 |
| dukascopy:XAUUSD | 2005-2012 (V 17:00, D 17:00, P —); 2013-2026 (V 17:00, D 18:00, P 17:00→18:00) | 2003, 2004 |
| dukascopy:EURUSD | 2003-2018 (V 17:00, D 17:00, P —); 2019-2019 (V 17:00, D 17:00, P 17:00→18:00); 2020-2024 (V 17:00, D 17:00, P —); 2025-2025 (V 17:00, D 17:00, P 17:10→17:25); 2026-2026 (V 17:00, D 17:00, P —) | — |
| dukascopy:GBPUSD | 2003-2010 (V 17:00, D 17:00, P —); 2011-2011 (V 17:00, D 17:00, P 17:05→17:20); 2012-2017 (V 17:00, D 17:00, P —); 2018-2018 (V 17:00, D 17:00, P 17:30→18:15); 2019-2019 (V 17:00, D 17:00, P 17:00→18:00); 2020-2026 (V 17:00, D 17:00, P —) | — |
| dukascopy:USDJPY | 2003-2011 (V 17:00, D 17:00, P —); 2012-2012 (V 17:00, D 17:00, P 17:20→17:50); 2013-2018 (V 17:00, D 17:00, P —); 2019-2019 (V 17:00, D 17:00, P 17:00→18:00); 2020-2020 (V 17:00, D 17:00, P —); 2021-2021 (V 17:00, D 17:00, P 17:15→17:25); 2022-2026 (V 17:00, D 17:00, P —) | — |
| broker:US100 | 2022-2026 (V 16:50, D 18:00, P 16:50→18:05) | — |
| broker:US500 | 2022-2026 (V 16:50, D 18:00, P 16:50→18:05) | — |
| broker:US30 | 2022-2026 (V 16:50, D 18:00, P 16:50→18:05) | — |
| broker:XAUUSD | 2022-2026 (V 16:50, D 18:00, P 16:50→18:05) | — |
| broker:EURUSD | 2022-2026 (V 16:55, D 17:00, P 16:55→17:05) | — |
| broker:GBPUSD | 2022-2026 (V 16:55, D 17:00, P 16:55→17:05) | — |
| broker:USDJPY | 2022-2026 (V 16:55, D 17:00, P 16:55→17:05) | — |

Los índices de Dukascopy no tienen tramo en 2013/2014 (domingo 56-58 %) ni en
2016/2017 (sin apertura de domingo plausible). XAUUSD no tiene tramo en 2003/2004.
No se inventó ningún horario para esos años.

## 3. Diagnóstico índices 2015-2018

Primera y última barra M1 de US100 en días consecutivos (hora NY):

| Día (NY) | Primera barra | Última barra | Barras |
|---|---|---|---|
| 2016-01-04 | 02:00 | 16:00 | 841 |
| 2016-01-05 | 02:00 | 16:00 | 841 |
| 2016-01-06 | 02:00 | 16:00 | 841 |
| 2016-01-07 | 02:00 | 16:00 | 841 |
| 2016-01-08 | 02:00 | 16:00 | 841 |
| 2019-01-07 | 00:00 | 23:59 | 1335 |
| 2019-01-08 | 00:00 | 23:59 | 1335 |
| 2019-01-09 | 00:00 | 23:59 | 1335 |
| 2019-01-10 | 00:00 | 23:59 | 1335 |
| 2019-01-11 | 00:00 | 16:14 | 975 |

En enero de 2016 Dukascopy sirve US100 solo de 02:00 a 16:00 NY (841 barras), sin
la sesión de tarde/noche; en enero de 2019 sirve el día completo 00:00-23:59
(1335 barras). Esa estructura distinta explica los ~250 huecos reales por año de
2015-2018 y por qué 2016/2017 no permiten derivar una apertura de domingo: no se
convierten en sesión.

## 4. usable_from

Comando:

```text
lab discovery usable-from [--source dukascopy|broker] [--symbol S] [--tf TF] [--write]
```

Tabla 7×7 de Dukascopy (fecha, estado y huecos reales del data-check recortado):

| Símbolo | TF | usable_from | Estado | Huecos reales |
|---|---|---|---|---:|
| US100 | M1 | 2018-01-02 | WARN | 140 |
| US100 | M5 | 2018-01-02 | WARN | 23 |
| US100 | M15 | 2015-01-02 | WARN | 13 |
| US100 | M30 | 2015-01-02 | WARN | 2 |
| US100 | H1 | 2018-01-02 | WARN | 77 |
| US100 | H4 | 2019-01-01 | WARN | 1 |
| US100 | D1 | 2014-01-01 | OK | 0 |
| US500 | M1 | 2018-01-02 | WARN | 3152 |
| US500 | M5 | 2018-01-02 | WARN | 29 |
| US500 | M15 | 2015-01-02 | WARN | 9 |
| US500 | M30 | 2015-01-02 | WARN | 2 |
| US500 | H1 | 2018-01-02 | WARN | 74 |
| US500 | H4 | 2019-01-01 | WARN | 1 |
| US500 | D1 | 2018-01-01 | OK | 0 |
| US30 | M1 | 2018-01-02 | WARN | 135 |
| US30 | M5 | 2015-01-02 | WARN | 87 |
| US30 | M15 | 2015-01-02 | WARN | 9 |
| US30 | M30 | 2015-01-02 | WARN | 5 |
| US30 | H1 | 2018-01-02 | WARN | 76 |
| US30 | H4 | 2019-01-01 | WARN | 1 |
| US30 | D1 | 2015-01-01 | OK | 0 |
| XAUUSD | M1 | 2005-01-02 | WARN | 12696 |
| XAUUSD | M5 | 2005-01-02 | WARN | 623 |
| XAUUSD | M15 | 2005-01-02 | WARN | 56 |
| XAUUSD | M30 | 2004-01-01 | WARN | 31 |
| XAUUSD | H1 | 2005-01-02 | WARN | 113 |
| XAUUSD | H4 | 2004-01-01 | WARN | 6 |
| XAUUSD | D1 | 2003-05-04 | OK | 0 |
| EURUSD | M1 | 2003-05-04 | WARN | 475 |
| EURUSD | M5 | 2003-05-04 | WARN | 30 |
| EURUSD | M15 | 2003-05-04 | WARN | 6 |
| EURUSD | M30 | 2003-05-04 | WARN | 1 |
| EURUSD | H1 | 2003-05-04 | WARN | 3 |
| EURUSD | H4 | 2003-05-04 | OK | 0 |
| EURUSD | D1 | 2003-05-04 | OK | 0 |
| GBPUSD | M1 | 2003-05-04 | WARN | 657 |
| GBPUSD | M5 | 2003-05-04 | WARN | 29 |
| GBPUSD | M15 | 2003-05-04 | WARN | 7 |
| GBPUSD | M30 | 2003-05-04 | WARN | 2 |
| GBPUSD | H1 | 2003-05-04 | WARN | 2 |
| GBPUSD | H4 | 2003-05-04 | OK | 0 |
| GBPUSD | D1 | 2003-05-04 | OK | 0 |
| USDJPY | M1 | 2003-05-04 | WARN | 555 |
| USDJPY | M5 | 2003-05-04 | WARN | 32 |
| USDJPY | M15 | 2003-05-04 | WARN | 7 |
| USDJPY | M30 | 2003-05-04 | WARN | 1 |
| USDJPY | H1 | 2003-05-04 | WARN | 4 |
| USDJPY | H4 | 2003-05-04 | WARN | 2 |
| USDJPY | D1 | 2003-05-04 | OK | 0 |

Resultado: 77 claves escritas en `data_quality.usable_from`; 21 quedan fuera
(11 sin fichero de datos y 10 sin ningún año que cumpla, sobre todo bróker M1/M5 y
H1/H4 sin historia suficiente). Todas las claves escritas tienen estado OK o WARN,
ninguna FAIL por construcción. `campaigns.register` rechaza con error claro
`campaña empieza antes de usable_from (fecha < fecha)`; los tests cubren rango
anterior (rechazo) y posterior (OK), y no se valida ninguna campaña ya registrada.

## 5. Data-check antes / después

Antes = `06ecf30`; después = R2j-b. Historia completa, Dukascopy:

| Símbolo | TF | Antes (06ecf30) | Después (R2j-b) |
|---|---|---|---|
| US100 | M1 | WARN · 2857 | WARN · 2800 |
| US100 | M5 | WARN · 414 | WARN · 411 |
| US100 | M15 | WARN · 21 | WARN · 20 |
| US100 | M30 | WARN · 11 | WARN · 10 |
| US100 | H1 | FAIL · 870 | FAIL · 812 |
| US100 | H4 | FAIL · 814 | FAIL · 790 |
| US100 | D1 | WARN · 8 | WARN · 1 |
| US500 | M1 | WARN · 8949 | WARN · 8612 |
| US500 | M5 | WARN · 454 | WARN · 449 |
| US500 | M15 | WARN · 36 | WARN · 35 |
| US500 | M30 | WARN · 14 | WARN · 14 |
| US500 | H1 | FAIL · 872 | FAIL · 813 |
| US500 | H4 | FAIL · 814 | FAIL · 791 |
| US500 | D1 | FAIL · 18 | WARN · 11 |
| US30 | M1 | WARN · 2018 | WARN · 1964 |
| US30 | M5 | WARN · 360 | WARN · 356 |
| US30 | M15 | WARN · 18 | WARN · 17 |
| US30 | M30 | WARN · 8 | WARN · 7 |
| US30 | H1 | FAIL · 867 | FAIL · 797 |
| US30 | H4 | FAIL · 806 | FAIL · 782 |
| US30 | D1 | WARN · 9 | WARN · 2 |
| XAUUSD | M1 | WARN · 26549 | WARN · 25324 |
| XAUUSD | M5 | WARN · 2417 | WARN · 2293 |
| XAUUSD | M15 | WARN · 122 | WARN · 117 |
| XAUUSD | M30 | WARN · 45 | WARN · 43 |
| XAUUSD | H1 | WARN · 171 | WARN · 137 |
| XAUUSD | H4 | WARN · 28 | WARN · 7 |
| XAUUSD | D1 | WARN · 17 | OK · 0 |
| EURUSD | M1 | WARN · 597 | WARN · 475 |
| EURUSD | M5 | WARN · 35 | WARN · 30 |
| EURUSD | M15 | WARN · 6 | WARN · 6 |
| EURUSD | M30 | WARN · 1 | WARN · 1 |
| EURUSD | H1 | WARN · 3 | WARN · 3 |
| EURUSD | H4 | OK · 0 | OK · 0 |
| EURUSD | D1 | OK · 0 | OK · 0 |
| GBPUSD | M1 | WARN · 840 | WARN · 657 |
| GBPUSD | M5 | WARN · 36 | WARN · 29 |
| GBPUSD | M15 | WARN · 8 | WARN · 7 |
| GBPUSD | M30 | WARN · 3 | WARN · 2 |
| GBPUSD | H1 | WARN · 2 | WARN · 2 |
| GBPUSD | H4 | OK · 0 | OK · 0 |
| GBPUSD | D1 | OK · 0 | OK · 0 |
| USDJPY | M1 | WARN · 701 | WARN · 555 |
| USDJPY | M5 | WARN · 33 | WARN · 32 |
| USDJPY | M15 | WARN · 7 | WARN · 7 |
| USDJPY | M30 | WARN · 1 | WARN · 1 |
| USDJPY | H1 | WARN · 4 | WARN · 4 |
| USDJPY | H4 | WARN · 2 | WARN · 2 |
| USDJPY | D1 | OK · 0 | OK · 0 |

### Cambios de estado

- **US500 D1**: FAIL · 18 → WARN · 11. Los 7 huecos movidos son festivos
  (Viernes Santo 2013-2020 y festivos NYSE fuera de 2021-2027).
- **XAUUSD D1**: WARN · 17 → OK · 0. Los 17 huecos son festivos
  (Viernes Santo, Navidad y Año Nuevo con observados).
- El resto de estados no cambia; los recuentos bajan en casi todos los TF. Los
  índices H1/H4 siguen FAIL por los huecos reales de 2015-2018.

### Movidos real → programado y nuevos reales

Total movido: **2647**. Causas: **2594 festivo**, **36 cierre temprano**,
**10 fin de semana**, **7 pausa**, **0 horario**. Ningún símbolo×TF supera el 5 %
por `horario`: **no hay SOSPECHOSO**.

| Símbolo | TF | Reales antes | Reales después | Movidos | Festivo | Cierre temp. | Pausa | Fin semana | Horario | Nuevos reales | % horario | Sospechoso |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| US100 | M1 | 2857 | 2800 | 58 | 55 | 3 | 0 | 0 | 0 | 1 | 0.0% | no |
| US100 | M5 | 414 | 411 | 3 | 2 | 1 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | M15 | 21 | 20 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | M30 | 11 | 10 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | H1 | 870 | 812 | 60 | 54 | 6 | 0 | 0 | 0 | 2 | 0.0% | no |
| US100 | H4 | 814 | 790 | 24 | 24 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | D1 | 8 | 1 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | M1 | 8949 | 8612 | 339 | 335 | 4 | 0 | 0 | 0 | 2 | 0.0% | no |
| US500 | M5 | 454 | 449 | 5 | 4 | 1 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | M15 | 36 | 35 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | M30 | 14 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | H1 | 872 | 813 | 60 | 54 | 6 | 0 | 0 | 0 | 1 | 0.0% | no |
| US500 | H4 | 814 | 791 | 23 | 23 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | D1 | 18 | 11 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | M1 | 2018 | 1964 | 55 | 49 | 6 | 0 | 0 | 0 | 1 | 0.0% | no |
| US30 | M5 | 360 | 356 | 4 | 2 | 2 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | M15 | 18 | 17 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | M30 | 8 | 7 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | H1 | 867 | 797 | 72 | 57 | 7 | 0 | 8 | 0 | 2 | 0.0% | no |
| US30 | H4 | 806 | 782 | 24 | 24 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | D1 | 9 | 2 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | M1 | 26549 | 25324 | 1225 | 1225 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | M5 | 2417 | 2293 | 124 | 124 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | M15 | 122 | 117 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | M30 | 45 | 43 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | H1 | 171 | 137 | 34 | 26 | 0 | 7 | 1 | 0 | 0 | 0.0% | no |
| XAUUSD | H4 | 28 | 7 | 21 | 20 | 0 | 0 | 1 | 0 | 0 | 0.0% | no |
| XAUUSD | D1 | 17 | 0 | 17 | 17 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | M1 | 597 | 475 | 122 | 122 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | M5 | 35 | 30 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | M15 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | M30 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | H1 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | H4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | D1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | M1 | 840 | 657 | 183 | 183 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | M5 | 36 | 29 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | M15 | 8 | 7 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | M30 | 3 | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | H1 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | H4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | D1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | M1 | 701 | 555 | 146 | 146 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | M5 | 33 | 32 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | M15 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | M30 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | H1 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | H4 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | D1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |

Los **9 huecos reales nuevos** son huecos anteriores al cierre en días de cierre
temprano que el clasificador antiguo ocultaba al considerar festivo el día entero:
US100 M1 2024-12-24 06:32-06:40; US100 H1 2025-11-27 22:00→28 02:00 y
28 03:00-08:00; US500 M1 2024-07-03 00:14-00:19 y 2025-11-28 08:31-08:37;
US500 H1 2025-11-28 02:00-08:00; US30 M1 2024-12-24 06:26-06:37; US30 H1
2025-11-27 22:00→28 02:00 y 28 03:00-08:00. Son datos que faltan de verdad y por
eso se cuentan.

### FAIL que siguen (fechas y causa)

- **US100 H1**: 812 huecos reales.
- **US100 H4**: 790 huecos reales.
- **US500 H1**: 813 huecos reales.
- **US500 H4**: 791 huecos reales.
- **US30 H1**: 797 huecos reales.
- **US30 H4**: 782 huecos reales.

Los seis FAIL son de índices Dukascopy en H1/H4. El detalle por año y muestras:

### US100 H1 — 812 huecos reales
Años: 2013: 12, 2014: 38, 2015: 182, 2016: 252, 2017: 251, 2018: 69, 2020: 4, 2024: 1, 2025: 3
Causas: sesión: 812
Muestras: 2013-11-01T17:00:00-04:00, 2013-11-08T17:00:00-05:00, 2014-01-03T17:00:00-05:00, 2014-01-10T17:00:00-05:00, 2015-03-03T16:00:00-05:00, 2015-03-13T17:00:00-04:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T16:00:00-05:00, 2018-01-03T16:00:00-05:00, 2020-03-09T05:00:00-04:00, 2020-03-15T19:00:00-04:00

### US100 H4 — 790 huecos reales
Años: 2013: 21, 2014: 14, 2015: 182, 2016: 252, 2017: 251, 2018: 69, 2020: 1
Causas: sesión: 790
Muestras: 2013-06-02T21:00:00-04:00, 2013-08-09T13:00:00-04:00, 2014-01-24T17:00:00-05:00, 2014-01-27T21:00:00-05:00, 2015-03-03T17:00:00-05:00, 2015-03-13T17:00:00-04:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T17:00:00-05:00, 2018-01-03T17:00:00-05:00, 2020-03-15T21:00:00-04:00

### US30 H1 — 797 huecos reales
Años: 2013: 3, 2014: 33, 2015: 182, 2016: 252, 2017: 251, 2018: 69, 2019: 1, 2020: 3, 2024: 1, 2025: 2
Causas: sesión: 797
Muestras: 2013-12-25T15:00:00-05:00, 2013-12-26T02:00:00-05:00, 2014-01-03T17:00:00-05:00, 2014-01-10T17:00:00-05:00, 2015-03-03T16:00:00-05:00, 2015-03-13T17:00:00-04:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T16:00:00-05:00, 2018-01-03T16:00:00-05:00, 2019-02-26T20:00:00-05:00, 2020-03-09T06:00:00-04:00

### US30 H4 — 782 huecos reales
Años: 2013: 16, 2014: 12, 2015: 182, 2016: 252, 2017: 250, 2018: 69, 2020: 1
Causas: sesión: 782
Muestras: 2013-09-30T13:00:00-04:00, 2013-10-01T17:00:00-04:00, 2014-01-24T17:00:00-05:00, 2014-01-27T17:00:00-05:00, 2015-03-03T17:00:00-05:00, 2015-03-13T17:00:00-04:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T17:00:00-05:00, 2018-01-03T17:00:00-05:00, 2020-03-15T21:00:00-04:00

### US500 H1 — 813 huecos reales
Años: 2013: 11, 2014: 38, 2015: 192, 2016: 249, 2017: 249, 2018: 69, 2019: 1, 2020: 3, 2025: 1
Causas: sesión: 813
Muestras: 2013-11-01T17:00:00-04:00, 2013-11-08T17:00:00-05:00, 2014-01-01T08:00:00-05:00, 2014-01-03T17:00:00-05:00, 2015-02-12T16:00:00-05:00, 2015-02-16T16:00:00-05:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T16:00:00-05:00, 2018-01-03T16:00:00-05:00, 2019-02-26T20:00:00-05:00, 2020-03-09T04:00:00-04:00

### US500 H4 — 791 huecos reales
Años: 2013: 16, 2014: 16, 2015: 192, 2016: 249, 2017: 248, 2018: 69, 2020: 1
Causas: sesión: 791
Muestras: 2013-06-02T21:00:00-04:00, 2013-08-09T13:00:00-04:00, 2014-01-01T09:00:00-05:00, 2014-01-22T17:00:00-05:00, 2015-02-12T17:00:00-05:00, 2015-02-16T17:00:00-05:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T17:00:00-05:00, 2018-01-03T17:00:00-05:00, 2020-03-15T21:00:00-04:00

La causa es la estructura diaria de 2015-2018 (US100 solo 02:00-16:00 en
2016/2017) y los huecos de sesión asociados; 2013/2014 y 2020 añaden huecos
sueltos. No son festivos ni fines de semana: son sesiones sin datos. Al no haber
tramo estable en 2016/2017, no se excusan. XAUUSD y US500 D1 ya no tienen FAIL.

## 6. Cierre

`git status --short`:

```text
?? tl2-edge-map.patch
```

`git log --oneline -5`:

```text
8a121d0 tl2: R2j-b - calendario completo, tramos y usable_from
06ecf30 tl2: R2j - calendarios por instrumento
1a5049d merge: principal (R2g + R2g-fix) en integración
cb5417d tl2: R2g - huecos de fin de semana por calendario
1886c20 orquestador: protocolo de relevo por archivos
```

- `pytest -q`: **1602 passed, 1 skipped (1068,68 s; 1 warning psutil)**.
- `ruff check src/tradinglab/discovery src/tradinglab/cli.py tests`: **limpio**.
- `lab propfund verify`: **OK en ai_trader (17), ea_us100_ftmo1 (18), ftmo_forward (8) y ftmo_risk (14)**.
- `count_tests`: **1676**.
- Tag `tl2-r2j-b` → `8a121d0`.

## Aviso

- No se bajó el 60 % de estabilidad: 2016/2017 siguen sin tramo y sus huecos
  reales siguen contando. Por eso los índices H1/H4 continúan FAIL.
- La ruta sin sesión ya reconoce festivos 2003-2030; el límite que queda es la
  estructura de datos de Dukascopy en 2015-2018, no el calendario.
- No se ejecutaron campañas ni se leyó OOS-1/OOS-2. No se hizo push.

## Siguiente

PARA.
