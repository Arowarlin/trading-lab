# HIPÓTESIS 4-10 · plan de búsqueda en papel

Fecha: 2026-11-23. Modelo: DeepSeek V4.1 Flash. Repo: `E:\trading-lab`.

Fase **solo documento**. No se tocó código, configuración, datos ni git. No se
ejecutaron backtests, ni expectativa/PF/percentiles, ni `preflight`/`feasibility`,
ni `register`/`approve`/`run`, ni OOS, ni push. No se registró ninguna campaña.
Las únicas escrituras son este archivo y `.orquestador/fomc-fechas.md`.

## 0. Alcance, estado del repo y una discrepancia

- `PLAN-BUSQUEDA.md` (2026-11-23) tiene **8 filas**: hipótesis 1-8. **No existen
  las hipótesis 9 y 10**. Este documento cubre 4-8; 9-10 quedan **Sin datos** y
  no se inventan. Si el operador tenía un plan de 10, la copia vigente no lo
  contiene.
- Estado leído: `HEAD dd2f1f8` (`tl2-r9b`), rama
  `feature/prop-fund-multifirm`. La sesión R9c está trabajando en paralelo:
  había cambios sin confirmar en `costs.py`, `drift.py`, `fastbt.py`,
  `propfund/costs.py`, `config/propfund/swap.yaml` y
  `tests/test_discovery_swap.py`. **No se usaron** para las cifras de este
  documento. El coste de swap se está construyendo en R9c; aquí solo se cuenta
  **cuántas noches** cruza cada hipótesis, no su importe.
- Los datos y `usable_from` se leyeron de `config/discovery/engine.yaml`. Las
  plantillas se leyeron de `config/discovery/templates/` y los bloques de
  `src/tradinglab/discovery/blocks.py` en el `HEAD` indicado.
- `fomc-fechas.md` contiene las fechas oficiales 2010-2026 y las fuentes. Es el
  anexo de la hipótesis 4.

## 1. Criterio común: qué debe superar cualquier hipótesis

Tomado de `PLAN-BUSQUEDA.md`, del motor (`engine.yaml`) y del flujo de campañas.
No se cambia ningún umbral.

| Criterio | Valor | Fuente |
|---|---|---|
| Coste relativo máximo | `cost_r_max = 0.10` | `engine.yaml` · `fitness` |
| Operaciones mínimas IS | H1: 40; D1: 15 | `engine.yaml` · `validation.by_timeframe` |
| Operaciones mínimas por pliegue | H1: 6; D1: 3 | `engine.yaml` · `validation.by_timeframe` |
| Pliegues | H1: 4; D1: 3 | `engine.yaml` · `validation.by_timeframe` |
| Control de deriva | percentil ≥ 90 | `PLAN-BUSQUEDA.md` |
| Confirmación | OOS-1/OOS-2 limpios; OOS-2 decide | `PLAN-BUSQUEDA.md` |
| Éxito | expectativa neta OOS-2 > 0 (IC 95 % sin cruzar 0 o lo más cerca posible), deriva ≥ 90 y mejora de P(pasar) en una cuenta | `PLAN-BUSQUEDA.md` |
| Parada de la búsqueda | 2026-12-14 sin ninguna estrategia que pase OOS-2 | `PLAN-BUSQUEDA.md` |

El `cost_R` de las tablas de abajo se estima dividiendo el `cost_R` de la tabla
corregida de R2k (que usa 1×ATR como 1R) por el múltiplo de stop de la
hipótesis. Es una estimación de coste, no una medición nueva ni rendimiento.
Cuando falta un dato se escribe **Sin datos**.

## 2. Tabla resumen

| # | Hipótesis | Símbolo · TF | n_total | Ops/año (calendario) | Qué falta | Riesgo principal |
|---|---|---|---:|---|---|---|
| 4 | Deriva pre-FOMC | US500 · H1 (ES continuo) | 6 | 8 (119 en 2010-2024) | Fechas FOMC, bloque de evento; futuros ES y rolls si se quiere coste de futuros | 8 sucesos/año, efecto posiblemente agotado, saltos de roll sin ajustar |
| 5 | Efecto pre-festivo | US100 · D1 (primario); US500 · D1 (confirmación) | 3 | 9-10 (~100 / ~59 en IS) | `pre_holiday` + anclaje correcto de la barra D1 | Efecto antiguo, pocos sucesos, solape con cambio de mes |
| 6 | Reversión tras el fix de Londres | EURUSD y GBPUSD · H1 | 18 | ≤ 252 (el filtro reduce; Sin datos) | Bloque `bar_return_atr` + plantilla | Coste H1 alto, fix ya arbitrado, EUR/GBP correlacionados |
| 7 | Reversión tras caídas fuertes | US100 · D1 (primario); US500 · D1 (confirmación) | 27 | Sin datos (condición de señal; pocas/año) | Nada de código: plantilla existente + spec | Pocas operaciones, misma familia que `d1_extension_reversion` |
| 8 | Estacionalidad intradía del oro (Asia) | XAUUSD · H1 | 6 | ~252 | Plantilla + test de `flat_at` alineado | Estacionalidad de muestra, coste diario, referencia del plan no verificada |

Si se ejecutan las cinco con un solo símbolo primario: **60 combinaciones**
(6 + 3 + 18 + 27 + 6). No se registra ninguna aquí.

## 3. Hipótesis 4 · Deriva antes de la Fed (pre-FOMC)

### 4.1 Hipótesis literal y referencias

El S&P 500 tiende a subir en las 24 horas anteriores al comunicado del FOMC,
porque el mercado cobra una prima por el riesgo de evento (decisión, lenguaje y
conferencia) y la cobra **antes** de la noticia, no después. Si el efecto es
real, debe superar el coste de un ida y vuelta de 24 h y aparecer en la mayoría
de las 8 reuniones anuales, no en una sola.

