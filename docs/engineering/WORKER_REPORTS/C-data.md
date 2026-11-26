# WORKER C · Auditoría de calidad de datos

- **ID tarea:** ENG-C1
- **SHA:** adc0eec
- **Fecha:** 2026-11-26
- **Modo:** solo lectura sobre el repositorio. No se descargó nada, no se usó ninguna clave y no se lanzó
  ninguna campaña, research ni barrido. Las reproducciones usan datos **sintéticos** y están en
  `/tmp/claude-0/-home-user-trading-lab/89310f7f-0a4e-5602-b5a9-56cac624406b/scratchpad/C/`
  (`SCR/` en adelante). Se ejecutan con `.venv/bin/python -W ignore SCR/<script>`.
- **Sin datos de mercado en el contenedor:** `data/cache/` no existe aquí. Las cifras de cobertura real
  son **Sin datos**; solo se citan las que ya constan en informes del repositorio.
- **Alcance:** `discovery/{data_sources,fetch_databento,fetch_dukascopy,fetch,resample,data_quality,
  source_quality,futures_roll,calendars,sessions,timeframes}.py`, `lab discovery data-check`
  (`cli.py:10106`) y su uso en `campaigns._quality`.
- **Documentos previos leídos:** `docs/tradinglab2/06_TRADINGLAB_DATA_AND_COST_AUDIT.md`,
  `docs/datacheck.md`, `TL3_REPORTS/edge2_costes.md`, `.orquestador/COLA-EDGE-2.md`,
  `TL3_REPORTS/TL3_DATA_AND_COSTS_AUDIT.md`, `TL3_REPORTS/TL3_FORENSIC_AUDIT.md` (G-2).

## Resumen por severidad

| ID | Sev. | Estado | Tema |
|---|---|---|---|
| C-01 | HIGH | NUEVO | `data-check` en M1–M30 no ve huecos ≥ 4 h dentro de sesión (H1/H4 sí): el IS 2015-2019 de EDGE-2 M15/M30 pasa con noches enteras sin datos |
| C-02 | HIGH | NUEVO | La reanudación de Dukascopy da por completo un mes con día máximo ≥ 20: los últimos días del mes se pierden para siempre |
| C-03 | MEDIUM | NUEVO | La última vela agregada (o la vela M5 en curso de MT5) se guarda y se trata como cerrada aunque sea parcial |
| C-04 | HIGH | CONOCIDO (TL3_FORENSIC_AUDIT G-2; TL3_DATA_AND_COSTS_AUDIT D2) + detalle NUEVO | Futuros NQ con identidad del CFD US100: M15/M30/H1 con `databento` se pueden registrar con cuentas de coste CFD; los rolls `c` y `v` escriben el mismo fichero |
| C-05 | MEDIUM | CONOCIDO parcial (TL3_DATA_AND_COSTS_AUDIT §3) + NUEVO | `futures_roll.detect_rolls` borra saltos reales, no ve rolls fuera de las 18:00 ET y su validación residual es tautológica |
| C-06 | MEDIUM | NUEVO | `gap_pct` cuenta eventos, no velas: 8 días hábiles perdidos en H1 = 0,018 % → solo `warn` |
| C-07 | LOW | NUEVO | Año Nuevo en sábado marca el viernes 31-dic como festivo (NYSE, CME, FX y `nyse_calendar` 2021-12-31) |
| C-08 | LOW | NUEVO (verificar) | Calendario CME: Memorial, 4-jul, Labor, Acción de Gracias y Juneteenth como cierre completo |
| C-09 | LOW | NUEVO | Rejilla H4 de Databento (corte 18:00) distinta de la HTF del compilador (corte 17:00) |
| C-10 | LOW | NUEVO | `dataset_hash` ignora ASK, volumen y spread |
| C-11 | LOW | NUEVO | Volumen: VWAP mezcla volumen Dukascopy, tick volume MT5 y contratos CME, y cae a 1,0 en silencio; `tick_volume`/`real_volume` se agregan con `last` |
| C-12 | LOW | NUEVO | El doc 06 §3 promete controles que `data_quality` no implementa (continuidad de rolls, zona declarada frente a observada, `point/digits`) |
| C-13 | LOW | NUEVO | Una sola vela OHLC inválida de Dukascopy bloquea el mes entero con el mensaje engañoso «días sin respuesta» |
| C-14 | LOW | NUEVO | Los duplicados se eliminan en silencio (`keep="last"`) antes del control: «Duplicados 0» en Dukascopy y Databento no prueba nada |

---

## 1. Confirmado con reproducción

### C-01 · HIGH · NUEVO: `data-check` en M1–M30 no ve huecos ≥ `max_gap_hours` dentro de sesión

- **Archivo:** `src/tradinglab/discovery/data_quality.py:591` (`_gap_analysis`);
  `src/tradinglab/discovery/source_quality.py:28-36` (`_GAP_RULES`);
  `src/tradinglab/discovery/source_quality.py:73` (`missing_weekdays`).
- **Descripción:** en TF < 60 min, cualquier salto `>= max_gap` (4 h) se descarta **antes** de
  clasificarlo, porque se supone que es un fin de semana o un festivo:

  ```python
  if tf_minutes < 60 and (minutes <= threshold or minutes >= max_gap):
      continue
  ```

  En TF ≥ 60 min no hay filtro: cada hueco pasa por `_calendar_gap(_session)`, que sí comprueba si falta
  una sesión hábil. Para los **mismos** minutos que faltan, M15/M30 dan `ok` y H1/H4 dan `warn`/`fail`.
  El `max_gap_hours` de `_GAP_RULES` para H1 (6), H4 (24) y D1 (72) no se usa en ningún sitio. El
  contador «Sesiones sin datos» (`missing_weekdays`) agrupa por fecha NY y tampoco ve una sesión
  17:00→17:00 que falte, porque las fechas vecinas sí tienen barras.
