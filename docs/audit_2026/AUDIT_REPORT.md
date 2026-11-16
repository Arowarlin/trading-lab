# AUDIT_REPORT — TradingLab, auditoría técnica y funcional

- Commit auditado: `9d7c5ad` (master, 2026-11-14).
- Alcance: 138 módulos Python, unos 58 000 líneas en `src/tradinglab`, 136 ficheros de test con unas 1040 funciones de test, `config/`, `mql5/` y `docs/`.
- Método: lectura del código de los motores críticos y comprobaciones numéricas aisladas con datos sintéticos. No se ejecutó ninguna campaña, no se sumó nada al contador DSR y no se tocó código fuente.
- Límite importante: la base de datos, los datos de mercado y los resultados forward viven en el PC del operador (`E:\trading-lab`), no en el repo. Todo resultado de trading que no esté en el repo se marca **Sin datos verificables**.

## 1. Diagnóstico en una frase

Por proceso, TradingLab es un laboratorio semiprofesional: pre-registro, holdout sellado, contador único de pruebas, cementerio de estrategias, guardián y kill-switch independientes. Pero **la métrica central con la que decide (el DSR) está mal calculada**, y hoy no tiene ninguna estrategia con ventaja demostrada fuera de muestra.

## 2. Hallazgos críticos (P0)

| ID | Hallazgo | Evidencia | Impacto |
|---|---|---|---|
| A1 | **El DSR se alimenta con Sharpe anualizado** y `n_obs` en días. La fórmula de Bailey y López de Prado exige un Sharpe por periodo coherente con `n_obs`. | `research.py:513`, `optimize.py:219/310`, `ea_us100.py:375` y `campaign.py:2540` pasan `metrics["sharpe"]` o `_sharpe()` con `×√252`. | La z sale inflada unas 10 a 16 veces y el DSR se vuelve casi binario (0 o 1). Prueba sintética: la mejor de 1040 estrategias **sin edge** obtiene DSR = 0,9999998 (el valor correcto es 0,74). Todo DSR histórico del lab, incluido el "DSR 1,0" del EA, **no es evidencia**. |
| A2 | `campaign.py` (etapa de confirmación en holdout) inventa la dispersión entre pruebas: `sr_std = |SR|/√bars`. | `campaign.py:2539` | El SR0 del DSR no corresponde a la dispersión real de las pruebas de la campaña. |
| A3 | El PBO de confirmación de campaña **siempre es None**: se llama a `returns_matrix({"cell": …})` con una sola variante, la función devuelve una tupla y `cscv_pbo` lanza una excepción que se traga en silencio. | `campaign.py:2548-2554` | La métrica aparece vacía sin explicar por qué. Con una sola celda, el PBO no aplica y debe decirlo. |
| A4 | El guardián MQL5 y `account_daily_stop` no incluyen los magics del EA US100 (93010001 y 93020001). | `guardian.py:244-268` solo lee `intraday_forward.yaml` y el carril IA. | Con el guardián en CLOSE, el EA puede llevar la cuenta FTMO demo a romper el límite del 5 % sin que nada lo frene. |
| A5 | Hay dos bots forward **activados** con Sharpe de backtest −4,42 (EURUSD london_pullback) y −4,63 (USDJPY tokyo_breakout). | `config/intraday_forward.yaml` | Consumen presupuesto de riesgo diario de la cuenta compartida, sin ninguna hipótesis que justifique esperar algo positivo. |

## 3. Hallazgos importantes (P1)

