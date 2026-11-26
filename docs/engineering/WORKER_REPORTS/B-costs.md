# B-costs · Auditoría de costes y ejecución (Worker B)

- **ID tarea:** ENG-B1 · **SHA:** `adc0eec` · **Fecha:** 2026-11-26
- **Modo:** solo lectura. No se tocó `src/`, `tests/`, `config/` ni `data/`. `costs.py` y `fastbt.py` están congelados por EDGE-2: aquí solo se encuentran y reproducen fallos, no se corrigen.
- **Scripts y salidas:** `/tmp/claude-0/-home-user-trading-lab/89310f7f-0a4e-5602-b5a9-56cac624406b/scratchpad/B/` (`bNN_*.py` y `bNN_*.out.txt`). Todo es sintético. Los perfiles de comisión, swap y slippage se leen de `config/` en solo lectura. No se usó ningún precio, spread ni swap de mercado inventado: donde hace falta un precio, se marca como **sintético**.
- **Lecturas previas:** `docs/tradinglab2/06_TRADINGLAB_DATA_AND_COST_AUDIT.md` §4-5, `docs/audit_2026/QUANT_ENGINE_AUDIT.md` §6, `.orquestador/tl2-audit/TL2_MASTER_AUDIT.md` P0-1/P1-1..3, `.orquestador/COLA-ROBUST-1.md` y `RESULTADO-ROBUST-1.md`, `TL3_REPORTS/tca_diagnostico.md`, `ESTADO.md` y el informe A-engine (para no duplicar).
- **Tests concretos:** `pytest tests/test_discovery_execution_v2.py`: 18 pasan. Ninguno cubre los hallazgos de abajo.

## Resumen por severidad

| ID | Sev. | Estado | Hallazgo (sesgo) |
|---|---|---|---|
| B-01 | HIGH | NUEVO | La comisión por lote en USD se pasa a bps con `precio × contrato` en la divisa cotizada. En USDJPY queda **÷ precio (~100-150 veces menor)**. **A favor** de las estrategias. |
| B-02 | HIGH | NUEVO | `levels._account_confirmation` (confirmación OOS-2 por cuenta) crea un `CostBook` **v1** por defecto: cobra el doble spread y el p75 en campañas v2. **En contra**. |
| B-03 | HIGH | NUEVO | Robustez, perturbación, `levels` (neto base) y `lab discovery retest` no usan el `CostBook` (`cost_accounts`/`cost_mode`/spread por hora) del fitness, sino `cost_from_profile(setup.account)`: una sola cuenta y spread p75 estático. Validación ≠ selección. El sesgo puede ir en cualquier dirección. |
| B-04 | MEDIUM | NUEVO | El triple swap cae un día antes: el de los índices (viernes) se cobra el jueves por la noche y el fin de semana paga una sola noche. El de FX (miércoles) cae en la noche del martes. Requiere cola de producción. |
| B-05 | MEDIUM | NUEVO (coincide con A-06) | En `_calendar_core`, el objetivo de un corto se dispara con el BID, sin spread. **A favor**: hasta un spread completo por operación. |
| B-06 | MEDIUM | NUEVO (latente) | `historical_spread_provider` aplica `ffill` sin límite y rellena con la mediana global: un minuto de ASK se propaga durante años. |
| B-07 | MEDIUM | NUEVO | El spread medido en EST se ancla a la hora de `session_tz`. En USDJPY (`Asia/Tokyo`), el pico del rollover NY 17:00 cae una hora tarde unos 8 meses al año. |
| B-08 | MEDIUM | NUEVO | `slippage_measured.build_proposal` mezcla cuentas y no casa `US100.CASH` con `US100`. Además, Discovery ignora el slippage del perfil (B-09). |
| B-09 | LOW | NUEVO | `build_account_cost` sustituye siempre `slippage_price` por `engine.yaml::assumed_slippage`. Una medición aprobada nunca llega a Discovery. |
| B-10 | MEDIUM | NUEVO | El escenario `slippage_plus_2` (2 × `point`) es casi nulo en índices y oro: +0,8 % a +13 % del slippage supuesto. La puerta 3 no discrimina. |
| B-11 | MEDIUM | NUEVO (latente) | `CostBook.panel` cachea por `id(bars)` y `apply()` usa el **último** panel calculado. Si se reutiliza un id, se devuelve un panel de otras barras. |
| B-12 | LOW | NUEVO | En v2, `slip_r` incluye el slippage de salida en las salidas por objetivo, que no lo pagan. `spread_r+slip_r+comm_r−swap_r ≠ r_cost`. Solo afecta al informe. |
| B-13 | LOW | NUEVO | Un swap ausente en el perfil da `SwapSpec=None` y swap 0 silencioso (`swap_r=None`), sin marca de "Sin datos". |
| B-14 | LOW | CONOCIDO(tca_diagnostico §5), ampliado | La TCA v2 ya está aplicada en `mt5.py`. Quedan huecos: `expected_cost_bps` siempre vale 0 en MT5, `bid`/`ask` del tick previo, `signal_px` cae al tick sin marca, las salidas SL/TP no pasan por la TCA y el paper se graba como `tca_version=2`. Requiere cola de producción. |

