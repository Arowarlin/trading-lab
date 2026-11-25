# Cambios en producción

Registro obligatorio de los cambios en componentes de producción: EA
`us100-ftmo1`, carril forward FTMO, riesgo FTMO, `ai_trader`, Prop Fund y
`ea_lab`. Cada entrada indica la autorización del operador, qué cambió y cómo se
comprueba. El baseline de hashes vive en
`config/propfund/protected_manifest.json` y se consulta con
`lab propfund verify`; se reescribe con `lab propfund baseline --reason "..."`.

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
