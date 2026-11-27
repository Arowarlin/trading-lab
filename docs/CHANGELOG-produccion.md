# Cambios en producción

Registro obligatorio de los cambios en componentes de producción: EA
`us100-ftmo1`, carril forward FTMO, riesgo FTMO, `ai_trader`, Prop Fund y
`ea_lab`. Cada entrada indica la autorización del operador, qué cambió y cómo se
comprueba. El baseline de hashes vive en
`config/propfund/protected_manifest.json` y se consulta con
`lab propfund verify`; se reescribe con `lab propfund baseline --reason "..."`.

## 2026-11-26 · TCA v2: señal real, versión y lectores (TL2-TCA2)

- **Autorización del operador (literal):** «Lee AGENTS.md y
  .orquestador/COLA-TL2-TCA2.md completa y síguela SIN PARAR NI PEDIRME
  CONFIRMACIÓN de T0 a T7. Antes haz commit de ese archivo con git add -f.
  APRUEBO CAMBIO DE PRODUCCIÓN TL2-TCA2: signal_price desde ai_trader y
  forward_intraday, columna tca_version (filas antiguas intactas), lectores solo
  v2 y tests del cambio de ejecución de e02ad7e. Tag tl2-tca2-pre ANTES de tocar
  código, baseline, tests de regresión y CHANGELOG. No reinicies ni actives
  ningún proceso, sin órdenes ni push. Commits por ruta y PARA al final.»
- **P-1 · `ai_trader`:** `execute()` pasa `signal_price=float(row["entry"])`,
  el precio de la propuesta, no el tick de envío. Añade `age_ms` al `reason` de
  la orden cuando `ai_trades.ts` existe.
- **P-2 · forward:** `forward_intraday.run_forward_bot()` pasa
  `signal_price=entry`, el precio de la decisión (`ForwardDecision.price`).
- **P-3 · lectores:** `ai_trader._slippage_avg`, `ai_distill`
  (`scalping_tick_confirmation`), `tca.build_tca` (web y `lab tca`) y
  `discovery/slippage_measured.py` filtran `tca_version >= 2`. `drift.py` queda
  cubierto por `attach_to_drift` → `build_tca`. Con solo filas v1 devuelven
  **sin datos**, nunca 0.
- **P-4 · ejecución de `e02ad7e`:** tests propios: la orden usa el tick
  releído; un SL exactamente en `stop_distance` pasa; uno a un punto menos se
  rechaza con `MT5Error`; con el mismo tick de señal y envío el resultado
  coincide con `tl2-tca-pre`.
- **Riesgo de frontera corregido:** la comparación de distancia usaba `<`
  estricto y la coma flotante rechazaba un SL exactamente en `stop_distance`
  (0,1000000000000085 frente a 0,1). Se añadió una tolerancia de `1e-9`; la
  regla del bróker no cambia, solo deja de rechazar el caso legítimo de igualdad.
- **TCA v2:** `db.py::_migrate_tca` añade `tca_version INTEGER` de forma
  idempotente y **sin actualizar filas**; las antiguas quedan `NULL` (= v1).
  `tca.record_fill` escribe `tca_version = 2` en toda fila nueva, desde MT5 y
  desde paper. `execution/paper.py` acepta `signal_price` opcional y mide el
  slippage contra la señal.
- **Qué no cambia:** las filas antiguas de `tca` (mismo contenido, mismo
  `slippage_bps`), `operator.py`/`cli.py` (órdenes manuales siguen usando el
  tick de envío), `slippage_probe.py`, EA, riesgo FTMO, `prop/`, `config/` y
  `.env`. No se reinicia ni se activa ningún proceso y no se envía ninguna
  orden.
- **Nota de reinicio:** los procesos de demo en marcha (`ai_trader`, forward)
  cargaron el código antiguo; este cambio no les afecta hasta que el operador
  los reinicie.
- **Tests:** `tests/test_tca_v2.py` (migración idempotente, filas antiguas
  intactas, filas nuevas v2), `tests/test_tca_v2_readers.py` (66 filas v1 a 0 +
  6 v2 a 2,0 → media 2,0; solo v1 → sin datos), `tests/test_tca2_callers.py`
  (`signal_price` en ai_trader y paper), `tests/test_mt5_tca.py` (P-4) y
  `tests/test_forward_intraday.py` (signal_price en forward).
