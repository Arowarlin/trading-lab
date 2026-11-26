# WORKER D · Statistical Validation Auditor

| Campo | Valor |
|---|---|
| ID de tarea | ENG-D1 |
| SHA | `adc0eec` |
| Fecha | 2026-11-26 |
| Modo | Solo lectura. Simulaciones sintéticas fuera del repo; no se abrió `discovery.db` ni `lab.db`; no suman al contador DSR |
| Scripts | `/tmp/claude-0/-home-user-trading-lab/89310f7f-0a4e-5602-b5a9-56cac624406b/scratchpad/D/` (en adelante `$D`): `s1_dsr_bailey.py`, `s2_pbo_selection.py`, `s2b_pbo_edge.py`, `s3_montecarlo.py`, `s4_wf_selected.py`, `s4b_wf_duplicates.py`, `s5_dsr_confirm.py`, `s5b_dsr_proper_var.py`, `s6_power_sharpe.py`, `s7_count_readonly.py`, `s8_spa.py` |

Metodología y umbrales congelados (EDGE-2): **ninguna corrección propone bajar un umbral**. Todas van dirigidas a reducir falsos positivos o a dejar de presentar como prueba algo que no lo es. Las correcciones que cambian la metodología se proponen para después de EDGE-2 y con prerregistro.

## Resumen por severidad

| ID | Sev. | Estado | Tema |
|---|---|---|---|
| D-01 | HIGH | NUEVO | El walk-forward de Robustness corre dentro del IS con el que el GA eligió el frontier: no es OOS |
| D-02 | HIGH | NUEVO (parcialmente CONOCIDO(robust1_pbo.md)) | PBO sobre el frontier final: depende de su composición y no de la población probada |
| D-03 | HIGH | NUEVO | DSR de `confirm`: V[SR] de IS/OOS-1 de K≤5 finalistas, así que en la práctica no deflacta; N=K por campaña ignora que todas las campañas comparten el mismo OOS-2 |
| D-04 | MEDIUM | NUEVO | `family.spa_test`: no es el SPA de Hansen, el bloque sale casi siempre 1 y alinea las series por posición |
| D-05 | MEDIUM | NUEVO | Monte Carlo `mc_trades`: la permutación conserva la media (la puerta equivale a "expectativa > 0") y el remuestreo i.i.d. infravalora las colas |
| D-06 | MEDIUM | NUEVO | Puerta de potencia: cuenta OOS-1+OOS-2 como holdout, pero la confirmación solo usa OOS-2 |
| D-07 | MEDIUM | NUEVO | Series de "días con operación": `sharpe_daily` ×√252 infla el Sharpe en baja frecuencia; MC del challenge y bootstrap con horizonte en días-operación |
| D-08 | LOW | CONOCIDO(QUANT_ENGINE_AUDIT §3) | `efficiency` = 0 cuando IS ≤ 0, y eficiencia mediana 0,000 por pliegues sin operaciones |
| D-09 | LOW | NUEVO | `count_tests_readonly` (consola) omite `informal_trials` y se traga los errores de `discovery.db` |
| D-10 | LOW | NUEVO | `jobs._slice_bars` incluye la barra de las 00:00 del día siguiente al fin del IS (ruta `run_queue`, hoy sin uso) |
| D-11 | LOW | NUEVO | Protocolo v2: LCB de desarrollo sobre R diario frente a holdout sobre R por operación; `holdout_decision` no entra en `level4_ok` |
| D-12 | LOW | CONOCIDO(QUANT_ENGINE_AUDIT §8) | Ni el DSR, ni el PBO, ni el t de v2 corrigen la autocorrelación |

---

## Respuestas a las preguntas 1-8

