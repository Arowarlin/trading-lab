# QUANT_ENGINE_AUDIT — Backtesting, investigación, optimización y validación

Commit `9d7c5ad`. Todas las pruebas numéricas se hicieron con datos sintéticos fuera del repo y no suman nada al contador DSR.

## 1. Deflated Sharpe Ratio: error de unidades (P0)

`research.deflated_sharpe` implementa bien la fórmula. Con entradas por periodo reproduce el ejemplo de Bailey y López de Prado (2014): SR anual 2,5, T = 1250, asimetría −3, curtosis 10, N = 100 y V[SR] anual de 0,5 dan **DSR = 0,9004**.

El error está en **todas las llamadas**, que pasan el Sharpe anualizado:

| Llamada | Sharpe que pasa | Dispersión entre pruebas |
|---|---|---|
| `research.py:513` | `metrics["sharpe"]` (×√252) | `pstdev` de Sharpes anualizados |
| `optimize.py:219, 310` | `_sharpe()` (×√252) | `pstdev(trial.value)`, anualizada |
| `ea_us100.py:375` | `_sharpe()` (×√252) | desviación de Sharpes anualizados |
| `campaign.py:2540` | `metrics["sharpe"]` | `|SR|/√bars` (inventada) |

Con el ejemplo del artículo, la versión del lab da 0,99999994 en vez de 0,9004. Con la mejor de 1040 series de ruido puro da 0,9999998 en vez de 0,74. Y una estrategia con SR real de 0,83 por debajo del SR0 da 0,0 en vez de 0,077.

**Consecuencia:** el DSR del lab funciona como un escalón: todo lo que supera SR0 sale con aproximadamente 1. Ningún DSR guardado en la base de datos es utilizable. El PBO, el walk-forward y el holdout sí siguen siendo válidos.

**Corrección:** una única función `dsr_from_returns(returns, trial_returns_or_srs, n_trials, periods)` que calcule internamente el Sharpe por periodo, la asimetría y la curtosis no excesiva, y la dispersión por periodo. Prohibir pasar el Sharpe a mano. Después, recalcular los DSR históricos y guardarlos en una columna nueva (`dsr_v2`) sin borrar `dsr`, que queda marcada como `invalid_units`.

## 2. PBO/CSCV: correcto, con una excepción

- Bloques contiguos, número par de bloques, se descarta el resto más antiguo, empates promediados y ω = rango/(N+1). Está bien implementado.
- El Sharpe por bloque se calcula con sumas y sumas de cuadrados: correcto y eficiente.
- **Error en `campaign.py:2548`:** se le pasa una sola variante, `returns_matrix` devuelve una tupla y `cscv_pbo` falla sin avisar, así que el resultado siempre es None. El PBO no tiene sentido con una sola celda: hay que registrar `pbo: "no_aplica (1 variante)"` y calcular el PBO sobre **toda la matriz de celdas de la campaña** en la fase de descubrimiento.
- Mejora: cuando el número de variantes es grande y las variantes están muy correlacionadas, el PBO sale engañosamente bajo. Conviene informar también del número efectivo de pruebas (por clúster de correlación) y usarlo como N del DSR.

## 3. Walk-forward

- La selección en cada fold usa solo los datos de entrenamiento. Correcto.
- `efficiency` es la mediana de OOS/IS por fold y se fija en 0 cuando el IS es ≤ 0. Conviene registrarlo como `nan` para no mezclarlo con la mediana.
- `ea_us100.py` usa folds de 252/63 días sobre 8 variantes de la rejilla. Es poco poder estadístico: con 8 variantes tan parecidas, la estabilidad sale alta por construcción.

## 4. Optuna (`optimize.py`)

- El holdout sellado se excluye del desarrollo (`dev_end = sealed_start − 1`). Correcto.
- El objetivo es el Sharpe del walk-forward OOS concatenado. Tras elegir el mejor de N trials, ese Sharpe ya **es en muestra respecto a la selección**. El informe debe llamarlo `wf_selected_sharpe` y no "OOS".
- Faltan un límite de trials por estudio que dependa de la muestra, la mediana y la meseta de los 20 mejores trials en lugar del máximo, y una semilla y una versión de los datos en el registro.

## 5. Motor diario (`backtest.py`)

| Punto | Estado |
|---|---|
| Ejecución | Señal en t, ejecución al open de t+1 (`shift(1)`). Sin look-ahead. |
| Costes | En bps del nocional. Sirve para acciones y ETFs, **no** para CFD ni FX: ahí manda el spread en puntos. |
| Swap y financiación | **No existe.** |
| Contabilidad por operación | La comisión de entrada no se atribuye a la operación, y las reducciones parciales cuentan como operaciones. |
| `realized_days` | Fecha en UTC, no en la zona de sesión. |
| Margen y apalancamiento | `max_gross` limita la exposición bruta; no hay modelo de margen (aceptable para paper). |

## 6. Motor de eventos intradía (`intraday.run_event_backtest`)

Es conservador en casi todo: el SL tiene prioridad en la misma barra, los gaps se llenan al peor precio y hay guarda de sesión, rollover y corte de viernes. Tiene **una asimetría optimista**: la entrada limitada y el objetivo no pagan spread. Para CFD y FX con barras BID, una compra limitada o la recogida de beneficios de un corto exigen que el ASK toque el nivel. Hay que añadir el spread de esa hora a la condición de llenado.

## 7. Réplica del EA (`ea_us100_engine.py`)

Es el motor mejor construido del repo. La entrada se hace en el open siguiente, LONG al ASK con el gráfico en BID, el SL va antes que el TP en la misma barra, los gaps se llenan al peor precio, hay slippage de 0,5 puntos en entrada y stop, y el BE y el trailing se aplican desde la barra siguiente. Coincide con el Strategy Tester de MT5 con ticks reales: 480 operaciones con PF 1,45 frente a 445 con PF 1,50.

Lo que falta no es del motor, sino del protocolo: no hay ningún periodo que no se haya mirado al diseñar las versiones 1 a 3.

## 8. Sesgos

| Sesgo | Situación |
|---|---|
| Look-ahead | No se encontró en los motores revisados. |
| Supervivencia | ETFs e índices: bajo. Acciones individuales del carril de equities: sin verificar. |
| Selección y pruebas múltiples | El contador es correcto, pero el DSR está roto (A1). |
| Holdout | El de la campaña B está contaminado y ya documentado. El EA no tiene holdout. |
| Dependencia serial | Ni el PBO ni el DSR corrigen la autocorrelación; en estrategias diarias de tendencia, el T efectivo es menor. |

## 9. Motores por clase de activo

No hace falta un motor por mercado. Hace falta un **modelo de costes por instrumento y bróker** con una interfaz común: `CostModel.entry(side, ts, px)`, `exit(...)` y `carry(position, from, to)`. Las implementaciones serían spread por hora y comisión para CFD/FX, bps y SEC/TAF para acciones, y ticks más comisión por contrato y rollover para futuros. Hoy los costes están repartidos entre `costs.py`, `broker_costs.py`, `costs.yaml` y parámetros sueltos (`slippage_bps`, `spread_bps`).