| ID | Hallazgo | Evidencia |
|---|---|---|
| B1 | Ningún motor modela **swap ni financiación**, y `us100-trend-d1` y el carril swing mantienen CFD varios días. | `grep swap` en backtest, intradía y campaña: 0 resultados. |
| B2 | En el motor de eventos, **las entradas limitadas y los objetivos no pagan spread**. Con barras BID, una compra limitada se llena cuando el ASK toca el nivel, no el BID. | Docstring de `intraday.py:465`. |
| B3 | `backtest.py` atribuye a cada operación solo la comisión de salida, nunca la de entrada. Además cuenta cada reducción parcial como una "operación", lo que con el objetivo de volatilidad infla `num_trades` y distorsiona el PF y la expectativa. | `backtest.py:140-160` |
| B4 | Hay 37 llamadas a `datetime.now()` o `date.today()` sin zona horaria (f13, lifecycle, orchestrator, costs y otros). El PC está en UTC−4 todo el año, mientras Nueva York cambia de horario. | grep |
| B5 | Optuna maximiza el Sharpe de los retornos walk-forward OOS. Una vez se elige el mejor trial, ese "OOS" deja de ser fuera de muestra, y el informe no lo distingue. | `optimize.py:169-195` |
| B6 | La réplica del EA y el carril IA tienen el universo y las reglas concentrados en **US100**: EA, us100-trend-d1, scalping IA e intradía IA. No hay ningún límite de riesgo por símbolo. | `config/*.yaml` |

## 4. Lo que está bien hecho (conservar)

- `validation.cscv_pbo`: implementación correcta. Bloques contiguos, empates promediados, logit, pendiente de degradación y uso de sumas por bloque (rápido).
- `walkforward.walk_forward`: selección solo con datos de entrenamiento y test concatenado, sin fugas.
- `ea_us100_engine.py`: modelo de ejecución conservador. Entrada en el open siguiente, LONG al ASK, SL antes que TP en la misma barra, gap al peor precio y slippage en entrada y stop.
- `run_event_backtest`: SL prioritario, gaps al peor precio, guarda de sesión que falla en cerrado, rollover y corte de viernes.
- Contador único de pruebas (`learning.count_tests`), con las campañas sumando su N completo al registrarse.
- Holdout sellado con registro de lecturas, cementerio de estrategias, `lab doctor` y hash de F13.
- Seguridad operativa: lease de ejecución, keyring, guardián MQL5 independiente, kill-switch y la separación entre LLM y código (el LLM no calcula SL, TP ni lote).

## 5. Contradicciones entre documentación y código

1. `docs/ea_us100_ftmo1.md` presenta el DSR 1,0 como un filtro superado, pero el valor viene del error A1.
2. En mi revisión anterior dije que el DSR del EA "solo cuenta 8 variantes". Es incorrecto: `ea_us100.py:374` suma `count_tests` (unas 1040 pruebas). El problema real es el de unidades.
3. `intraday_forward.yaml` dice "no es una validación", pero los bots están en `enabled: true` sobre la misma cuenta que el EA y el carril IA.
4. `PLAN.md` y `estado.md` describen el PBO de confirmación de campaña como parte del protocolo, pero nunca se calcula (A3).

## 6. Inventario de funcionalidades

| Área | Estado | Evidencia | Problemas |
|---|---|---|---|
| Datos diarios y datacheck | Implementado y probado | tests y `datacheck.py` | — |
| Backtest vectorial diario | Implementado | `backtest.py` | B1, B3 |
| Motor de eventos intradía | Implementado y conservador | `intraday.py` | B2 |
| Réplica del EA US100 | Implementado; coincide con el tester de MT5 (PF 1,45 frente a 1,50) | `docs/ea_us100_ftmo1.md` | Sin OOS limpio |
| PBO/CSCV | Correcto | lectura y revisión | A3 en campaña |
| DSR | **Incorrecto** | prueba numérica | A1, A2 |
| Walk-forward | Correcto | lectura | B5 |
| Optuna | Implementado | `optimize.py` | B5 |
| Campañas pre-registradas | Implementado | `campaign.py` (2833 líneas) | A2, A3 |
| Carril IA discrecional | Operando en demo | config y tareas | Muestra mínima; resultados Sin datos verificables |
| Destilación y replay | Implementado | `ai_distill.py`, `ai_replay.py` | Sin evidencia de bots destilados |
| Guardián y kill-switch | Operando | `guardian.py`, `.mq5` | A4 |
| F13 en Alpaca | Operando (piloto) | `f13.md` | Es una prueba operativa, no de edge |
| Observabilidad | Vector, Healthchecks, Telegram | docs | Crons de Healthchecks sin aplicar |
