# RESULTADO · R2j — calendarios completos por instrumento

Fecha: 2026-11-22. Sin campañas, sin OOS, sin push. Sin tocar umbrales numéricos.

## Hecho

- `discovery/calendars.py`: NYSE 2003-2030 por reglas, cierres especiales separados y
  cierres tempranos; FX/metales con Viernes Santo, Navidad y Año Nuevo.
- `discovery/sessions.py` + `lab discovery derive-sessions`: moda semanal por año,
  60 % mínimo, tramos con fecha desde/hasta.
- `engine.yaml`: `data_quality.sessions` con las 10 claves estables.
- `_calendar_gap` con intervalos reales del instrumento (festivo, cierre temprano,
  pausa, horario), con comportamiento legacy exacto si no hay sesión configurada.
- Tests nuevos en `tests/test_discovery_calendars.py` y regresión en
  `tests/test_discovery_data_quality.py`.
- Commit `06ecf30` · `tl2: R2j - calendarios por instrumento`.
- Tag `tl2-r2j`.

## 1. Calendarios

Test obligatorio: `nyse_holidays(2021, 2027) == nyse_calendar.FULL_HOLIDAYS` y
`nyse_early_closes(2021, 2027) == nyse_calendar.EARLY_CLOSES`: **pasan exactos**.

Los cierres especiales van en `NYSE_SPECIAL_CLOSURES`, separados del calendario
regular para no romper esa igualdad: `2004-06-11`, `2007-01-02`, `2012-10-29`,
`2012-10-30`, `2018-12-05`, `2025-01-09`. `is_holiday` los incluye.

## 2. Estabilidad de sesiones por año

Cada valor es la moda semanal del año. Un año con moda < 60 % de las semanas se
marca INESTABLE. La tabla completa, clave por clave:

| Clave | Año | Viernes | % | Domingo | % | Pausa | % | Corta | % | Estado |
|---|---|---|---:|---|---:|---|---:|---|---:|---|
| dukascopy:US100 | 2013 | 17:00 | 62% | 18:00 | 56% | — | — | — | — | INESTABLE: domingo 56% < 60%; pausa no estable: se omite; sesión corta no estable: se omite |
| dukascopy:US100 | 2014 | 17:00 | 94% | 18:00 | 58% | 16:15→16:30 | 60% | — | — | INESTABLE: domingo 58% < 60%; sesión corta no estable: se omite |
| dukascopy:US100 | 2015 | 16:00 | 66% | 18:00 | 79% | — | — | 13:00 | 100% | ESTABLE |
| dukascopy:US100 | 2016 | 16:00 | 98% | — | — | — | — | — | — | INESTABLE: apertura de domingo no plausible; sin cierre de viernes o apertura de domingo |
| dukascopy:US100 | 2017 | 16:00 | 98% | — | — | — | — | — | — | INESTABLE: apertura de domingo no plausible; sin cierre de viernes o apertura de domingo |
| dukascopy:US100 | 2018 | 16:15 | 73% | 18:00 | 97% | 16:15→18:00 | 90% | — | — | ESTABLE |
| dukascopy:US100 | 2019 | 16:15 | 98% | 18:00 | 98% | 16:15→18:00 | 92% | — | — | ESTABLE |
| dukascopy:US100 | 2020 | 16:15 | 96% | 18:00 | 98% | 16:15→18:00 | 91% | — | — | ESTABLE |
| dukascopy:US100 | 2021 | 16:15 | 96% | 18:00 | 98% | 16:15→18:00 | 90% | 16:15 | 100% | ESTABLE |
| dukascopy:US100 | 2022 | 16:15 | 98% | 18:00 | 100% | 16:15→18:00 | 88% | — | — | ESTABLE |
| dukascopy:US100 | 2023 | 16:15 | 96% | 18:00 | 100% | 16:15→18:00 | 90% | — | — | ESTABLE |
| dukascopy:US100 | 2024 | 16:15 | 98% | 18:00 | 94% | — | — | — | — | ESTABLE |
| dukascopy:US100 | 2025 | 16:15 | 96% | 18:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:US100 | 2026 | 16:15 | 96% | 18:00 | 100% | 16:15→18:00 | 87% | — | — | ESTABLE |
| broker:US100 | 2022 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 85% | — | — | ESTABLE |
| broker:US100 | 2023 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 88% | — | — | ESTABLE |
| broker:US100 | 2024 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 91% | — | — | ESTABLE |
| broker:US100 | 2025 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 92% | — | — | ESTABLE |
| broker:US100 | 2026 | 16:50 | 94% | 18:00 | 100% | 16:50→18:05 | 91% | — | — | ESTABLE |
| dukascopy:US500 | 2013 | 17:00 | 65% | 18:00 | 56% | — | — | — | — | INESTABLE: domingo 56% < 60%; pausa no estable: se omite; sesión corta no estable: se omite |
| dukascopy:US500 | 2014 | 17:00 | 86% | 18:00 | 56% | — | — | — | — | INESTABLE: domingo 56% < 60%; pausa no estable: se omite; sesión corta no estable: se omite |
| dukascopy:US500 | 2015 | 16:00 | 72% | 18:00 | 73% | — | — | 13:00 | 100% | ESTABLE |
| dukascopy:US500 | 2016 | 16:00 | 98% | — | — | — | — | — | — | INESTABLE: apertura de domingo no plausible; sin cierre de viernes o apertura de domingo |
| dukascopy:US500 | 2017 | 16:00 | 98% | — | — | — | — | — | — | INESTABLE: apertura de domingo no plausible; sin cierre de viernes o apertura de domingo |
| dukascopy:US500 | 2018 | 16:15 | 73% | 18:00 | 97% | 16:15→18:00 | 79% | — | — | ESTABLE |
| dukascopy:US500 | 2019 | 16:15 | 98% | 18:00 | 98% | 16:15→18:00 | 87% | — | — | ESTABLE |
| dukascopy:US500 | 2020 | 16:15 | 96% | 18:00 | 98% | 16:15→18:00 | 91% | — | — | ESTABLE |
| dukascopy:US500 | 2021 | 16:15 | 96% | 18:00 | 98% | 16:15→18:00 | 90% | 16:15 | 100% | ESTABLE |
| dukascopy:US500 | 2022 | 16:15 | 98% | 18:00 | 100% | 16:15→18:00 | 88% | — | — | ESTABLE |
| dukascopy:US500 | 2023 | 16:15 | 96% | 18:00 | 100% | 16:15→18:00 | 88% | — | — | ESTABLE |
| dukascopy:US500 | 2024 | 16:15 | 98% | 18:00 | 100% | 16:15→18:00 | 91% | — | — | ESTABLE |
| dukascopy:US500 | 2025 | 16:15 | 96% | 18:00 | 100% | 16:15→18:00 | 87% | — | — | ESTABLE |
| dukascopy:US500 | 2026 | 16:15 | 96% | 18:00 | 98% | 16:15→18:00 | 89% | — | — | ESTABLE |
| broker:US500 | 2022 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 85% | — | — | ESTABLE |
| broker:US500 | 2023 | 16:50 | 94% | 18:00 | 100% | 16:50→18:05 | 88% | — | — | ESTABLE |
| broker:US500 | 2024 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 91% | — | — | ESTABLE |
| broker:US500 | 2025 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 92% | — | — | ESTABLE |
| broker:US500 | 2026 | 16:50 | 94% | 18:00 | 100% | 16:50→18:05 | 91% | — | — | ESTABLE |
| dukascopy:US30 | 2013 | 17:00 | 69% | 19:00 | 90% | — | — | — | — | ESTABLE |
| dukascopy:US30 | 2014 | 17:00 | 94% | 18:00 | 58% | 16:15→16:30 | 60% | — | — | INESTABLE: domingo 58% < 60%; sesión corta no estable: se omite |
| dukascopy:US30 | 2015 | 16:00 | 66% | 18:00 | 79% | 16:15→16:30 | 65% | 13:00 | 100% | ESTABLE |
| dukascopy:US30 | 2016 | 16:00 | 98% | — | — | — | — | — | — | INESTABLE: apertura de domingo no plausible; sin cierre de viernes o apertura de domingo |
| dukascopy:US30 | 2017 | 16:00 | 98% | — | — | — | — | — | — | INESTABLE: apertura de domingo no plausible; sin cierre de viernes o apertura de domingo |
| dukascopy:US30 | 2018 | 16:15 | 73% | 18:00 | 97% | 16:15→18:00 | 88% | — | — | ESTABLE |
| dukascopy:US30 | 2019 | 16:15 | 98% | 18:00 | 98% | 16:15→18:00 | 92% | — | — | ESTABLE |
| dukascopy:US30 | 2020 | 16:15 | 96% | 18:00 | 98% | 16:15→18:00 | 91% | — | — | ESTABLE |
| dukascopy:US30 | 2021 | 16:15 | 96% | 18:00 | 98% | 16:15→18:00 | 90% | 16:15 | 100% | ESTABLE |
| dukascopy:US30 | 2022 | 16:15 | 98% | 18:00 | 100% | 16:15→18:00 | 88% | — | — | ESTABLE |
| dukascopy:US30 | 2023 | 16:15 | 96% | 18:00 | 100% | 16:15→18:00 | 90% | — | — | ESTABLE |
| dukascopy:US30 | 2024 | 16:15 | 98% | 18:00 | 94% | 16:15→18:00 | 91% | — | — | ESTABLE |
| dukascopy:US30 | 2025 | 16:15 | 96% | 18:00 | 100% | 16:15→18:00 | 94% | — | — | ESTABLE |
| dukascopy:US30 | 2026 | 16:15 | 96% | 18:00 | 100% | 16:15→18:00 | 87% | — | — | ESTABLE |
| broker:US30 | 2022 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 85% | — | — | ESTABLE |
| broker:US30 | 2023 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 88% | — | — | ESTABLE |
| broker:US30 | 2024 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 91% | — | — | ESTABLE |
| broker:US30 | 2025 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 92% | — | — | ESTABLE |
| broker:US30 | 2026 | 16:50 | 94% | 18:00 | 100% | 16:50→18:05 | 91% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2003 | 16:55 | 24% | 17:00 | 32% | — | — | — | — | INESTABLE: viernes 24% < 60%; domingo 32% < 60% |
| dukascopy:XAUUSD | 2004 | 17:00 | 36% | 17:00 | 83% | — | — | — | — | INESTABLE: viernes 36% < 60%; sesión corta no estable: se omite |
| dukascopy:XAUUSD | 2005 | 17:00 | 65% | 17:00 | 96% | — | — | — | — | ESTABLE |
| dukascopy:XAUUSD | 2006 | 17:00 | 88% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:XAUUSD | 2007 | 17:00 | 92% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:XAUUSD | 2008 | 17:00 | 98% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:XAUUSD | 2009 | 17:00 | 98% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:XAUUSD | 2010 | 17:00 | 100% | 17:00 | 100% | — | — | 17:00 | 100% | ESTABLE |
| dukascopy:XAUUSD | 2011 | 17:00 | 100% | 17:00 | 94% | — | — | — | — | ESTABLE |
| dukascopy:XAUUSD | 2012 | 17:00 | 100% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:XAUUSD | 2013 | 17:00 | 96% | 18:00 | 98% | 17:00→18:00 | 89% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2014 | 17:00 | 96% | 18:00 | 87% | 17:00→18:00 | 75% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2015 | 17:00 | 96% | 18:00 | 98% | 17:00→18:00 | 90% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2016 | 17:00 | 98% | 18:00 | 100% | 17:00→18:00 | 90% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2017 | 17:00 | 98% | 18:00 | 98% | 17:00→18:00 | 92% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2018 | 17:00 | 98% | 18:00 | 100% | 17:00→18:00 | 92% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2019 | 17:00 | 98% | 18:00 | 100% | 17:00→18:00 | 92% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2020 | 17:00 | 96% | 18:00 | 100% | 17:00→18:00 | 92% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2021 | 17:00 | 98% | 18:00 | 100% | 17:00→18:00 | 90% | 17:00 | 100% | ESTABLE |
| dukascopy:XAUUSD | 2022 | 17:00 | 98% | 18:00 | 100% | 17:00→18:00 | 88% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2023 | 17:00 | 98% | 18:00 | 100% | 17:00→18:00 | 90% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2024 | 17:00 | 98% | 18:00 | 100% | 17:00→18:00 | 92% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2025 | 17:00 | 96% | 18:00 | 100% | 17:00→18:00 | 92% | — | — | ESTABLE |
| dukascopy:XAUUSD | 2026 | 17:00 | 96% | 18:00 | 100% | 17:00→18:00 | 91% | — | — | ESTABLE |
| broker:XAUUSD | 2022 | 16:50 | 84% | 18:00 | 100% | 16:50→18:05 | 88% | — | — | ESTABLE |
| broker:XAUUSD | 2023 | 16:50 | 98% | 18:00 | 100% | 16:50→18:05 | 90% | — | — | ESTABLE |
| broker:XAUUSD | 2024 | 16:50 | 98% | 18:00 | 100% | 16:50→18:05 | 92% | — | — | ESTABLE |
| broker:XAUUSD | 2025 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 92% | — | — | ESTABLE |
| broker:XAUUSD | 2026 | 16:50 | 96% | 18:00 | 100% | 16:50→18:05 | 91% | — | — | ESTABLE |
| dukascopy:EURUSD | 2003 | 17:00 | 97% | 17:00 | 97% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2004 | 17:00 | 100% | 17:00 | 100% | — | — | 17:00 | 100% | ESTABLE |
| dukascopy:EURUSD | 2005 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2006 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2007 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2008 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2009 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2010 | 17:00 | 100% | 17:00 | 100% | — | — | 17:00 | 100% | ESTABLE |
| dukascopy:EURUSD | 2011 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2012 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2013 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2014 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2015 | 17:00 | 98% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2016 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2017 | 17:00 | 100% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2018 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2019 | 17:00 | 100% | 17:00 | 100% | 17:00→18:00 | 100% | — | — | ESTABLE |
| dukascopy:EURUSD | 2020 | 17:00 | 98% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2021 | 17:00 | 100% | 17:00 | 100% | — | — | 17:00 | 100% | ESTABLE |
| dukascopy:EURUSD | 2022 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2023 | 17:00 | 100% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2024 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:EURUSD | 2025 | 17:00 | 100% | 17:00 | 100% | 17:10→17:25 | 100% | — | — | ESTABLE |
| dukascopy:EURUSD | 2026 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| broker:EURUSD | 2022 | 16:55 | 98% | 17:00 | 100% | 16:55→17:05 | 94% | — | — | ESTABLE |
| broker:EURUSD | 2023 | 16:55 | 100% | 17:00 | 100% | 16:55→17:05 | 98% | — | — | ESTABLE |
| broker:EURUSD | 2024 | 16:55 | 98% | 17:00 | 100% | 16:55→17:05 | 98% | 16:55 | 100% | ESTABLE |
| broker:EURUSD | 2025 | 16:55 | 100% | 17:00 | 100% | 16:55→17:05 | 98% | 16:55 | 100% | ESTABLE |
| broker:EURUSD | 2026 | 16:55 | 100% | 17:00 | 100% | 16:55→17:05 | 98% | — | — | ESTABLE |
| dukascopy:GBPUSD | 2003 | 17:00 | 97% | 17:00 | 97% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2004 | 17:00 | 100% | 17:00 | 98% | — | — | 17:00 | 100% | ESTABLE |
| dukascopy:GBPUSD | 2005 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2006 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2007 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2008 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2009 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2010 | 17:00 | 100% | 17:00 | 100% | — | — | 17:00 | 100% | ESTABLE |
| dukascopy:GBPUSD | 2011 | 17:00 | 100% | 17:00 | 100% | 17:05→17:20 | 100% | — | — | ESTABLE |
| dukascopy:GBPUSD | 2012 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2013 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2014 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2015 | 17:00 | 98% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2016 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2017 | 17:00 | 100% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2018 | 17:00 | 100% | 17:00 | 100% | 17:30→18:15 | 100% | — | — | ESTABLE |
| dukascopy:GBPUSD | 2019 | 17:00 | 100% | 17:00 | 100% | 17:00→18:00 | 100% | — | — | ESTABLE |
| dukascopy:GBPUSD | 2020 | 17:00 | 98% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2021 | 17:00 | 100% | 17:00 | 100% | — | — | 17:00 | 100% | ESTABLE |
| dukascopy:GBPUSD | 2022 | 17:00 | 100% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2023 | 17:00 | 100% | 17:00 | 96% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2024 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2025 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:GBPUSD | 2026 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| broker:GBPUSD | 2022 | 16:55 | 98% | 17:00 | 100% | 16:55→17:05 | 94% | — | — | ESTABLE |
| broker:GBPUSD | 2023 | 16:55 | 100% | 17:00 | 100% | 16:55→17:05 | 100% | — | — | ESTABLE |
| broker:GBPUSD | 2024 | 16:55 | 98% | 17:00 | 100% | 16:55→17:05 | 98% | 16:55 | 100% | ESTABLE |
| broker:GBPUSD | 2025 | 16:55 | 100% | 17:00 | 100% | 16:55→17:05 | 96% | 16:55 | 100% | ESTABLE |
| broker:GBPUSD | 2026 | 16:55 | 100% | 17:00 | 100% | 16:55→17:05 | 87% | — | — | ESTABLE |
| dukascopy:USDJPY | 2003 | 17:00 | 94% | 17:00 | 97% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2004 | 17:00 | 100% | 17:00 | 98% | — | — | 17:00 | 100% | ESTABLE |
| dukascopy:USDJPY | 2005 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2006 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2007 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2008 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2009 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2010 | 17:00 | 100% | 17:00 | 100% | — | — | 17:00 | 100% | ESTABLE |
| dukascopy:USDJPY | 2011 | 17:00 | 96% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2012 | 17:00 | 92% | 17:00 | 91% | 17:20→17:50 | 100% | — | — | ESTABLE |
| dukascopy:USDJPY | 2013 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2014 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2015 | 17:00 | 98% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2016 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2017 | 17:00 | 100% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2018 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2019 | 17:00 | 100% | 17:00 | 100% | 17:00→18:00 | 100% | — | — | ESTABLE |
| dukascopy:USDJPY | 2020 | 17:00 | 98% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2021 | 17:00 | 100% | 17:00 | 100% | 17:15→17:25 | 100% | 17:00 | 100% | ESTABLE |
| dukascopy:USDJPY | 2022 | 17:00 | 100% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2023 | 17:00 | 100% | 17:00 | 98% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2024 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2025 | 17:00 | 100% | 17:00 | 100% | — | — | — | — | ESTABLE |
| dukascopy:USDJPY | 2026 | 17:00 | 100% | 17:00 | 96% | — | — | — | — | ESTABLE |
| broker:USDJPY | 2022 | 16:55 | 98% | 17:00 | 98% | 16:55→17:05 | 92% | — | — | ESTABLE |
| broker:USDJPY | 2023 | 16:55 | 100% | 17:00 | 100% | 16:55→17:05 | 94% | — | — | ESTABLE |
| broker:USDJPY | 2024 | 16:55 | 98% | 17:00 | 100% | 16:55→17:05 | 98% | 16:55 | 100% | ESTABLE |
| broker:USDJPY | 2025 | 16:55 | 100% | 17:00 | 100% | 16:55→17:05 | 98% | 16:55 | 100% | ESTABLE |
| broker:USDJPY | 2026 | 16:55 | 100% | 17:00 | 98% | 16:55→17:05 | 93% | — | — | ESTABLE |

