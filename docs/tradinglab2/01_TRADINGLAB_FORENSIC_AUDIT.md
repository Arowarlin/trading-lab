# 01 · Auditoría forense de TradingLab (para TradingLab 2.0)

Fecha: 2026-11-19 · Base auditada: `feature/prop-fund-multifirm@262274d` (GitHub).
Nota: tu rama local tiene además `src/tradinglab/ea_lab/` (US500 y motor de sesiones), creada por
OpenCode y aún no subida; se cita por nombre, no se auditó línea a línea.

Leyenda: ✅ funcional · 🟡 parcial · ⚪ stub · 📄 documentado sin implementar · 🗄 obsoleto (acciones/ETF, en migración)

## 1. Inventario del motor de investigación

| Pieza | Archivo real | Estado | Qué hace / límite |
|---|---|---|---|
| Backtest diario long/short | `backtest.py::run` | ✅ | Bucle `iterrows` barra a barra, coste en bps sobre nocional. Lento para miles de estrategias. |
| Backtest intradía vectorizado | `intraday.py::backtest_intraday` | ✅ | Recibe una **serie objetivo** (−1..+1), coste = turnover × (spread horario + slippage + comisión). Rápido, pero **sin SL/TP/trailing intrabarra**. |
| Backtest por eventos | `intraday.py::run_event_backtest` | ✅ | Órdenes limitadas, stop/objetivo con reglas pesimistas (stop gana en empate, huecos al peor precio). Bucle Python. |
| Réplica del EA US100 | `ea_us100_engine.py::run` | ✅ 🔒 | Motor vela a vela fiel al `.mq5`. **Protegido.** |
| Familias de estrategia | `intraday.py::STRATEGIES` | ✅ | **14 familias escritas a mano** (orb, pullback, asian_rev, orb_ny, trend_intraday, overlap_breakout, range_reversal, london_pullback, session_trend, tokyo_breakout, session_hold, fix_flow, h1_orb, trend_daily_atr). |
| Familias de campaña | `campaign.py::FAMILIES` | ✅ | tsmom, st_reversal, vol_breakout, calendar, escaladas por densidad de barras. |
| Universo por coste | `campaign.py::cost_atr`, `COST_ATR_MAX = 0.05` | ✅ | Filtro coste/ATR ya existente: **base del filtro de coste de 2.0**. |
| Campaña registrada | `campaign.py::register_campaign/run_discovery/apply_plateau/run_holdout` | ✅ | `N_total` escrito **antes** de correr, hash de configuración, holdout sellado por hash, meseta y confirmación. **El esqueleto estadístico correcto para el motor genético.** |
| Optimizador | `optimize.py::run_optuna` | ✅ | Optuna (TPE), `walk_forward_returns`, registra `optimization_trials`. |
| Walk-forward | `walkforward.py::walk_forward` | ✅ | WF de **selección** sobre una matriz de variantes (elige la mejor en train, mide en test). Correcto. |
| Regímenes | `walkforward.py::regime_report/regime_gate` | ✅ | Gate exige año positivo en todos los años: estricto (ver §4). |
| PBO | `validation.py::cscv_pbo` | ✅ | CSCV (Bailey et al.) con 16 particiones. Correcto. |
| DSR | `stats.py::dsr_from_returns`, `dsr_local_global` | ✅ | Fórmula Bailey & López de Prado, local y global. Correcta. |
| Contador único del DSR | `learning.py::count_tests` | ✅ | Suma lecciones + Optuna + lecturas de holdout + `strategy_trials` (counted=1) + campañas (`N_total` completo) + incubados. |
| Registro de pruebas | `trials.py::record_trial`, tabla `strategy_trials` | ✅ | Fingerprint, outcome, `counted`, `sr_period`. |
| Presupuesto | `config/research_budget.yaml` | ✅ | 5 intentos por activo y semana ISO. |
| Holdout sellado | `learning.py` (`learning_holdout`, `holdout_reads`, `holdout_evaluations`) | ✅ | Una lectura por configuración (hash), cada lectura cuenta. |
| Ciclo de vida | `lifecycle.py::STATES` | ✅ | candidato → incubando → evaluado → promovible / rechazado / archivado. |
| Cartera | `portfolio.py::build_clusters/select_portfolio/simulate` | ✅ | Clústeres por correlación y simulación. |
| Indicadores | `indicators.py` | 🟡 | Solo **sma, ema, atr, zscore, rsi**. Faltan MACD, ADX, Bollinger, Stochastic, CCI, Donchian, Keltner, VWAP (el VWAP existe dentro del motor del EA, no como bloque). |
| Calidad de datos | `datacheck.py::check_frame/check_symbol` | ✅ | Índice, OHLC, calendario, saltos, ajuste, zona horaria, bid/ask. |
| Datos CFD | MT5 (`execution/mt5.py`, cachés parquet) | ✅ | Hasta ~2017 en M5 para US100/US500 (comprobado por OpenCode). |
| Datos futuros | `data/futures.py::ProjectXFuturesProvider` | ⚪ | **Stub**: no descarga barras. Sin intradía de futuros. |
| Costes CFD | `broker_costs.py`, `config/costs.yaml`, `propfund/costs.py` | ✅ | Spread medido por hora, comisión FTMO verificada, perfiles por cuenta. |
| Costes futuros | `propfund/costs.py::estimate_futures` | 🟡 | Modelo por contrato listo; **comisiones de firma sin verificar**. |
| Prop firms | `prop/` 🔒, `propfund/` | ✅ | Reglas FTMO, simulador Monte Carlo de challenge, 10 firmas, matriz de automatización. |
| Paralelismo | `concurrent.futures` en research/campaign/optimize/swing | 🟡 | Paralelismo por variante; sin cola persistente, sin reanudación ni límites de CPU/RAM globales. |
| Agentes IA | `agents/`, `llm.py`, `market_agents.py`, `ai_trader.py` 🔒 | 🟡 | TradingAgents/LLM orientados a tickers de acciones (en migración). `ai_trader` protegido. |
| Lecciones / hipótesis | `learning.py`, tabla `lessons` | ✅ | Hipótesis "proposed"; Qwen redacta, no ejecuta. |
| Exportación | — | 📄 | No existe exportador a MQL5/NinjaScript/Pine. |
| Consola | `web.py` + `webui/index.html` | ✅ | 19 vistas + Prop Fund; sin vista de descubrimiento. |

