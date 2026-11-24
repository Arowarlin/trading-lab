# RESULTADO · tom-anclaje — `month_turn` mapea por sesión NYSE

Fecha: 2026-11-23. Sesión única en `E:\trading-lab`, HEAD `4d6f2c0`.
Sin register/approve/run/confirm/supersede, sin OOS, sin rendimiento, sin push,
sin tareas programadas, sin borrar, sin umbrales, sin protegidos.

## 1. Evidencia con datos reales (solo fechas)

D1 de US500 (Dukascopy), 2011-09-18…2026-11-19, 3.751 barras. La etiqueta D1
es la **apertura** de la sesión: 17:00 de Nueva York del día anterior. Por eso
la sesión del viernes se etiqueta como jueves y la del lunes como domingo. La
barra `2024-06-27 21:00 UTC` = `2024-06-27 17:00 NY` cubre la sesión del
viernes `2024-06-28`; no existe una barra etiquetada `2024-06-28`.

Antes del cambio, `compiler.py:388-389` (`HEAD`) construía `local` y
`dates = [stamp.date() for stamp in local]`, es decir, mapeaba por la **fecha de
la etiqueta**. Con datos reales eso producía dos fallos:

- cuando la fecha de sesión también era una etiqueta (p. ej. martes 31 de
  enero), la entrada caía en la barra siguiente y se ejecutaba un día tarde;
- cuando la sesión terminaba en viernes o víspera de festivo (p. ej. viernes
  28 de junio de 2024), no había etiqueta con esa fecha y el mes se perdía.

Conteo de señales con N=1, M=2 en todo el histórico (solo fechas, no
rendimiento): **69 antes**, **173 después**. El calendario NYSE genera 182
pares; 9 no tienen barra (huecos de datos al principio de la serie y en
2013/2016). El motor omite esos pares, no los inventa.

## 2. Tablas de fechas (N=1, M=2)

La barra de señal se etiqueta con su apertura; la entrada se ejecuta al cierre
de esa barra. El cierre nominal es la etiqueta + 1 día a las 17:00 NY (o el
cierre real si el día es de cierre temprano).

| Mes | Día hábil N | Barra señal (UTC → NY) | Sesión entrada | Cierre entrada | Día M | Barra salida (UTC → NY) | Sesión salida | Cierre salida |
|---|---|---|---|---|---|---|---|---|
| 2023-01 | 2023-01-31 | 2023-01-30 22:00Z → 17:00 NY | 2023-01-31 | 2023-01-31 17:00 NY | 2023-02-02 | 2023-02-01 22:00Z → 17:00 NY | 2023-02-02 | 2023-02-02 17:00 NY |
| 2023-02 | 2023-02-28 | 2023-02-27 22:00Z → 17:00 NY | 2023-02-28 | 2023-02-28 17:00 NY | 2023-03-02 | 2023-03-01 22:00Z → 17:00 NY | 2023-03-02 | 2023-03-02 17:00 NY |
| 2023-03 | 2023-03-31 | 2023-03-30 21:00Z → 17:00 NY | 2023-03-31 | 2023-03-31 17:00 NY | 2023-04-04 | 2023-04-03 21:00Z → 17:00 NY | 2023-04-04 | 2023-04-04 17:00 NY |
| 2024-01 | 2024-01-31 | 2024-01-30 22:00Z → 17:00 NY | 2024-01-31 | 2024-01-31 17:00 NY | 2024-02-02 | 2024-02-01 22:00Z → 17:00 NY | 2024-02-02 | 2024-02-02 17:00 NY |
| 2024-02 | 2024-02-29 | 2024-02-28 22:00Z → 17:00 NY | 2024-02-29 | 2024-02-29 17:00 NY | 2024-03-04 | 2024-03-03 22:00Z → 17:00 NY | 2024-03-04 | 2024-03-04 17:00 NY |
| 2024-03 | 2024-03-28 | 2024-03-27 21:00Z → 17:00 NY | 2024-03-28 | 2024-03-28 17:00 NY | 2024-04-02 | 2024-04-01 21:00Z → 17:00 NY | 2024-04-02 | 2024-04-02 17:00 NY |