## 3. Sesiones escritas en engine.yaml

Estables (10): `broker:US100`, `broker:US500`, `broker:US30`, `broker:XAUUSD`,
`dukascopy:EURUSD`, `dukascopy:GBPUSD`, `dukascopy:USDJPY`, `broker:EURUSD`,
`broker:GBPUSD`, `broker:USDJPY`.

No escritas por inestabilidad (<60 % en algún año): `dukascopy:US100`,
`dukascopy:US500`, `dukascopy:US30`, `dukascopy:XAUUSD`. No se inventó un horario
único para ellas.

## 4. Data-check antes / después

Antes = HEAD `1a5049d` reproducido con `sessions=None` y el calendario previo
(índices `nyse`, FX/metales sin calendario). Después = R2j. Cada celda:
estado · huecos reales.

| Símbolo | TF | Antes | Después |
|---|---|---|---|
| US100 | M1 | WARN · 2857 | WARN · 2857 |
| US100 | M5 | WARN · 414 | WARN · 414 |
| US100 | M15 | WARN · 21 | WARN · 21 |
| US100 | M30 | WARN · 11 | WARN · 11 |
| US100 | H1 | FAIL · 870 | FAIL · 870 |
| US100 | H4 | FAIL · 814 | FAIL · 814 |
| US100 | D1 | WARN · 8 | WARN · 8 |
| US500 | M1 | WARN · 8949 | WARN · 8949 |
| US500 | M5 | WARN · 454 | WARN · 454 |
| US500 | M15 | WARN · 36 | WARN · 36 |
| US500 | M30 | WARN · 14 | WARN · 14 |
| US500 | H1 | FAIL · 872 | FAIL · 872 |
| US500 | H4 | FAIL · 814 | FAIL · 814 |
| US500 | D1 | FAIL · 18 | FAIL · 18 |
| US30 | M1 | WARN · 2018 | WARN · 2018 |
| US30 | M5 | WARN · 360 | WARN · 360 |
| US30 | M15 | WARN · 18 | WARN · 18 |
| US30 | M30 | WARN · 8 | WARN · 8 |
| US30 | H1 | FAIL · 867 | FAIL · 867 |
| US30 | H4 | FAIL · 806 | FAIL · 806 |
| US30 | D1 | WARN · 9 | WARN · 9 |
| XAUUSD | M1 | WARN · 26549 | WARN · 26549 |
| XAUUSD | M5 | WARN · 2417 | WARN · 2417 |
| XAUUSD | M15 | WARN · 122 | WARN · 122 |
| XAUUSD | M30 | WARN · 45 | WARN · 45 |
| XAUUSD | H1 | WARN · 171 | WARN · 171 |
| XAUUSD | H4 | WARN · 28 | WARN · 28 |
| XAUUSD | D1 | WARN · 17 | WARN · 17 |
| EURUSD | M1 | WARN · 597 | WARN · 597 |
| EURUSD | M5 | WARN · 35 | WARN · 35 |
| EURUSD | M15 | WARN · 6 | WARN · 6 |
| EURUSD | M30 | WARN · 1 | WARN · 1 |
| EURUSD | H1 | WARN · 3 | WARN · 3 |
| EURUSD | H4 | WARN · 0 | OK · 0 |
| EURUSD | D1 | WARN · 0 | OK · 0 |
| GBPUSD | M1 | WARN · 840 | WARN · 840 |
| GBPUSD | M5 | WARN · 36 | WARN · 36 |
| GBPUSD | M15 | WARN · 8 | WARN · 8 |
| GBPUSD | M30 | WARN · 3 | WARN · 3 |
| GBPUSD | H1 | WARN · 3 | WARN · 2 |
| GBPUSD | H4 | WARN · 0 | OK · 0 |
| GBPUSD | D1 | WARN · 0 | OK · 0 |
| USDJPY | M1 | WARN · 701 | WARN · 701 |
| USDJPY | M5 | WARN · 33 | WARN · 33 |
| USDJPY | M15 | WARN · 7 | WARN · 7 |
| USDJPY | M30 | WARN · 1 | WARN · 1 |
| USDJPY | H1 | WARN · 4 | WARN · 4 |
| USDJPY | H4 | WARN · 2 | WARN · 2 |
| USDJPY | D1 | WARN · 0 | OK · 0 |