**1. ¿Usa el DSR unidades por periodo?** **Sí, ya está corregido.** `stats.deflated_sharpe`/`dsr_from_returns` (src/tradinglab/stats.py:63-178) calcula el Sharpe, la asimetría, la curtosis no excesiva y la dispersión por periodo, y rechaza las entradas con |SR por periodo| > 1. Con el ejemplo de Bailey y López de Prado sale **0,9004**. La ruta antigua, con el Sharpe anualizado, daba 0,99999994 (`$D/s1_dsr_bailey.py`). Ya no queda `research.deflated_sharpe`: research, optimize, ea_us100 y event_families llaman a `dsr_local_global`. **Discovery** solo usa el DSR en `levels.confirm` (src/tradinglab/discovery/levels.py:662-720 y `_account_confirmation` 403-435): con K=1 calcula el PSR frente a 0 y con K>1 el DSR con N = K×cuentas y V[SR] de los finalistas. Las unidades son correctas, pero el contenido tiene el problema que explica D-03. El §1 de QUANT_ENGINE_AUDIT queda **resuelto** en el código. La guarda "|SR| > 1" no detecta un Sharpe anualizado menor que 1 (LOW; las rutas internas calculan siempre a partir de retornos).

**2. ¿Qué cuenta el N de `count_tests`?** `learning.count_tests` (learning.py:175) suma las lecciones, los trials de Optuna, las lecturas de holdout, `strategy_trials` (también los fallidos), `informal_trials`, `campaign_registry`, los bots incubados y `discovery_tests`. Este último toma el `n_total` **presupuestado y congelado** de cada campaña aprobada (campaigns.py:1097-1135): población×(generaciones+1) o el tamaño de la rejilla (campaigns.py:371-373), con un trigger de inmutabilidad (databank.py:258). Por tanto **cuenta también las evaluaciones que el GA descartó, las campañas abortadas o canceladas y las inválidas**; solo dejan de contar las `superseded`, y `supersede` exige 0 evaluaciones. Contar el presupuesto es conservador: el GA nunca evalúa más que `n_total` (engine.py:871). Los pasos de robustez (perturbaciones, retest, azar, meseta) no cuentan. Es correcto, porque son filtros que solo pueden rechazar y no eligen nada. **Pero la decisión de Discovery no usa este N**: `confirm` usa N = K finalistas, y `global_dsr_tests` solo se guarda como dato informativo (levels.py:836-841). Ver D-03. La consola usa un contador paralelo con defectos (D-09).

**3. ¿PBO sobre la población o sobre el frontier?** **Solo sobre el frontier final**: `databank.frontier`, rango 0 de la última generación (databank.py:1058-1098), vía `robustness._frontier_frame`/`_pbo_wf` (robustness.py:242-447). Sale el mismo número para toda la campaña y se guarda por estrategia. El arreglo R2 (calendario de días hábiles) es correcto, pero no cambia esto. La simulación (D-02) muestra que el PBO sobre el top-k sale inflado y el de un frontier mixto, hundido; ninguno de los dos mide el sobreajuste del proceso.

**4. ¿Qué hace el Monte Carlo?** `_mc_trades` (robustness.py:173) **permuta y remuestrea las operaciones de forma i.i.d.** `_bootstrap` (robustness.py:205) usa bloques fijos de 5 sobre la serie de **días con operación**: el campo dice `block_days`, pero no son días de calendario. Afirma medir la robustez de la expectativa y del drawdown. En realidad, la permutación devuelve exactamente la media real (p5 = media) y la puerta `mc_trades` se reduce a "media > 0". Ver D-05. Ni `mc_trades` ni `bootstrap` entran en `level4_ok` (decisions.py:84-110): son informativos, aunque se guardan con `passed`.