- **Verificación:** `ruff check`, `pytest -q`, `lab doctor`,
  `lab propfund verify` y contador. El detalle y los hashes quedan en
  `.orquestador/BASELINE-prod-tca2.md`.
- **Vuelta atrás:** `git checkout tl2-tca2-pre -- <ruta>`; el tag
  `tl2-tca2-pre` es `6fa4d2f`.

## 2026-11-25 · TCA MT5 separa señal, envío y fill (prod-tca)

- **Autorización del operador (literal):** «Lee AGENTS.md y ejecuta el parche de
  producción para corregir el cálculo de slippage en
  src/tradinglab/execution/mt5.py:772-783 (separando signal_price de submit_price
  y fill_price). Cumple el protocolo completo: adquiere orq_lock
  proyecto-prod-tca, guarda baseline en .orquestador/BASELINE-prod-tca.md, crea
  el tag tl2-tca-pre, añade tests en tests/test_mt5_tca.py, documenta en
  docs/CHANGELOG-produccion.md, corre ruff, pytest -q y lab doctor, confirma
  count_tests == 1926, haz commit por ruta, etiqueta tl2-tca-post, libera locks y
  PARA.»
- **Qué cambia:** `MT5Broker.submit_market` acepta `signal_price`; captura el
  tick de la señal, relee el tick justo antes de `order_send` y registra
  `signal_px`, `order_px` y `fill_px` por separado. `slippage_bps` se mide como
  diferencia adversa entre `signal_px` y `fill_px` (positivo = peor que la
  señal). Si el bróker devuelve 0 o vacío, `fill_px` queda `None`; ya no se
  sustituye por el precio pedido. `latency_ms` mide `order_send` → respuesta.
- **Por qué:** el diagnóstico D5b mostró 66 de 68 filas con slippage 0 por
  construcción: `signal_px` y `order_px` eran el mismo tick y `fill_px` caía al
  precio pedido cuando MT5 devolvía 0.
- **Alcance:** `src/tradinglab/execution/mt5.py` y tests. `signal_price` es
  opcional; los llamadores existentes no cambian. No se tocan EA, `ai_trader`,
  forward, riesgo FTMO, `paper.py`, base de datos ni configuración.
- **Baseline/tag:** `tl2-tca-pre` → `b412853`; baseline en
  `.orquestador/BASELINE-prod-tca.md`; `config/propfund/protected_manifest.json`
  reescrito con `lab propfund baseline --reason "prod-tca: ..."`.
- **Tests de regresión:** `tests/test_mt5_tca.py` (9 casos) compara el
  comportamiento anterior y el nuevo, cubre fill 0, `signal_price` explícito y
  slippage positivo/negativo/cero. Se mantienen `tests/test_tca.py` y
  `tests/test_mt5.py`.
- **Verificación:** `ruff check` limpio; `pytest -q` completa **2037 pasados,
  1 skip**; `lab doctor` con un FAIL de frescura de datos (US100 M1/M5/M15 y
  XAUUSD M1, ajeno a este parche) y el resto OK/WARN; `lab propfund verify`
  4/4 OK. `count_tests` real: **5446** al empezar el protocolo y **7206** al
  cerrar, por la pasada EDGE1 en curso; el **1926** de `ESTADO.md` está
  desactualizado y este parche no añade ninguna prueba al contador.
- **Rollback:** `git checkout tl2-tca-pre -- src/tradinglab/execution/mt5.py`.

## 2026-11-25 · Suelo diario `higher_of_balance_or_equity` (TL2-DIARIO)

- **Autorización del operador (literal):** "APRUEBO CAMBIO DE PRODUCCIÓN
  TL2-DIARIO: solo la rama higher_of_balance_or_equity de prop/simulator.py y
  prop/guard.py (y snapshots.py solo si P1 lo permite), con tag
  tl2-diario-pre, baseline, tests de regresión y CHANGELOG. Sin órdenes, sin
  push."
- **Qué cambia (E-1):** en `prop/simulator.py::monte_carlo` y
  `monte_carlo_program`, la rama `higher_of_balance_or_equity` deja de usar el
  balance inicial. En el modelo diario no hay posiciones abiertas entre días,
  así que `day_start_balance = day_start` y el suelo es
  `max(day_start_balance, day_start) - effective_daily_limit_usd`. Antes, toda
  cuenta 5 % por debajo del balance inicial contaba como rotura diaria.