### Cambios de estado

- EURUSD H4: WARN · 0 → OK · 0
- EURUSD D1: WARN · 0 → OK · 0
- GBPUSD H4: WARN · 0 → OK · 0
- GBPUSD D1: WARN · 0 → OK · 0
- USDJPY D1: WARN · 0 → OK · 0

Los WARN→OK con 0 huecos reales desaparecen porque el calendario `fx_metal` ya está configurado para EURUSD/GBPUSD/USDJPY; no se movió ningún hueco, solo se retira el aviso «sin calendario».

Ningún símbolo×TF empeora.

### FAIL que siguen

- **US100 H1**: 870 huecos reales.
- **US100 H4**: 814 huecos reales.
- **US500 H1**: 872 huecos reales.
- **US500 H4**: 814 huecos reales.
- **US500 D1**: 18 huecos reales.
- **US30 H1**: 867 huecos reales.
- **US30 H4**: 806 huecos reales.

Los índices de Dukascopy siguen sin sesión escrita porque su horario no alcanza el
60 % de estabilidad en 2013/2014 (domingo 56-58 %) y 2016/2017 (sin apertura de
domingo plausible). XAUUSD de Dukascopy es inestable en 2003/2004 y tampoco se
escribió; aun así no tiene FAIL, queda en WARN. Al no haber sesión, se mantiene el
comportamiento anterior.