Lo ya conocido se confirma: el doble spread v1 y el stop de corto con BID (TL2 P0-1) están **corregidos en v2**, y el `point` del retester está corregido (ROBUST-1). Siguen en pie el slippage sin medir (TL2 P1-1) y los costes anacrónicos (TL2 P1-3, 06 §5 T11). Ver "Comprobado y correcto".

---

## Confirmado con reproducción

### B-01 · HIGH · NUEVO · Comisión por lote de USDJPY ÷ precio
- **Archivo:** `src/tradinglab/discovery/fastbt.py:343-353`, `CfdProfileCosts._commission_bps` (lo heredan `CfdHourlyCosts` y `CfdHourlyMedianCosts`, que son los que usa el `CostBook`).
- **Descripción:** `per_lot / (prices * contract_size) * 1e4` supone que el nocional `precio × contrato` está en USD. Eso vale en EURUSD/GBPUSD (cotizan en USD) y en XAUUSD, pero no en USDJPY: ahí el nocional `precio × 100.000` está en **JPY**, mientras que la comisión (`per_lot_usd` 2,5/lado en FTMO, 5 round turn en FundingPips) está en USD. El nocional en USD es 100.000. `propfund.costs.estimate_cfd` lo hace bien porque suma USD, y `swap_history.annual_swap_table` ya trata este caso de USDJPY (líneas 286-293). El motor rápido no.
- **Evidencia** (`b02_usdjpy_commission.py`, precios sintéticos):
  ```
  CFD-001 USDJPY px_sint= 150.0: motor=0.00167 bps/lado  correcto=0.25000 bps/lado  ratio=150.0
  CFD-006 USDJPY px_sint= 150.0: motor=0.00167 bps/lado  correcto=0.25000 bps/lado  ratio=150.0
  CFD-001 EURUSD px_sint=   1.1: motor=0.22727 bps/lado  correcto=0.22727 bps/lado  ratio=1.0
  USDJPY stop 20 pips a px 150: comisión ida+vuelta correcta -> 0.0375 R; motor -> 0.00025 R
  ```
- **Impacto:** **a favor** de USDJPY. Se omite ≈0,5 bps por ida y vuelta: 0,037 R con un stop de 20 pips y 0,075 R con 10 pips, frente al límite `cost_r_max` = 0,10. Puede dejar pasar estrategias de USDJPY que no son viables por coste. Afecta a fitness, feasibility, levels y basket en las dos cuentas.
- **Corrección mínima:** convertir la comisión a la divisa cotizada. Si la base es USD, usar `per_lot / contract_size · 1e4` (bps del nocional en USD). En general, `per_lot_usd / (contract_size · precio_base_en_USD)`. Hay que leer `quote_currency`/`base_currency` de `config/costs.yaml` (ya existen). Requiere descongelar `fastbt.py` después de EDGE-2.
- **Test de regresión:** USDJPY con 2,5 USD/lado a 100 y a 150 da 0,25 bps/lado en los dos precios; EURUSD sigue en 2,5/(1,1·1e5)·1e4.

### B-02 · HIGH · NUEVO · La confirmación OOS-2 por cuenta usa costes v1
- **Archivo:** `src/tradinglab/discovery/levels.py:334-341` (`_account_confirmation`), con `costs.py:681-691` (`build_cost_book(..., cost_model_version=1)` por defecto).
- **Descripción:** la llamada no pasa `cost_model_version` ni `spread_model`. El `CostBook` sale en **v1** (`legacy_*`: spread en la entrada **y** en la salida no-objetivo), y `choose_spread_model(v1, "p75_static")` elige **p75**. El motor se ejecuta en v2 (los límites vienen de `setup.cost_model_version`), pero `book.apply()` recalcula `r_cost` con las reglas v1. Esto contradice 06 §5 ("`levels` … la pasan").
- **Evidencia** (`b13_levels_v1_default.py`):
  ```
  levels._account_confirmation -> costs.build_cost_book( setup.instrument, accounts=[account.id], mode="target", session_tz=..., db_path=costs_db, config=load_engine_config()
  default de build_cost_book.cost_model_version = 1
  long: libro v1=5.00 bps, libro v2=3.00 bps (diferencia = 1 spread = 2.00 bps; con stop 1 % = 0.020 R)
  short: libro v1=5.00 bps, libro v2=3.00 bps
  ```
- **Impacto:** **en contra** de las estrategias (falsos negativos) justo en la puerta final, el neto OOS-2 por cuenta: un spread completo de más por cada salida que no es por objetivo, y además p75 en vez de mediana. En las specs de 06 §5, v1→v2 bajaba `cost_R` entre 0,002 y 0,007 R de mediana. Aquí se suma además el paso de p75 a mediana.
- **Corrección mínima:** pasar `cost_model_version=setup.cost_model_version` y `spread_model=setup.spread_model` en `levels.py:334`. Hacer obligatorio el parámetro en `build_cost_book`, sin valor por defecto.
- **Test de regresión:** campaña v2 sintética. El `CostBook` de `_account_confirmation` tiene `cost_model_version == 2`, y el coste de una salida por tiempo es 1 spread.