- **Qué cambia (E-2):** en `prop/guard.py::_bases`, la rama nueva usa
  `max(day_start_balance, day_start_equity)`. Si falta uno de los dos, usa el
  disponible; si faltan ambos, registra un aviso y conserva la base de equidad
  anterior. Los modos `balance` y `equity` no cambian.
- **E-3 (pendiente):** `propfund/snapshots.py` sigue traduciendo
  `higher_of_balance_or_equity` a `equity` y lo anota. P1 mostró que `overlay`,
  `defense` y `risk` no leen el modo ni reciben balance de inicio de día;
  darles soporte exige cambiar sus firmas y la fuente de datos, más que el
  cambio mínimo autorizado. Queda anotado para otra cola.
- **Qué no cambia:** los modos `balance`/`equity` (identidad bit a bit contra
  `tests/data/prop_daily_golden.json`), los límites y porcentajes, las reglas
  FTMO, `config/propfund/*.yaml`, el EA, `ai_trader`, el forward, las tareas y
  `.env`. No se envía ninguna orden ni se activa ningún bot.
- **Verificación:** `tests/test_prop_daily.py` (identidad de los 15 casos
  golden, camino de −0,25 % diario sin rotura en 30 días, día de −5,1 % que
  rompe ese día, suelo de `guard` en 95.000 con balance 100.000 y equidad
  98.000) y `tests/test_prop_n1.py` corregido. `ruff check` y los tests de
  `prop`/`propfund` en verde. Tabla antes/después de las 9 filas FundingPips de
  D2 en `TL3_REPORTS/tl2_diario_inventario.md` §9; P(diario) pasa de
  18,36-67,68 % a 0.
- **Informes históricos afectados (no reescritos):**
  `TL3_REPORTS/propfund_zero_edge.md` (9 filas de FundingPips; se le añade una
  línea que remite a la tabla nueva) y `reports/ea/p-pasar-oficial.md`
  (FundingPips 2-Step: backtest 0,25 % → P(pasar) 95,66 % / P(romper) 4,34 %;
  0,35 % → 87,52 % / 12,5 %; mitad y LCB95 → "ninguno").
- **Rollback:** tag `tl2-diario-pre` (HEAD de P1, antes de tocar el código).
  Tag de cierre: `tl2-diario`.

## 2026-11-24 · Retirada de la protección de componentes

- **Autorización del operador (literal):** "EL PASO YA NO ESTA PROTEGIDO
  QUITALE LA PROTECCION".
- **Qué cambia:** el manifiesto deja de bloquear. `lab propfund verify` informa
  de los archivos cambiados y sale con código 0; `lab propfund baseline
  --reason "..."` reescribe el baseline y añade una entrada a `authorizations`
  con fecha, motivo y lista de cambios. El concepto `protected` de una
  estrategia pasa a `external_engine` (la ejecuta su propio motor); el YAML
  antiguo con `protected: true` sigue cargando como alias de lectura.
- **Qué no cambia:** el router sigue rechazando enviar órdenes a estrategias de
  motor externo. Solo demo/paper; ninguna orden real.
- **Rollback:** tag `tl2-t00-pre`.

## 2026-11-24 · Modelo de ejecución BID/ASK v2 en Discovery

- **Qué cambia:** `CostPanel` lleva `spread_bps`, `slip_bps` y `comm_bps` por
  barra. Las campañas nuevas registran `cost_model_version: 2`: un solo spread
  por operación, stop de corto disparado por el ASK (`max(stop, open_ask)`) y
  desglose por operación (`spread_r`, `slip_r`, `comm_r`). Las campañas
  existentes se cargan como versión 1 y se reproducen igual.
- **Alcance:** `discovery/fastbt.py`, `discovery/costs.py`, `discovery/drift.py`,
  `discovery/jobs.py`, `discovery/fitness.py`, `discovery/robustness.py`,
  `discovery/levels.py`, `discovery/feasibility.py`, `discovery/specs.py`,
  `discovery/basket.py` y `discovery/campaigns.py`. No se toca
  `ea_us100_engine.py` (es la referencia).