Detalle de los FAIL que quedan (años y muestras de los huecos reales):

### US100 H1 — 870 huecos reales
Años: 2013: 13, 2014: 49, 2015: 188, 2016: 258, 2017: 257, 2018: 79, 2019: 10, 2020: 13, 2024: 1, 2025: 2
Causas: sesión: 870
Muestras: 2013-11-01T17:00:00-04:00, 2013-11-08T17:00:00-05:00, 2014-01-03T17:00:00-05:00, 2014-01-10T17:00:00-05:00, 2015-01-19T13:00:00-05:00, 2015-03-03T16:00:00-05:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T16:00:00-05:00, 2018-01-03T16:00:00-05:00, 2019-01-21T13:00:00-05:00, 2019-02-18T13:00:00-05:00

### US100 H4 — 814 huecos reales
Años: 2013: 21, 2014: 16, 2015: 187, 2016: 258, 2017: 257, 2018: 71, 2019: 1, 2020: 3
Causas: sesión: 814
Muestras: 2013-06-02T21:00:00-04:00, 2013-08-09T13:00:00-04:00, 2014-01-24T17:00:00-05:00, 2014-01-27T21:00:00-05:00, 2015-03-03T17:00:00-05:00, 2015-03-13T17:00:00-04:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T17:00:00-05:00, 2018-01-03T17:00:00-05:00, 2019-04-18T17:00:00-04:00, 2020-03-15T21:00:00-04:00

