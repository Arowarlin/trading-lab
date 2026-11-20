# 07 · Discovery Lab: databank, lotes, robustez, IA, consola, exportación y fondeo

## 1. Strategy Databank (SQLite, mismas `data/lab.db`, tablas nuevas `disc_*`)

| Tabla | Campos clave |
|---|---|
| `disc_campaigns` | id, created_at, instrument, timeframe, template, engine_profile, config_json, config_hash, is_start/is_end, oos1_start/oos1_end, oos2_start/oos2_end, dataset_hash, n_total (declarado antes), n_evaluated, n_effective, status (registered/running/done/cancelled), engine_version |
| `disc_strategies` | id, campaign_id, strategy_hash (UNIQUE por campaña), dsl_json, family, instrument, timeframe, session, generation, origin (`random`/`template`/`ai_hypothesis`/`protected_reference`), level (1–4), status, reject_reason, created_at |
| `disc_lineage` | strategy_id, parent_a, parent_b, operator, param_diff_json, generation |
| `disc_evaluations` | strategy_id, segment (`is_fold_k`/`is_full`/`oos1`/`oos2`/`retest:<nombre>`), cost_profile, metrics_json, trades_count, returns_blob (serie diaria R comprimida), computed_at |
| `disc_validations` | strategy_id, test (`wf_matrix`/`mc_trades`/`bootstrap`/`cost_stress`/`param_stability`/`pbo`/`dsr_confirm`/`prop_mc:<cuenta>`), result_json, passed, computed_at |
| `disc_jobs` | id, campaign_id, kind, payload_json, state (queued/running/done/failed/cancelled), attempts, error, started_at, finished_at |

Estados (mapa a niveles): Generated, Backtesting (nivel 1) → Experimental, Promising, Weak Candidate (nivel 2)
→ Validation, Robust (nivel 3) → Paper Trading, Approved (nivel 4); Rejected y Archived en cualquier nivel.
**Nada se borra.** Duplicados: mismo `strategy_hash` → se reutiliza la evaluación; equivalencia
estructural (AST canonicalizado: orden de `and`/`or`, umbrales redundantes) antes de evaluar.
Al llegar a Paper Trading se crea el registro en `lifecycle` (candidato) **mediante su API**, sin editar `lifecycle.py`.

## 2. Batch backtesting y cola (`discovery/jobs.py`)

Cola en `disc_jobs`, workers del doc 05 §7, reanudación (los `running` huérfanos vuelven a `queued` al
arrancar), cancelación limpia (`lab discovery cancel <campaña>`), errores guardados por job,
**reproducibilidad**: semilla de la campaña + hash de dataset + versión de motor → mismo resultado.

## 3. Optimizer y Retester

- **Optimizer** (`discovery/optimizer.py`): reutiliza Optuna **solo sobre IS**; además informa la
  **meseta** (estabilidad en el vecindario ±1 paso, reutilizando la idea de `campaign.apply_plateau`).
  Elige el centro de la meseta, no el pico. Nunca toca OOS-1/OOS-2.
- **Retester** (`discovery/retester.py`): re-evalúa una estrategia **congelada** (sin reoptimizar) en otros
  años, costes ×1,5/×2, slippage +1/+2, otras sesiones o volatilidades, otros contratos. Instrumentos
  relacionados se marcan `transfer` y nunca cuentan como validación original.

## 4. Robustness Lab (`discovery/robustness.py`, reutiliza lo existente)

| Prueba | Implementación |
|---|---|
| Walk-forward y matriz WF | `walkforward.walk_forward` + matriz de longitudes train/test |
| DSR | `stats.dsr_from_returns` (exploración: N efectivo; confirmación: N finalistas; global: `count_tests`) |
| PBO | `validation.cscv_pbo` sobre la matriz de la frontera de Pareto |
| Monte Carlo de operaciones | reordenación y remuestreo de R (nuevo, determinista con semilla) |
| Bootstrap | bloques de días (nuevo) |
| Estabilidad de parámetros | meseta ±1 paso |
| Estrés de coste/slippage | Retester |
| Regímenes | `walkforward.regime_report` (informe en nivel 2; gate solo en nivel 3–4) |
| Challenge de fondeo | `prop/simulator.py` 🔒 con las reglas de cada cuenta de `propfund` |