Referencia principal: Lucca & Moench (2015), *The Pre-FOMC Announcement Drift*,
*Journal of Finance* 70(1), 329-371, DOI `10.1111/jofi.12196` (verificado por
Crossref). El paper documenta una prima media positiva en la ventana de 24 h y
la relaciona con el riesgo de evento; no se usa un número del paper como
garantía de resultado.

### 4.2 Reglas exactas

| Elemento | Regla |
|---|---|
| Lado | **Solo largo**. El corto espejo no tiene la misma justificación económica; sería otra hipótesis (sorpresa post-anuncio). |
| Entrada | A las **14:00 ET** del último día hábil antes del anuncio programado (24 h antes). Implementación: señal en la barra H1 de 13:00-14:00; entrada en el open siguiente, 14:00. |
| Salida | A las **14:00 ET** del día del anuncio: 24 barras H1. Variante de frontera: 23 barras (13:00, una hora antes). |
| Stop de catástrofe | **3,0 × ATR(14) H1**, fijo, no optimizado. Cubre un movimiento de 3 sigma en 24 h y el pico de las 14:00; no es un target. |
| Target | **Ninguno**. La salida es temporal; un target recortaría la deriva. |
| Límites | Máximo 1 operación por reunión; sin pirámide; `cooldown = 0`; sesión 00:00-23:59; sin reentrada si salta el stop. |
| Días sin mercado | Si el día anterior es festivo o fin de semana, se usa la última barra hábil a las 14:00 o antes; la ventana puede ser > 24 h. Es raro y se documenta. |
| Anuncios excluidos | Conferencias telefónicas, reuniones no programadas y votaciones por notación. Solo las 8 reuniones programadas/año. |

### 4.3 Parámetros y n_total

| Parámetro | Valores | Por qué (antes de ver datos) |
|---|---|---|
| `stop_mult` | 2,5 · 3,0 · 3,5 | Es un stop de catástrofe: 2,5-3,5 ATR cubre el ruido de 24 h y el pico del anuncio sin confundirse con la señal. |
| `exit_minutes` | 1380 · 1440 | 24 h es la ventana del paper; 23 h comprueba que el efecto no depende de los últimos 60 minutos. |

`n_total = 3 × 2 = 6`. No se parametriza la hora de entrada: la ventana de 24 h
es la hipótesis; moverla sería optimizar el evento.

### 4.4 Datos, fuente y rango IS

| Opción | Símbolo · TF | Fuente | `usable_from` | IS propuesto | Nota |
|---|---|---|---|---|---|
| Primaria | US500 · H1 | Databento (ES continuo) | `databento:US500:H1` = **2010-06-07** | 2010-06-07 → 2024-06-30 | 98.113 barras H1 en caché; serie continua |
| Alternativa | US500 · H1 | Dukascopy (spot CFD) | `dukascopy:US500:H1` = **2018-01-02** | 2018-01-02 → 2024-06-30 | ~48 anuncios; justo por encima del mínimo H1 de 40 |
| No propuesta | US100 · H1 | Databento o Dukascopy | 2010-06-07 / 2018-01-02 | — | Duplicaría pruebas; el plan dice US500 |

- La caché Databento es un **contrato continuo sin ajuste de precio**
  (`adjust="none"` en `fetch_databento.py`). Los saltos de roll pueden crear
  retornos de 24 h falsos. Antes de registrar hay que usar una tabla de rolls,
  ajustar hacia atrás o excluir las ventanas de roll. **Sin datos** de la tabla
  de rolls en esta sesión.
- La fuente Databento es de futuros, pero la campaña sigue siendo `market: cfd`
  y usa el coste de una cuenta CFD. Es un híbrido: precios ES con spread CFD.
  Para coste de futuros real hace falta conectar `market: futures`, una cuenta
  de futuros (ES/MES) y el perfil de comisiones; hoy `spec.py` no tiene campo
  `market` y `costs.build_cost_book` es CFD. **Lo mínimo** se detalla en §4.6.
- Falta el calendario FOMC dentro del repo. `fomc-fechas.md` lo deja en papel;
  para la campaña hace falta un CSV y un bloque.

### 4.5 Operaciones IS esperadas

- **8 reuniones programadas/año**. 2010-2024 = **119 anuncios** (2020 tuvo 7:
  se canceló la reunión de marzo y se excluyen las dos no programadas). En el
  IS 2010-06 → 2024-06 hay ~112. No se cuenta ninguna señal sobre los datos: es
  calendario puro.
- Cada operación cruza el rollover de las 17:00 NY: **1 noche por operación**;
  ~112-119 noches en el IS. El importe del swap es **Sin datos** hasta R9c.

### 4.6 Bloques DSL, plantillas y lo que falta

Lo que ya sirve:

- `time_between`, `price`, `atr`, `stop` ATR y `time_exit_minutes` existen en
  `blocks.py`/`dsl.py`.
- `month_turn` demuestra el patrón de un nodo de calendario con
  `Signals.exit_index` en `compiler.py`; se puede reutilizar la idea, no el
  código tal cual (ver el aviso de anclaje D1 en §7).

Lo mínimo que falta:

1. `config/discovery/events/fomc.csv` con fecha, hora y tipo (`scheduled`).
2. Un cargador en `calendars.py` y un bloque `fomc_pre` (bool) que marque la
   barra de 13:00-14:00 del día anterior. El bloque solo usa el calendario, no
   precios futuros.
3. Plantilla `pre_fomc_drift.yaml`: `long_entry: fomc_pre`, stop 3×ATR, target
   nulo, `time_exit_minutes` 1440.
4. Tests: fechas conocidas, 2020 excluido, 14:00 exacto, cambio de barras
   futuras no cambia la señal, y `exit_index`/tiempo de salida correctos.
5. Solo si se quiere coste de futuros: conectar `market: futures`, cuenta
   ES/MES y tabla de rolls. Es un cambio mayor; la alternativa es aceptar el
   híbrido ES/CFD y documentarlo.

