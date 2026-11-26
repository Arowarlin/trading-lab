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
| **B-03** | Robustez, perturbación, `levels` (neto base) y `retest` usan `cost_from_profile` (una cuenta, p75 estático) en lugar del `CostBook` del fitness: **la validación usa otro modelo de coste que la selección** | Ambiguo | R | Sí | Un único constructor de coste por campaña |
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