**5. ¿Walk-forward con re-optimización?** **No re-optimiza parámetros.** En cada pliegue de 60/20 días hábiles elige, entre las ~40 estrategias fijas del frontier, la de mayor Sharpe en train, y la mide en test (walkforward.py:115-195). Además, todas las ventanas caen **dentro del IS que el GA usó para elegir ese frontier**, así que el "OOS" del WF es dentro de muestra respecto a la selección (D-01). La eficiencia OOS/IS no es informativa: con IS ≤ 0 se fija en 0 (walkforward.py:154); en baja frecuencia la mediana sale 0,000 porque el Sharpe de una ventana sin varianza vale 0, y con IS pequeño el cociente es inestable (D-08). El WF del `fitness` (4 pliegues) solo evalúa una estrategia congelada por subperiodos (fitness.py:72-90 y 184-214), y es correcto como tal.

**6. ¿Puede alguna ruta leer el OOS-2 sin autorización?** **No encontré ninguna fuga de datos al OOS-2 en las rutas de selección.**
- `load_segment` prohíbe `oos2` (campaigns.py:1004-1010).
- IS, OOS-1 y OOS-2 se compilan cada uno sobre su propio tramo: el warm-up se pierde en lugar de leer datos fuera del tramo (robustness.py:681-737, levels.py:535-560).
- Los indicadores son causales: `rolling` con `min_periods`, `ewm` y ningún `shift(-k)`.
- La alineación HTF exige que la vela superior haya cerrado (compiler.py:106-112).
- Al registrar la campaña se leen las barras del OOS-2 solo para el hash y la calidad (campaigns.py:376-391), sin calcular métricas.

Puntos débiles: la autorización del operador solo se comprueba en `levels.confirm` (`approved_by_operator`); `campaigns.read_holdout` solo exige `status == done`, así que un script que lo llame directamente lee el OOS-2 sin flag (aunque la lectura queda registrada y es única). La única fuga de calendario es D-10, latente.

**7. Muestra, correlación y anualización.** Hay mínimos de operaciones por TF en el IS y por pliegue (engine.yaml `validation.by_timeframe`) y `min_trades_oos2 = 30`. Todas las pruebas sobre operaciones (DSR, t de v2, `lcb_dev`, MC) suponen independencia (D-12, D-05). `sharpe_daily` anualiza ×√252 una serie que solo contiene los días con operación, lo que lo infla ×1,5 con 100 días-operación al año y ×2,6 con 40 (D-07). El Sharpe solo se muestra (webui) y no es puerta en Discovery. El PBO y el WF anualizan con √252 sobre la serie de días hábiles posterior a R2, que es consistente.

**8. ¿Hay White Reality Check, SPA o Romano-Wolf?** Existe `discovery/family.py` (`lab discovery family-test`), llamado "SPA de Hansen". En realidad es un Reality Check sin studentizar y con defectos (D-04), solo para las primarias v2, y no entra en ninguna puerta. **Sí hace falta un control conjunto**, por una limitación concreta: todas las campañas leen el **mismo tramo de calendario OOS-2** (`holdout_start` 2025-07-01) y cada `confirm` deflacta solo por las K de su campaña, con una V[SR] que casi no deflacta. Con 0,05-0,07 de falsos positivos por finalista y K=5, la probabilidad de al menos un falso positivo es del 23-30 % por campaña y del 60 % con 18 lecturas (`$D/s5_dsr_confirm.py`), siempre que lleguen al nivel 3. El contador global no controla esto, porque nunca entra en la decisión. Un Romano-Wolf o un RC/SPA studentizado con bootstrap estacionario, sobre las series **diarias de calendario** del OOS-2 de todas las lecturas del mismo tramo, o en su defecto un Holm sobre los p-valores de esas lecturas, cerraría el hueco sin tocar los umbrales individuales.

---

## Confirmado con reproducción