### 4.7 Coste esperado y swap

`cost_R` a 1×ATR (tabla R2k, últimos 12 meses):

| Cuenta | Símbolo · TF | 1×ATR | Stop 2,5× | Stop 3,0× | Stop 3,5× | Viable |
|---|---|---:|---:|---:|---:|---|
| CFD-006 | US500 · H1 | 0,1491 | 0,0596 | 0,0497 | 0,0426 | Sí |
| CFD-001 | US500 · H1 | — | — | — | — | No permite US500 |

- CFD-001 no admite US500; la única cuenta CFD para este símbolo es CFD-006.
- Si se usara US100 H1: 0,0433 (CFD-001) / 0,0449 (CFD-006) a 1×ATR; a 3× ≈
  0,0144/0,0150.
- Futuros ES: `FuturesCosts` existe en el motor, pero no hay camino de campaña
  ni perfil medido; `cost_R` de futuros = **Sin datos**. El roll tampoco está
  modelado.
- Swap: **1 noche/operación**; ~112-119 noches. Importe **Sin datos** hasta
  R9c.

### 4.8 Riesgo principal

- **Pocas operaciones**: 8/año; una sola reunión puede dominar la media y los
  pliegues. El mínimo H1 de 40 se cumple, pero la potencia es baja.
- **Efecto agotado**: la prima documentada puede haber caído después de
  2015/2020; el IS largo lo dirá, pero no se puede asumir.
- **Roll sin ajustar**: el riesgo técnico más grave de la opción Databento. Un
  salto de roll en la ventana de 24 h se lee como deriva.
- **Hora 14:00**: confirmada en los comunicados de 2016-2026; en 2010-2015 la
  página oficial dice “For immediate release” sin hora. El ancla de 14:00 es la
  regla, no un dato verificado para esos años (ver `fomc-fechas.md`).
- **Solape** con `turn_of_month` cuando una reunión cae a fin de mes; si ambas
  disparan, se están probando los mismos días. Marcar y excluir el solape.

## 4. Hipótesis 5 · Efecto pre-festivo

### 5.1 Hipótesis literal y referencias

Los índices de EE. UU. rinden más en el último día hábil antes de un festivo de
la NYSE que en un día normal, porque la reducción de posiciones y el optimismo
previo al cierre dejan una prima de compra. Si es real, debe superar el coste de
una operación de un día y no depender de Thanksgiving o Navidad.

Referencias: Ariel (1990), *High Stock Returns before Holidays: Existence and
Evidence on Possible Causes*, *Journal of Finance* 45(5), 1611-1626, DOI
`10.1111/j.1540-6261.1990.tb03731.x`; Kim & Park (1994), *Holiday Effects and
Stock Returns: Further Evidence*, *JFQA* 29(1), 145-157, DOI
`10.2307/2331196`. Ambas verificadas por Crossref.

### 5.2 Reglas exactas

| Elemento | Regla |
|---|---|
| Lado | **Solo largo**. El corto espejo no tiene la misma historia económica (optimismo pre-festivo) y duplicaría las pruebas. |
| Entrada | Al cierre del día hábil **anterior** al día pre-festivo. En D1, es la apertura de la barra que cubre el día pre-festivo (ver el aviso de anclaje). |
| Salida | Al cierre del día pre-festivo; salida de calendario, no target. |
| Stop de catástrofe | **3,0 × ATR(14) D1**, fijo. Un stop de 3 ATR cubre un hueco de varios días; la salida real es el calendario. |
| Target | **Ninguno**. |
| Festivos | Solo cierres completos de NYSE: Año Nuevo, MLK, Presidentes, Viernes Santo, Memorial, Juneteenth (desde 2022), 4 de julio, Labor, Thanksgiving, Navidad. Se excluyen cierres especiales y medias sesiones (Nochebuena, 3 de julio). |
| Límites | Máximo 1 operación por festivo; sin pirámide; sin corto. |

### 5.3 Parámetros y n_total

| Parámetro | Valores | Por qué (antes de ver datos) |
|---|---|---|
| `stop_mult` | 2,5 · 3,0 · 3,5 | Stop de catástrofe de una operación de un día; 2,5-3,5 ATR cubre un hueco sin confundirse con ruido. |

`n_total = 3`. **No se parametriza la fecha**: el calendario *es* la hipótesis.
Variar el número de días antes del festivo sería otra hipótesis (anticipación) y
gastaría DSR sin necesidad.

### 5.4 Datos, fuente y rango IS

| Símbolo | Fuente | `usable_from` | IS propuesto | Cuenta de coste | Nota |
|---|---|---|---|---:|---|
| US100 · D1 | Dukascopy | `dukascopy:US100:D1` = **2014-01-01** | 2014-01-01 → 2024-06-30 | CFD-001 y CFD-006 | Primario: 10,5 años, ~100 festivos, coste bajo |
| US500 · D1 | Dukascopy | `dukascopy:US500:D1` = **2018-01-01** | 2018-01-01 → 2024-06-30 | CFD-006 | Confirmación: 6,5 años, ~59 festivos |

- D1 exige Dukascopy (`campaigns.timeframe_source_error`); el bróker no tiene
  historia y Databento D1 solo se admite en specs `confirmation_only`, no en
  registro real.
- **Aviso de anclaje**: la barra D1 está etiquetada por su apertura a las 17:00
  NY y cubre hasta las 17:00 del día siguiente (`resample.py`). La sesión NYSE
  del día D cae en la barra etiquetada **D-1**. La regla debe elegir la barra
  por sesión, no por etiqueta. El patrón `month_turn` actual mapea
  `last_pos[date]` por etiqueta; **no copiarlo sin corregir** (ver §7).
- D1 no puede aislar la sesión 09:30-16:00: mide el día CFD 17:00-17:00, que
  incluye el overnight previo. Si el operador quiere la sesión NYSE exacta, hay
  que usar H1 y otro bloque; es otro TF y otro coste.