- **Evidencia:** `SCR/r01_gap_m15_blind.py`. M1 24/5 sintético (enero-febrero de 2024) con 12 h
  borradas el miércoles 17-ene y la sesión completa del jueves 8-feb:

  ```
   M15: status=ok   non_scheduled_gaps=0 gap_pct=0.0 missing_weekdays=0 []
   M30: status=ok   non_scheduled_gaps=0 gap_pct=0.0 missing_weekdays=0 []
    H1: status=warn non_scheduled_gaps=2 gap_pct=0.002157 missing_weekdays=0 []
          2024-01-17T00:00:00-05:00 min= 720.0
          2024-02-07T17:00:00-05:00 min= 1500.0
    H4: status=fail non_scheduled_gaps=2 gap_pct=0.008547 missing_weekdays=0 []
  ```
- **Relación con EDGE-2 Y0:** `TL3_REPORTS/edge2_costes.md §1` cuenta en H1, solo en US100, 182/252/251/69
  huecos por año en 2015-2018 («noche Dukascopy», de 8 a 10 h). En M15 cuenta 2/0/0/0. Ese informe
  concluye «no es un error del control». El código muestra que **sí hay una asimetría del control**:
  en M15/M30 esas noches miden más de 4 h y se descartan sin clasificar. La hipótesis ya estaba
  apuntada en `.orquestador/COLA-EDGE-2.md` («efecto de `gap_factor` × TF con `max_gap_hours`»), pero
  Y0 la descartó. `TL3_REPORTS/edge2_plan.md:34-39` registra seis campañas US100 M15/M30 con IS
  `2015-01-02:2019-12-31`, justo el periodo con esas noches vacías. Sin la caché no se puede comprobar
  en este contenedor cuántas caen dentro del IS (**Sin datos**), pero el control que las validó no
  podía verlas.
- **Impacto técnico:** el control `fail_if_gap_pct_gt` es inútil en M1–M30 para huecos largos, que son
  los más graves. Un día o una noche entera sin datos pasan como `ok`.
- **Impacto estadístico:** los indicadores con ventana (ATR, Bollinger, Donchian) cruzan la noche vacía
  como si fueran velas contiguas. Las operaciones que siguen abiertas sobre el hueco ven un salto de
  precio que no se pudo operar, y los stops se ejecutan al precio de reapertura sin la trayectoria
  intermedia. Los resultados del IS de M15/M30 en 2015-2018 pueden ser no reproducibles con datos
  completos, y el DSR cuenta esas pruebas como válidas.
- **Corrección mínima:** en TF < 60, clasificar también los huecos `>= max_gap` con
  `_calendar_gap(_session)`, igual que en H1. El filtro `max_gap` solo debe excusar lo que el
  calendario o la sesión explican. Después, volver a pasar `data-check` sobre los planes M15/M30 de
  EDGE-2 sin tocar umbrales. Antes de cambiar nada hace falta la aprobación del operador: cambia
  veredictos de campañas ya registradas.
- **Test de regresión:** con el mismo M1 sintético, M15, M30, H1 y H4 deben dar el mismo número de
  huecos no programados (2). Una noche de 9 h sin datos un martes debe contar como hueco en M15. Un fin
  de semana y un festivo NYSE no deben contar en ningún TF.

### C-02 · HIGH · NUEVO: la reanudación de Dukascopy pierde el final del mes anterior

- **Archivo:** `src/tradinglab/discovery/fetch_dukascopy.py:357-361` y `:416-424` (`download`).
- **Descripción:** un mes se marca «completo» si su última vela cae el día 20 o después. El mes en
  curso se vuelve a descargar mientras siga siendo el mes en curso, pero en cuanto cambia el mes se
  salta. Si la última ejecución fue entre el 20 y el último día del mes, los días siguientes no se
  descargan nunca. El fin por defecto, `hoy 00:00 − 1 µs`, hace que esto ocurra siempre que se actualiza
  a partir del día 21. Además, un HTTP 404 se toma como día sin mercado (`:226-227`), en silencio.
- **Evidencia:** `SCR/r02_dukascopy_month_tail.py` (feed simulado con `httpx.MockTransport`, sin red):

  ```
  run1 end: 2026-11-24T00:59:00+00:00 months: [('2026-11', 1020)]
  run2 skipped: 1 fetched: 1 months: [('2026-12', 120)]
  dias de noviembre >= 20 en cache: ['2026-11-20', '2026-11-23', '2026-11-24']
  ```

  Faltan para siempre el 25, 26, 27 y 30 de noviembre, salvo que se use `--force`.
- **Impacto:** huecos permanentes de 1 a 10 días hábiles a fin de mes. En M15/M30 no los detecta nadie
  (C-01), en H1/H4 pesan muy poco (C-06) y ninguno de los dos casos llega a `fail`. Si el hueco cae
  dentro de OOS-2, la cobertura del tramo sellado queda incompleta sin aviso.