- **Verificación:** `tests/test_discovery_execution_v2.py` (17 pruebas con
  resultados a mano), paridad v1 en las fixtures existentes, paridad de
  convención con `ea_us100_engine` y tabla de coste antes/después en
  `docs/tradinglab2/06_TRADINGLAB_DATA_AND_COST_AUDIT.md`.
- **Rollback:** tag `tl2-t10-pre` o `cost_model_version: 1` en la campaña.

## 2026-11-24 · Spread histórico por barra en Discovery (T11)

- **Qué cambia:** `discovery.spread_model` (`p75_static`, `hourly_median`,
  `historical_scaled`). Las campañas v2 intentan el spread por barra desde el
  ASK de Dukascopy, escalado al bróker por hora local; sin ASK o sin ventana
  común usan la mediana horaria. El p75 queda en los escenarios de estrés
  `cost_x1_5` y `spread_p75`.
- **Datos:** solo EURUSD tiene ASK (10,9 % de M1, 2021-09 a 2024-03); el bróker
  mide 2026-11-13 a 2026-11-19. No hay ventana común: `historical_scaled` es
  **Sin datos** y v2 usa `hourly_median`.
- **Verificación:** `tests/test_discovery_spread_history.py` y
  `reports/discovery/spread-historico.md`. No se ha descargado nada.
- **Rollback:** `spread_model: p75_static`.

## 2026-11-24 · Swap histórico en Discovery (T13)

- **Qué cambia:** `swap.mode: historical` y `SwapSpec` modo 6. El swap se
  calcula con tipos diarios de FRED (DFF, €STR/EONIA, SONIA, call money JP) y
  un markup calibrado para reproducir `swap.yaml` a fecha 2026-11-23.
  `swap_t = (tipo_ref_t + markup) · nocional · noches / 360`; triple rollover
  intacto. El crédito sigue en 0 en Discovery.
- **Datos:** FRED disponible por keyring y caché. FX usa el diferencial
  base−cotizada; índices y oro usan USD. Solo campañas v2; v1 conserva el swap
  medido.
- **Verificación:** `tests/test_discovery_swap_history.py` y
  `reports/discovery/swap-historico.md`.
- **Rollback:** `swap.mode: static`.

## 2026-11-24 · Propuesta de slippage medido (T12, no aplicada)

- **Qué cambia:** nuevo `lab costs slippage-measure` y
  `config/propfund/costs.measured.yaml`. Mide `|fill − solicitado|` por
  símbolo, cuenta, tipo y franja de 4 h; con `n ≥ 30` propone `measured`, con
  menos conserva el supuesto. **`costs.yaml` no se modifica.**
- **Datos:** 58 filas TCA / 116 fills / 65 órdenes. Todas las celdas `n < 30`
  y `order_px == fill_px`; la propuesta queda en `assumption`.
- **Verificación:** `tests/test_discovery_slippage.py`.
- **Rollback:** borrar la propuesta; no hay cambio aplicado.

## 2026-11-24 · C1 · Signo y fallback del swap histórico

- **Qué cambia:** `tasa_lado = s_lado · ref + markup_lado`, con
  `s_largo=-1/s_corto=+1` en índices, oro y CFD sobre USD y
  `s_largo=+1/s_corto=-1` en FX. Si una noche es anterior a la serie FRED se
  usa el swap estático y el trade queda `swap_source=static_fallback`.
  `DFF` se descarga desde 2003. La tabla USD convierte la divisa cotizada
  (USDJPY ya no trata yenes como dólares).
- **Verificación:** 23 tests de swap; `reports/discovery/swap-historico.md`.
- **Rollback:** `swap.mode: static` o `tl2-c1-pre`.

## 2026-11-24 · C2 · Versión de coste en edge map, optimizador y onboarding

- **Qué cambia:** `discovery.default_cost_model_version: 2`. Las evaluaciones
  nuevas de `edge_map.suggest`, `optimizer.plateau` y `onboarding.onboard`
  usan v2; las campañas guardadas conservan su versión. Onboarding gana el
  parámetro `cost_model_version` y `_run_with_cost` respeta la versión de los
  límites.
- **Baseline:** `tests/fixtures/baselines/onboarding_v1.json` (CFD-001/006).
  v2 reduce el coste medio 0,015 R y hace viables 9/10 combinaciones nuevas.
- **Verificación:** `tests/test_discovery_cost_versions.py`.
- **Rollback:** `default_cost_model_version: 1` o `tl2-c2-pre`.

