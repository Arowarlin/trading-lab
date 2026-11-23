# 10 · Prompt de ejecución para OpenCode — TradingLab 2.0 (Discovery Lab)

**Modelo:** DeepSeek V4.1 Flash (OpenCode Go).
**Cuándo usarlo:** cuando las fases 0–5b de la migración CFD/futuros estén hechas. Sustituye la FASE 5c.
**Cómo usarlo:** abre una sesión **nueva** de OpenCode en `E:\trading-lab` y pega **una fase cada vez**:
primero el BLOQUE COMÚN y después la fase. Cuando la fase termine, pégame aquí su resumen antes de
pasar a la siguiente.

> Por qué fase a fase: DeepSeek V4.1 Flash es rápido y barato, pero pierde precisión con contextos
> largos. Cada fase cabe en una sesión, tiene archivos concretos y termina en un punto de parada.

---

## BLOQUE COMÚN (pegarlo siempre antes de cada fase)

```text
Eres el ingeniero de TradingLab (E:\trading-lab, Windows, PowerShell, Python en .venv).
Responde en español. Trabaja solo dentro del repo.

LEE PRIMERO: AGENTS.md, docs/tradinglab2/03_TRADINGLAB_PROTECTED_COMPONENTS.md y el doc de
docs/tradinglab2/ que indique la fase. No leas otros docs salvo que la fase lo pida.

REGLAS DURAS (si una tarea las contradice, PARA y pregunta):
1. No modifiques ningún archivo listado en config/propfund/protected_manifest.json
   (incluye src/tradinglab/intraday.py, ea_us100_engine.py, prop/**, ai_trader*.py, execution/mt5.py).
   Puedes IMPORTARLOS, nunca editarlos.
2. Todo el código nuevo va en src/tradinglab/discovery/ , config/discovery/ y tests/test_discovery_*.py.
   Solo se tocan archivos existentes cuando la fase lo diga explícitamente (cli.py, web.py, webui/index.html, pyproject.toml).
3. No ejecutes `lab campaign run`, `lab research*`, ni `lab discovery run` con datos reales: suman al DSR.
   Para probar usa datos sintéticos generados en los tests.
4. No borres archivos, no hagas git push, no reescribas historial, no toques .env.
5. No inventes métricas, precios, comisiones ni resultados. Si falta un dato escribe "Sin datos".
6. No uses datos futuros: toda señal se calcula con barras cerradas y se ejecuta en el open siguiente.
7. No añadas dependencias salvo las que la fase autorice.
8. Antes de escribir código, muestra un PLAN corto (archivos y funciones) y ESPERA mi "OK PLAN".
9. Nunca calcules rendimiento (expectativa, PF, percentil de deriva, Monte Carlo,
   perturbaciones) antes de register+approve. Si ocurre, se anota en el contador
   con `lab learning record-informal --n N --reason "..." --approved-by-operator`.

AL TERMINAR CADA FASE (en este orden):
  .\.venv\Scripts\Activate.ps1
  ruff check src/tradinglab/discovery tests
  pytest -q --basetemp E:\pytest-tmp
  lab propfund verify
Si todo está verde: git add de los archivos de la fase, commit pequeño con mensaje
"tl2: fase N - <resumen>" y tag `tl2-fN`. Si algo falla, NO hagas commit: arregla o explícame.
Termina con un resumen en formato: Hecho / 1..N / Aviso / Siguiente. Después PARA.
```

---

## FASE 0 — Línea base y aislamiento