- **Corrección mínima:** dar un mes por completo solo si su última vela es la del último día hábil del
  mes (o, como mínimo, la del último día con datos ≥ día 28) y, en todo caso, volver a descargar siempre
  el mes anterior al actual. Contar los 404 de días hábiles y avisar de ellos.
- **Test de regresión:** el escenario de `r02`, con dos ejecuciones (25-nov y 3-dic), debe dejar en
  caché todos los días hábiles de noviembre.

### C-03 · MEDIUM · NUEVO: velas parciales aceptadas como cerradas

- **Archivo:** `src/tradinglab/discovery/snapshots.py:73-90` (`closed_bars`);
  `src/tradinglab/discovery/resample.py:100-128` (`resample_session`);
  `src/tradinglab/discovery/fetch.py:163-167,224-226` (`download`).
- **Descripción:** `closed_bars` solo compara el cierre **nominal** (`etiqueta + TF`) con el reloj. No sabe
  si la fuente llega hasta ese cierre. Dukascopy termina a las 23:59 UTC (18:59 o 19:59 NY), así que la
  última sesión D1/H4, que empieza a las 17:00 NY, tiene 1-3 h de minutos. Días después, en el
  registro, su cierre nominal ya ha pasado y se conserva. `resample_session` no guarda cuántos minutos
  tiene cada vela. `discovery fetch` (MT5) con `end=None` toma `now` y guarda la vela M5 en formación.
- **Evidencia:** `SCR/r03_partial_last_bar.py` y `SCR/r08_mt5_forming_bar.py`:

  ```
  H4: ultima vela 2025-01-16 17:00:00-05:00 conservada por closed_bars; minutos M1 dentro = 120 de 240
  D1: ultima vela 2025-01-16 17:00:00-05:00 conservada por closed_bars; minutos M1 dentro = 120 de 1380
  D1 misma etiqueta 2025-01-16 22:00:00+00:00 close antes 19917.12 despues 19988.62
  hash rango [inicio, etiqueta] antes == despues: False
  ---
  ultima vela guardada: 2026-11-24 14:00:00+00:00 tickvol: 7 | now: 2026-11-24T14:03:20+00:00 | cierre nominal: 2026-11-24 14:05:00+00:00
  ```
- **Impacto:** no hay lookahead: la vela parcial tiene **menos** información, no más. Pero (a) la última
  vela de OOS-2 queda congelada en el snapshot con un OHLC que no existió; (b) sin snapshot,
  `dataset_matches` rechaza la campaña en cuanto se amplía la caché (`campaigns.py:985-993`); (c) en H4/D1
  es la vela donde cierran las operaciones «fin de datos».
- **Corrección mínima:** recortar en la fuente: Dukascopy y Databento hasta el último corte de sesión
  completo (17:00/18:00 NY), y MT5 descartando la última vela si `time + TF > now`. Opcionalmente,
  añadir una columna `n_src` en `resample_session` y descartar las velas con menos del 50 % de los minutos
  esperados al final de la serie.
- **Test de regresión:** con M1 hasta 23:59 UTC, `closed_bars(resample_session(m1, "D1"))` no debe
  devolver la sesión que empieza a las 17:00 NY de ese día. Con un MT5 simulado y `now` a mitad de vela,
  `fetch.download` no debe escribir esa vela.

### C-04 · HIGH · CONOCIDO (TL3_FORENSIC_AUDIT G-2, TL3_DATA_AND_COSTS_AUDIT D2) + NUEVO: futuros con identidad de CFD

- **Archivo:** `src/tradinglab/discovery/fetch_databento.py:67-76,223-231` (`ROOT_TO_INTERNAL`,
  `cache_path`); `src/tradinglab/discovery/data_sources.py:187-233` (`load_source`);
  `src/tradinglab/discovery/campaigns.py:155-163` (`timeframe_source_error`), `:335-347` (`register`).
- **Ya conocido:** NQ se guarda como `US100_M1/H1.parquet`, sin `instrument_id`, y no hay MNQ.
- **NUEVO:**
  1. `timeframe_source_error` solo bloquea `databento` en H4/D1. En M15/M30/H1, `register` acepta
     `instrument="US100", data_source="databento"` y `resolve_cost_accounts("US100", ["CFD-001"])` es
     válido: se aplica el coste CFD (spread BID/ASK del modelo v2, swap) a precios de **operación** del
     futuro, que no son BID. Esto contradice la regla del doc 06 §4 («CFD y futuros nunca comparten
     modelo de coste»).
  2. `cache_path` no incluye el tipo de roll. `--roll c` y `--roll v` escriben y **concatenan**
     (`:675-678`) sobre el mismo `US100_M1.parquet`, así que mezclan dos series continuas distintas sin
     dejar rastro.
  3. `load_source(..., source="databento")` devuelve `symbol="US100"`. Solo `calendar="cme"` y
     `source="databento"` permiten distinguirlo.
- **Evidencia:** `SCR/r04_databento_identity.py`:

  ```
  cache_path('NQ', roll c/v): US100_M1.parquet
  continuous c: NQ.c.0  v: NQ.v.0 -> mismo fichero: True
  MNQ: símbolo no soportado: 'MNQ'; ...
  load_source('US100', source=databento): symbol= US100 calendar= cme source= databento rows= 40
  timeframe_source_error(M15, databento) -> None
  timeframe_source_error(H1, databento) -> None
  timeframe_source_error(H4, databento) -> H4 exige datos de Dukascopy; ...
  resolve_cost_accounts('US100', ['CFD-001']) -> (['CFD-001'], 'worst') (coste CFD sobre barras NQ)
  ```
