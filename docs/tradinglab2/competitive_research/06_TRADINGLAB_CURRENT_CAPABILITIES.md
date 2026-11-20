# 06 · Capacidades reales de TradingLab (auditoría)

Auditado: `origin/feature/prop-fund-multifirm` = **5cc0219 (tag tl2-f7b)**, 2026-11-20.
Paquete `src/tradinglab/discovery/`: 23 módulos, ~9.750 líneas; 22 archivos `tests/test_discovery_*`.

## Contradicciones con el historial

| Historial | Realidad en GitHub | Acción |
|---|---|---|
| Fase 7c cerrada (fix de instrumento, `preflight`, `last_error`, diagnostics, conftest) | **No está en GitHub**: el remoto termina en tl2-f7b. 7c existe solo en el PC (sin commit al cierre del último informe) | Confirmar commit `tl2-f7c` local y hacer push |
| Fase 7d propuesta | No implementada | Pendiente |
| Gate de regímenes funcional | `robustness._regime` llama a `regime_report(daily, years=REQUIRED_REGIMES)` con años fijos (2018/2020/2022 según el informe de campaña) que no existen en M5 real ⇒ **nivel 4 imposible para cualquier estrategia** | Corrección P0 (7d) |
| Primera campaña real ejecutada | Vive en `data/discovery.db` local (ignorado por git); no auditable desde GitHub | Informe en `reports/` |

## Matriz de capacidades

| Capacidad | Estado | Evidencia |
|---|---|---|
| Calidad de datos (granularidad, pausas en hora de sesión, festivos, hash por rango) | 1 · Implementada | `data_quality.py`, `data_sources.py`, tests |
| Datos M5 reales | 2 · Parcial | Solo US100 (caché del EA) y US500 desde 2021-09; resto de CFD sin descargar; futuros sin datos |
| DSL / AST con validación semántica | 1 | `dsl.py` |
| Bloques | 2 · Parcial | ~30 en `blocks.py` (tendencia, osciladores, volatilidad, estructura, patrones, régimen); sin calendario, sin intermercado, sin niveles de días previos como "sweep" |
| Compilador sin look-ahead (HTF cerrado, sesión local) | 1 | `compiler.py` + test de look-ahead por bloque |
| Simetría long/short | 4 · No existe | Finalista 258 con corto anómalo |
| Motor rápido con paridad exacta | 1 | `fastbt.py`, paridad 0,0, test de sesgo |
| Cola, databank, reanudación | 1 | `jobs.py`, `databank.py` (data/discovery.db) |
| Campañas, n_total inmutable, tramos sellados, conteo en DSR global | 1 | `campaigns.py`, trigger SQLite, `learning.count_tests` |
| NSGA-II, operadores, genealogía, nicho | 1 | `nsga2.py`, `genetic.py`, `engine.py` |
| Reintento de hijos inválidos/duplicados | 4 | 45 % del presupuesto perdido en la campaña real |
| Fitness con WF anclado interno y coste en R | 1 | `fitness.py` |
| Optimizer de meseta (sin cambiar parámetros) | 1 | `optimizer.py` |
| Retester (coste/slippage) y transfer informativo | 1 | `retester.py` |
| Robustness: WF, PBO (≥ 8), MC de operaciones, bootstrap, challenge MC, hora×día | 1 | `robustness.py` |
| Regímenes | 2 · Con bug | Ver contradicciones |
| Test contra azar en OOS-2 (requisito nivel 4) | 1 | `robustness.random_baseline`, `levels.confirm` |
| Noise Test / precio perturbado | 4 | — |
| Entradas/salidas retrasadas | 4 | — |
| MC de ejecución (saltar operaciones, spread/slippage aleatorio) | 4 | — |
| Niveles y veredictos deterministas | 1 | `levels.py` |
| Colecciones / etiquetas / familias / detección de clones entre campañas | 3 · Base técnica (hash, correlación) sin funcionalidad | `databank.py` |
| Consola Discovery Lab | 4 | `web.py` sin rutas `/api/discovery` |
| Agentes IA de hipótesis | 4 | No hay `discovery/agents` |
| Exportación MQL5 | 4 | No hay `discovery/export` |
| Cartera de estrategias de discovery | 3 | `portfolio.py` legado, no conectado |
| Prop firm: reglas por cuenta (FTMO, FundingPips) + MC | 1 | `propfund/`, `prop/simulator.py` (protegido) |

## Fortalezas reales (no tocar)

Contador global único, OOS-2 de una lectura, test contra el azar en OOS-2, paridad exacta con los motores
existentes, reproducibilidad 100 % (comprobada en la campaña real), tests de ruido sintético.
