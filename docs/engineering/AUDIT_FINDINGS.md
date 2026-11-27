# AUDIT_FINDINGS · Programa ENG-1 (consolidado de la Fase 1)

**SHA auditado:** `adc0eec` · **Fecha:** 2026-11-26 · **Consolidó:** Claude Code.
**Fuentes:** `WORKER_REPORTS/A-engine.md`, `B-costs.md`, `C-data.md`, `D-stats.md` y `BASELINE_REPORT.md`.
El detalle de cada hallazgo (código, script de reproducción, corrección y test propuestos) está en el
informe de su trabajador. Aquí solo van la prioridad, el grado de verificación y la consecuencia.

**Grado de verificación:**
- **V1:** Claude leyó el código y volvió a ejecutar la reproducción.
- **V2:** Claude leyó el código y confirmó el mecanismo.
- **R:** reproducido solo por el trabajador (sintético), pendiente de revisión independiente.

Todo es **sintético**. Ningún hallazgo se midió con datos reales: su magnitud real es **Sin datos**
hasta que se reproduzca en el equipo del operador (`OPENCODE_PROMPTS.md`).

## 1. HIGH

| ID | Hallazgo | Sesgo | Verif. | Bloqueado por EDGE-2 | Siguiente paso |
|---|---|---|---|---|---|
| **D-01** | El WF de robustez corre sobre el **IS** del frontier que eligió el GA (`robustness.py:325-345`): no es fuera de muestra. Con ruido, el stitched Sharpe sale > 0 el 90 % de las veces | Puerta WF **laxa** | V2 | Sí (metodología) | Rediseño prerregistrado: WF con re-selección dentro de cada pliegue o WF sobre OOS-1 |
| **D-02** | El PBO se calcula sobre el **frontier final**, no sobre la población probada. Con 5 estrategias con ventaja real, P(PBO ≤ 0,30) baja del 47 % (población) al 3 % (top-40). Con un frontier mixto, el ruido pasa el 97,5 % | Puerta PBO **sin sentido**: rechaza ventajas reales o aprueba ruido según cómo se forme el frontier | R (simulación) | Sí | PBO sobre una muestra de la población evaluada; prerregistro |
| **D-03** | DSR de `confirm` (`levels.py:402-428`): con k = 1 es un PSR contra 0 **sin deflación**; con k > 1, V[SR] de ≤ 5 finalistas y N por campaña, aunque todas las campañas leen el **mismo** OOS-2. Falso positivo del 23-31 % al elegir el mejor de K | **Laxo** en el último control | V2 | Sí | V[SR] de la población y N = `count_tests`, o control conjunto (Holm/Romano-Wolf) sobre todas las lecturas del OOS-2 |
| **A-01** | `weekdays` se filtra por el día civil de la etiqueta (`fastbt.py:1584`). D1 y H4 del domingo por la noche (etiqueta de las 17:00 NY) quedan fuera: **no se evalúa el stop** ni se entra. En la reproducción, un mínimo en 90 no dispara un stop en 98 | **A favor** (stops ciegos en la reapertura del domingo) | V1 | Sí (`fastbt.py`) | Test sintético + parche en rama, sin integrar |
| **A-02** | Mientras la posición "duerme" (fallo de `flat_at`, ya en MOTOR-FLAT) el stop y el objetivo **no se evalúan** fuera de `allowed` | **A favor** | R | Sí | Añadir a MOTOR-FLAT: gestionar el stop también en `legacy` o declararlo |
| **B-01** | Comisión por lote en USD dividida por un nominal en **JPY** en USDJPY (`fastbt.py:343-353`): ≈150 veces menor; faltan ≈0,037 R por operación con un stop de 20 pips (el límite `cost_r_max` es 0,10) | **A favor** en USDJPY | V2 | Sí (`fastbt.py`) | Parche con la divisa cotizada de `config/costs.yaml` |
| **B-02** | La confirmación por cuenta en OOS-2 (`levels.py:334`) crea un `CostBook` **v1** en campañas v2 (doble spread + p75) | **En contra** | R | Sí | Pasar `cost_model_version` de la campaña |
| **B-03** | Robustez, perturbación, `levels` (neto base) y `retest` usan `cost_from_profile` (una cuenta, p75 estático) en lugar del `CostBook` del fitness: **la validación usa otro modelo de coste que la selección** | Ambiguo | R | Sí | Un único constructor de coste por campaña. **Corregido con v3 (2026-11-27):** `costs.validation_cost` + `applied_result` (coste por operación); v2 y campañas legacy sin cambios. `retest` recibe el panel envolvente del libro |
| **C-01** | `data-check` en M1-M30 descarta sin clasificar todo hueco ≥ `max_gap_hours` (`data_quality.py:591`). Con los mismos minutos ausentes, M15 da `ok` y H4 da `fail`. Contradice la conclusión de EDGE-2 Y0 ("no es un error del control") | Datos con huecos aceptados en M15/M30 | V1 | Sí (afecta al plan Y1 congelado) | Medir con datos reales cuántos huecos así hay en el IS de las campañas M15/M30 de EDGE-2 (tarea L) |
| **C-02** | La reanudación de Dukascopy da por completo un mes cuya última vela cae el día ≥ 20: los últimos días del mes se pierden **para siempre** y los 404 cuentan como "sin mercado" (`fetch_dukascopy.py:357-361, 416-424`) | Huecos silenciosos (también en OOS-2) | V1 | No (fetch); sí si se re-descarga la caché de una campaña viva | Contar con datos reales los meses afectados en la caché actual (tarea L) |
| **C-04** | Futuros `databento` registrables como "US100" con cuentas de coste CFD; los rolls `c` y `v` escriben sobre el mismo fichero | Mezcla futuros/CFD | R (amplía G-2/D2 conocidos) | No | Bloquear la combinación en `register`/`preflight` |