- **Impacto:** una campaña intradía «US100» con barras NQ sin ajustar mide coste y ejecución de un CFD
  sobre un futuro. Cada roll trimestral es además un salto falso del 0,3-1 % (orden de magnitud,
  **verificar**), que las señales leen como movimiento real. Los resultados no son evidencia ni del CFD
  ni del futuro.
- **Corrección mínima:** con `data_source == "databento"`, rechazar las cuentas CFD y exigir un modelo
  `FuturesCosts` (o bloquear `databento` en todos los TF hasta que exista). Nombrar la caché
  `<RAÍZ>_<roll>0_<TF>.parquet`. Rechazar `download` si la caché existente es de otro roll.
- **Test de regresión:** `register(..., data_source="databento", cost_accounts=["CFD-001"])` debe lanzar
  `CampaignError` en cualquier TF, y `cache_path("NQ", roll="c") != cache_path("NQ", roll="v")`.

### C-05 · MEDIUM · CONOCIDO parcial (TL3_DATA_AND_COSTS_AUDIT §3) + NUEVO: `detect_rolls` borra movimientos reales

- **Archivo:** `src/tradinglab/discovery/futures_roll.py:35-72` (`detect_rolls`), `:101-126`
  (`residual_jumps`), `:22` (`ROLL_MONTHS`).
- **Ya conocido:** solo detecta 17 de unos 66 rolls de NQ, y GC vence en meses pares.
- **NUEVO:**
  1. Todo salto mayor de 5σ en la vela de las 18:00 ET de marzo, junio, septiembre o diciembre se toma
     como roll y se **resta** del histórico, aunque sea un movimiento real (por ejemplo, la apertura del
     domingo tras una noticia del fin de semana, como en marzo de 2020).
  2. El salto atribuido al roll es `close[t] − close[t−1]`, que incluye el movimiento real de mercado de
     esa hora y de la pausa. Lo correcto es la diferencia entre los dos contratos en el **mismo** instante.
  3. Un roll que aparece en otra vela (si Databento cambia el mapeo a 00:00 UTC, el salto cae a las 19:00
     o 20:00 ET; **verificar**) o que mide menos de 5σ (un contango del 0,5 % con σ horaria del 0,2 % son
     2,5σ) no se detecta.
  4. `residual_jumps` sobre la serie ajustada por diferencia da siempre 0, porque el ajuste anula por
     construcción el retorno de esa vela. No valida nada.
- **Evidencia:** `SCR/r05_futures_roll.py`:

  ```
  A) rolls detectados sin roll real: [('2020-03-08 18:00:00-04:00', 17.4)]
     retorno real en esa vela: 0.0305 -> tras ajuste: 0.0
  B) roll real -0,5 % a las 19:00 ET -> detectados: 0
  C) roll de GC en febrero (salto 5 %) -> detectados: 0
  D) residual_jumps(adjust_diff) sobre caso A: {'n': 1, 'max_abs_return': 0.0, ..., 'over_sigma': 0}
  E) roll real -0,5 % justo a las 18:00 ET (sigma horaria 0,2 %) -> detectados: 0
  ```
- **Alcance actual:** `futures_roll` solo lo usan `tests/test_discovery_futures_roll.py` y los
  snapshots `futuros_*_H1_*.parquet`. No entra en `load_source`, que sigue sirviendo la serie **sin
  ajustar** (C-04).
- **Impacto estadístico:** si se usa, quita colas reales (sesgo a la baja de la volatilidad de
  apertura del domingo) y deja rolls sin corregir. Las dos cosas sesgan cualquier estrategia de
  ruptura o reversión en futuros.
- **Corrección mínima:** no detectar rolls por salto. Guardar `instrument_id` (`map_symbols=true` y
  conservar la columna; ahora `fetch_databento.py:465,514` la descartan) y calcular el ajuste con los
  dos contratos en el mismo timestamp. Mientras tanto, marcar `futures_roll` como experimental y
  sustituir `residual_jumps` por una comparación frente a la tabla de rolls real.
- **Test de regresión:** una serie sin roll y con un salto real de 6σ en marzo a las 18:00 debe quedar
  intacta, y una tabla de rolls con `instrument_id` debe producir exactamente esos ajustes.

### C-06 · MEDIUM · NUEVO: `gap_pct` cuenta eventos, no velas perdidas

- **Archivo:** `src/tradinglab/discovery/data_quality.py:855-865` (`check_dataset`).
- **Descripción:** `gap_pct = non_scheduled / expected_bars`. Un hueco de 8 días hábiles vale 1, lo
  mismo que una vela suelta. El umbral `fail_if_gap_pct_gt: 0.005` (0,5 %) equivale a «se permite un
  hueco de cualquier duración cada 200 velas». Solo la regla de densidad mensual de `_granularity`
  (menos del 50 % de las velas del mes típico) corta los agujeros muy largos.
- **Evidencia:** `SCR/r09_gap_pct_counts_events.py`: M1 sintético de 2023 sin 2023-06-05..06-14:

  ```
  M15: status=ok gaps=0 gap_pct=0.00000 (~685 velas perdidas de 22416 esperadas)
  H1: status=warn gaps=1 gap_pct=0.00018 (~171 velas perdidas de 5640 esperadas)
  H4: status=warn gaps=1 gap_pct=0.00070 (~42 velas perdidas de 1423 esperadas)
  ```

  El 3 % de las velas del año desaparece y nada falla. En M15 ni siquiera se ve (C-01).