### US500 H1 — 872 huecos reales
Años: 2013: 12, 2014: 49, 2015: 199, 2016: 254, 2017: 255, 2018: 79, 2019: 11, 2020: 12, 2025: 1
Causas: sesión: 872
Muestras: 2013-11-01T17:00:00-04:00, 2013-11-08T17:00:00-05:00, 2014-01-01T08:00:00-05:00, 2014-01-03T17:00:00-05:00, 2015-01-19T13:00:00-05:00, 2015-02-12T16:00:00-05:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T16:00:00-05:00, 2018-01-03T16:00:00-05:00, 2019-01-21T13:00:00-05:00, 2019-02-18T13:00:00-05:00

### US500 H4 — 814 huecos reales
Años: 2013: 16, 2014: 17, 2015: 198, 2016: 254, 2017: 254, 2018: 71, 2019: 1, 2020: 3
Causas: sesión: 814
Muestras: 2013-06-02T21:00:00-04:00, 2013-08-09T13:00:00-04:00, 2014-01-01T09:00:00-05:00, 2014-01-22T17:00:00-05:00, 2015-02-12T17:00:00-05:00, 2015-02-13T17:00:00-05:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T17:00:00-05:00, 2018-01-03T17:00:00-05:00, 2019-04-18T17:00:00-04:00, 2020-03-15T21:00:00-04:00