### 5.5 Operaciones IS esperadas

- **9-10 festivos completos/año**. US100 2014-2024 ≈ **100** operaciones;
  US500 2018-2024 ≈ **59**. Es calendario puro, no se cuentan señales.
- **1 noche por operación**; ~100 / ~59 noches. Importe del swap: **Sin datos**
  hasta R9c.

### 5.6 Bloques DSL, plantillas y lo que falta

Lo que ya sirve:

- `calendars.nyse_trading_days`, `is_holiday`, `nyse_holidays` y el patrón
  `month_turn` de `compiler.py`/`fastbt.py` (`exit_index` y entrada/salida al
  cierre).
- Stop ATR, target nulo y límites del DSL.

Lo mínimo que falta:

1. `calendars.pre_holiday_pairs(start, end)` que devuelva
   `(entrada, salida)`: entrada = día hábil anterior al pre-festivo; salida =
   día pre-festivo. Debe usar la fecha de **sesión**, no la etiqueta D1.
2. Nodo `pre_holiday` en `dsl.py` (raíz, long-only) y `_pre_holiday_signals` en
   `compiler.py`, copiando la estructura de `month_turn` pero con el mapeo
   corregido.
3. Tests: 4 de julio, Thanksgiving, Navidad, festivo en lunes y en viernes,
   fin de año, ausencia de anticipación (cambiar el futuro no cambia la señal),
   y que la entrada/salida caigan en la sesión correcta.
4. Plantilla `pre_holiday_index.yaml` con `symmetric: false`, `valid_timeframes:
   [D1]`, stop 3×ATR, target nulo.

### 5.7 Coste esperado y swap

`cost_R` a 1×ATR (R2k):

| Cuenta | Símbolo · D1 | 1×ATR | Stop 2,5× | Stop 3,0× | Stop 3,5× | Viable |
|---|---|---:|---:|---:|---:|---|
| CFD-001 | US100 | 0,0078 | 0,0031 | 0,0026 | 0,0022 | Sí |
| CFD-006 | US100 | 0,0081 | 0,0032 | 0,0027 | 0,0023 | Sí |
| CFD-006 | US500 | 0,0278 | 0,0111 | 0,0093 | 0,0079 | Sí |

- Swap: **1 noche/operación**; ~100 (US100) / ~59 (US500) noches. Importe
  **Sin datos** hasta R9c. El swap de índices puede ser negativo o positivo;
  no se asume.

### 5.8 Riesgo principal

- **Efecto antiguo**: la evidencia es fuerte en el siglo XX; puede haberse
  reducido. El IS 2014-2024 lo pone a prueba, pero 9-10 sucesos/año dan poca
  potencia.
- **Clústeres**: Thanksgiving/Navidad y fin de año concentran varios festivos;
  una racha puede dominar la media. Reportar por festivo, no solo la media.
- **Anclaje D1**: si se mapea por etiqueta, la operación se desplaza un día y
  el efecto se mide en la sesión equivocada. Es el riesgo técnico principal.
- **Solape con `turn_of_month`** en diciembre/enero: los mismos días pueden
  estar en dos pruebas. Marcar y excluir el solape.
- **Cierres especiales**: un día de luto o una media sesión no es un festivo
  normal; incluirlos cambia la muestra. Usar solo cierres completos regulares.

## 5. Hipótesis 6 · Reversión tras el fix de Londres (16:00)

### 6.1 Hipótesis literal y referencias

Alrededor del fix WM/Reuters de las 16:00 de Londres se concentran órdenes de
liquidez; el flujo empuja el precio antes del fix y ese impacto se revierte
después porque era una demanda temporal. Si la hora previa al fix se mueve más
de X ATR, el precio vuelve en las 1-3 horas siguientes; debe superar el coste de
un ida y vuelta intradía y no ser solo un aumento de volatilidad.

Referencias: Evans (2018), *Forex trading and the WMR Fix*, *Journal of Banking
& Finance* 87, 233-247, DOI `10.1016/j.jbankfin.2017.09.017`; Krohn, Mueller &
Whelan (2024), *Foreign Exchange Fixings and Returns around the Clock*,
*Journal of Finance*, DOI `10.1111/jofi.13306`. Ambas verificadas por Crossref.
El signo y el tamaño exactos son la hipótesis a probar, no un dato del paper.

### 6.2 Reglas exactas

| Elemento | Regla |
|---|---|
| Lado | **Simétrico**: largo si el retorno de 15:00-16:00 Londres < -umbral; corto si > +umbral. El espejo es exacto. |
| Entrada | A las **16:00 Londres**, en el open siguiente al cierre de la barra de 15:00-16:00. La señal se calcula solo con esa barra (`time_between 15:00-15:59`). |
| Salida | Por tiempo, tras **1-3 barras H1** (17:00, 18:00 o 19:00 Londres). Sin target. |
| Stop de catástrofe | **2,5 o 3,0 × ATR(14) H1**, fijo. 2,0× no es viable por coste en GBPUSD CFD-006 (ver §5.7); no se incluye. |
| Target | **Ninguno**; la reversión es de horizonte fijo y un target la recortaría. |
| Sesión | Europe/London 08:00-19:00; `flat_at` 18:00 (última barra) o salida por tiempo; máximo 1 operación/día; sin overnight. |
| Días sin barra | Si falta la barra de 15:00 (festivo/cierre), no hay operación. |

### 6.3 Parámetros y n_total

| Parámetro | Valores | Por qué (antes de ver datos) |
|---|---|---|
| `threshold_atr` | 0,25 · 0,50 · 0,75 | Mide el desequilibrio pre-fix en ATR, no en pips: 0,25 es un movimiento normal, 0,75 es extremo. |
| `hold_bars` | 1 · 2 · 3 | La reversión documentada es de minutos-horas; 1-3 barras H1 es el horizonte razonable. |
| `stop_mult` | 2,5 · 3,0 | Mantiene `cost_R` ≤ 0,10 en GBPUSD CFD-006; 2,0× lo incumple. |