- **Impacto:** la puerta de calidad no limita la fracción real de datos perdidos.
- **Corrección mínima:** sumar los minutos de los huecos no programados, dividirlos entre el TF y usar
  esa cifra (velas perdidas / velas esperadas) en `gap_pct`. Conservar el número de eventos como dato
  informativo.
- **Test de regresión:** el escenario de `r09` debe dar `gap_pct ≈ 0,03`, `fail` en los tres TF, y una
  vela suelta debe pesar `1/expected`.

### C-07 · LOW · NUEVO: Año Nuevo en sábado marca el viernes 31-dic como festivo

- **Archivo:** `src/tradinglab/discovery/calendars.py:83-94` (`nyse_holidays`), `:150-161`
  (`fx_metal_holidays`), `:180-196` (`cme_holidays`); `src/tradinglab/nyse_calendar.py:28`.
- **Descripción:** `_observed()` traslada el 1-ene de sábado al viernes 31-dic. NYSE no observa Año
  Nuevo en ese caso: abrió el 31-12-2004, el 31-12-2010 y el 31-12-2021 (conocimiento general;
  **verificar** con el calendario oficial de NYSE). CME Globex y el FX spot también operan ese día.
- **Evidencia:** `SCR/r06_calendars.py`:

  ```
  2010-12-31 Fri | nyse: Año Nuevo 2011 (observado) | cme: Año Nuevo (observado) | fx_metal: Año Nuevo (observado)
  2021-12-31 Fri | nyse: Año Nuevo 2022 (observado) | ... | nyse_calendar.FULL: Año Nuevo 2022 (observado)
  2027-12-31 Fri | nyse: Año Nuevo 2028 (observado) | cme: ... | fx_metal: ...
  ```
- **Impacto:** los huecos de ese día se excusan como festivo y un patrón de cambio de año
  (`month_turn_pairs`) toma mal el último día hábil de diciembre. `nyse_calendar.py` es la fuente de
  `InpHolidays` del EA `us100-ftmo1` (componente de producción): su entrada 2021-12-31 es histórica y no
  afecta al futuro mientras el módulo termine en 2027. Si se amplía a 2028, el error alcanzaría
  2027-12-31.
- **Corrección mínima:** en Año Nuevo, si el observado cae en el año anterior, no añadirlo (NYSE, CME y
  FX). En `nyse_calendar.py` hay que seguir el protocolo de producción (baseline, test, CHANGELOG, tag).
- **Test de regresión:** `holiday_reason(NYSE, date(2021,12,31)) is None` y lo mismo para 2010 y 2027,
  con `nyse_trading_days(2021, 12)[-1] == date(2021, 12, 31)`.

### C-09 · LOW · NUEVO: dos rejillas H4 para la misma fuente CME

- **Archivo:** `src/tradinglab/discovery/data_sources.py:213` (`cut_hour=18`) frente a
  `src/tradinglab/discovery/compiler.py:100` (`resample_session(bars, tf)`, corte 17).
- **Evidencia:** `SCR/r07_resample_checks.py`, apartado 5:
  `horas NY H4 cut17: [1, 5, 9, 13, 17, 21]  cut18: [2, 6, 10, 14, 18, 22]`.
- **Impacto:** una campaña Databento H1 con un filtro HTF H4 usa velas H4 distintas de las de una
  campaña Databento H4. En D1 no cambia la agrupación, solo la etiqueta (17:00 frente a 18:00).
  Hoy H4 con Databento está bloqueado, así que el impacto es bajo.
- **Corrección mínima:** propagar `cut_hour` de la fuente al compilador, o fijar 17:00 para todas.
- **Test de regresión:** `_htf_bars` de una serie Databento debe coincidir con
  `load_source(..., "H4", source="databento").frame`.

### C-10 · LOW · NUEVO: `dataset_hash` ignora ASK, volumen y spread

- **Archivo:** `src/tradinglab/discovery/data_quality.py:154-170` (`dataset_hash`).
- **Evidencia:** `r07`, apartado 6: `hash igual con ASK y volumen cambiados: True`.
- **Impacto:** el modelo `historical_scaled` (doc 06, T11) usa el ASK de Dukascopy y VWAP usa el
  volumen. Si cambian, el hash de la campaña no lo detecta y la reproducibilidad queda sin garantía.
- **Corrección mínima:** incluir en el hash `ask_*`, `volume`/`tickvol` y `spread` cuando existan, con
  un prefijo de versión `v2` para no invalidar los hashes antiguos.
- **Test de regresión:** cambiar una celda `ask_close` debe cambiar el hash v2 y mantener el v1.

### C-11 · LOW · NUEVO: semántica de volumen mezclada

- **Archivo:** `src/tradinglab/discovery/indicators_ext.py:212-219` (`vwap_session`);
  `src/tradinglab/discovery/resample.py:91-96` (`_aggregation`).
- **Descripción:** `vwap_session` usa `volume` si existe (Dukascopy: volumen propio del proveedor;
  Databento: contratos CME) y si no `tickvol` (MT5: ticks). Sin ninguna de las dos, usa 1,0 (TWAP)
  sin avisar. `_aggregation` suma `volume`, `tickvol` y `ask_volume`, pero agrega cualquier otra columna
  con `last`.