### B-03 · HIGH · NUEVO · Validación con un modelo de coste distinto al de selección
- **Archivos:** `discovery/robustness.py:678-683`, `discovery/perturb.py:54-58`, `discovery/levels.py:540-545` (neto base OOS-2) y `cli.py:11916-11917` (`lab discovery retest`, que ni siquiera pasa `cost_model_version`). El fitness usa `jobs.py:395-397` → `build_cost_book_for_setup`.
- **Descripción:** el fitness aplica `CostBook(cost_accounts, cost_mode, spread por hora local)`. Robustez, perturbación, retest y OOS-1 aplican `cost_from_profile(load_profile(setup.account, firm=setup.firm))`: **una sola cuenta** (la primera), spread `spread_p75_price` **constante en precio** y slippage del perfil. Así:
  1. `cost_mode: worst` deja de cumplirse en robustez.
  2. `setup.firm` vale `"ftmo"` por defecto aunque la cuenta sea CFD-006.
  3. Si la primera cuenta es CFD-006 (que no tiene `slippage_price` en el perfil), robustez falla con "Sin datos" aunque el fitness funcionara. Falla de forma ruidosa, sin coste silencioso.
- **Evidencia** (`b10_robustness_cost_model.py`; campaña sintética en memoria, `broker_spreads` sintético):
  ```
  setup.account= CFD-006  firm= ftmo  cost_accounts= ('CFD-006', 'CFD-001')  cost_mode= worst
  coste robustness: ERROR MissingCostData Sin datos: coste CFD incompleto: slippage
  coste fitness: worst:CFD-006+CFD-001:USDJPY
  --- mismo caso con CFD-001 primero ---
  robustness: CFD perfil · CFD-001 · USDJPY | spread bps (constante, p75 estático en precio): [0.4831]
  fitness   : worst:CFD-001+CFD-006:USDJPY | spread bps por hora (máx. de cuentas, mediana horaria): [2.]
  ```
  (0,4831 = `spread_p75_price` real de config 0,007246 / 150 sintético; el 2,0 es sintético.)
- **Impacto:** las puertas (OOS-1, `cost_x1_5`, `slippage_plus_2`, PBO/WF, azar) evalúan otro coste que el prerregistrado. Con p75 estático el resultado suele ser más pesimista, salvo en las horas caras (rollover), donde el estático es más barato. Y se pierde el "worst" entre cuentas. El signo no se puede calcular sin datos, pero la incoherencia es segura.
- **Corrección mínima:** una sola fábrica `cost_for_setup(setup)` que devuelva el `CostBook` (o el perfil legacy si `setup.legacy_cost`), usada en robustness, perturb, levels y CLI retest. Aplicar `book.apply()` después de cada `fastbt.run`.
- **Test de regresión:** con una campaña sintética de dos cuentas en `worst`, `r_cost` por operación en robustez = `r_cost` en fitness para las mismas barras.

### B-04 · MEDIUM · NUEVO · Triple swap asignado al rollover anterior (requiere cola de producción, AGENTS.md: Prop Fund)
- **Archivo:** `src/tradinglab/propfund/costs.py:125-127`, `rollover_nights`: `server_day = (boundary.weekday() + 2) % 7`.
- **Descripción:** el corte de NY 17:00 = 00:00 del servidor del día siguiente se etiqueta con el día que **empieza**. En MT5, `swap_rollover3days` es el día cuyo cierre (su noche) se triplica: FX el miércoles (liquidación T+2 sobre el fin de semana) e índices el viernes (la noche que cubre sábado y domingo). La convención del código manda el triple de los índices a la noche **jueves→viernes**, que no cubre fin de semana. Eso es una señal económica fuerte de que hay un desfase de un día. `config/propfund/swap.yaml` tiene `swap_rollover3days: 5` en índices y `3` en FX/oro.
- **Evidencia** (`b04_swap_triple.py`):
  ```
  Índice triple=5 (viernes) · jue 10:00 -> vie 10:00: unidades=3
  Índice triple=5 (viernes) · vie 10:00 -> lun 10:00: unidades=1
  FX triple=3 · mar->mié: 3 ; mié->jue: 1
  corto vie->lun, 1R=200 pts: motor=-0.0839 R; con triple el viernes=-0.2516 R; falta -0.1677 R
  ```
  (swap_short medido de US100 en CFD-001: −1677,49 points × 0,01.)
- **Impacto:** el total semanal es correcto (7 unidades). El reparto por operación no. **A favor** de lo que duerme el fin de semana en índices (swing D1, cambio de mes): falta hasta 2 noches, unos 0,17 R por fin de semana con 1R = 200 puntos en un corto de US100. **En contra** de lo que duerme solo jueves→viernes. En FX el error se desplaza al martes.
- **Pendiente:** confirmar la convención con **un** deal real del historial MT5 (`DEAL_SWAP` del jueves frente al viernes 00:00 del servidor). Sin ese deal: **Sin datos** sobre la convención del bróker. El mecanismo sí está reproducido.
- **Corrección mínima:** `server_day = (boundary.weekday() + 1) % 7` (día de servidor que termina en el corte) y actualizar el docstring.
- **Test de regresión:** índice con triple=5 y posición vie 10:00→lun 10:00 da 3 unidades; jue→vie da 1. FX con triple=3: mié→jue da 3.