### D-01 · HIGH · NUEVO — Walk-forward de Robustness dentro de la muestra de selección
- **Archivo:** src/tradinglab/discovery/robustness.py:242-262 (`_frontier_frame`), 383-447 (`_pbo_wf`); src/tradinglab/walkforward.py:115-195 (`walk_forward`).
- **Descripción:** la matriz del WF son las series `fitness_is` del frontier, que el NSGA-II eligió mirando **todo** el IS (fitness.py:118-139). Las ventanas de test del WF caen dentro de ese IS, así que `stitched_sharpe`, `frac_positive` y `rank_pct` heredan el sesgo de selección. Además, el veredicto es de la campaña, no del finalista: puede aprobar el WF de un finalista que nunca eligió el WF.
- **Evidencia** (`$D/s4_wf_selected.py`): 500 ruidos y frontier = top-40 en todo el IS.

  | Matriz | stitched SR medio | P(stitched > 0) |
  |---|---:|---:|
  | top-40 elegido en el IS | +0,53 | 0,90 |
  | 40 al azar | +0,02 | 0,50 |
  | top-40 en datos nuevos | −0,07 | 0,42 |

  Con actividad del 5 %: +0,62 y P = 0,95. Con 40 estrategias distintas el veredicto completo falla por estabilidad: P(WF ok) = 0. Pero con un frontier de clones (`$D/s4b_wf_duplicates.py`), 4 ruidos distintos elegidos en el IS y repetidos ×10 dan **P(WF ok) = 0,40**, y 2 ruidos ×20 dan 0,18. La estabilidad se fabrica con duplicados, y con ellos el ruido aprueba.
- **Impacto:** la puerta WF infla falsos positivos hasta un 40 % en frontiers poco diversos. En el resto de casos, el stitched > 0 es una evidencia ficticia.
- **Corrección mínima:** hacer el WF **anidado**: en cada pliegue, seleccionar con el GA (o, como mínimo, con la regla de fitness) usando solo el train, o bien correrlo sobre OOS-1 con la población. Como alternativa barata, deduplicar el frontier por correlación ≥ 0,95 antes del WF y etiquetar el resultado "WF dentro de muestra (no OOS)" mientras no exista el WF anidado. Los umbrales no cambian.
- **Test de regresión:** con 500 ruidos y un frontier top-40 elegido en todo el IS, comprobar que el WF devuelve `in_sample_selection=True`, o que el WF anidado da P(stitched > 0) ≈ 0,5 (±0,1) en 60 réplicas. Con 4 clones ×10 de ruido, P(WF ok) ≤ 0,05.

### D-02 · HIGH · NUEVO (la matriz por campaña es CONOCIDO(TL3_REPORTS/robust1_pbo.md)) — PBO sobre el frontier y no sobre la población
- **Archivo:** src/tradinglab/discovery/robustness.py:383-430; src/tradinglab/discovery/databank.py:1058-1098 (`frontier`); src/tradinglab/discovery/nsga2.py:49-51.
- **Descripción:** el PBO se calcula sobre el rango 0 final, que (a) ya fue elegido con todo el IS y (b) puede incluir estrategias con expectativa IS negativa, porque el frente de Pareto tiene 5 objetivos (complejidad, DD, etc.) y `_rank1_candidates` filtra IS > 0 **después** (engine.py:483-520). Si no hay ninguna factible, el frente 0 lo forman las no factibles (nsga2.py:49-51).
- **Evidencia** (`$D/s2_pbo_selection.py`, 40 réplicas; `$D/s2b_pbo_edge.py`, 30 réplicas):

  | Matriz | Ruido puro: PBO medio | Ruido puro: P(PBO ≤ 0,30) | 5 ventajas reales: P(PBO ≤ 0,30) |
  |---|---:|---:|---:|
  | Población (500) | 0,537 | 0,10 | 0,47 |
  | 40 al azar | 0,506 | 0,125 | — |
  | Top-40 (frontier) | 0,914 | 0,00 | **0,03** |
  | Frontier mixto (20 top + 20 perdedoras) | **0,104** | **0,975** | 1,00 |