```text
FASE 0. Lee docs/tradinglab2/08_TRADINGLAB_IMPLEMENTATION_ROADMAP.md (fila 0) y 09 (sección 2).

1. Ejecuta pytest completo y anota cuántos pasan/omiten (línea base). No cambies nada aún.
2. Crea src/tradinglab/discovery/__init__.py (solo docstring y __version__ = "0.1.0").
3. Crea config/discovery/engine.yaml con: workers: 12, ram_limit_gb: 8, profiles small/medium/large
   (population, generations), mutation_rate 0.3, crossover_rate 0.6, elite_frac 0.1, max_nodes 12,
   max_depth 4, min_trades_is 100, min_trades_fold 15, folds 4, finalists_max 5, corr_cluster 0.7.
4. Crea src/tradinglab/discovery/config.py que carga y valida ese YAML con pydantic.
5. Crea tests/test_discovery_isolation.py:
   - importar tradinglab.discovery no importa tradinglab.execution ni funciones submit_market/close_position/modify_position
     (recorre sys.modules tras el import y busca con ast en los .py de discovery/);
   - ningún .py de discovery/ escribe a archivos protegidos (comprueba que no aparecen sus rutas como literales).
6. Tests de config.py.
Punto de parada: resumen + tag tl2-f0.
```

## FASE 1 — Calidad de datos CFD

```text
FASE 1. Lee docs/tradinglab2/06_TRADINGLAB_DATA_AND_COST_AUDIT.md.

1. Crea src/tradinglab/discovery/data_quality.py:
   - reutiliza tradinglab.datacheck.check_frame (impórtalo, no lo copies);
   - añade: duplicados, OHLC inválido, huecos dentro de sesión, cobertura de tres tramos dados
     (is/oos1/oos2 como fechas), hash sha256 del dataset (de los bytes de las columnas OHLC + índice);
   - devuelve un dataclass QualityReport(status ok/warn/fail, issues, dataset_hash, rows, start, end).
2. Para cargar barras usa la función de caché de MT5 que ya usa intraday.py (búscala con grep, impórtala).
   Si no hay caché local del símbolo → status "fail" con "Sin datos". No descargues nada.
3. Añade a cli.py un sub-app `discovery` con el comando `lab discovery data-check SYMBOL --tf M5`
   que imprime el informe (rich table). Solo AÑADE líneas en cli.py, no cambies nada existente.
4. Tests con DataFrames sintéticos (duplicados, high<low, huecos, cobertura insuficiente, hash estable).
Punto de parada. Luego ejecuta tú `lab discovery data-check US100.cash --tf M5` y pega la salida en el resumen.
```

## FASE 2 — DSL, bloques y compilador

```text
FASE 2. Lee docs/tradinglab2/04_TRADINGLAB_STRATEGY_BUILDER_ARCHITECTURE.md (secciones 1, 2, 3, 5).

1. src/tradinglab/discovery/dsl.py: modelos pydantic del AST (Strategy, nodos lógicos, comparación,
   cruce, indicador, nivel, precio, patrón, régimen, HTF, Exit, Session, Limits). Funciones:
   validate(strategy) -> list[str] (vacía = válida), canonical_json(strategy), strategy_hash(strategy),
   count_nodes(strategy), depth(strategy).
2. src/tradinglab/discovery/indicators_ext.py: macd, adx, bollinger, stochastic, cci, donchian, keltner,
   vwap_session, realized_vol, atr_pct_rank, range_compression, swing_high/low (con confirmación
   desplazada `right` barras). Importa sma/ema/atr/rsi/zscore de tradinglab.indicators.
3. src/tradinglab/discovery/blocks.py: catálogo BLOCKS {nombre: BlockSpec(params con rango y paso,
   output "float"|"bool", warmup(params))}.
4. src/tradinglab/discovery/compiler.py: compile(strategy, bars) -> Signals(long_entry, short_entry, valid_from)
   con numpy, caché de indicadores por (bloque, params), HTF alineado a la última barra HTF CERRADA,
   señales False fuera de sesión o antes del warmup.
5. config/discovery/templates/: 3 plantillas YAML (ny_open_vol_filter, asia_range_reversion,
   session_breakout_htf).
6. Tests: test_discovery_dsl.py y test_discovery_lookahead.py. El test de look-ahead, para CADA bloque
   de BLOCKS: calcula salida, altera aleatoriamente las barras > t, recalcula, y exige igualdad en ≤ t.
Punto de parada.
```

## FASE 3 — Motor rápido y paridad (la más delicada)