### B-05 · MEDIUM · NUEVO (también en A-06, aquí con el coste) · Objetivo corto sin spread en `_calendar_core`
- **Archivo:** `src/tradinglab/discovery/fastbt.py:1317-1319` (`hit_target = low[i] <= tgt_p`), frente a `_core:1005-1010`, que exige `low·(1+spread) ≤ tgt` en CFD.
- **Descripción:** en las plantillas de calendario (`month_turn`), el corto recompra al ASK, pero el objetivo se comprueba con el mínimo BID. Como en v2 la salida por objetivo de un corto no paga spread, ese corto **no paga ningún spread**.
- **Evidencia** (`b05_calendar_short_target.py`, spread 30 bps sintético, ASK mínimo 98,28 > objetivo 98):
  ```
  calendar_core corto: reason=target exit_px=98.00 r_gross=2.000 r_net=2.000
  _core (eventos) corto:   reason=end_of_data exit_px=100.00 r_gross=0.000 r_net=-0.300
  ```
- **Impacto:** **a favor**. Hasta un spread completo por cada objetivo corto de calendario, y además objetivos "tocados" que en realidad no se tocan. Afecta poco al cambio de mes clásico, que es largo.
- **Corrección mínima:** copiar el filtro `market_cfd` de `_core` (`_calendar_core` necesitaría recibir `market_cfd`).
- **Test de regresión:** el escenario de arriba da la misma razón de salida en `_calendar_core` y en `_core`.

### B-06 · MEDIUM · NUEVO (latente: hoy `historical_scaled` es Sin datos) · `ffill` sin límite del spread histórico
- **Archivo:** `src/tradinglab/discovery/spread_history.py:229-231`, `historical_spread_provider.provider`.
- **Descripción:** `scaled.reindex(bars.index, method="ffill")` propaga el último minuto con ASK a todas las barras posteriores, sin límite. Las barras anteriores al primer ASK se rellenan con la mediana global, que incluye datos futuros. Con la cobertura real (EURUSD, 10,9 % de barras M1 entre 2021-09 y 2024-03), un solo minuto marcaría el spread de meses enteros. Además, `DEFAULT_WINDOW_DAYS=90` no se usa: la ventana es el rango del bróker y, si no hay `from_ts`, la serie entera.
- **Evidencia** (`b06_spread_ffill.py`, ASK sintético de 2 días con el último minuto a 3 pips):
  ```
  2021-06-01 10:00 -> 0.180 bps   (antes del ASK: mediana global)
  2022-03-08 23:59 -> 2.700 bps
  2022-09-01 10:00 -> 2.700 bps   (6 meses después)
  2024-06-03 14:00 -> 2.700 bps   (2 años después)
  ```
- **Impacto:** sesgo arbitrario en cualquier dirección cuando se active (en cuanto haya ventana común con el bróker).
- **Corrección mínima:** limitar el relleno (por ejemplo, `tolerance` igual a la barra), y fuera de cobertura volver a `hourly_median` del bróker por hora local, no a la mediana global.
- **Test de regresión:** las barras a más de una barra de distancia de cualquier ASK reciben el valor de la mediana horaria del bróker.

### B-07 · MEDIUM · NUEVO · El spread horario se ancla a `session_tz`, no a NY
- **Archivos:** `src/tradinglab/discovery/costs.py:241-245` (`load_local_hour_spreads`) y `fastbt.py:438-447` (`CfdHourlyCosts._local_spread`). `session_tz` sale de `engine.yaml` (`USDJPY: Asia/Tokyo`, `EURUSD/GBPUSD: Europe/London`) a través de `campaigns.py:134`.
- **Descripción:** el docstring de `costs.py:3-4` promete hora local de **Nueva York**, pero se usa la zona de sesión del instrumento. La medición es de noviembre (EST). En verano, NY 17:00 = 21 UTC = Tokio 06:00, pero el modelo pone el pico en Tokio 07:00 = NY 18:00. En Londres el desfase solo aparece en las semanas en que no coinciden los cambios de hora (unas 3 al año).
- **Evidencia** (`b07_tz_mapping.py`, `broker_spreads` sintético con pico de 10 bps a las 22 UTC):
  ```
  session_tz=America/New_York: 2026-07-15 21:00 UTC = 17:00 NY -> 10.0 bps (correcto)
  session_tz=Asia/Tokyo:       2026-07-15 21:00 UTC = 17:00 NY -> 1.0 bps ; 22:00 UTC = 18:00 NY -> 10.0 bps
  ```
- **Impacto:** en USDJPY, de marzo a noviembre: **a favor** de lo que opera en el rollover real y **en contra** de lo que opera una hora después. Magnitud: la diferencia entre el spread del rollover y el normal en esa hora (Sin datos de su tamaño real).
- **Corrección mínima:** indexar `broker_spreads` siempre por hora de NY (la del rollover del servidor), con independencia de `session_tz`.
- **Test de regresión:** con el pico a NY 17:00 EST, en julio el pico cae a las 21 UTC con cualquier `session_tz`.