### US500 D1 — 18 huecos reales
Años: 2013: 3, 2014: 1, 2015: 1, 2016: 7, 2017: 3, 2018: 1, 2019: 1, 2020: 1
Causas: sesión: 18
Muestras: 2013-10-01T17:00:00-04:00, 2013-10-11T17:00:00-04:00, 2014-02-05T17:00:00-05:00, 2015-02-20T17:00:00-05:00, 2016-03-01T17:00:00-05:00, 2016-03-24T17:00:00-04:00, 2017-04-13T17:00:00-04:00, 2017-05-09T17:00:00-04:00, 2018-03-29T17:00:00-04:00, 2019-04-18T17:00:00-04:00, 2020-04-09T17:00:00-04:00

### US30 H1 — 867 huecos reales
Años: 2013: 14, 2014: 44, 2015: 189, 2016: 258, 2017: 257, 2018: 79, 2019: 11, 2020: 12, 2024: 1, 2025: 2
Causas: sesión: 867
Muestras: 2013-11-01T17:00:00-04:00, 2013-11-08T17:00:00-05:00, 2014-01-03T17:00:00-05:00, 2014-01-10T17:00:00-05:00, 2015-01-19T13:00:00-05:00, 2015-02-15T20:00:00-05:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T16:00:00-05:00, 2018-01-03T16:00:00-05:00, 2019-01-21T13:00:00-05:00, 2019-02-18T13:00:00-05:00