## 2. MEDIUM con efecto directo en las decisiones

| ID | Hallazgo | Sesgo | Verif. |
|---|---|---|---|
| D-07 | `daily_r` solo contiene los días con alguna salida (`fastbt.py:2046-2051`) y se anualiza con √252 (`metrics.py:83`): Sharpe ×1,5 con 100 días de operación al año y ×2,6 con 40. ROBUST-1 R2 lo corrigió en la matriz del PBO, no aquí. También entra en el DSR de `confirm` | **A favor** (baja frecuencia) | V2 |
| D-04 | `family.spa_test` no es el SPA de Hansen. Con autocorrelación 0,3 rechaza la nula el 29 % de las veces en vez del 5 % | Laxo | R |
| D-05 | La puerta `mc_trades` equivale a "expectativa > 0"; el remuestreo i.i.d. infravalora las colas del DD | Laxo | R |
| D-06 | La potencia cuenta OOS-1+OOS-2 como holdout, aunque `confirm` solo usa OOS-2 (87 operaciones estimadas frente a 51) | Laxo | R |
| A-03 | En sesiones de 24 h no se opera la última vela del día civil (1 de cada 6 en H4) | Neutro (diverge del EA) | R |
| A-04 | `_calendar_core`: la salida por calendario va antes que el stop | A favor | R |
| B-04 | El triple swap cae un día antes (índices: viernes→jueves). **Requiere cola de producción** (`propfund/costs.py`) | A favor (cortos de índice) | R |
| B-10 | `slippage_plus_2` añade +0,8 % a +13 % en índices y oro: la puerta 3 no discrimina | Laxo | R |
| C-03, C-05, C-06 | Vela parcial tratada como cerrada; `detect_rolls` borra saltos reales; `gap_pct` cuenta eventos | Calidad de datos | R |

LOW y latentes: A-05..A-10, B-05..B-09, B-11..B-14, C-07..C-14, D-08..D-12 (ver informes).
**C-07** (Año Nuevo en sábado) afecta a `nyse_calendar`, que usa el EA: requiere cola de producción.

## 3. Entorno, CI y reproducibilidad (Fase 0)