- **Evidencia:** `r07`, apartado 4: `tickvol: 5.0  tick_volume: 1.0  real_volume: 2.0 (5 minutos)`.
- **Impacto:** una regla VWAP descubierta con Dukascopy y ejecutada en MT5 usa otro peso. Las cachés con
  columnas MT5 sin renombrar (`tick_volume`, `real_volume`) se agregan mal. `discovery fetch` sí renombra
  a `tickvol`; la caché del EA es **Sin datos** aquí.
- **Corrección mínima:** declarar `volume_kind` en `LoadedSource` y exigir que VWAP use el mismo tipo en
  investigación y ejecución. Sumar `tick_volume` y `real_volume`.
- **Test de regresión:** `_aggregation` debe sumar `tick_volume` y `real_volume`, y `vwap_session` sin
  volumen debe fallar o marcar el resultado.

### C-12 · LOW · NUEVO: controles prometidos por el doc 06 §3 que no existen

- **Archivo:** `src/tradinglab/discovery/data_quality.py` (todo el módulo) frente a
  `docs/tradinglab2/06_TRADINGLAB_DATA_AND_COST_AUDIT.md §3`.
- **Descripción:** el doc 06 dice que `data_quality` comprueba «zona horaria declarada vs observada,
  `point/digits` … y, para futuros, continuidad en los rolls». El módulo no contiene ninguno de esos
  controles.
- **Evidencia:** confirmado por lectura, no por reproducción: `grep -n -i "roll\|point\|digits\|declarada"
  src/tradinglab/discovery/data_quality.py` no devuelve nada. La zona horaria solo se **declara**
  (`SourceConfig.timezone`) y nunca se contrasta con lo observado (p. ej., la hora modal de la apertura
  del domingo frente a la esperada).
- **Impacto:** el doc da una garantía que el código no cumple. Una caché con la zona mal declarada
  (desplazada 1 h) pasa `data-check` como `ok`.
- **Corrección mínima:** implementar el control de zona observada (apertura del domingo y cierre del
  viernes frente a la sesión esperada, como ya hace `mt5_offsets.infer_bar_offsets`) y el de
  continuidad de rolls cuando exista `instrument_id`. Mientras tanto, corregir el doc 06.
- **Test de regresión:** una serie desplazada +1 h respecto a su zona declarada debe dar `warn` o
  `fail` en `check_dataset`.

### C-13 · LOW · NUEVO: una vela inválida bloquea un mes de Dukascopy

- **Archivo:** `src/tradinglab/discovery/fetch_dukascopy.py:192-195` (`decode_candles`), `:441-443,471-476`
  (`download`).
- **Evidencia:** `SCR/r02_dukascopy_month_tail.py 2026-10-14` (una vela con high < low):
  `ERROR: 1 días sin respuesta en 2026-10 (2026-10-14); vuelve a ejecutar para reanudar`. Volver a
  ejecutar falla igual.
- **Impacto:** bloquea la descarga, sin riesgo de datos falsos. El mensaje hace pensar en un fallo de red.
- **Corrección mínima:** separar el error de datos del de red en el mensaje y permitir descartar la vela
  con un contador visible en el resumen.
- **Test de regresión:** un día con una vela inválida produce un mensaje que nombra «OHLC inválido» y
  ese día.

### C-14 · LOW · NUEVO: duplicados eliminados antes del control

- **Archivo:** `fetch_dukascopy.py:280`, `fetch_databento.py:408,473`, `resample.py:120` (todos
  `duplicated(keep="last")`); `fetch.py:223` (`keep="first"`).
- **Descripción:** en Dukascopy, Databento y cualquier serie remuestreada, `check_dataset` nunca recibe
  duplicados. «Duplicados 0» es una garantía del cargador, no una medida de la fuente. Además, MT5 y el
  resto usan reglas de desempate opuestas (`first` frente a `last`).
- **Impacto:** bajo. Si una fuente entrega dos versiones de la misma vela, se elige una en silencio.
- **Corrección mínima:** contar los duplicados eliminados en `LoadedSource.dropped` y mostrarlos en el
  informe.
- **Test de regresión:** un parquet con un timestamp repetido debe dar `dropped == 1` en `load_source`.

---

## 2. Sospechas no reproducidas

| ID | Sev. | Estado | Archivo:línea | Sospecha | Por qué no se reproduce |
|---|---|---|---|---|---|
| C-08 | LOW | NUEVO (verificar) | `calendars.py:169-205` (`cme_holidays`) | Los futuros de índice CME no cierran todo el día en Memorial, 4-jul, Labor, Acción de Gracias ni Juneteenth: hacen una sesión abreviada (parada hacia las 12:00 CT) y reabren a las 17:00 CT. El código los trata como cierre completo y excusa los huecos de esas mañanas. Salida de `r06`: `CME 2024-05-27 Memorial early: None`. El propio docstring reconoce el caso para MLK y Presidents | Depende del calendario oficial de CME; **verificar** con CME Group Holiday Calendar |
| S-1 | — | NUEVO | `fetch_databento.py:18-19` | El docstring dice que `.c.0` hace el «roll por calendario (fecha fija antes del vencimiento)». Hasta donde sé, en Databento `c` ordena por vencimiento y cambia de contrato al vencer el frontal, no unos días antes. Si es así, la serie usa el contrato que vence durante su última semana, cuando ya tiene poca liquidez | Necesita la documentación de Databento o datos reales; **verificar** |
| S-2 | — | NUEVO | `fetch_databento.py`, `futures_roll.py:51` | Hora del cambio de contrato en la serie continua: ¿00:00 UTC (19:00/20:00 ET) o apertura de sesión a las 18:00 ET? Condiciona C-05 | **Verificar** con la documentación de Databento |
| S-3 | — | NUEVO | `fetch_databento.py:19` | `.v.0`: si Databento decide el roll por volumen con el volumen del día anterior, no hay lookahead. Si lo decide con el del mismo día, sí lo habría | **Verificar** |
| S-4 | — | NUEVO | `fetch.py:210-216` | Qué representa la columna `spread` de la vela MT5 (mínimo o valor en apertura). `resample` la promedia | **Verificar** con la documentación de MQL5 |
| S-5 | — | NUEVO | `data_sources.py:89-101` (`_localize`) | Con datos NY sin zona y deduplicados, `ambiguous="infer"` falla y cae a `ambiguous=False`: la hora repetida del cambio de otoño se etiqueta como EST. Con el universo actual no tiene efecto, porque el cambio cae el domingo de madrugada y el mercado está cerrado | No hay datos 24/7 en el universo. La caché del EA es **Sin datos** aquí |
| S-6 | — | CONOCIDO (TL3_DATA_AND_COSTS_AUDIT §2.1) | `data/cache/ea/US100_CASH_M5_NY.parquet` | La caché del EA mezcla granularidades y su zona real no está confirmada | **Sin datos** en el contenedor |