- **Impacto:** si el frontier contiene perdedoras estructurales, el ruido aprueba el PBO el 97,5 % de las veces. Si es un top-k puro, el PBO rechaza también las ventajas reales (potencia del 3 %). Ninguno de los dos mide el sobreajuste del proceso de búsqueda. EDGE-1 muestra los dos extremos (0,023 frente a 0,957). Aun sobre la población, el PBO deja pasar el ruido un 10 % de las veces.
- **Corrección mínima:** calcular el PBO sobre la matriz de **todas las evaluaciones** de la campaña (o sobre una muestra estratificada de, como mínimo, 200 columnas), alineadas a días hábiles como en R2. Las estrategias con evaluación `fitness_is` ya están en `disc_evaluations`. Guardar también el PBO del frontier, con la etiqueta "frontier (no decisorio)". El umbral 0,30 no cambia.
- **Test de regresión:** con 500 ruidos y un frontier = top-20 + 20 con deriva −0,15, `pbo_campaign` (población) da una media de 0,45-0,60 y P(≤ 0,30) ≤ 0,15. Además, un test que compruebe que `_frontier_frame` no se usa para la puerta.

### D-03 · HIGH · NUEVO — DSR de confirmación: V[SR] de desarrollo y N por campaña
- **Archivo:** src/tradinglab/discovery/levels.py:243-275 (`_trial_srs`), 640-720 (`confirm`), 403-435 (`_account_confirmation`).
- **Descripción:** (a) `trial_srs` son los Sharpe por periodo de **IS+OOS-1** de 1 a 5 finalistas; con eso SR0 sale minúsculo y el DSR ≈ PSR. La V[SR] debería salir de las pruebas sobre **la misma muestra** que el candidato. (b) N = K×cuentas no recoge que cada campaña relee el **mismo tramo de calendario OOS-2** (mismas fechas para EURUSD, GBPUSD, USDJPY...). (c) Con K=1 se usa el PSR frente a 0 con 0,90, que es un nivel unilateral del 10 %.
- **Evidencia** (`$D/s5_dsr_confirm.py`, 20 000 réplicas bajo H0):

  | K | P(DSR ≥ 0,90) | P(DSR ∧ neto > 0 ∧ azar ≥ 95) | SR0 medio por periodo |
  |---|---:|---:|---:|
  | 1 | 0,103 | 0,053 | — |
  | 3 | 0,080 | 0,050 | 0,018 |
  | 5 | 0,070 | 0,051 | 0,028 |

  El Sharpe nulo del OOS-2 tiene una desviación típica de ≈ 0,10-0,18, así que el SR0 es despreciable. `$D/s5b_dsr_proper_var.py`: para el mejor de K en el OOS-2, el DSR del lab da 0,226 (K=3) y 0,309 (K=5), frente a 0,014 y 0,003 con la V[SR] del OOS-2. Familia: con p = 0,05 la probabilidad de al menos un falso positivo es 0,23 con 5 lecturas, 0,60 con 18 y 0,99 con 90.
- **Impacto:** el DSR no aporta deflación; el filtro efectivo del nivel 4 es "azar ≥ 95", con un 5 % por finalista. Con EDGE-2 (18 campañas), si varias llegan al nivel 3 bajo H0, la probabilidad de al menos una "ROBUSTA" falsa ronda el 23-60 %, siempre condicionada a pasar las puertas del IS.
- **Corrección mínima:** (1) calcular la V[SR] a partir de los Sharpes del OOS-2 de **todas** las lecturas del mismo tramo (o, con K=1, mantener el PSR), sin bajar el 0,90. (2) Llevar un registro de lecturas por tramo de calendario del OOS-2 y aplicar Holm, o Romano-Wolf (ver §8), sobre todas las lecturas del tramo. (3) Guardar `n_trials_family`. Para después de EDGE-2 y prerregistrado.
- **Test de regresión:** con K=5 finalistas de ruido y 20 000 réplicas, P(confirmada | H0) ≤ 0,05/K por finalista con el control familiar. Con 18 campañas simuladas que comparten el OOS-2, FWER ≤ 0,05.