`n_total = 3 × 3 × 2 = 18`.

### 6.4 Datos, fuente y rango IS

| Símbolo | Fuente | `usable_from` | IS propuesto | Cuenta de coste | Nota |
|---|---|---|---:|---:|---|
| EURUSD · H1 | Dukascopy (spot) | `dukascopy:EURUSD:H1` = **2003-05-04** | 2010-01-01 → 2024-06-30 | CFD-001 y CFD-006 | Serie spot, la correcta para coste CFD |
| GBPUSD · H1 | Dukascopy (spot) | `dukascopy:GBPUSD:H1` = **2003-05-04** | 2010-01-01 → 2024-06-30 | CFD-001 y CFD-006 | Misma nota; alta correlación con EURUSD |
| Alternativa | Databento 6E/6B H1 | 2010-06-07 | — | — | Precios de futuros con coste CFD; no mezclar sin documentar |

- H1 no está bloqueado por `timeframe_source_error`; Dukascopy H1 se puede
  cargar y remuestrear desde M1.
- `session_tz` de EURUSD/GBPUSD es `Europe/London` en `engine.yaml`, así que
  `time_between` y la sesión se evalúan en hora de Londres.
- Falta el bloque `bar_return_atr`; no hay nodo de aritmética en el DSL para
  multiplicar `body` por `ATR`.

### 6.5 Operaciones IS esperadas

- El fix ocurre **cada día hábil**: máximo ~252/año. El umbral de 0,25-0,75 ATR
  reduce la muestra, pero **no se cuenta sobre los datos**. El mínimo H1 de 40
  se alcanza con pocos meses; el riesgo es el exceso de operaciones y el coste,
  no la falta de muestra.
- **0 noches**: 16:00-19:00 Londres cae antes del rollover de las 17:00 NY.
  Swap: 0.

### 6.6 Bloques DSL, plantillas y lo que falta

Lo que ya sirve:

- `time_between`, `atr`, `price`, stop ATR, `time_exit_minutes`, sesión con
  `tz` Europe/London.
- `mirror`/`symmetric` para el largo-corto exacto.

Lo mínimo que falta:

1. Bloque `bar_return_atr`: `(close - open) / ATR(n)`, salida float,
   `mirror="signed"`, `n` fijo 14 (o parámetro 14). Sin look-ahead: usa la barra
   cerrada.
2. Plantilla `london_fix_reversion.yaml`:
   `long_entry = and(time_between("15:00","15:59"), lt(bar_return_atr, -threshold))`;
   `short_entry` espejo con `gt(..., +threshold)`; `exit.time_exit_minutes` =
   60/120/180; stop ATR 2,5/3,0; target nulo; `session.start "08:00"`,
   `session.end "19:00"`, `flat_at "18:00"`.
3. Tests: barra sintética con cuerpo -1 ATR → señal larga; +1 ATR → corta;
   cambiar el futuro no cambia la señal; `time_between` solo marca las 15:00;
   el espejo es exacto.

### 6.7 Coste esperado y swap

`cost_R` a 1×ATR (R2k) y escalado por stop:

| Cuenta | Símbolo · H1 | 1×ATR | Stop 2,5× | Stop 3,0× | Viable |
|---|---|---:|---:|---:|---|
| CFD-001 | EURUSD | 0,1576 | 0,0630 | 0,0525 | Sí |
| CFD-006 | EURUSD | 0,2039 | 0,0816 | 0,0680 | Sí |
| CFD-001 | GBPUSD | 0,1556 | 0,0622 | 0,0519 | Sí |
| CFD-006 | GBPUSD | 0,2209 | 0,0884 | 0,0736 | Sí |

- A stop 2,0×: EURUSD CFD-006 0,1020 y GBPUSD CFD-006 0,1105, ambos **> 0,10**.
  Por eso el grid excluye 2,0×. Si el operador quiere 2,0×, la campaña no pasa
  el gate de coste en CFD-006.
- Swap: **0 noches**. El coste es el spread/comisión de un ida y vuelta diario.

### 6.8 Riesgo principal

- **Fix ya arbitrado**: el efecto puede haberse reducido después de 2015; el IS
  largo lo dirá, pero la literatura no garantiza que siga.
- **Resolución H1**: el fix es una ventana de minutos; la barra de 15:00-16:00
  es un proxy y la de 16:00 incluye flujo post-fix. No se puede afirmar que se
  está midiendo el fix exacto.
- **Correlación EUR/GBP**: dos campañas no son independientes; si se ejecutan
  las dos, la segunda es confirmación, no una prueba nueva.
- **Coste alto**: es el TF más caro; un movimiento pequeño no cubre el spread.
  La hipótesis debe superar 0,05-0,09 R de coste, no solo ser positiva bruta.
- **Solape con carriles demo FX** (EURUSD london_pullback, USDJPY
  tokyo_breakout) en horas similares; no es la misma regla, pero la exposición
  está correlacionada.

## 6. Hipótesis 7 · Reversión de corto plazo tras caídas fuertes

### 6.1 Hipótesis literal y referencias

Tras una caída extrema de corto plazo en un índice que sigue en tendencia larga,
el precio rebota en los días siguientes porque la caída es sobrerreacción y
liquidez, no un cambio de régimen. Comprar la extensión debe superar el coste de
una operación de varios días y ser estable en los tres pliegues.

Referencias: De Bondt & Thaler (1985), *Does the Stock Market Overreact?*,
*Journal of Finance* 40(3), 793-805, DOI `10.1111/j.1540-6261.1985.tb05004.x`;
Jegadeesh (1990), *Evidence of Predictable Behavior of Security Returns*,
*Journal of Finance* 45(3), 881-898, DOI `10.1111/j.1540-6261.1990.tb05110.x`
(verificadas). Connors & Alvarez (2008), *Short Term Trading Strategies That
Work*, es práctica (RSI-2), no un paper.