```text
FASE 3. Lee docs/tradinglab2/04 (sección 4). Lee el código de tradinglab.intraday.backtest_intraday
y run_event_backtest SOLO para entender su semántica; NO los edites.

Dependencia autorizada: numba (añádela en pyproject.toml como extra opcional `discovery = ["numba>=0.60"]`
e instálala con pip install -e ".[discovery]"). Debe existir fallback en Python puro con resultado idéntico.

1. src/tradinglab/discovery/fastbt.py:
   - run(signals, bars, exit_spec, cost, limits) -> FastResult(trades, daily_r, metrics);
   - entrada en open de t+1; long paga spread; SL y TP en la misma barra -> SL; hueco -> peor precio;
     BE/trailing desde la barra siguiente; flat_at; time_exit_bars; max_trades_per_day; cooldown;
   - núcleo @njit si numba está disponible, misma función en Python si no;
   - costes: usa tradinglab.propfund.costs (CFD vs futuros), nunca mezcles.
2. src/tradinglab/discovery/metrics.py: expectativa R, PF, win rate, max DD en R, nº ops, Sharpe diario,
   concentración (mayor op / beneficio total), sensibilidad +1 punto.
3. tests/test_discovery_parity.py:
   a) señales -> serie objetivo -> backtest_intraday vs fastbt sin SL/TP: retornos iguales (tol 1e-9);
   b) fixtures sintéticos con huecos, empates SL/TP y salida forzada: operaciones iguales a run_event_backtest;
   c) numba vs Python: resultados idénticos.
4. scripts/bench_fastbt.py (no lo registres como tarea): mide backtests/minuto con datos sintéticos de
   3 años M5 y 12 workers. Imprime el número medido; no lo inventes.
Si la paridad no se consigue: PARA y explícame la diferencia exacta (no ajustes tolerancias).
Punto de parada.
```

## FASE 4 — Databank y cola de trabajos

```text
FASE 4. Lee docs/tradinglab2/07 (secciones 1 y 2).

1. src/tradinglab/discovery/databank.py: crea (si no existen) las tablas disc_campaigns, disc_strategies,
   disc_lineage, disc_evaluations, disc_validations, disc_jobs en data/lab.db usando la conexión de
   tradinglab.db (impórtala). Solo CREATE TABLE IF NOT EXISTS; no alteres tablas existentes.
   API: add_strategy (dedupe por strategy_hash), add_evaluation, add_validation, set_status,
   get_strategy, list_strategies(filtros), lineage(strategy_id). Nada se borra (estado "archived").
2. src/tradinglab/discovery/jobs.py: cola en disc_jobs; run_queue(campaign_id, workers) con
   ProcessPoolExecutor (max_workers del config, prioridad below normal en Windows con psutil si existe),
   reanudación (running huérfanos -> queued), cancelación, error guardado por job, semilla reproducible.
3. Tests con una base SQLite temporal (tmp_path): dedupe, reanudación tras simular caída, cancelación.
Punto de parada.
```

## FASE 5 — Campañas y segmentos sellados

```text
FASE 5. Lee docs/tradinglab2/05 (sección 1) y el código de tradinglab.campaign.register_campaign,
run_holdout y tradinglab.learning.count_tests (solo lectura).

1. src/tradinglab/discovery/campaigns.py:
   - register(instrument, tf, template, profile, segments{is, oos1, oos2}, seed) -> campaign_id:
     calcula n_total = population*generations ANTES de correr, guarda config_hash y dataset_hash,
     estado "registered";
   - load_segment(campaign_id, "is") devuelve SOLO barras IS; "oos1" solo si la campaña está "done";
     "oos2" solo vía read_holdout(strategy_id) que permite UNA lectura por estrategia y la registra;
   - integra con count_tests: si count_tests no puede leer disc_campaigns sin editar learning.py,
     NO edites learning.py: crea una función discovery.campaigns.total_tests() y explícame en el resumen
     cómo unificarlo (decisión mía).
2. lab discovery register ... (CLI) con --dry-run por defecto; sin --approved-by-operator no cuenta para el DSR.
3. Tests test_discovery_segments.py y test_discovery_count.py.
Punto de parada.
```