### D-04 · MEDIUM · NUEVO — `family.spa_test` no es SPA y puede sobrerrechazar
- **Archivo:** src/tradinglab/discovery/family.py:22-33 (`_aligned`), 36-80 (`spa_test`), 140-176.
- **Descripción:**
  - El estadístico es max √n·media, sin studentizar y con recentrado total: es el RC de White, no el SPA de Hansen.
  - El bloque = duración media de la operación en días suele dar 1, así que el bootstrap es i.i.d.
  - `_aligned` recorta todas las series a la más corta **por posición**, no por fecha, y descarta el resto de la historia.
  - Toma la última evaluación entre `fitness_is` y `oos1`, que según el caso es solo IS o solo OOS-1.
  - `arch` está declarado en pyproject, pero no está instalado en este `.venv`, por lo que la función falla en este entorno.
- **Evidencia** (`$D/s8_spa.py`, mismo estadístico con un bootstrap estacionario de réplica): H0 i.i.d. → 0,040; AR(1) ρ = 0,3 con bloque 1 → **0,290**; con bloque 5 → 0,080. `_aligned(500, 80)` → forma (80, 2) usando las posiciones 0..79.
- **Impacto:** si se usa como prueba de familia, con autocorrelación sobrerrechaza H0 ×6. Hoy no es decisorio.
- **Corrección mínima:** studentizar (o usar el SPA de `arch.bootstrap.SPA`), alinear por fecha sobre el calendario de días hábiles con ceros, bloque ≥ 5 días o elegido automáticamente, y renombrarlo "RC/SPA".
- **Test de regresión:** 10 series AR(1) ρ = 0,3 bajo H0 en 300 réplicas, con P(p < 0,05) ≤ 0,08; y `_aligned` con fechas desfasadas tiene que emparejar por fecha.

### D-05 · MEDIUM · NUEVO — Monte Carlo de operaciones: mide poco y lo presenta como "passed"
- **Archivo:** src/tradinglab/discovery/robustness.py:173-202 (`_mc_trades`), 205-228 (`_bootstrap`), 823-827.
- **Evidencia** (`$D/s3_montecarlo.py`):
  - (a) Con media 0,059547, `shuffle_mean` y `shuffle_p5` valen 0,059547 y la puerta da True con t = 1,02.
  - (b) Con AR(1) ρ = 0,3: el p5 real del DD es −50,1; el remuestreo i.i.d. da −41,3, la permutación −28,9 y el bloque 5, −50,7. La desviación típica real de la media es 1,43 veces la i.i.d.
  - Bajo H0, P(resample_p5 > 0) pasa de 0,065 (i.i.d.) a 0,138 (ρ = 0,3).
- **Impacto:** no afecta al nivel 4. Sí a la lectura humana: "mc_trades passed" equivale a "expectativa > 0".
- **Corrección mínima:** quitar el p5 de la permutación de la puerta (se puede dejar el DD de la permutación como informativo); poner `passed` solo con un remuestreo por bloques sobre la serie de calendario. Renombrar `block_days` a `block_trade_days` mientras siga sobre la serie de días con operación.
- **Test de regresión:** dada una lista de operaciones con media > 0 y t < 1, `mc_trades.passed` es False; además, `shuffle_expectancy_p5 == mean` no puede decidir.