---

## 3. Comprobado y correcto

| Tema | Evidencia |
|---|---|
| **Etiqueta = apertura** en `resample_session`; `open`/`close`/`high` salen del primer, último y máximo minuto del cubo; no se usa ningún minuto posterior al cierre | `r07` §2: `open==primer minuto: True close==ultimo minuto: True high==max: True` |
| **DST:** la rejilla H4/D1 queda anclada a las 17:00 NY antes y después del cambio de marzo de 2024 (horas NY `[1,5,9,13,17,21]` en ambas semanas; D1 a las 21:00/22:00 UTC); sin duplicados y con índice ordenado | `r07` §1 |
| **D1 de FX a las 17:00 NY:** `session_labels` asigna cada minuto a la sesión que contiene su apertura; el domingo por la tarde pertenece al lunes | `resample.py:62-72`; `r07` §1 |
| **Sin lookahead HTF** en el compilador: `_htf_positions` solo usa velas HTF con `inicio + duración <= barra base` | `compiler.py:107-111`; `r07` §3: `barras M15 que ven una H4 aun abierta: 0` |
| **BID/ASK separados** en Dukascopy: el BID es obligatorio, el ASK opcional (`ask_*`), sin rellenar; se usa `join` por la izquierda sobre el BID; minutos de volumen 0 descartados (no se fabrican velas) | `fetch_dukascopy.py:172-204,381-408,495-503` |
| **Velas BID** en Discovery, coherentes con el modelo v2 (stop del corto con ASK = high + spread) para Dukascopy y MT5. Databento no es BID (C-04) | doc 06 §5; `fetch.py` |
| **6J → USDJPY:** inversión con intercambio de H/L correcta | `fetch_databento.py:428-439` |
| **Timestamps en UTC** en las tres cachés. MT5 usa el offset semanal inferido (no global) | `fetch.py:194-207`; `execution/mt5_offsets.py:101-179` |
| **`closed_bars`** descarta correctamente las velas con cierre nominal posterior a `now` (el defecto de C-03 es otro: la fuente incompleta) | `snapshots.py:73-90` |
| **Pausa programada** medida en `pause_tz` NY, no en UTC | `data_quality.py:582-605`; `engine.yaml:119-126` |
| **Festivos NYSE regulares** y cierres especiales (Sandy, Bush, Carter…) correctos, salvo C-07 | `calendars.py:19-26,80-125` |
| **Coste estimado antes de pagar** en Databento: `download` exige que `approved_cost` coincida al centavo con la estimación | `fetch_databento.py:645-651` |

---

## 4. Datos NQ/MNQ: qué falta

### 4.1 Qué espera hoy `fetch_databento.py`

- **Dataset:** `GLBX.MDP3` (CME Globex MDP 3.0).
- **Schemas:** solo `ohlcv-1m` y `ohlcv-1h` (`SCHEMAS`, `:79`). Son barras de **operaciones**, sin BID/ASK.
- **Símbolos:** `stype_in=continuous`, `NQ.c.0` (calendario) o `NQ.v.0` (volumen). Raíces: NQ, ES, YM, GC,
  6E, 6B y 6J. **MNQ, MES, MYM y MGC no existen** en `ROOT_TO_INTERNAL`.
- **Clave:** `DATABENTO_API_KEY` en Windows Credential Manager (servicio `KEYRING_SERVICE`). La añade el
  operador; el agente no la toca.
- **Salida:** CSV (`pretty_px`, `pretty_ts`, `map_symbols=false`) → `data/cache/databento/US100_M1.parquet`
  con `open, high, low, close, volume`. Se descartan `instrument_id`, `rtype` y `publisher_id`.
- **Granularidad utilizable:** M1 y H1 nativas. M5, M15, M30 y H4/D1 se derivan con
  `resample_session(cut_hour=18)`. Los registros H4/D1 con `databento` están bloqueados
  (`campaigns.py:158`), salvo la spec D1 `confirmation_only`.
- **Ajuste:** `adjust="none"` por defecto (precios sin ajustar). `adjust="back"` necesita una tabla de
  rolls manual que nadie genera (C-05).

### 4.2 Qué falta para investigar NQ/MNQ con rigor