| ID | Hallazgo | Verif. | Tarea |
|---|---|---|---|
| **F0-08 (HIGH)** | **La suite escribe en el laboratorio real y puede enviar alertas reales.** Los tests sin marcador (`test_freshness`, `test_intraday_bots`, entre otros) llaman a `orchestrator` y `alerts.send` con `DEFAULT_DB` = `data/lab.db`. Esto deja alertas falsas (incluida una **crítica**: "paper_main: posición BTCUSD sin SL"), filas de `data_freshness`, un `INSERT OR IGNORE` en `learning_holdout` y sobrescribe `data/telegram_state.json`. `AlertConfig.from_env()` carga `.env` y el keyring, así que en el equipo del operador esas alertas **pueden salir por ntfy/Telegram**. Probado aquí con `NTFY_TOPIC` en el entorno: **5 envíos intentados** sin el fixture, 0 con él. Que llegaran de verdad en el equipo del operador: **Sin datos** (no hay keyring aquí) | V1 | ENG-F4 (fixture `_no_real_secrets`, hecho en la rama); ENG-F5 (redirigir `DEFAULT_DB` en los tests; toca `config.py`, requiere aprobación) |
| F0-01/05 | `uv.lock` desfasado: faltan `arch` y la extra `discovery` (numba). La prueba SPA no corre en una instalación limpia | V1 | ENG-F3 |
| F0-03 | CI en rojo: 43 tests dependen del equipo del operador (`lab.db` con `broker_spreads`, terminal MT5, `data/cache`, `discovery.db`, `reports/research/*.json`) | V1 | ENG-F2 |
| F0-06 | Un error en `_init_worker` aparece como `BrokenProcessPool` y se pierde el "Sin datos" real | V1 | Con ENG-F2b |
| F0-07 | **Fuga de aislamiento:** `test_optimize` y `test_research` pasan en el equipo del operador solo porque el DSR global lee los informes reales de `reports/research/` (`global_dsr.py:188`). Su resultado depende de lo que haya en disco | V1 | ENG-F2 |
| F0-02 | `engine_version` = `0.1.0` desde siempre: no distingue el motor de antes y después de ROBUST-1 | V1 | Con MOTOR-FLAT (sube la versión) |

## 3b. Discovery: qué no puede encontrar el motor (`WORKER_REPORTS/E-edge.md`)

| ID | Hallazgo | Verif. |
|---|---|---|
| E-01 | `genetic.mutate_session` tiene fija la ventana 09:30-15:00 (`genetic.py:425`). En las plantillas de Asia, Londres y 24 h **toda** mutación de sesión se descarta (0/200 frente a 147/200 en `ny_open`): el GA nunca exploró el horario en FX ni en índices 24 h | V2 |
| E-02 | Los finalistas se eligen por OOS-1 **sin un n mínimo**: los cinco de `edge1-07` pasaron con 1 operación en OOS-1 | R |
| E-03 | `edge_map.py:437-446` etiqueta "sin edge bruto" casos con bruto **y** neto positivos (turn_of_month US100, d1_extension_reversion US100, donchian XAU) | R |
| E-04 | **Contador:** EDGE-1 registró 12.320 pruebas, pero `count_tests` subió +10.768. Faltan **1.552** sin explicar. Verificar en `discovery.db` (tarea L) | R (documentos) |
| E-05 | `ESTADO.md` §3 dice "Y2 no se lanza en esta sesión", pero `554497c` muestra 4 campañas EDGE-2 terminadas: ESTADO está desfasado | V1 (git) |
| E-06 | Estructural: solo OHLCV (sin order flow; VWAP con volumen 1 si falta), sin nodo de eventos ni señales entre activos, todo en R con stop ATR. Con `cost_r ≤ 0,10` la microestructura de stop corto queda fuera (NQ: stop ≥ ~12,7 pt) | R |

**Potencia** (unilateral, α 0,05, 80 %; comprobado por Claude): para 0,1 R hacen falta
**619 / 1.212 / 2.233** operaciones con σ = 1,0 / 1,4 / 1,9 R. Los 22 finalistas de EDGE-1 hacen
6-58 operaciones al año en IS. **EDGE-1 descarta ventajas de ≳0,3-0,4 R en esas plantillas, pero no
dice nada de 0,05-0,15 R.**