### D-06 · MEDIUM · NUEVO — Potencia con holdout = OOS-1 + OOS-2
- **Archivo:** src/tradinglab/discovery/power.py:58-87 (`segment_years`, `counts_from_is`); campaigns.py:700-716.
- **Descripción:** OOS-1 sirve para elegir finalistas (engine.py:551-599) y el nivel 4 solo usa el OOS-2 (`min_trades_oos2`, `confirm`).
- **Evidencia** (`$D/s6_power_sharpe.py`): con 100 operaciones en el IS y los tramos por defecto, el lab estima 87 operaciones de holdout, frente a las 51 reales del OOS-2. El MDE sale 0,267 R en lugar de 0,349 R. Con δ = 0,30, el lab da `potencia_ok = True` y lo correcto sería False.
- **Impacto:** aprueba campañas sin potencia en el OOS-2, que luego no pueden confirmar nada o lo hacen con poco poder. No sube directamente la tasa de falsos positivos, pero sube la proporción de falsos entre los confirmados.
- **Corrección mínima:** escalar los conteos de `counts_from_is` solo con `oos2`.
- **Test de regresión:** con los tramos por defecto y 100 operaciones en el IS, `trades_holdout == 51`.

### D-07 · MEDIUM · NUEVO — Series de "días con operación"
- **Archivo:** src/tradinglab/discovery/fastbt.py:2046-2054 (`daily_r` solo con los días de salida); src/tradinglab/discovery/metrics.py:76-83 (`sharpe_daily`); robustness.py:589-596 (MC del challenge, `horizon=180`); levels.py:662-720 (n_obs del DSR).
- **Evidencia** (`$D/s6_power_sharpe.py`): con 100 días-operación al año, el Sharpe calendario es 0,68 y `sharpe_daily` da 1,02 (×1,50). Con 40 días al año, 1,80 frente a 4,68 (×2,60).
- **Impacto:** en informes y webui, un Sharpe que compara mal con la tabla de VALIDATION_PROTOCOL (Swing > 0,7). En el challenge, 180 "días" equivalen a 180 días con operación, es decir, años de calendario en H4. El DSR sigue siendo consistente en unidades (todas las series son de días-operación), pero mezcla estrategias de frecuencias distintas.
- **Corrección mínima:** reindexar a días hábiles con ceros (como `_frontier_frame` tras R2) antes del Sharpe, del MC del challenge y del bootstrap.
- **Test de regresión:** con una serie de 40 días-operación al año, `sharpe_daily` es igual al Sharpe calendario con una tolerancia del 5 %.

### D-08 · LOW · CONOCIDO(QUANT_ENGINE_AUDIT §3; robust1_wf.md) — Eficiencia del WF
- **Archivo:** walkforward.py:154.
- **Descripción:** si IS ≤ 1e-12 la eficiencia es 0, cuando debería ser `nan`. En baja frecuencia (`$D/s4_wf_selected.py`, actividad del 5 %), la eficiencia mediana sale 0,000 por los Sharpe nulos en test. Con ruido, las eficiencias por pliegue van de −2,06 a +2,28.
- **Corrección:** usar `nan` y excluirlo de la mediana, o mejor, calcular el cociente sobre los agregados (stitched OOS / IS medio).

### D-09 · LOW · NUEVO — `count_tests_readonly`
- **Archivo:** src/tradinglab/discovery/console.py:81-133.
- **Evidencia** (`$D/s7_count_readonly.py`, BD sintética): con 10 lecciones y 250 `informal_trials`, el contador da total = 10, cuando `learning.count_tests` daría 260. Con una `discovery.db` ilegible, `discovery` = 0 sin avisar (`except Exception`).
- **Impacto:** la consola muestra un N menor que el real. No es decisorio.
- **Corrección:** sumar `informal_trials` y propagar el error como "Sin datos".
- **Test:** paridad con `learning.count_tests` sobre la misma BD sintética.

### D-10 · LOW · NUEVO — `_slice_bars` +1 día
- **Archivo:** src/tradinglab/discovery/jobs.py:361.
- **Descripción:** `<= end + 1 día` incluye la barra de las 00:00 UTC del primer día del tramo siguiente. Afecta a `_init_worker` cuando `setup.bars` no está ya recortado, que es la ruta `run_queue`, sin llamadas en `src/`. `run_campaign` pasa `is_frame` ya recortado con `_end_ts`, así que no hay fuga activa.
- **Corrección:** usar `campaigns._end_ts`.
- **Test:** con IS hasta 2024-06-30 y barras M5, ninguna barra ≥ 2024-07-01 00:00.