## 3. Tablas de fechas (N=2, M=4)

| Mes | Día hábil N | Barra señal (UTC → NY) | Sesión entrada | Cierre entrada | Día M | Barra salida (UTC → NY) | Sesión salida | Cierre salida |
|---|---|---|---|---|---|---|---|---|
| 2023-01 | 2023-01-30 | 2023-01-29 22:00Z → 17:00 NY | 2023-01-30 | 2023-01-30 17:00 NY | 2023-02-06 | 2023-02-05 22:00Z → 17:00 NY | 2023-02-06 | 2023-02-06 17:00 NY |
| 2023-02 | 2023-02-27 | 2023-02-26 22:00Z → 17:00 NY | 2023-02-27 | 2023-02-27 17:00 NY | 2023-03-06 | 2023-03-05 22:00Z → 17:00 NY | 2023-03-06 | 2023-03-06 17:00 NY |
| 2023-03 | 2023-03-30 | 2023-03-29 21:00Z → 17:00 NY | 2023-03-30 | 2023-03-30 17:00 NY | 2023-04-06 | 2023-04-05 21:00Z → 17:00 NY | 2023-04-06 | 2023-04-06 17:00 NY |
| 2024-01 | 2024-01-30 | 2024-01-29 22:00Z → 17:00 NY | 2024-01-30 | 2024-01-30 17:00 NY | 2024-02-06 | 2024-02-05 22:00Z → 17:00 NY | 2024-02-06 | 2024-02-06 17:00 NY |
| 2024-02 | 2024-02-28 | 2024-02-27 22:00Z → 17:00 NY | 2024-02-28 | 2024-02-28 17:00 NY | 2024-03-06 | 2024-03-05 22:00Z → 17:00 NY | 2024-03-06 | 2024-03-06 17:00 NY |
| 2024-03 | 2024-03-27 | 2024-03-26 21:00Z → 17:00 NY | 2024-03-27 | 2024-03-27 17:00 NY | 2024-04-04 | 2024-04-03 21:00Z → 17:00 NY | 2024-04-04 | 2024-04-04 17:00 NY |

Casos especiales que antes se perdían o se desplazaban:

| Par | Sesión entrada | Barra señal | Sesión salida | Barra salida |
|---|---|---|---|---|
| 2024-06-28 → 2024-07-02 | viernes 2024-06-28 | 2024-06-27 21:00Z → 2024-06-27 17:00 NY | martes 2024-07-02 | 2024-07-01 21:00Z → 2024-07-01 17:00 NY |
| 2024-11-29 → 2024-12-03 | viernes 2024-11-29 (tras Acción de Gracias) | 2024-11-28 22:00Z → 2024-11-28 17:00 NY | martes 2024-12-03 | 2024-12-02 22:00Z → 2024-12-02 17:00 NY |

## 4. Respuesta

**Con el código corregido, sí**: la estrategia entra al cierre de la sesión
NYSE del día hábil N antes de fin de mes y sale al cierre de la sesión del día
hábil M del mes siguiente. La sesión se identifica por el intervalo
17:00→17:00 de Nueva York, no por la fecha de la etiqueta.

**Antes había desfase de un día** (o pérdida del mes) porque `month_turn`
mapeaba por la etiqueta. La corrección está en:

- `src/tradinglab/discovery/compiler.py:384-401`: `_session_dates` convierte
  cada etiqueta en la sesión NYSE que cubre (17:00 NY como frontera).
- `src/tradinglab/discovery/compiler.py:414-432`: `_month_turn_signals` usa
  esas fechas de sesión para `last_pos`, `month_turn_pairs`, la señal y
  `exit_index`. El cierre de la barra de señal es el cierre de la sesión.

Las specs `r9-tom-us500-d1.yaml` y `r9-tom-us100-d1.yaml` **no se han
modificado**: mismos instrumentos, fechas, grid y parámetros.