### 6.2 Reglas exactas

| Elemento | Regla |
|---|---|
| Lado | **Solo largo**. El sesgo largo del índice y la compra del dip son asimétricos; el corto espejo sería otra hipótesis (continuación bajista). |
| Entrada | Open siguiente a una barra D1 con `close > SMA(200)`, `zscore(20) < -2,0` y `RSI(2) < 10`. Es la condición exacta de `d1_extension_reversion.yaml`. |
| Salida | Target **1R**, stop **2,0 × ATR(14) D1**, tiempo máximo **5 días** (7.200 minutos), lo que ocurra primero. |
| Stop de catástrofe | 2,0 × ATR(14) D1, fijo (el grid prueba 1,5/2,0/2,5). Da espacio al rebote tras la caída; no es un stop ajustado. |
| Target | 1R fijo. La reversión es de corto plazo; 1R captura el rebote sin exigir una tendencia nueva. |
| Límites | Máximo 1 operación/día; sin pirámide; si ya hay posición, la señal se ignora. |

### 6.3 Parámetros y n_total

| Parámetro | Valores | Por qué (antes de ver datos) |
|---|---|---|
| `z_n` | 10 · 20 · 30 | Ventana de la desviación: 10 días es corto, 30 es medio; 20 es el centro. |
| `z_entry` | -1,5 · -2,0 · -2,5 | Define “caída extrema”; -2,0 es el valor central de la plantilla, -2,5 exige más sobrerreacción. |
| `stop_mult` | 1,5 · 2,0 · 2,5 | Control de riesgo del rebote; 2,0 es el centro, 1,5/2,5 prueban sensibilidad. |

`n_total = 3 × 3 × 3 = 27`. `RSI(2) < 10`, `SMA(200)` y target 1R quedan fijos:
son la definición de la hipótesis, no dimensiones de optimización.

### 6.4 Datos, fuente y rango IS

| Símbolo | Fuente | `usable_from` | IS propuesto | Cuenta de coste | Nota |
|---|---|---|---:|---:|---|
| US100 · D1 | Dukascopy | `dukascopy:US100:D1` = **2014-01-01** | 2014-01-01 → 2024-06-30 | CFD-001 y CFD-006 | Primario: 10,5 años, coste 0,0078/0,0081 |
| US500 · D1 | Dukascopy | `dukascopy:US500:D1` = **2018-01-01** | 2018-01-01 → 2024-06-30 | CFD-006 | Confirmación: 6,5 años, coste 0,0278 |

- D1 exige Dukascopy; no hay Databento D1 para registro real.
- La plantilla `d1_extension_reversion.yaml` ya existe con este grid exacto
  (`parameter_space` y `grid`). El `instrument: XAUUSD` del YAML se sobrescribe
  con el instrumento de la campaña; no hace falta editar la plantilla.
- **Nada de código nuevo**. Solo una spec con `template:
  d1_extension_reversion`, `instrument: US100`, `timeframe: D1`,
  `data_source: dukascopy`, IS y `mode: grid`.

### 6.5 Operaciones IS esperadas

- **Sin datos**: la condición es de señal (z-score, RSI-2, SMA-200); no se puede
  estimar por calendario y no se cuenta sobre los datos. Es la hipótesis con más
  riesgo de muestra pequeña: el mínimo D1 es 15 operaciones IS y 3 por pliegue.
- US100 (10,5 años) tiene más margen que US500 (6,5 años); si US500 no llega a
  15, se descarta sin leer OOS.
- **4-5 noches por operación** si se agota el tiempo máximo; target/stop pueden
  salir antes. Swap: 4-5 noches por operación.

### 6.6 Bloques DSL, plantillas y lo que falta

Lo que ya sirve:

- `config/discovery/templates/d1_extension_reversion.yaml` con `symmetric:
  false`, `valid_timeframes: [D1]`, `z_n`, `z_entry`, `stop_mult`, target 1R,
  `time_exit_minutes: 7200` y `RSI(2) < 10`.
- `zscore`, `rsi`, `sma`, `atr`, stop/target del DSL.

Lo que falta:

- **Nada de código**. Solo la spec y el registro/approve del operador.
- Aviso: la misma familia ya se usó en la feasibility N2 sobre XAUUSD; en US100
  es un símbolo nuevo, pero no una familia nueva. Si el operador considera que
  “ya está probada”, esta hipótesis se cae.

### 6.7 Coste esperado y swap

`cost_R` a 1×ATR (R2k):

| Cuenta | Símbolo · D1 | 1×ATR | Stop 1,5× | Stop 2,0× | Stop 2,5× | Viable |
|---|---|---:|---:|---:|---:|---|
| CFD-001 | US100 | 0,0078 | 0,0052 | 0,0039 | 0,0031 | Sí |
| CFD-006 | US100 | 0,0081 | 0,0054 | 0,0041 | 0,0032 | Sí |
| CFD-006 | US500 | 0,0278 | 0,0185 | 0,0139 | 0,0111 | Sí |

- Swap: 4-5 noches/operación; importe **Sin datos** hasta R9c.
- El coste no es el problema; la muestra y la estabilidad sí.

### 6.8 Riesgo principal

- **Pocas operaciones**: es el riesgo dominante. Si US500 no llega a 15 en 6,5
  años, no se evalúa; US100 es la opción con más historia.
- **Misma familia**: `d1_extension_reversion` ya se probó en XAUUSD; el operador
  puede considerarlo repetido. No es una familia distinta, es otro símbolo.
- **Régimen**: el filtro SMA(200) funciona en mercados alcistas; en un mercado
  bajista la caída sigue. Los pliegues deben cubrir 2020 y 2022.
- **Target 1R**: puede ser demasiado pequeño para un rebote de varios días, o
  demasiado grande si el rebote es débil; está fijado por la plantilla, no se
  optimiza.