## 2. Por qué TradingLab no encuentra candidatos (evidencia)

1. **Generador pequeño y manual**: 14 familias intradía + 4 de campaña, rejillas de 2–8 valores. El espacio explorado es diminuto y concentrado en reglas conocidas (ORB, pullback), ya arbitradas.
2. **El motor rápido no modela salidas reales**: `backtest_intraday` trabaja con exposición objetivo; no hay SL/TP/trailing intrabarra, así que no puede representar la mayoría de sistemas "reales" (el EA usa SL estructural, BE y RR 3:1).
3. **Coste frente a movimiento**: equilibrio 0,14–1,61 bps vs coste calibrado 2,0–3,1 bps (Etapa 3). 0/84 variantes pasan.
4. **Contador único del DSR**: 1.060 pruebas acumuladas. Cualquier búsqueda masiva sin rediseño estadístico hace el DSR global inalcanzable (el EA real está en 0,634).
5. **Datos**: sin intradía de futuros; CFD de un solo bróker.
6. **Gates de producción aplicados también a la exploración**: `regime_gate` exige todos los años positivos; correcto para producción, demasiado temprano para descubrir.

## 3. Defectos técnicos detectados

| Hallazgo | Severidad | Nota |
|---|---|---|
| `InpSlBufAtr` del setfile se usa como distancia fija en precio en `ea_us100_engine` | Media (revisar) | El nombre sugiere múltiplo de ATR. Archivo protegido: solo documentar y confirmar contra el `.mq5`. |
| `backtest.py::run` usa `iterrows` | Baja | Correcto pero lento; no apto para cribado masivo. |
| Paralelismo sin límites globales | Media | Riesgo de saturar el 5950X mientras corren MT5, el EA y LM Studio. |

## 4. Revisión estadística

- DSR, PBO (CSCV) y walk-forward de selección: **correctos**.
- Holdout sellado de una lectura y campañas con `N_total` pre-registrado: **correctos y avanzados**; son la base de 2.0.
- Riesgo principal para 2.0: **contar cada individuo genético como una prueba independiente** inflaría el DSR global, y **no contarlos** sería data snooping. Solución en el doc 05: el GA se registra como **una campaña** con presupuesto declarado y N efectivo (clústeres de retornos), y la confirmación final ocurre en un **holdout sellado** con un N pequeño (finalistas).