## 4. Qué significa esto para los veredictos

1. **"EDGE-1: 0 robustas" no demuestra que no haya ventaja.** La puerta que más rechazó fue el PBO
   (> 0,30 en la mayoría). D-02 muestra que el PBO calculado sobre un frontier de las mejores tiende
   a dar más de 0,30 **incluso con ventaja real** (P(PBO ≤ 0,30) = 3 % en la simulación). Lo que se
   puede afirmar es más débil: con estas herramientas no se puede distinguir.
2. **A la vez, otras puertas son laxas** (D-01, D-03, D-04, D-05, D-07) y hay sesgos del motor a favor
   (A-01, A-02, B-01). Si EDGE-2 deja algún candidato, **no** debe considerarse confirmado hasta
   repetir su evaluación con las herramientas corregidas, como hizo ROBUST-1 con EDGE-1.
3. **No hace falta parar EDGE-2.** Sus campañas guardan las estrategias y los resultados por
   barra/operación; las puertas se pueden volver a calcular después sin sumar pruebas al contador.
   Parar exigiría la aprobación del operador y no aporta nada.
4. **Lo que más aumenta la capacidad de encontrar una ventaja real** no es más campañas: es arreglar
   D-01/D-02/D-03 (que la validación mida lo que dice medir) y tener datos de calidad conocida
   (C-01/C-02).

## 5. Orden de corrección propuesto

| Orden | Bloque | Archivos | Cuándo |
|---|---|---|---|
| 0 | ENG-F4: los tests no ven secretos reales ni envían alertas (hecho en la rama, `tests/conftest.py`). ENG-F5: `DEFAULT_DB` configurable para los tests | `tests/conftest.py`; F5: `config.py` | F4 ya; F5 con aprobación |
| 1 | ENG-F2a: marcar `local` los tests que necesitan el equipo del operador (MT5, caché, `reports/`) | `tests/…`, `pyproject.toml`, `ci.yml` | Ya (solo tests) |
| 2 | ENG-F3: `uv lock` con `arch` y numba | `uv.lock` | Decisión del operador |
| 3 | ENG-M1: motor (A-01, A-02, B-01, D-07) como **tests rojos + parche en rama**, con modo `legacy` idéntico bit a bit | `fastbt.py`, `metrics.py` | Parche ya; integración tras el tag `edge2` |
| 4 | ENG-S1: rediseño estadístico (D-01, D-02, D-03, D-06) con **prerregistro** | `robustness.py`, `levels.py`, `power.py` | Tras `edge2`; cambiar puertas requiere aprobación |
| 5 | ENG-C2: datos (C-01, C-02, C-04) | `data_quality.py`, `fetch_dukascopy.py`, `register` | C-02 y C-04 ya en rama; C-01 tras `edge2` |
| 6 | Costes (B-02, B-03) | `levels.py`, `robustness.py`, `perturb.py` | Tras `edge2` |
| 7 | Producción (B-04, C-07, B-14) | `propfund/costs.py`, `nyse_calendar.py`, `execution/mt5.py` | Cola de producción de AGENTS.md (baseline, tag `-pre`, CHANGELOG) |

## 6. Cifras reales del equipo del operador (informes L, 2026-11-26)