1. **Identidad propia:** raíces NQ y MNQ con caché `NQ_c0_M1.parquet` / `MNQ_v0_M1.parquet` (C-04, D2).
2. **Contrato por fila:** `map_symbols=true` y conservar `instrument_id`/`raw_symbol`, o descargar por
   contrato (`stype_in=parent`, `NQ.FUT`, o símbolos `raw`; **verificar** la sintaxis exacta).
3. **Tabla de rolls generada a partir de los datos:** fecha del cambio y diferencia entre contratos en
   el mismo timestamp. Regla fijada **antes** de mirar resultados (volumen u OI; Databento también
   ofrece `n` por open interest, **verificar**).
4. **Especificaciones por raíz:** multiplicador, tick y valor del tick. Por conocimiento general:
   NQ 20 USD/punto y MNQ 2 USD/punto, ambos con tick de 0,25 (**verificar** en CME). Están en el schema
   `definition` de Databento.
5. **Spread:** OHLCV no lo trae. Haría falta `tbbo`, `mbp-1` o `bbo-1m` (**verificar** disponibilidad y
   coste) o un supuesto declarado de 1 tick en RTH.
6. **Historia de MNQ:** el contrato Micro E-mini Nasdaq-100 se lanzó en mayo de 2019 (conocimiento
   general, **verificar**). Antes de esa fecha, usar NQ como proxy de MNQ es una **transferencia**
   (mismo precio, otro coste y otra liquidez) y debe marcarse así.
7. **Coste de futuros obligatorio** con `databento` y prohibición de cuentas CFD (C-04).
8. **Calendario CME** corregido (C-07, C-08) y un único corte de sesión (C-09).
9. **Control de continuidad de rolls** en `data_quality` (C-12) y `data-check` sin el agujero de C-01.
10. **Autorizaciones:** estimar es gratis; descargar requiere la aprobación del operador con
    `--i-approve-cost` (regla del repositorio). Este informe no estima ni descarga nada.

### 4.3 Comparación de proveedores (conocimiento general declarado; sin precios)

| Proveedor | Qué es | Futuros CME NQ/MNQ | Granularidad | Contrato / roll | BID/ASK | Notas |
|---|---|---|---|---|---|---|
| **Databento** | API histórica y en tiempo real, pago por uso o planes | Sí, `GLBX.MDP3`, desde 2010-06 (coincide con la caché H1 citada en TL3) | Tick (MBO/MBP), `trades`, OHLCV 1 s/1 m/1 h/1 d | `instrument_id` por fila; símbolos continuos `c`/`v`/`n` | Sí con `mbp-1`/`tbbo`/`bbo` | Ya integrado en parte. Precio por GB y planes: **verificar** |
| **CME DataMine** | Fuente oficial del exchange | Sí, todos los contratos | Tick, profundidad, top of book y EOD; historia muy larga (**verificar** desde qué año) | Por contrato (raw) | Sí | Licencias y entrega (SFTP/nube) más complejas; coste: **verificar** |
| **Kinetick / IQFeed (DTN)** | Feed en tiempo real con historia limitada | Sí | Tick y minuto; la profundidad histórica del tick es corta (**verificar**) | Continuos propios y por contrato | Sí en tiempo real | Pensado para live con NinjaTrader o un cliente Windows; no para descargas masivas |
| **Polygon.io / Massive** | API de mercado (renombrada Massive; **verificar**) | Soporte de futuros reciente o limitado: **verificar** | Depende del plan | **Verificar** | **Verificar** | Fuerte en acciones, opciones, FX y cripto; para CME, **verificar** antes de contar con él |
| **FirstRate Data** | Ficheros históricos de compra única | Sí, NQ y probablemente MNQ (**verificar**) | 1 min y tick (**verificar**) | Continuos ajustados y sin ajustar; metodología de roll del proveedor (**verificar**) | Normalmente no | Útil para un IS largo. Hay que auditar el roll y las sesiones antes de usarlo |
| **Dukascopy** | CFD propio `USATECHIDXUSD` | **No es un futuro.** Es el CFD del Nasdaq-100 de Dukascopy | M1/tick, BID y ASK (el ASK casi vacío en la caché, según TL3) | No aplica | Sí (BID/ASK del CFD) | Gratis. El volumen es del proveedor, no de CME. Nunca sustituye a NQ: su uso correcto es US100 CFD |

**Regla que se mantiene:** US100 (CFD FTMO/Dukascopy) ≠ NQ ≠ MNQ. Ningún resultado de uno es evidencia
del otro sin marcarlo como transferencia (introducción de TL3_DATA_AND_COSTS_AUDIT; doc 06 §4).

---

## Anexo · Scripts de reproducción

Todos en `/tmp/claude-0/-home-user-trading-lab/89310f7f-0a4e-5602-b5a9-56cac624406b/scratchpad/C/`:

| Script | Hallazgos |
|---|---|
| `r01_gap_m15_blind.py` | C-01 |
| `r02_dukascopy_month_tail.py` (sin argumentos → C-02; con `2026-10-14` → C-13) | C-02, C-13 |
| `r03_partial_last_bar.py` | C-03 |
| `r04_databento_identity.py` | C-04 |
| `r05_futures_roll.py` | C-05 |
| `r06_calendars.py` | C-07, C-08 |
| `r07_resample_checks.py` | C-09, C-10, C-11, «Comprobado y correcto» |
| `r08_mt5_forming_bar.py` | C-03 (MT5) |
| `r09_gap_pct_counts_events.py` | C-06 |