### B-08 · MEDIUM · NUEVO · La propuesta de slippage medido mezcla cuentas y no casa símbolos
- **Archivo:** `src/tradinglab/discovery/slippage_measured.py:403-407` (`build_proposal`: el filtro es solo `cell.symbol == symbol.upper()`).
- **Descripción:** (a) no filtra por `cell.account`, así que las celdas de CFD-001 aparecen como medición de CFD-006. (b) Las celdas del historial MT5 traen el símbolo del bróker (`US100.CASH`, `NDX100`) y la clave de config es `US100`, así que nunca casan. Esto se ve en la **propuesta real** `config/propfund/costs.measured.yaml`: CFD-006 XAUUSD/EURUSD/GBPUSD con `n` = 3/2/1, que son las celdas de CFD-001, y US100 con `n: 0` aunque hay una celda `US100.CASH n: 6`. (c) Mezcla de definiciones: el camino TCA usa `abs(fill−order)` y el camino MT5 usa slippage con signo. La mediana se calcula como media ponderada de medianas.
- **Evidencia** (`b08_slippage_proposal.py`, celdas sintéticas solo de CFD-001, n=40):
  ```
  CFD-001 XAUUSD {'slippage_price': 0.3, 'source': 'measured', 'n': 40}
  CFD-001 US100 {'slippage_price': 1.0, 'source': 'assumption', 'n': 0}
  CFD-006 XAUUSD {'slippage_price': 0.3, 'source': 'measured', 'n': 40}
  CFD-006 US100 {'slippage_price': None, 'source': 'assumption', 'n': 0}
  ```
- **Impacto:** cuando haya n ≥ 30, la propuesta atribuirá slippage a la cuenta equivocada y nunca medirá los índices. Dato informativo, no concluyente (n < 30), de la propuesta real: XAUUSD mediana 0,23 frente a 0,15 supuesto; US100.CASH mediana 0,295 y p75 1,21 frente a 1,0 supuesto.
- **Corrección mínima:** filtrar por `(account, canonical(symbol))` con `propfund.instruments.resolve` o con el mapa `broker_symbols` de la cuenta.
- **Test de regresión:** las celdas de una cuenta no cambian la propuesta de otra, y `US100.CASH` cuenta para `US100`.

### B-09 · LOW · NUEVO · Discovery ignora el slippage del perfil
- **Archivo:** `src/tradinglab/discovery/costs.py:312-315` (`profile = replace(profile, slippage_price=assumed)`).
- **Descripción:** el slippage de `engine.yaml::assumed_slippage` sustituye siempre al del perfil, aunque el docstring (`costs.py:8-9`) dice "el slippage **no medido**". Aunque el operador lleve una medición aprobada a `config/propfund/costs.yaml`, Discovery seguirá con el supuesto. Esto se comprueba leyendo el código; no hace falta reproducción porque la asignación es incondicional.
- **Impacto:** el T12 no tiene salida hacia Discovery. Con el supuesto de TL2 P1-1, el sesgo probable es en contra en FX.
- **Corrección mínima:** usar `profile.slippage_price` cuando su `source` sea `measured`, y si no, el supuesto. Guardar la fuente en `slippage_assumption`.
- **Test de regresión:** un perfil con slippage medido llega al panel.

### B-10 · MEDIUM · NUEVO (sobre la corrección de ROBUST-1) · `slippage_plus_2` es casi nulo en índices y oro
- **Archivo:** `src/tradinglab/discovery/retester.py:121-122` y `_scenario_panel:33-42`.
- **Descripción:** ROBUST-1 dejó bien las unidades (2 × `point` del instrumento). Pero `point` es el tick de cotización, no una unidad de slippage, así que el estrés queda en un porcentaje mínimo del slippage supuesto. La puerta 3 de X3 (que, según ROBUST-1, "pasa en la mayoría") apenas mide nada en índices.
- **Evidencia** (`b03_retester_slip_stress.py`, ratios independientes del precio):
  ```
  US100 +2.0 % | US500 +4.0 % | US30 +0.8 % | XAUUSD +13.3 % | EURUSD/GBPUSD/USDJPY +40.0 %
  panel: slip base=1.0000 bps, slip +2pt(point=0.01, px=100)=3.0000 bps   (la mecánica es correcta)
  ```
  Como referencia, `TL3_REPORTS/tca_diagnostico.md` §3 da en US100 un p95 decisión→fill de 2,1 bps, varios órdenes de magnitud por encima de +0,02 puntos.
- **Impacto:** la puerta de slippage se vuelve vacía: no sesga el estimador, pero no protege.
- **Corrección mínima:** definir el escenario como `+1×`/`+2×` el slippage supuesto (o el p95 medido cuando haya n ≥ 30) y prerregistrarlo antes de usarlo.
- **Test de regresión:** con `slippage_plus_2`, el slippage por lado se multiplica por 3 en todos los instrumentos.

### B-11 · MEDIUM · NUEVO (latente) · Caché de `CostBook.panel` por `id(bars)` y `apply()` con el último panel
- **Archivo:** `src/tradinglab/discovery/costs.py:433-436` (caché) y `:502-512` (`apply` usa `self._panels` sin comprobar que las barras sean las de los trades). Lo mismo en `spread_history.py:226-228` (caché `id(bars)` del proveedor).
- **Descripción:** CPython reutiliza los `id` de objetos ya liberados. Si se libera un DataFrame y se crea otro, `panel()` devuelve el panel viejo, con otra longitud y otros valores. Con Numba, un índice fuera de rango no se comprueba. Por separado, `apply()` aplica los paneles de la **última** llamada a `panel()`: si se preparan dos tramos con el mismo libro antes de aplicar, los costes salen de las barras equivocadas.
- **Evidencia** (`b12_panel_cache_id.py`):
  ```
  iteración 13: id reutilizado; len(bars)=30 len(panel)=10 spread=1.0 (esperado 3.0)
  reutilizaciones de id en 2000 intentos: 1987
  ```