| Hallazgo | Resultado real | Fuente |
|---|---|---|
| **F0-08** | **1.210 alertas de test enviadas de verdad por ntfy** (`ok = 1`) entre el 2026-11-09 y el 2026-11-26 17:44 UTC; 130 intentos fallidos. Incluyen `missing_sl … BTCUSD` (crítica). Ritmo ≈ 16 ejecuciones al día: cada `pytest` que lanzan las sesiones de agentes. La tabla `data_freshness` tiene filas de test intercaladas con las reales (EURUSD M15 `last_bar` 2025-01-03 y 2025-03-14). El `learning_holdout` es el real (sellado el 2026-11-07): el `INSERT OR IGNORE` de los tests no lo pisó | `WORKER_REPORTS/L1a-alertas.md` |
| **C-01** | US100 y US500: **650 y 655 huecos ≥ 4 h entre semana dentro del IS 2015-2019** de EDGE-2 M15/M30; casi todos nocturnos 16:00→02:00 NY (10 h), sobre todo en 2015-2017 (~200 al año). `data-check` los dio por buenos en M15/M30. Las campañas `edge2-13` a `edge2-18` (US100 M15/M30) se evaluaron sin la sesión nocturna en cientos de noches. FX: 7 huecos en el IS; XAUUSD: 44 | `WORKER_REPORTS/L1b-datos.md` |
| **C-02** | Meses truncados reales: US100 y US500 **2013-02** (faltan del 25 al 28) y 2011-09 (inicio de la serie). Ninguno dentro de los IS de EDGE-1/EDGE-2. FX y oro: ninguno | `L1b-datos.md` |
| **E-04** | 440 de las pruebas que faltan son `edge1-13-fix-reversal-xauusd-h1`, que quedó en `draft` (no cuenta). EDGE-1 suma 11.880, no 12.320. El resto de la diferencia con el +10.768 de ESTADO (1.112) **no se explica** con este dato: el 1.926 inicial pudo incluir otras fuentes. Sin impacto en el DSR (cuenta de más, no de menos) | `L1d-contador.md` |
| **C1 (prep.)** | **La caché USDJPY no tiene ASK** en 2003-2022 (`ask_open` vacío en las 10.234 velas de la ventana). C1, tal como está prerregistrado (entrada al ASK), **no se puede ejecutar**: Sin datos. Festivos JP descargados (1955-2027, 1.067 fechas) | `L2-c1-prep.md` |
| Estado | En el equipo del operador ya existen los tags `edge2` y `motor-flat`: EDGE-2 y MOTOR-FLAT están cerradas. **No** hay ningún `lab discovery run` vivo. Esos commits no están en `origin/master` | `L0-estado.md` |

## 7. EDGE-2 y WF-TF a la luz de la auditoría (2026-11-26, tras `edge2` y `wf-tf-1`)

- **EDGE-2:** 12/18 campañas ejecutadas (6 bloqueadas por `feasibility < 50 %`), 12 finalistas,
  **0 pasan Y3**; con WF-TF también 0 de 12. Todos fallan la puerta 2: PBO 0,31-0,86 y WF sin pliegues
  suficientes (1 pliegue en H4: el IS H1/H4 empieza en 2019).
- **Mismas limitaciones que EDGE-1:** el WF corre sobre el IS del frontier (D-01) y el PBO sobre el
  frontier (D-02). Con 1 pliegue en H4 no hay walk-forward posible. **EDGE-2 no aporta evidencia ni a
  favor ni en contra** de una ventaja de tamaño realista en índices.
- **C-01 casi no afectó a EDGE-2:** de las 6 campañas US100 M15/M30 (las de las ~650 noches sin datos),
  5 quedaron bloqueadas por `feasibility` y la única ejecutada (`edge2-14`) no dejó finalistas.
- El OOS-2 sigue **sin leer** en EDGE-1 y en EDGE-2.

## 8. Evidencia del test de ruido (`test_discovery_noise::test_noise_five_campaigns`, motor 0.3.0)

- 5 campañas GA sobre **ruido puro** con spreads sintéticos realistas (0,8-2,3 bps): la media OOS-1 de
  los candidatos es **−0,049 R** (73 candidatos). Bien: el ruido no parece rentable después de costes.
- Pero las 5 campañas dejan **7 finalistas con OOS-1 positivo** (+0,32, +0,17, +0,09 R… sobre 1-3
  finalistas por campaña). Es ruido elegido por su OOS-1: la ilustración directa de **E-02** (selección
  de finalistas por OOS-1 sin n mínimo) y de por qué el OOS-1 no puede ser el juez.
- Con spreads irrealmente bajos (0,3/0,5 bps) la media de los candidatos salía +0,006 R: el test depende
  del nivel de coste y su margen es moderado. Se deja con valores realistas, no ajustados para que pase.