## 5. Niveles de madurez

| Nivel | Entra si | Puede |
|---|---|---|
| 1 Exploration | AST válido | Evaluarse en IS |
| 2 Experimental | Factible, frontera de Pareto IS, expectativa neta > 0 | Retester, informe de regímenes |
| 3 Validation | Finalista (doc 05 §5), expectativa IS completa > 0 y estrés de coste ×1,5 > 0 | Robustness Lab completo, **una** lectura del holdout |
| 4 Production/Prop | Nivel 3 + OOS-2 > 0, DSR de confirmación ≥ 0,90, PBO ≤ 0,30, WF ok, regímenes ok, slippage +2 > 0, `test_vs_random_oos2` ≥ 95 y challenge MC aceptable (con al menos `min_trades_oos2` operaciones en OOS-2) | Matriz por firma, forward demo, exportación |

El test contra entradas aleatorias sobre IS+OOS-1 es **informativo** (`test_vs_random_insample`): no decide nivel ni veredicto. El requisito es el de OOS-2 (`test_vs_random_oos2`), calculado con la única lectura del holdout.

Ningún nivel habilita trading real. Expectativa neta negativa → nunca "rentable".

## 6. Agentes IA (LM Studio local, `discovery/agents/`)

Ocho roles (Research, Hypothesis, Strategy Architect, Evolution Advisor, Strategy Analyst, Failure Analyst,
Validation Analyst, Portfolio Analyst) con **contratos JSON** validados por pydantic:

- Hypothesis/Architect: devuelven un AST del doc 04 + fundamento + criterio de invalidación → entran como
  `origin = ai_hypothesis` en la población inicial **de una campaña nueva** (nunca en una en curso).
- Analysts: leen métricas ya calculadas del databank y escriben **texto**; no tienen herramientas de escritura
  sobre métricas, datos ni estados.
- Prohibido (por diseño y test): inventar métricas, cambiar resultados, aprobar estrategias, leer OOS-2,
  ocultar fallidas. El cambio de nivel lo hace solo código determinista.
- Integración con `ai_trader`: ninguna dependencia directa; si se comparte el cliente LLM se **importa**
  `llm.py` sin modificarlo. Cola LLM con un único worker para no competir con `ai_trader` por la GPU.

## 7. Consola: vista nueva "Discovery Lab"

Endpoints GET nuevos en `web.py` (`/api/discovery/summary|campaigns|strategies|strategy|lineage|robustness|portfolio`)
y POST con CSRF solo para registrar/lanzar/cancelar campañas. Pantallas: A Dashboard, B Builder (formulario
de campaña), C Evolución (generaciones, frontera, diversidad), D Databank (tabla filtrable), E Detalle
(reglas, equity, drawdown, distribución, mensual, sesión, régimen, costes, sensibilidad, genealogía,
validaciones), F Retester/Optimizer, G Robustness, H Portfolio. Tema v4 Quantum. **Cada control conectado a
una función real o marcado "Próximamente".**

## 8. Portfolio Builder

Reutiliza `portfolio.build_clusters` y `simulate`; añade exposición por subyacente con
`propfund/risk.exposure_by_underlying` y drawdown conjunto. Solo combina estrategias de nivel ≥ 3.

## 9. Exportación (`discovery/export/`)

Exportador **MQL5 primero** (FTMO/MT5). Cada exportador declara los bloques soportados y rechaza el resto;
genera el `.mq5` y un CSV de señales esperadas sobre un tramo fijo para comparar con el Strategy Tester
(comparación manual documentada en el informe). NinjaScript y Pine: fase posterior. Nunca activa trading.

## 10. Prop Firm Intelligence

Reutiliza `propfund` (firmas, cuentas, costes por cuenta, matriz de automatización) y `prop/simulator.py`.
Para cada estrategia de nivel 4: matriz estrategia × cuenta con expectativa neta, coste/R, P(pasar),
P(romper) y si la firma permite automatizarla.
