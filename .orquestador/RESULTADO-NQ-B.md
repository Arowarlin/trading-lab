# RESULTADO NQ-B · Enmienda A: puente, validez NQ y prueba

- **Fecha:** 2026-11-25
- **Opción:** **A** (aprobada por el operador en esta sesión)
- **Commit:** `tl2: NQ-B - prueba fuera de periodo`
- **Tag:** `tl2-nq-b`
- **Cuenta:** A-1 y A-2 son **paridad, no suma**. `count_tests` = **1895**.

## B1 · Descarga

| Concepto | Valor |
|---|---:|
| Dataset | GLBX.MDP3 |
| Símbolo | `NQ.c.0` (futuro CME) |
| Schema | OHLCV-1m |
| Archivo | `data/cache/databento/US100_M1.parquet` (etiqueta interna; es NQ) |
| Filas | **2.720.203** |
| Inicio / fin | 2010-06-07 00:00 → 2018-12-31 21:59 UTC |
| Columnas | open, high, low, close, volume |
| **Coste cobrado (suma de cargos del fetcher)** | **USD 9,930875** |

La descarga se hizo por tramos anuales porque `metadata.*` devolvía 504 con
el rango completo. El primer intento completó 2010-2015; un 504 en 2016 se
resolvió relanzando **solo** 2016-2018 con el mismo coste aprobado. No hubo
descarga duplicada. Coste por tramo:

| Tramo | USD |
|---|---:|
| 2010-06-06 → 2011-01-01 | 0,619987 |
| 2011 | 1,132375 |
| 2012 | 1,127315 |
| 2013 | 1,097236 |
| 2014 | 1,103263 |
| 2015 | 1,170613 |
| 2016 | 1,200104 |
| 2017 | 1,222319 |
| 2018 | 1,257662 |
| **Total** | **9,930875** |

## E1 · Cambios de contrato

`metadata.get_symbology` para `NQ.c.0` devolvió **HTTP 404** (sin coste). No
se repitió. Se aplicó la regla de respaldo CME §3.3.3:

- tercer viernes de marzo/junio/septiembre/diciembre, 2010-2018;
- exclusión desde el jueves 8 días naturales antes hasta la primera sesión
  posterior, ambos incluidos;
- **36 rolls**, **288 sesiones** excluidas;
- `.orquestador/nq-rolls.json` con `source`, `rolls` y `excluded_sessions`.

## E0 · Código, festivos y tests

- `--reference-m1`, `--bridge`, `--roll-dates`; `k` contra la referencia
  Dukascopy, nunca contra la caché del EA.
- §3.5: se excluyen festivos NYSE, cierres especiales y cierres tempranos de
  `discovery/calendars.py` en A-2 (ambos lados) y B3, contados por año.
- A-1 no cambia: el calendario del motor cubre 2022 en ambos lados.
- `pytest` dirigido: **10 passed**; `ruff`: limpio.
- El filtro de noticias (`InpNewsFilter`) no está modelado, igual que en las
  478 operaciones del backtest.

## E2 · A-1 Puente Dukascopy vs US100.cash (2022)

`reports/ea/us100-ftmo1-nq-bridge.md`

| Métrica | Valor |
|---|---:|
| Operaciones Dukascopy | 85 |
| Operaciones US100.cash | 84 |
| Emparejadas | 72 (**85,7 %**) |
| Correlación de R | **0,9129** |
| ¿Válida? | **Sí** |

Solo paridad: no se calcularon expectativa, PF ni R totales de 2022.

## E3 · A-2 Validez NQ 2018

`reports/ea/us100-ftmo1-nq-2010-2017.md`

| Métrica | Valor |
|---|---:|
| Operaciones NQ | 87 |
| Operaciones referencia | 81 |
| Emparejadas | 62 (**76,5 %**) |
| Correlación de R | 0,9538 |
| ¿Válida? | **No** |

`k = 0,9957` (ATR14 M5 NQ / Dukascopy 2018), dentro de [0,9; 1,1]: no se
escaló nada. Se excluyeron 89 operaciones NQ por roll y 13 por
festivos/cierres; en la referencia, 80 y 15.

**El 76,5 % < 80 % incumple el umbral de emparejamiento.** La correlación
(0,9538) sí supera 0,7, pero el criterio exige las dos. Por tanto:

**Prueba no válida (Sin datos).** No se abre 2010-2017. **B3 no se ejecutó**;
no se calcularon expectativa, PF, DD ni LCB de NQ 2010-2017. No hay
reinterpretación: el fallo es de validez del adaptador, no del EA.

### Lectura

- **No válida en A-1:** no ocurrió; el procesado Dukascopy reproduce al
  bróker (85,7 %, 0,91).
- **No válida en A-2:** NQ (futuro, volumen de contratos) no reproduce al CFD
  con este adaptador al 80 % de operaciones. La prueba NQ 2010-2017 no es
  posible con este diseño.
- Esto **no** dice nada sobre la ventaja del EA; dice que la réplica NQ no es
  suficientemente fiel para usarla como prueba fuera de periodo.

## Cumplimiento

- No se tocó el EA, el setfile, `ea_us100_engine.py` ni `nq_adapter.py`.
- No se ejecutó B3 ni se miró el rendimiento de 2010-2017.
- Sin campañas, OOS, `confirm`, push, borrado ni órdenes.
- `count_tests` = 1895; A-1/A-2 no suman pruebas.