- **D1 17:00**: el “cierre” es el de la sesión CFD (17:00 NY), no el cierre
  NYSE de las 16:00; incluye el overnight. Es coherente con el motor, pero no
  es exactamente el cierre del índice.

## 7. Hipótesis 8 · Estacionalidad intradía del oro (Asia vs Londres/NY)

### 7.1 Hipótesis literal y referencias

El oro tiene un retorno medio positivo en la sesión asiática (19:00-03:00 NY) y
plano o negativo en Londres/NY, porque la demanda física asiática y el riesgo
overnight se pagan en esa ventana. Comprar al inicio de Asia y vender al final
debe superar el coste de un ida y vuelta diario; es una estacionalidad intradía,
no una tendencia.

Referencias verificables: Iwatsubo, Watkins & Xu (2018), *Intraday seasonality
in efficiency, liquidity, volatility and volume: Platinum and gold futures in
Tokyo and New York*, *Journal of Commodity Markets*, DOI
`10.1016/j.jcomm.2018.05.001`; Speck (2013), *Intraday Movements of the Gold
Price 1986-2012*, en *The Gold Cartel*, DOI `10.1057/9781137286437.0012`.
**Baur 2013, la referencia del plan, no se pudo verificar para estacionalidad
intradía**: se marca **por verificar** y probablemente no es la referencia
correcta. Iwatsubo et al. estudian liquidez/volatilidad/volumen, no
necesariamente el signo del retorno; el signo es la hipótesis a probar.

### 7.2 Reglas exactas

| Elemento | Regla |
|---|---|
| Lado | **Solo largo** en Asia. El corto de Asia es otra hipótesis (asimetría de la demanda física); no se espeja. |
| Entrada | A las **19:00 NY**, open siguiente a la barra de 18:00-19:00. Sesión 18:00-03:00; señal `time_between("18:00","18:59")`. |
| Salida | A las **03:00 NY**, al cierre de la última barra. `flat_at` **02:00** (la barra de 02:00 cierra a las 03:00); 02:45 no funciona en H1 porque no hay barra a esa hora. |
| Stop de catástrofe | **2,0 × ATR(14) H1** (grid 1,5/2,0/2,5), fijo. Cubre noticias/gaps de la sesión; no es un target. |
| Target | **Ninguno**; la salida es temporal. |
| Límites | Máximo 1 operación/día; sin pirámide; lunes-viernes; si falta la barra de 18:00 (viernes después del cierre), no hay operación. |
| Noches | **0**: 19:00-03:00 NY no cruza el rollover de las 17:00. |

### 7.3 Parámetros y n_total

| Parámetro | Valores | Por qué (antes de ver datos) |
|---|---|---|
| `stop_mult` | 1,5 · 2,0 · 2,5 | Stop de catástrofe de una sesión; 2,0 es el centro y mantiene `cost_R` ~0,02. |
| `flat_at` | 01:00 · 02:00 | 02:00 es el cierre real de Asia; 01:00 prueba si el efecto se agota una hora antes. |

`n_total = 3 × 2 = 6`. La entrada a las 19:00 y la sesión 18:00-03:00 quedan
fijas: son la hipótesis. `flat_at 02:45` no se incluye porque en H1 no existe
una barra a las 02:45 y el `flat_flag` nunca se activaría.

### 7.4 Datos, fuente y rango IS

| Símbolo | Fuente | `usable_from` | IS propuesto | Cuenta de coste | Nota |
|---|---|---|---:|---:|---|
| XAUUSD · H1 | Dukascopy (spot) | `dukascopy:XAUUSD:H1` = **2005-01-02** | 2010-01-01 → 2024-06-30 | CFD-001 y CFD-006 | Serie spot, la correcta para coste CFD |
| Alternativa | Databento GC H1 | `databento:XAUUSD:H1` = **2010-06-07** | 2010-06-07 → 2024-06-30 | — | Futuros con coste CFD; no mezclar sin documentar |

- `session_tz` de XAUUSD es `America/New_York` en `engine.yaml`; las horas de la
  regla son NY.
- Falta solo la plantilla; no hay bloque nuevo.

### 7.5 Operaciones IS esperadas

- **Una por día hábil**: ~252/año; 2010-2024 ≈ 3.600. Es calendario puro, no se
  cuentan señales. El mínimo H1 de 40 es amplio; el riesgo es el coste diario y
  el exceso de operaciones.
- **0 noches**; swap 0. El coste es spread/comisión de un ida y vuelta diario.

### 7.6 Bloques DSL, plantillas y lo que falta

Lo que ya sirve:

- `time_between` con sesión que cruza medianoche (`_session_mask` soporta
  `start > end`), `atr`, stop, `flat_at` y `weekday_in`.
- No hace falta `session_return`: la regla es una ventana temporal, no un
  retorno condicional.

Lo mínimo que falta:

1. Plantilla `asia_session_gold.yaml`:
   `session.start "18:00"`, `session.end "03:00"`, `flat_at "02:00"`,
   `long_entry: {kind: time_between, start: "18:00", end: "18:59"}`,
   `short_entry: null`, stop ATR 2,0, target nulo, `max_trades_per_day: 1`.
2. Tests: la barra de 18:00 entra en la sesión, la de 02:00 activa el flat, la
   de 03:00 queda fuera, la entrada es a las 19:00, no hay operación el viernes
   después del cierre, y cambiar el futuro no cambia la señal.
3. Verificar que `flat_at` está alineado con una apertura de barra H1; si no, el
   `flat_flag` no se activa y la posición se queda abierta.

### 7.7 Coste esperado y swap

`cost_R` a 1×ATR (R2k):

| Cuenta | Símbolo · H1 | 1×ATR | Stop 1,5× | Stop 2,0× | Stop 2,5× | Viable |
|---|---|---:|---:|---:|---:|---|
| CFD-001 | XAUUSD | 0,0431 | 0,0287 | 0,0216 | 0,0172 | Sí |
| CFD-006 | XAUUSD | 0,0375 | 0,0250 | 0,0188 | 0,0150 | Sí |