## 2026-11-24 · C4 · Slippage desde MT5 y slippage de equilibrio

- **Qué cambia:** `lab costs slippage-measure --source mt5` lee el historial
  (attach-only) de FTMO y FundingPips; `tca` gana `bid`, `ask`,
  `requested_price`, `order_type` y `origin` (migración aditiva), y
  `execution/mt5.py` los guarda antes/después del envío sin cambiar la orden.
  `lab discovery results` añade `slip_eq` solo en campañas aprobadas.
- **Datos:** FTMO 34 órdenes/35 deals; FundingPips 0/1. Las entradas a mercado
  no guardan `price_open`; solo las cierres permiten medir y todas quedan
  `n < 30`. Propuesta en `costs.measured.yaml`, `costs.yaml` intacto.
- **Verificación:** tests de celdas MT5, `record_fill`, `submit_market` simulado
  y `slip_eq`; baseline de producción actualizado.
- **Rollback:** `tl2-c4-pre`.








## 2026-11-24 - Contador de pruebas v2 = n_total (CNT)

- **Que cambia:** `discovery_tests` suma siempre `n_total` de cada campana
  aprobada y no reemplazada, sea v1 o v2. Desaparece la rama
  `1 + plateau_n`, que contaba de menos las campanas v2 con primaria y
  `plateau_n = 0`. `register` calcula un unico `protocol_version` efectivo y
  guarda `plateau_n = n_total - 1` (puntos de rejilla sin la primaria, solo
  informativo) y `decision_n_total = 1` cuando hay primaria v2. La ruta de
  cesta guarda tambien `plateau_grid` y `plausible_edge_r`.
- **Alcance:** `discovery/campaigns.py` y `discovery/basket.py`. No cambia
  ninguna fila de las bases de datos ni reejecuta campanas.
- **Verificacion:** `lab research-trials` pasa de 1886 a **1894** (1883 + 2
  del registro informal + 9 de `v2-fix-londres-eurgbp-h1`); tests de contador
  v1/v2/fila antigua y de `register` con `protocol_version=None`.
- **Rollback:** tag `tl2-cnt-pre`.

## 2026-11-24 - Reglas oficiales de firmas y P(pasar) real (N1)

- **Que cambia:** `config/propfund/firms.yaml` pasa a fuentes oficiales de FTMO (2-Step y 1-Step) con `effective_from: 2026-11-24`, anade el programa 1-Step, la fase de verificacion del 2-Step (5 %), `max_days: null` y la base diaria de FundingPips `max(balance, equity)`. `prop.simulator.monte_carlo_program` simula dos fases, dias minimos, tope tecnico de 180 dias habiles por fase y `P(sin terminar)`; `robustness._challenge` lo usa.
- **Alcance:** `prop/rules.py`, `prop/simulator.py`, `discovery/robustness.py`, `propfund/models.py` y `config/propfund/firms.yaml`. El motor y el setfile del EA no se tocan.
- **Verificacion:** tests de FundingPips max(balance, equity), verificacion desde balance inicial, dias minimos y 1-Step al 3 %; baseline de produccion actualizado; suite completa.
- **Rollback:** tag `tl2-n1-pre`.

### 2026-11-26 · ENG-1 F5 · `DEFAULT_DB` configurable solo para la suite de tests
- **Autorización del operador (literal):** «apruebo todo» (2026-11-26, sesión de Claude Code),
  en respuesta a: aprobar ENG-F5 (`DEFAULT_DB` configurable; toca `config.py`) y ENG-F3 (`uv lock`).
- **Qué:** `config.DEFAULT_DB` lee `TRADINGLAB_DB` si existe; `telegram.STATE_PATH` y
  `task_health.STATE_FILE` van junto a `DEFAULT_DB`. `tests/conftest.py` define la variable con una
  carpeta temporal y quita `.env`/keyring a los tests sin marcador de red/credenciales.
- **Por qué:** cada `pytest` escribía alertas de test en `data/lab.db` real y las **enviaba por ntfy**
  (1.210 envíos entre el 2026-11-09 y el 2026-11-26, incluida una crítica "missing_sl BTCUSD"),
  además de filas de `data_freshness` y `telegram_state.json`
  (docs/engineering/AUDIT_FINDINGS.md, F0-08 y §6).