- **Impacto:** no encontré ningún camino actual que lo dispare: jobs, fitness, levels, edge_map y basket construyen un libro por marco y lo aplican enseguida. Pero cualquier reutilización futura del libro entre IS y OOS daría costes erróneos y silenciosos.
- **Corrección mínima:** clave de caché `(id(bars), len, índice[0], índice[-1])`, o guardar una referencia fuerte a `bars` y comparar con `is`. `apply()` debería recibir `bars` o comprobar `len(panel) > max(exit_index)`.
- **Test de regresión:** dos marcos distintos con el mismo `id` simulado dan paneles distintos, y `apply` con trades fuera de rango lanza un error.

### B-12 · LOW · NUEVO · `slip_r` cobra el slippage de salida en las salidas por objetivo
- **Archivos:** `src/tradinglab/discovery/fastbt.py:1956-1958` y `costs.py:523,560`.
- **Descripción:** en v2 el objetivo solo paga comisión (`ex_b = comm`), pero la descomposición suma `slip[e] + slip[x]`. `r_cost` y `r_net` son correctos; el desglose no lo es. Contradice 06 §5 ("su suma menos `swap_r` es `r_cost`, tolerancia 1e-9"). El test `test_costbook_aplica_las_mismas_reglas` no lo detecta porque usa slippage 0 y salida por tiempo.
- **Evidencia** (`b01_slip_target.py`):
  ```
  fastbt.run  reason= target  r_cost=0.040000  suma componentes=0.050000  diferencia=0.010000 R (= slip[x]·factor)
  CostBook    reason= target  r_cost=0.040000  suma componentes=0.050000
  ```
- **Impacto:** informes de atribución (`tl3/report.py` usa los pasos spread/commission/slippage) con el slippage inflado y la suma que no cuadra. No sesga R.
- **Corrección mínima:** `slip_r = (slip[e] + (slip[x] if reason != "target" else 0)) · factor` en los dos sitios.
- **Test de regresión:** una salida por objetivo con slippage > 0 cumple la identidad de 06 §5.

### B-13 · LOW · NUEVO · Swap ausente → 0 silencioso
- **Archivos:** `src/tradinglab/propfund/costs.py:186-191` (`SwapSpec.from_profile` devuelve `None`) y `fastbt.py:1993-1995` (sin swap no se aplica nada). `cost_from_profile` llama a `estimate_cfd(nights=0)`, que no comprueba el swap.
- **Evidencia** (`b14_checks.py` §4): `swap ausente: cp.swap= None  noches= 5  swap_r= None  swap_source= None`.
- **Impacto:** hoy no hay ninguno: todas las cuentas y símbolos permitidos tienen swap en `swap.yaml`. Si se añade un símbolo sin medir, las estrategias de varias noches salen **a favor** sin aviso, en contra de la regla "Sin datos".
- **Corrección mínima:** con `swap=None` y alguna operación de varias noches, marcar `swap_source="Sin datos"` (o marcar el individuo como no factible).
- **Test de regresión:** perfil sin swap y operación de 5 noches dan `swap_source == "Sin datos"`.

### B-14 · LOW · CONOCIDO(TL3_REPORTS/tca_diagnostico.md §1, §5; ESTADO §4 fila 3), ampliado · Huecos de la TCA v2 (requiere cola de producción, AGENTS.md: `execution/`)
- **Estado:** la fila 3 de ESTADO §4 (`mt5.py:772-783`, slippage siempre 0) **ya no describe el código**. TL2-TCA2 cambió `execution/mt5.py:718-831`: hay `signal_price`, `submit_px` releído, `fill_px=None` si MT5 devuelve 0, `latency_ms` de `order_send` y `tca_version=2`. Quedan:
  1. `mt5.py:819`: `expected_cost_bps=getattr(self, "slippage_bps", 0.0)`. El bróker MT5 no tiene ese atributo, así que vale **siempre 0**, y `build_tca` compara contra 0.
  2. `mt5.py:827-828`: `bid`/`ask` del tick **previo** (`tick`), no del `submit_tick`, mientras `requested_price=submit_px`.
  3. `mt5.py:718-722`: sin `signal_price`, `signal_px` cae al tick sin ninguna marca. En esas filas el slippage mide tick→fill, no decisión→fill.
  4. Las salidas por SL/TP las ejecuta el servidor y **nunca** pasan por `order_send`, así que la TCA no mide el slippage de stop, que es el que más pesa en R.
  5. `execution/paper.py:177-187`: el paper graba con `tca_version=2` un "slippage" que es el supuesto (`self.slippage_bps`) y sin `origin`, así que `slippage_measured` no puede excluirlo (diag §5.4 sigue sin aplicar).
  6. `ts_utc` es la hora de registro, no la del fill (`deal.time_msc`).
- **Impacto:** el T12 seguirá midiendo poco y mal aun con n ≥ 30, y en el lado de la entrada.
- **Corrección y test:** ver "Diseño de medición TCA".

---

## Sospecha no reproducida