- Swap: **0 noches**. El coste diario es la prueba: el retorno de Asia debe
  superar ~0,02-0,03 R por día.

### 7.8 Riesgo principal

- **Estacionalidad de muestra**: el patrón puede ser fuerte en 2005-2012 y
  desaparecer después; los pliegues deben cubrir 2020 y 2022-2024.
- **Coste diario**: 252 idas y vueltas al año; un retorno medio pequeño se lo
  come el spread. Es la hipótesis con más riesgo de “positiva bruta, negativa
  neta”.
- **Referencia del plan no verificada**: Baur 2013 no se pudo confirmar; la
  hipótesis se apoya en Iwatsubo et al. (2018) y Speck (2013), que no garantizan
  el signo del retorno. Marcar como hipótesis exploratoria, no como efecto
  establecido.
- **Solape con el carril demo XAUUSD** (Donchian H4): no es la misma regla, pero
  la exposición al oro está correlacionada.
- **`flat_at` mal alineado**: si se pone 02:45 en H1, no hay barra y la posición
  no se cierra; es un fallo silencioso. El test debe cubrirlo.

## 8. Lo mínimo que hay que construir (resumen)

| # | Construcción | Hipótesis | Tamaño | Dónde |
|---|---|---|---|---|
| 1 | `fomc.csv` + cargador + bloque `fomc_pre` + plantilla | 4 | Medio | `config/discovery/events/`, `calendars.py`, `blocks.py`, `templates/` |
| 2 | `market: futures` + cuenta ES/MES + rolls | 4 | Grande (opcional) | `spec.py`, `costs.py`, `campaigns.py`, `config/propfund/` |
| 3 | `pre_holiday_pairs` + nodo `pre_holiday` + mapeo sesión D1 | 5 | Medio | `calendars.py`, `dsl.py`, `compiler.py`, `templates/` |
| 4 | Bloque `bar_return_atr` + plantilla London fix | 6 | Pequeño | `blocks.py`, `templates/` |
| 5 | Nada de código; solo spec | 7 | Ninguno | `.orquestador/specs/` |
| 6 | Plantilla `asia_session_gold` + tests de `flat_at` | 8 | Pequeño | `templates/`, `tests/` |
| 7 | Auditoría del anclaje D1 (fecha NYSE → barra) | 5 y `turn_of_month` | Pequeño pero crítico | `compiler.py`, tests |

Orden recomendado por coste de construcción, no por número:

1. **H7** (sin código; solo spec).
2. **H8** (plantilla + tests; sin bloque nuevo).
3. **H5** (calendario + mapeo D1; el más delicado).
4. **H6** (bloque pequeño; coste H1 justo).
5. **H4** (calendario FOMC + evento; futuros/rolls si se quieren de verdad).

Si el operador quiere respetar el orden del plan, H4 va primero, pero es la que
más infraestructura pide y la que más riesgo técnico tiene.

## 9. Avisos

- **Hipótesis 9-10**: no existen en `PLAN-BUSQUEDA.md`. No se inventan. Si el
  operador las tiene en otra copia, hay que añadirlas antes de documentarlas.
- **D1 y etiquetas**: la barra D1 se etiqueta por su apertura a las 17:00 NY y
  cubre hasta las 17:00 del día siguiente. Cualquier regla de calendario NYSE
  (pre-festivo, cambio de mes) debe elegir la barra por la **sesión**, no por la
  etiqueta. El `month_turn` actual mapea por etiqueta; el test existente
  comprueba la etiqueta, no la sesión. Revisar antes de copiar el patrón.
- **Databento**: la serie continua está sin ajuste de roll. Para H4 (ventana de
  24 h) un salto de roll puede falsear la señal. Hace falta tabla de rolls o
  ajuste back; **Sin datos** en esta sesión.
- **Futuros ES**: `FuturesCosts` existe en `fastbt.py`, pero no hay campaña con
  `market: futures`, cuenta ES/MES ni perfil de comisiones conectado. El H4 con
  Databento es un híbrido ES/CFD; documentarlo.
- **Hora FOMC**: 14:00 ET confirmada en los comunicados de 2016-2026; en
  2010-2015 la página oficial dice “For immediate release” sin hora. El ancla de
  la regla es 14:00; la hora exacta de esos años queda **por verificar** en el
  PDF. Ver `fomc-fechas.md`.
- **Baur 2013**: no verificada para estacionalidad intradía del oro. La
  referencia del plan se marca **por verificar**; no se usa como prueba.
- **H6 coste**: a stop 1,0×ATR las celdas H1 de EURUSD/GBPUSD no son viables; a
  2,0× CFD-006 sigue por encima de 0,10. El grid solo incluye 2,5/3,0×. No
  “arreglar” el coste bajando el stop.
- **H7 muestra**: la condición es de señal; no se puede estimar por calendario.
  Es la hipótesis con más riesgo de no llegar a 15 operaciones D1. No se cuenta
  sobre los datos.
- **Swap**: R9c está midiendo el swap; en el `HEAD` leído no hay importe. Este
  documento solo cuenta noches; no inventa tasas.
- **Sin rendimiento**: no se calculó expectativa, PF, percentil de deriva,
  Monte Carlo ni ninguna métrica de rendimiento. Las tablas de coste son coste,
  no resultado.

## 10. Cierre

- Ninguna campaña registrada; ningún DSR consumido; ninguna spec aprobada.
- Ningún cambio de código, configuración, datos ni git.
- Archivos escritos: `.orquestador/HIPOTESIS-4-10.md` y
  `.orquestador/fomc-fechas.md`.
- Siguiente: el operador decide si acepta el orden, si añade 9-10 y si autoriza
  la construcción mínima de §8. Sin esa decisión, no se ejecuta nada.

PARA.