- **Sin cambio en producción:** sin la variable las rutas son idénticas
  (`tests/test_eng1_default_db.py::test_sin_variable_las_rutas_son_las_de_siempre`).
- **Mismo merge:** C-02 (reanudación de Dukascopy), C-04 (`register` no mezcla futuros y CFD),
  `uv.lock` con `arch` y `numba`, y 3 regresiones `xfail` del motor.
- **Baseline:** `lab propfund baseline --reason "ENG-1 F5 …"` antes del merge.
- **Vuelta atrás:** tag `tl2-eng1-f5-pre`.

### 2026-11-26 · ENG-1 F0-09 · Hash del forward del EA independiente de los finales de línea
- **Autorización del operador (literal):** «si a ambas preguntas» y «tienes permiso para todo»
  (2026-11-26, sesión de Claude Code), en respuesta a corregir F0-09.
- **Qué:** `ea_forward._sha256` y `_code_sha256` normalizan CRLF → LF antes de calcular el hash.
  `ensure_forward` acepta el hash congelado anterior `f490642ba7a1f71b` como alias de
  `71ee2cabe6aa9aef` (`LEGACY_CRITERIA_HASHES`); cualquier otro hash distinto sigue bloqueando.
- **Por qué:** el hash solo se reproducía si en la copia de Windows `US100_EA.mq5`,
  `US100_ExitManager.mqh`, `US100_RiskManager.mqh` y `ea_us100_engine.py` tenían CRLF. El día que git
  los reescribiera con LF, el forward fallaría con "criterios ya congelados" aunque el EA fuera el
  mismo (docs/engineering/AUDIT_FINDINGS.md §10).
- **Prueba:** `tests/test_eng1_ea_hash.py` reconstruye la copia del operador desde git y demuestra que
  el cálculo anterior da `f490642ba7a1f71b` y el nuevo `71ee2cabe6aa9aef` sobre el mismo contenido; el
  forward con el hash antiguo sigue funcionando y con otro hash sigue bloqueado. `test_ea_forward`
  pasa ahora también en CI (antes fallaba 5 tests).
- **Sin cambio en el forward en marcha:** la fila de `lifecycle_bots` no se reescribe.
- **Baseline:** `lab propfund baseline --reason "ENG-1 F0-09 …"` antes y después del merge
  (`ea_forward.py` está en el grupo protegido `ea_us100_ftmo1`).
- **Vuelta atrás:** tag `tl2-eng1-f009-pre`.

### 2026-11-27 · ENG-1 B-14 · Huecos de la TCA v2 (MT5 y paper)
- **Autorización del operador (literal):** «tienes permiso para todo» y «hacer» (2026-11-26/27,
  sesión de Claude Code), en respuesta a la lista de pendientes que incluía B-14.
- **Qué:** solo cambia lo que se **graba** en `tca`; el envío de órdenes (`request`, SL/TP, volumen,
  reintentos de filling) es idéntico.
  1. `execution/mt5.py`: sin `signal_price`, `slippage_bps` va nulo (antes medía tick → fill y se
     guardaba como decisión → fill). `ai_trader` y `forward_intraday` ya pasan `signal_price`.
  2. `execution/mt5.py`: `expected_cost_bps` nulo cuando el bróker no tiene coste supuesto (antes 0).
  3. `execution/mt5.py`: `bid`/`ask` del tick del envío (`submit_tick`), el mismo que `requested_price`.
  4. `execution/paper.py`: el paper graba `origin="paper"`; `slippage_measured` (T12) lo excluye,
     porque su slippage es el supuesto, no una medición.
- **No incluido (diseño aparte):** salidas SL/TP del servidor (reconciliar con `history_deals`) y
  `ts_utc` del fill (`deal.time_msc`). Ver docs/engineering/WORKER_REPORTS/B-costs.md, "Diseño de
  medición TCA".
- **Prueba:** `tests/test_eng1_b14_tca.py` (valor anterior frente al nuevo); `test_mt5_tca` y
  `test_mt5` actualizados con el valor anterior anotado.
- **Baseline:** `lab propfund baseline --reason "ENG-1 B-14 …"` antes y después del merge
  (`execution/mt5.py` está en el grupo protegido `ftmo_risk`).
- **Vuelta atrás:** tag `tl2-eng1-b14-pre`.