### D-11 · LOW · NUEVO — Protocolo v2: unidades y peso en la decisión
- **Archivo:** engine.py:1063 (`lcb_dev` sobre `daily_returns`, R por día-operación); levels.py:566-583 (`holdout_decision` sobre `r_net` por operación); decisions.py:84-110.
- **Descripción:** el LCB y la media del holdout están en unidades distintas; si hay varias operaciones por día, la comparación es conservadora. `protocol_v2_holdout` se guarda, pero **no entra en `level4_ok`**: el t ≥ 1,645 de v2 no es puerta.
- **Corrección:** usar R por operación en los dos lados y decidir explícitamente si v2 es puerta, con prerregistro.

### D-12 · LOW · CONOCIDO(QUANT_ENGINE_AUDIT §8) — Autocorrelación
- **Descripción:** ni el DSR, ni el PBO, ni el t de v2, ni `lcb_dev` ajustan por dependencia. La magnitud está en `$D/s3_montecarlo.py`: con ρ = 0,3 el error estándar real es ×1,43 el i.i.d., y la tasa de falsos positivos del p5 sube de 0,065 a 0,138.

## Sospecha no reproducida

- **Frontier con clones en las campañas reales.** El mecanismo de D-01 con clones está reproducido, pero no comprobé si los frontiers reales de EDGE-1/EDGE-2 contienen estrategias casi duplicadas: haría falta leer `discovery.db`, que está prohibido. Los valores idénticos de `robust1_wf.md` se explican porque el WF es de la campaña, no por clones.
- **Frontier mixto en las campañas reales.** La lógica de rango 0 permite estrategias con IS < 0 en el frontier (está verificado en el código), pero no medí qué fracción tienen las campañas reales. El PBO de 0,023 de `edge1-12` es compatible con este mecanismo, pero no lo prueba.
- **`read_holdout` sin flag del operador.** Es posible por código (campaigns.py:1022-1094), pero no encontré ningún script que lo llame fuera de `confirm`.
- **MC del challenge con días-operación.** La compresión temporal afecta por igual a las tasas de aprobación y de breach; no medí el efecto sobre "pass > breach" (probablemente pequeño respecto al signo de la deriva).

## Comprobado y correcto

- **Fórmula del DSR v2:** 0,9004 en el ejemplo publicado (`$D/s1_dsr_bailey.py`), con curtosis no excesiva y guarda de unidades.
- **`n_total` congelado e inmutable:** cuenta desde la aprobación, incluye las campañas abortadas o inválidas, y `supersede` solo se permite con 0 evaluaciones (campaigns.py:786-830, databank.py:258).
- **`cscv_pbo`:** bloques contiguos, número par, empates promediados y ω = rango/(N+1) (validation.py:71-155). Tras R2, la matriz es diaria, ordenada y en días hábiles (robustness.py:242-262).
- **Selección en `walk_forward`:** elige con train y mide en test, sin mirar el test (el problema es la matriz de entrada, D-01).
- **OOS-2:** `load_segment` lo prohíbe, `read_holdout` es único (índice único más IntegrityError), cada tramo se compila por separado, los indicadores son causales y el HTF exige vela cerrada.
- **Perturbaciones, retest, azar y meseta:** no cuentan en el DSR y solo pueden rechazar, así que no inflan los falsos positivos.
- **El GA no excede el presupuesto:** `len(known) >= total_budget` (engine.py:871, 959).

## Nota de entorno

`arch==9.0.0` está en `pyproject.toml`, pero no está instalado en `/home/user/trading-lab/.venv`: `family.spa_test` falla con `ModuleNotFoundError` en este entorno. No toqué el `.venv`.