## FASE 6 — NSGA-II, operadores y genealogía

```text
FASE 6. Lee docs/tradinglab2/05 (secciones 2–6).

1. discovery/nsga2.py: fast_non_dominated_sort, crowding_distance, select (torneo binario por rango y crowding).
2. discovery/genetic.py: los 8 operadores de la tabla del doc 05; todos devuelven AST válidos o None;
   inicialización desde plantillas + aleatoria (profundidad ≤ 2).
3. discovery/fitness.py: 5 objetivos con walk-forward interno anclado de 4 pliegues SOLO en IS;
   restricciones duras; nicho por correlación > 0.9; effective_trials por clústeres (umbral 0.7).
4. discovery/engine.py: bucle generacional que usa jobs.py, guarda disc_lineage por individuo,
   se detiene por evaluaciones o tiempo, y al final aplica la regla de finalistas (doc 05 §5).
5. lab discovery run CAMPAIGN_ID: rechaza ejecutar si la campaña no está "registered" o si no hay
   --approved-by-operator; con --synthetic usa un paseo aleatorio (para pruebas).
6. Tests test_discovery_nsga2.py, test_discovery_genetic.py y la PRUEBA DE RUIDO de docs/tradinglab2/09 §3:
   en un paseo aleatorio no debe quedar ningún finalista que pase la confirmación.
Punto de parada.
```

## FASE 7 — Optimizer, Retester, Robustness Lab y niveles

```text
FASE 7. Lee docs/tradinglab2/07 (secciones 3, 4, 5).
Reutiliza (importa) stats.dsr_from_returns, validation.cscv_pbo, walkforward.walk_forward,
walkforward.regime_report y prop.simulator. No copies su lógica.

1. discovery/optimizer.py (Optuna solo IS + meseta ±1 paso), discovery/retester.py (estrategia congelada),
   discovery/robustness.py (WF matrix, MC operaciones, bootstrap por bloques, estrés coste, PBO, DSR x3),
   discovery/levels.py (reglas deterministas de niveles 1–4; la IA nunca cambia niveles).
2. lab discovery show STRATEGY_ID, lab discovery retest, lab discovery robustness.
3. test_discovery_levels.py: nivel 4 imposible sin DSR confirmación ≥ 0.90 y PBO ≤ 0.30.
Punto de parada. AQUÍ TERMINA EL MVP. No continúes a la fase 8 sin mi aprobación.
```

## FASES 8–12 (después del MVP, una por sesión)

```text
FASE 8 Consola: rutas GET /api/discovery/* en web.py y vista "Discovery Lab" en webui/index.html con
el tema v4 Quantum (doc 07 §7). Cada botón usa una API real o muestra "Próximamente".
FASE 9 Agentes IA: discovery/agents/ con contratos JSON pydantic, LM Studio vía tradinglab.llm (importado),
un solo worker LLM; los agentes solo leen métricas y proponen AST para campañas NUEVAS (doc 07 §6).
FASE 10 Futuros: discovery/data_databento.py, clave en keyring DATABENTO_API_KEY, estimación de coste
antes de descargar y espera mi "OK DESCARGA"; contrato continuo + tabla de rolls (doc 06 §2).
FASE 11 Cartera y fondeo: matriz estrategia × cuenta con propfund y prop.simulator (doc 07 §8 y §10).
FASE 12 Exportación MQL5: discovery/export/mql5.py, solo bloques soportados, CSV de señales esperadas.
```

---

## Frases de aprobación que entiende el flujo

| Frase | Efecto |
|---|---|
| `OK PLAN` | Puede escribir el código de la fase |
| `OK COMMIT` | Puede hacer commit y tag si dudó |
| `APROBADO CAMPAÑA <id>` | Puede ejecutar `lab discovery run <id> --approved-by-operator` (suma al DSR) |
| `OK DESCARGA` | Puede descargar de Databento tras mostrar el coste |
| `ROLLBACK FASE N` | `git reset --hard tl2-f(N-1)` (solo local) |