## 5. Tests

`tests/test_discovery_turn_of_month.py`: **8 passed**.

- `test_senales_y_salida_coinciden_con_el_calendario` ahora compara la
  **sesión** de la barra, no su etiqueta.
- `test_mapea_por_sesion_y_no_por_etiqueta`: frame D1 con una barra por sesión
  NYSE, etiquetada el día anterior a las 17:00 (como los datos reales). Cubre
  junio 2024 (mes que termina en viernes) y noviembre 2024 (último día tras
  Acción de Gracias).
- `test_n2_m4_mapea_por_sesion_en_datos_reales`: N=2, M=4, con el 4 de julio
  como festivo; la salida es el 5 de julio y su barra se etiqueta el 4.
- `test_ejecuta_al_cierre_y_sale_el_dia_m` también valida la sesión.

## 6. Q1 · `d1_extension_reversion`

No usa calendario. La entrada es `zscore`/`SMA(200)`/`RSI(2)` y el motor usa
stop ATR, target 1R y `time_exit_minutes`; no hay `month_turn` ni pares
entrada/salida por fecha. Por tanto, el anclaje D1 no le afecta. Ver
`config/discovery/templates/d1_extension_reversion.yaml`.

## 7. Campañas r9-tom ya ejecutadas (no tocadas)

| Campaña | Estado | n_total | n_evaluated | Estrategias | Evaluaciones | Jobs | Aprobada |
|---|---|---:|---:|---:|---:|---:|---|
| `r9-tom-us500-d1` | `done` | 9 | 9 | 9 | 10 | 0 | 2026-11-24 02:11:18Z |
| `r9-tom-us100-d1` | `done` | 9 | 9 | 9 | 9 | 0 | 2026-11-24 02:12:38Z |

No se han tocado sus snapshots, especificaciones ni resultados. Fueron
ejecutadas con el mapeo antiguo, así que sus señales no coinciden con el
código corregido.

### `supersede` no puede retirarlas con el código actual

El comando que pedía la cola **fallaría**:

- `src/tradinglab/discovery/campaigns.py:701` exige estado `rejected` o
  `registered`; ambas están `done`.
- `src/tradinglab/discovery/campaigns.py:705` rechaza campañas con
  evaluaciones; ambas tienen `n_evaluated=9` y US500 tiene 10 filas de
  evaluación.
- La CLI (`src/tradinglab/cli.py:11162-11167`) no acepta `--reason`, y
  `campaigns.supersede` (`src/tradinglab/discovery/campaigns.py:677-683`)
  tampoco recibe un motivo: usa `reject_reason`/`last_error` de la campaña.
- `supersede` crea su propio id `disc-…`, no un `r9b-…`.

Por eso no se ejecutó nada y se para para decisión humana. Las opciones son:

1. **Registrar `r9b-…` sin retirar las viejas**: no requiere cambiar código,
   pero suma 9+9 pruebas al contador (doble conteo de la misma hipótesis).
   Las specs `r9b-tom-us500-d1.yaml` y `r9b-tom-us100-d1.yaml` quedan
   preparadas, idénticas salvo `campaign_id`.
2. **Autorizar un cambio de `supersede`** para campañas `done` con un motivo
   auditado: la vieja pasaría a `superseded` y dejaría de contar
   (`campaigns.py:972`), sin doble conteo. Es una decisión de integridad de la
   investigación y no se implementa en esta sesión.
3. `invalidate` no sirve para el contador: una campaña `invalid` sigue
   contando porque `discovery_tests` solo excluye `superseded`.

## 8. Verificación

- `ruff check src/tradinglab tests docs`: limpio.
- `pytest -q`: **1796 passed, 1 skipped**.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1865** (sin cambios; no se ejecutó `record-informal`).
- Sin register/approve/run, sin OOS-2, sin push, sin descargas.

Commit `tl2: month_turn - anclaje por sesión`, tag `tl2-tom-anclaje`.

PARA.