## 9. EDGE-1 y EDGE-2 con puertas v3 (informe L4, `WORKER_REPORTS/V3-gate2.md`)

Puerta 2 recalculada sobre una copia de discovery.db (sin campañas, sin contador, sin OOS-2).

- **38 de 39 campañas no pasan con v3.** En FX y oro (14-101 pliegues, 200 estrategias de la población),
  el `stitched_sharpe` de "elegir la mejor del pasado" es **negativo** en casi todas. A diferencia del
  rechazo de v2, este es **informativo**: con esas plantillas, la selección no funciona fuera de muestra.
- **PBO bajo con WF negativo** (p. ej. `edge1-10` PBO 0,03; `edge1-14` 0,00; `edge1-17` 0,00): el orden
  relativo se mantiene, pero **todas pierden después de costes**. El problema es el nivel, no el
  sobreajuste.
- **Única que pasa: `edge2-04-st-reversal-idx-us100-h1`** (PBO 0,241; WF eficiencia 0,608, `stitched`
  1,611; **5 pliegues**). Cautelas: no dejó finalistas en EDGE-2; 1 de 39 es compatible con el azar de
  la puerta; su OOS coincide con el periodo de diseño del EA (contaminación declarada). **No es
  evidencia de ventaja**; como mucho, una hipótesis para un prerregistro nuevo con forward.
- **EDGE-2 H4: 1 pliegue** en todas (H4 de índices desde 2019): sin información con v2 ni con v3.

**Veredicto:** con herramientas corregidas, las plantillas de EDGE-1 (FX/oro, M15-H4) no muestran una
ventaja seleccionable después de costes. Para seguir, hacen falta hipótesis nuevas con más operaciones
o cestas (STATS_REDESIGN §4, EDGE_RESEARCH_PLAN), no más barridos de estas plantillas.

## 10. F0-09 (HIGH, producción) · El hash congelado del forward del EA depende de los finales de línea del disco

- `ea_forward.EA_CRITERIA` incluye `sha256` de los bytes crudos de `US100_EA.mq5`, los `.mqh`, el `.set`,
  `ea_us100_engine.py` y `nyse_calendar.py` (`ea_forward.py:31-40`). El hash congelado
  `f490642ba7a1f71b` (`tests/test_ea_forward.py:28`) **solo se reproduce** si en la copia del operador
  `US100_EA.mq5`, `US100_ExitManager.mqh`, `US100_RiskManager.mqh` y `ea_us100_engine.py` tienen **CRLF**
  y el resto LF (comprobado por fuerza bruta sobre las 2.048 combinaciones). En git todos están en LF
  (`.gitattributes`: `* text=auto eol=lf`), así que CI y cualquier checkout limpio dan `71ee2cabe6aa9aef`.
- **Riesgo:** el día que git reescriba uno de esos 4 ficheros (checkout, reset, merge que los toque), el
  hash cambia aunque el EA sea idéntico, y las comprobaciones de criterios congelados del forward pueden
  fallar ("congelados").
- **Corrección propuesta (requiere la cola de producción de AGENTS.md):** normalizar `\r\n` → `\n` antes
  de calcular el hash y migrar el hash congelado (con baseline, tag `-pre` y CHANGELOG). Mientras tanto,
  los 5 tests de `test_ea_forward` siguen fallando en CI **a propósito**: avisan de este problema.

## 11. F0-10 (LOW, latente) · Duración de vela con índices de pandas 3

`fastbt` calculaba la duración de la vela con `asi8 // 1_000_000_000`, que supone nanosegundos. En
pandas 3 los índices son de **microsegundos** por defecto (también al leer parquet): la duración salía
1000 veces menor. Afectaba al `no_overnight` de MOTOR-FLAT (la regla "vela que contiene `flat_at`" no
disparaba), pero la regla de reserva (última vela de la sesión del día) daba el mismo resultado en todos
los casos probados (M15 con datos de 24 h, sesión nocturna H1): **sin efecto encontrado**. Corregido con
`_bar_seconds` (segundos reales, cualquier unidad). Test: `tests/test_eng1_tf_seconds.py`.