### US30 H4 — 806 huecos reales
Años: 2013: 16, 2014: 14, 2015: 187, 2016: 258, 2017: 256, 2018: 71, 2019: 1, 2020: 3
Causas: sesión: 806
Muestras: 2013-09-30T13:00:00-04:00, 2013-10-01T17:00:00-04:00, 2014-01-24T17:00:00-05:00, 2014-01-27T17:00:00-05:00, 2015-03-03T17:00:00-05:00, 2015-03-13T17:00:00-04:00, 2016-01-04T17:00:00-05:00, 2016-01-05T17:00:00-05:00, 2017-01-03T17:00:00-05:00, 2017-01-04T17:00:00-05:00, 2018-01-02T17:00:00-05:00, 2018-01-03T17:00:00-05:00, 2019-04-18T17:00:00-04:00, 2020-03-15T21:00:00-04:00

## 5. Huecos reales → programados

Total de huecos que pasan de reales a programados: **1**.
Causas: festivo: 1.

- GBPUSD:H1: `2004-12-31T12:00:00-05:00` → `2004-12-31T14:00:00-05:00` · festivo

Huecos reales nuevos: **0**.

Ninguno: el clasificador con sesión no crea huecos reales nuevos; solo puede
reclasificar de real a programado.

Tabla completa por símbolo × TF:

| Símbolo | TF | Reales antes | Reales después | Movidos | Festivo | Cierre temp. | Pausa | Fin semana | Horario | Nuevos reales | % horario | Sospechoso |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| US100 | M1 | 2857 | 2857 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | M5 | 414 | 414 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | M15 | 21 | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | M30 | 11 | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | H1 | 870 | 870 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | H4 | 814 | 814 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US100 | D1 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | M1 | 8949 | 8949 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | M5 | 454 | 454 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | M15 | 36 | 36 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | M30 | 14 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | H1 | 872 | 872 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | H4 | 814 | 814 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US500 | D1 | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | M1 | 2018 | 2018 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | M5 | 360 | 360 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | M15 | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | M30 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | H1 | 867 | 867 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | H4 | 806 | 806 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| US30 | D1 | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | M1 | 26549 | 26549 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | M5 | 2417 | 2417 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | M15 | 122 | 122 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | M30 | 45 | 45 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | H1 | 171 | 171 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | H4 | 28 | 28 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| XAUUSD | D1 | 17 | 17 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | M1 | 597 | 597 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | M5 | 35 | 35 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | M15 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | M30 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | H1 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | H4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| EURUSD | D1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | M1 | 840 | 840 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | M5 | 36 | 36 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | M15 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | M30 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | H1 | 3 | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | H4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| GBPUSD | D1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | M1 | 701 | 701 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | M5 | 33 | 33 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | M15 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | M30 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | H1 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | H4 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |
| USDJPY | D1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% | no |

### SOSPECHOSO

Ninguno: ningún símbolo×TF supera el 5 % de movimientos por causa `horario`.

## 6. Cierre

`git status --short`:

```text
?? tl2-edge-map.patch
```

`git log --oneline -5`:

```text
06ecf30 tl2: R2j - calendarios por instrumento
1a5049d merge: principal (R2g + R2g-fix) en integración
cb5417d tl2: R2g - huecos de fin de semana por calendario
1886c20 orquestador: protocolo de relevo por archivos
f9666ef tl2: R2g - revertir umbral D1
```

- `pytest -q`: **1594 passed, 1 skipped (1003,67 s; 1 warning psutil)**.
- `ruff check src/tradinglab/discovery tests`: **limpio**.
- `lab propfund verify`: **OK en ai_trader (17), ea_us100_ftmo1 (18), ftmo_forward (8) y ftmo_risk (14)**.
- `count_tests`: **1676**.
- Tag `tl2-r2j` → `06ecf30`.

## Aviso

- El 60 % de estabilidad deja sin sesión a los índices y XAU de Dukascopy. En los
  índices eso mantiene los FAIL; en XAU mantiene los WARN. No se ha bajado el
  umbral ni se ha inventado el horario.
- La alternativa para una fase siguiente es decidir si se aceptan tramos parciales
  (p. ej. índices Dukascopy desde 2018) o si se usa el bróker para esos símbolos.
- No se ejecutaron campañas ni se leyó OOS-1/OOS-2. No se hizo push.

## Siguiente

PARA.