| ID | Sospecha | Por qué no se reprodujo |
|---|---|---|
| S-1 | Signo y magnitud del swap de US100 en CFD-001: `swap_long +1076,28` (crédito para el largo) y `swap_short −1677,49` points (≈16,8 puntos de índice por noche y contrato). En un índice se espera que el largo pague. | Medido en MT5 y guardado en `config/propfund/swap.yaml`. No tengo precio ni un deal para comprobarlo: **Sin datos**. Si está bien, el corto en US100 paga una financiación muy alta, lo que amplifica B-04. Verificarlo con un `DEAL_SWAP` real. |
| S-2 | El spread de 2026 en bps aplicado a 2017-2025 subestima el spread absoluto pasado en XAUUSD si el spread en dólares no escala con el precio. | Sin datos de spread histórico del oro. Es CONOCIDO como costes anacrónicos (TL2 P1-3, 06 §5 T11). |
| S-3 | En modo `best`, el panel del camino (disparo del stop corto, salida en `open_ask`) usa el **mínimo** de spread entre cuentas, y luego `apply` elige la mejor por operación. El camino resulta más optimista que el de cualquier cuenta individual. | Diseño documentado en `costs.py:5-6`. No lo reproduje porque no hay ninguna campaña conocida en `best` con dos cuentas. |
| S-4 | `DFF` de FRED se publica con un día de retraso y `asof(noche)` usa el valor del mismo día: lookahead de un día en el tipo. | El efecto es despreciable (tipo diario). No se cuantificó. |

## Comprobado y correcto

1. **v2, un solo spread por ida y vuelta** (CONOCIDO TL2 P0-1, corregido): largo y corto con salida por tiempo cuestan 2,00 bps con spread de 2 (`b14_checks.py` §1).
2. **Stop de corto con ASK y hueco** (CONOCIDO TL2 P0-1, corregido): sale a `max(stop, open_ask)` = 101,5203 y `exit_bps=0`, sin segundo spread (`b14` §2; `fastbt.py:996-1027`).
3. **Objetivo largo al BID y objetivo corto exigiendo ASK en `_core`** (`fastbt.py:1005-1010`). La única excepción es `_calendar_core` (B-05).
4. **Ningún coste ausente se convierte en 0** en spread, slippage, comisión y futuros: `MissingCostData "Sin datos"` para `CfdBpsCosts` sin slippage o sin spread y para `MNQ` de FUT-001 con comisión `null` (`b14` §3). Las excepciones son el swap (B-13) y las horas sin medir, que usan el **máximo** de las horas medidas (cota conservadora, `fastbt.py:440`). `_hour_values` (`fastbt.py:205-222`) usa hora UTC y la **mediana** como reserva, pero ningún llamador le pasa `spread_bps_by_hour` (comprobado con grep): es código muerto.
5. **Comisión `percent_of_volume`:** 0,0007 % = 0,07 bps/lado. **`round_turn`:** factor 0,5 (FP XAUUSD 5 USD → 0,125 bps/lado a 2000 sintético) (`b14` §6).
6. **Futuros:** `fut_price = (com·lado + fees + ticks·tick_value)/(tick_value/tick_size)`. MNQ sintético a 0,75 USD/lado + 1 tick da 0,625 pt/lado y `cost_R = 2·0,625/riesgo` (`b14` §5). Spread 0 por diseño (06 §5); el tick de spread queda dentro de `slippage_ticks`. La comisión de 0,75 USD/lado acordada (ESTADO §4 fila 1) solo está en el prerregistro TL3 (`scripts/tl3_e2_verify_nqf.py:123`). `config/propfund/costs.yaml:139` sigue con `null`, y Discovery responde "Sin datos", que es correcto.
7. **`point` del retester** (CONOCIDO ROBUST-1, corregido): `QueueSetup.point` sale de `propfund.instruments.point_size` (`jobs.py:92-99`). EURUSD/GBPUSD 1e-5, USDJPY 1e-3, índices/oro 0,01 y MNQ 0,25. No queda ningún `point=0.01` por defecto en `discovery/` (grep). Su magnitud se discute en B-10.
8. **Swap en R:** modo 1 `points·point/riesgo` y modo 5 `precio·%/360/riesgo` (`propfund/costs.py:426-450`). El crédito cuenta 0 (`swap_credit: false`, conservador). Las noches solo cuentan de lunes a viernes a NY 17:00, con 7 unidades por semana (`b04`). Lo único mal es la posición del triple (B-04).
9. **Swap histórico (T13):** el signo de cada lado (FX +diferencial para el largo; índices y oro, el largo paga) y la calibración del markup reproducen el swap de hoy (`propfund/costs.py:221-267`). Si FRED no tiene datos, cae al estático con `static_fallback`. Que el markup se calibre con hoy y se aplique al pasado es una decisión de diseño documentada.
10. **Unidades:** todo `r_cost` se expresa como `bps·entry/riesgo/1e4` (precio/precio), y el slippage del perfil se convierte con `slip_price/close·1e4`. Es coherente en CFD. La única incoherencia de unidades es B-01.
11. **Modo `worst`:** por operación se elige el máximo de `r_cost` entre cuentas, swap incluido (`costs.py:604-612`). El camino usa el máximo componente a componente, que es más conservador que el máximo de las sumas.
12. **TCA:** `tca.slippage_bps` tiene signo correcto (positivo = peor; venta invertida, `tca.py:96-101`). Los lectores filtran `tca_version >= 2`.

---

## Diseño de medición TCA

Objetivo: comparar por operación (entrada **y** salida) lo que supuso el backtest con lo que se ejecutó, en bps y en R, por componente. Inventario frente a `db.py:340-354` (`tca`), `db.py:57-64` (`fills`), `mt5_fills.py:105-118` y `execution/mt5.py:705-831`.

| Campo | Definición | ¿Existe? | Dónde / qué falta |
|---|---|---|---|
| `decision_ts` | Momento de la decisión (cierre de la barra de señal) | **Falta** | Hay `ai_decisions`/`signals` sin `order_id` (diag §3). |
| `signal_px` | Precio de referencia del backtest en la decisión (open siguiente BID/ASK o nivel de stop/TP) | Existe (`tca.signal_px`) | Sin señal cae al tick de forma silenciosa. Falta `signal_source` (`decision`/`tick_fallback`). |
| `submit_ts` | Hora de `order_send` | **Falta** | Solo `latency_ms` relativo. |
| `requested_px` | Precio enviado | Existe (`order_px`, `requested_price` = `submit_px`) | Duplicado. |
| `bid_submit`, `ask_submit` | BBO en el envío | **Parcial** | `bid`/`ask` vienen del tick **anterior** (`mt5.py:827-828`). Hay que usar `submit_tick`. |
| `spread_bps_submit` | `(ask−bid)/mid` | Falta (se puede derivar) | Comparar con `CostPanel.spread_bps[i]` del backtest. |
| `fill_ts` | Hora del deal (`deal.time_msc`) | **Falta** en `tca` (`ts_utc` = hora de registro) | `fills.ts_utc` existe en `mt5_fills`. |
| `fill_px` | Precio del deal | Existe | `None` si MT5 devuelve 0 (correcto). |
| `volume_req` / `volume_fill` | Parciales | **Falta** | Para la tasa de llenado. |
| `slippage_bps` (decisión→fill) | Con signo | Existe | Válido solo si `signal_source=decision`. |
| `slippage_submit_bps` (envío→fill) | Con signo | **Falta** (hoy `realized_cost_bps` usa abs) | Separar latencia de ejecución. |
| `commission_usd` | `deal.commission` | En `fills.commission` (`mt5_fills`) | No está unido a la fila `tca` (`fill_id` nulo en 68/68). |
| `swap_usd` | `deal.swap` en el cierre | En `fills.swap` | Falta unirlo a la operación y a la noche (para verificar B-04 y S-1). |
| `latency_ms` | `order_send` ida y vuelta | Existe | Falta decisión→envío (`submit_ts − decision_ts`). |
| `expected_*_bps` | Coste supuesto **por componente** del modelo (`cost_model_version`, `spread_bps`, `slip_bps`, `comm_bps` de la barra) | **Falta**; `expected_cost_bps` = 0 en MT5 (B-14.1) | Grabar desde el panel de la estrategia en el envío. |
| `leg` | `entry` / `exit_sl` / `exit_tp` / `exit_signal` | **Falta** | Las salidas SL/TP son del servidor y no pasan por `order_send`. Reconciliar con `history_deals` (`DEAL_REASON_SL/TP`) contra el `sl`/`tp` pedido (stop: slippage = `fill − sl` con signo). |
| `risk_px` | Distancia al stop de la orden | Parcial (`sl` en `_record`) | Necesaria para expresar todo en R. |
| `position_id`, `deal_id`, `magic` | Enlace exacto | En `fills` (`deal_id`, `magic`) | `tca.fill_id` nulo. Usar `position_id` para unir entrada y salida. |
| `broker`, `account`, `canonical_symbol` | Agrupación | `account` y `symbol` (del bróker) | Falta el canónico (causa de B-08). |
| `origin`, `order_type` | Bot y tipo | Existen | `order_type` fijo en `"market"`. El paper no rellena `origin` (B-14.5). |
| `tca_version` | Versión del esquema | Existe | El paper debería grabar `measured=0` o una versión aparte. |

**Reglas de medición:**
1. Sin el precio de la decisión, `slippage_bps` va nulo, nunca 0.
2. Las salidas se miden contra el nivel pedido (SL/TP).
3. Las celdas se agrupan por `(account, canonical, leg, order_type, franja)` con n ≥ 30 antes de proponer.
4. Se informa la mediana y el p95 con signo, y su equivalente en R (`bps·px/riesgo/1e4`).
5. Se mide el residuo `fill − (signal_px ± spread_modelo/2)` por componente, para validar por separado `spread_bps` y `slip_bps` del `CostPanel`.

Todo cambio en `execution/mt5.py` y `execution/paper.py` **requiere cola de producción (AGENTS.md)**: baseline, test de regresión, CHANGELOG y tag `tl2-<id>-pre`. La reconciliación de salidas puede hacerse fuera de producción, leyendo `fills`/`mt5_fills` (solo lectura).

## Scripts (scratchpad, solo sintético)

`common.py`, `b01_slip_target.py` (B-12), `b02_usdjpy_commission.py` (B-01), `b03_retester_slip_stress.py` (B-10), `b04_swap_triple.py` (B-04), `b05_calendar_short_target.py` (B-05), `b06_spread_ffill.py` (B-06), `b07_tz_mapping.py` (B-07), `b08_slippage_proposal.py` (B-08), `b10_robustness_cost_model.py` (B-03), `b12_panel_cache_id.py` (B-11), `b13_levels_v1_default.py` (B-02) y `b14_checks.py` (B-13 y "Comprobado"). Cada uno tiene su salida en `*.out.txt`. Las bases `b07_lab.db` y `b10_lab.db` son sintéticas y están en el scratchpad.
