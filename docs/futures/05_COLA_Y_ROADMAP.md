# FUT-5 · Hoja de ruta, decisiones del operador y cola de OpenCode

**Fecha:** 2026-11-27 · **Autor:** Claude Code · **Cola:** `proyecto-futures` (una sola activa).
**Modelo de OpenCode para todas las tareas:** **DeepSeek V4.1 Flash** (OpenCode Go). Cada prompt cabe
en una sesión, dice qué ficheros puede escribir y cuándo **PARAR**. Claude revisa cada entrega.

> Nada de esta cola está delegado todavía: no hay integración directa entre Claude y OpenCode. El
> operador pega cada prompt en OpenCode, y OpenCode deja su entrega en
> `docs/futures/WORKER_REPORTS/<ID>.md`. Solo cuenta como hecho lo que tenga commit y tests verdes.

## 1. Hoja de ruta

| Fase | Contenido | Estado | Puerta para pasar |
|---|---|---|---|
| 0 | Auditoría del repo | **Hecha** (`00_AUDITORIA_REPO.md`) | OP-1 |
| 1 | Auditoría tecnológica open-source | **Hecha** (`01_MATRIZ_TECNOLOGIA.md`) | OP-2 |
| 2 | Extensiones de Claude Code | **Hecha** (`02_EXTENSIONES_CLAUDE_CODE.md`) | OP-3 |
| 3 | Skills, subagentes y hooks | **Diseñada** (`02 §5-7`) | OP-5 → FUT-T1 |
| 4 | Benchmarks (FUT-X1-X3) | Protocolo listo (`01 §5`) | OP-6 (instalación y datos) |
| 5 | Datos de futuros | Arquitectura (`03 §3`); FUT-B1/B3 READY | OP-4 (compra) |
| 6 | Motor EV de prop firms | **Especificado** (`04_SPEC_PROP_EV.md`); FUT-A READY tras OP-1 | tests T1-T14 verdes |
| 7 | Research A (order flow) | BLOCKED por datos | OP-4 + FUT-C0 |
| 8 | Research B (NY open) | FUT-D0 (especificación) | contaminación resuelta por hipótesis |
| 9 | Multiplataforma (NT8 primero) | FUT-E1 (investigación) | matriz con "V" probadas en demo |
| 10 | Integración y validación | — | — |

## 2. Decisiones del operador

| ID | Decisión | Desbloquea | Recomendación de Claude |
|---|---|---|---|
| **OP-1** | Aprobar la arquitectura y los ADR-F01…F10 (`03_ARQUITECTURA_FUTURES.md §8`) | FUT-A1…A9 | Sí |
| **OP-2** | Dependencias: añadir `hypothesis` y `pytest-cov` (dev), declarar `scipy`, quitar `alpaca-py` (sin uso) | FUT-A9, cobertura | Sí |
| **OP-3** | Plugins: `context7` y `pyright-lsp` (`02 §3`) | — | Sí, solo esos dos |
| **OP-4** | Compra de datos de Databento (tras FUT-B1, con el coste exacto) | FUT-B2, Research A, Research B en ES/GC | Empezar por `trades` + `definition` de MNQ/NQ |
| **OP-5** | Crear `.claude/` del proyecto (hooks de §7, 9 skills, 7 agentes) | FUT-T1 | Sí; los hooks primero |
| **OP-6** | Venv aparte para Nautilus/hftbacktest y datos de muestra para los PoC | FUT-X1…X3 | Después de FUT-A6 |
| **OP-7** | Confirmar si los 0,75 USD/lado de MNQ incluyen exchange, clearing y NFA | costes de futuros (FUT-03) | — |

## 3. Cola

**Carriles en paralelo** (no comparten ficheros): **A** = motor EV (worktree `..\tl-fut-a`);
**B** = datos (lee `E:\trading-lab\data`, escribe solo en `docs/futures/evidencia/`); **C** =
investigación de Claude (solo documentos). Dentro del carril A las tareas van en orden por dependencias;
A1 y A2 pueden ir a la vez. Nadie toca `discovery/`, `prop/`, `propfund/`, `execution/` ni `cli.py` salvo
la línea de FUT-A8, que se coordina con el lock `cli-py`.

| ID | Objetivo | Quién | Estado | Depende | Ficheros permitidos | Tests / aceptación | Vuelta atrás |
|---|---|---|---|---|---|---|---|
| FUT-A1 | Esquema YAML de programas (pydantic), cargador, caducidad, incógnitas | OpenCode | **READY** (tras OP-1) | — | `src/tradinglab/prop_economics/__init__.py`, `rules.py`; `config/prop_economics/programs/topstep_50k_combine_xfa.yaml`, `synthetic_static.yaml`, `synthetic_trailing.yaml`; `tests/test_prop_economics_rules.py` | prompt §4.2 | borrar el paquete nuevo con `git revert` |
| FUT-A2 | `DayPath`, constructor desde operaciones, desplazamiento δ | OpenCode | **READY** (tras OP-1) | — | `src/tradinglab/prop_economics/paths.py`; `tests/test_prop_economics_paths.py` | prompt §4.3 | `git revert` |
| FUT-A3 | Motor de una cuenta en evaluación (drawdown, DLL, objetivo, consistencia, días, plazo) sobre una secuencia dada | OpenCode | BACKLOG | A1, A2 | `prop_economics/account.py`, `tests/test_prop_economics_account.py` | T8, T10, T13 exactos | `git revert` |
| FUT-A4 | Fase financiada y payouts | OpenCode | BACKLOG | A3 | `prop_economics/account.py` (misma tarea que A3 cerrada), `tests/test_prop_economics_payout.py` | T9 exacto | `git revert` |
| FUT-A5 | Tarifas, política de intentos, bankroll | OpenCode | BACKLOG | A1 | `prop_economics/fees.py`, `tests/test_prop_economics_fees.py` | T11, T12 exactos | `git revert` |
| FUT-A6 | Monte Carlo: stationary bootstrap, CRN, horizontes, métricas, error MC | OpenCode | BACKLOG | A2-A5 | `prop_economics/simulate.py`, `metrics.py`, tests | T1-T7 con ±0,004 (marcar `slow`) | `git revert` |
| FUT-A7 | Escenarios y ventaja mínima μ\* | OpenCode | BACKLOG | A6 | `prop_economics/scenarios.py`, tests | monotonía en 9 puntos; μ\* de un pool sintético conocido | `git revert` |
| FUT-A8 | Informe, sub-app CLI `lab propecon`, libro real separado | OpenCode | BACKLOG | A7 | `prop_economics/report.py`, `cli.py` del paquete, `ledger.py`; **1 línea** en `src/tradinglab/cli.py` con lock `cli-py` | el simulador no puede escribir en el libro (test) | `git revert` |
| FUT-A9 | Tests de propiedades (T14) | OpenCode | BACKLOG | A4, OP-2 | `tests/test_prop_economics_properties.py` | hypothesis 500 ejemplos | `git revert` |
| FUT-B1 | Coste exacto de datos Databento (gratis, solo metadatos) | OpenCode en el equipo del operador | **READY** | — | `scripts/futures_data_cost.py` (nuevo); `docs/futures/evidencia/databento_costes_2026-11.json` y `.md` | prompt §4.4 | borrar nada; `git revert` |
| FUT-B2 | Descarga con `instrument_id` + `definition` y normalización | OpenCode | BLOCKED (OP-4) | B1 | `src/tradinglab/futures/data/` | identidad y hash por fichero | — |
| FUT-B3 | Manifiesto con hash de los datos de futuros que ya existen | OpenCode en el equipo del operador | **READY** | — | `scripts/futures_manifest.py` (nuevo); `docs/futures/evidencia/manifest_futuros.jsonl` y `.md` | prompt §4.5 | `git revert` |
| FUT-R1 | Reglas oficiales vigentes de Topstep, Apex, TradeDay, MyFundedFutures, Take Profit Trader y Earn2Trade (tarifas, drawdown, payouts, automatización) | **Claude** | **READY** | — | `docs/futures/research/prop_firms_2026-12.md` + YAML de programas | cada valor con URL y fecha; discrepancias marcadas | — |
| FUT-E1 | Matriz de plataformas con documentación oficial (NT8, Tradovate, ProjectX) | **Claude** | **READY** | — | `03_ARQUITECTURA_FUTURES.md §6` | estados V/PV/NA/NI/RL/RC con fuente | — |
| FUT-C0 | Especificación de Research A (hipótesis A-J con definición matemática, datos mínimos, costes, criterio de rechazo) | **Claude** | READY | — | `docs/futures/research/RA_spec.md` | cada hipótesis con nivel de datos de `03 §3.1` | — |
| FUT-D0 | Especificación de Research B con clasificación de contaminación por hipótesis e instrumento | **Claude** | READY | — | `docs/futures/research/RB_spec.md` | ninguna hipótesis NQ sin su etiqueta | — |
| FUT-J0 | Contrato de ejecución y riesgo (`OrderIntent`, `RiskCheck`, ticket) | **Claude** | BACKLOG | E1 | `docs/futures/research/execution_spec.md` | — | — |
| FUT-H0 | Modelo de dominio del dashboard (realizado vs simulado) | **Claude** | BACKLOG | A8 | `docs/futures/research/dashboard_model.md` | — | — |
| FUT-T1 | Hooks, skills y agentes del proyecto | OpenCode + revisión de Claude | BLOCKED (OP-5) | — | `.claude/settings.json`, `.claude/hooks/*.py`, `.claude/skills/*/SKILL.md`, `.claude/agents/*.md` | cada hook bloquea su caso en un test | borrar la entrada del JSON |
| FUT-T2 | Servidor MCP `tradinglab-state` de solo lectura | OpenCode | BACKLOG | T1 | `src/tradinglab/mcp_state/` | abre SQLite con `mode=ro` (test) | — |
| FUT-X1…X3 | PoC de benchmark | OpenCode | BLOCKED (OP-6) | A6 | venv aparte; `docs/futures/benchmarks/` | `01 §5` | borrar el venv |

**Estimación** (sesiones de OpenCode, **Estimado**): A1-A2 1 cada una; A3-A4 2; A5 1; A6 2; A7 1; A8 2;
A9 1 → ~12 sesiones para el motor EV completo. B1 y B3: 1 cada una.

**Fin de la cola:** se cierra cuando FUT-A8 entregue el primer informe EV de Topstep 50K con el pool
sintético y los tests T1-T14 estén verdes. No se añaden tareas nuevas a esta cola: van a la siguiente.

## 4. Prompts para OpenCode (DeepSeek V4.1 Flash)

### 4.0 Preparación (una vez, el operador, PowerShell)

```powershell
cd E:\trading-lab
git fetch origin claude/vibrant-mayer-r46s0o
git worktree add ..\tl-fut-a origin/claude/vibrant-mayer-r46s0o
```

### 4.1 BLOQUE COMÚN (pegar siempre antes de cada prompt)

```text
Eres el ingeniero de TradingLab. Responde en español. Modelo: DeepSeek V4.1 Flash.
LEE PRIMERO: AGENTS.md y SOLO el documento que indique la tarea.
REGLAS DURAS (si la tarea las contradice, PARA y pregunta):
1. Escribe SOLO en los ficheros que la tarea lista. Si necesitas otro, PARA y pregunta.
2. No ejecutes: lab campaign run, lab research*, lab discovery run/approve/confirm/supersede,
   record-informal, git push, borrar ficheros, schtasks/Register-ScheduledTask. No toques .env.
3. No descargues datos de pago. No calcules rendimiento de estrategias con datos reales.
4. No inventes cifras, comisiones, reglas ni resultados: si falta un dato escribe "Sin datos".
5. Muestra primero un PLAN corto (ficheros y funciones) y ESPERA mi "OK PLAN".
6. Commits por ruta: git add <rutas> ; git commit -m "fut: <ID> ..." -- <rutas>. Nunca git add -A ni .
AL TERMINAR (en este orden):
  .\.venv\Scripts\Activate.ps1
  ruff check <tus rutas>
  pytest -q <tus tests>
  Escribe docs\futures\WORKER_REPORTS\<ID>.md con: Hecho / ficheros / salida literal de ruff y pytest /
  Aviso / Siguiente. Haz commit de tus rutas y de ese informe. PARA.
```

### 4.2 FUT-A1 · Esquema de programas (worktree `E:\tl-fut-a`)

```text
TAREA FUT-A1. Lee docs/futures/04_SPEC_PROP_EV.md secciones 3, 4, 5 y 8. Nada más.
Ficheros permitidos (nuevos): src/tradinglab/prop_economics/__init__.py, src/tradinglab/prop_economics/rules.py,
config/prop_economics/programs/topstep_50k_combine_xfa.yaml, config/prop_economics/programs/synthetic_static.yaml,
config/prop_economics/programs/synthetic_trailing.yaml, tests/test_prop_economics_rules.py.

1. rules.py con pydantic v2 (ya instalado). Status = Literal["verified","verified_repo","discrepancia","sin_datos","assumed"].
   Clases: Source(url, consulted_at: date); Value(value: float|int|str|None=None, alt: float|None=None, status, note: str|None=None);
   MaxLoss(mode: Literal["static","trailing_eod","trailing_intraday"], amount: float>0, check: Literal["realtime_unrealized","eod_only"]="realtime_unrealized",
   lock_at: float|Literal["start_balance"]|None=None, lock_after_first_payout: bool=False, status);
   DailyLoss(amount>0, action: Literal["pause_day","breach"], enabled: bool=True, optional: bool=False,
   base: Literal["day_start_balance","higher_of_balance_or_equity"]="day_start_balance", status);
   Consistency(max_best_day_fraction: 0<x<=1, basis: Literal["total_profit"]="total_profit", on_violation: Literal["raise_target","fail"]="raise_target", status);
   EvaluationPhase, FundedPhase, Payout, Fees, Program exactamente con los campos del YAML de la sección 8.
   Program.schema_version: Literal[1]. Program.phases.funded es opcional (None si no hay fase financiada).
   Fees.evaluation.type: Literal["subscription","one_time"]. Un objeto con solo "status" (p. ej. reset: {status: sin_datos})
   es válido.
2. Funciones: load_program(path) -> Program; is_expired(program, today: date) -> bool
   (caducado si today >= consulted_at + expires_after_days días); blocking_unknowns(program) -> list[str]
   (claves con puntos de todo valor con status "sin_datos" o "discrepancia", ordenadas; ignora las reglas con enabled: false).
3. topstep_50k_combine_xfa.yaml = el YAML de la sección 8, literal.
4. synthetic_static.yaml: evaluación S=0, T=3000, static D=2000, sin DLL, sin consistencia, min_trading_days 0;
   sin fase funded; fees evaluation one_time 100, activation 150; todo status "assumed"; consulted_at 2026-11-27.
   synthetic_trailing.yaml: igual pero trailing_eod D=2000 lock_at 0.
5. Tests (exactos):
   - los 3 YAML cargan sin error;
   - is_expired(topstep, date(2026,12,24)) is False y is_expired(topstep, date(2026,12,25)) is True;
   - blocking_unknowns(topstep) == ["commissions_per_side.MNQ","commissions_per_side.NQ","fees.data_platform_monthly",
     "fees.reset","phases.funded.payout.cap_per_payout","phases.funded.payout.processing_days","phases.funded.scaling_plan"];
   - un YAML con mode "trailing_xyz" o amount -1 lanza ValidationError;
   - blocking_unknowns(synthetic_static) == [].
NO escribas el simulador. PARA al terminar.
```

### 4.3 FUT-A2 · `DayPath` (worktree `E:\tl-fut-a`, puede ir a la vez que A1)

```text
TAREA FUT-A2. Lee docs/futures/04_SPEC_PROP_EV.md secciones 2 y 7.1. Nada más.
Ficheros permitidos (nuevos): src/tradinglab/prop_economics/paths.py, tests/test_prop_economics_paths.py.
(Si src/tradinglab/prop_economics/__init__.py no existe aún, créalo vacío y dilo en el informe.)

1. @dataclass(frozen=True) DayPath con los campos de la sección 2 (marks como np.ndarray float64).
   Método validate() que lanza ValueError si: marks[0] != 0, algún valor no finito, cost < 0,
   abs(marks[-1] - (gross_pnl - cost)) >= 1e-9.
2. @dataclass(frozen=True) TradeSpec(pnl_net: float, mfe: float, mae: float, cost: float). mfe>=0, mae>=0,
   -mae <= pnl_net <= mfe; si no, ValueError.
3. from_trades(session_date, trades: list[TradeSpec], *, risk_usd=None, flags=frozenset(), source="synthetic") -> DayPath.
   Para cada operación, con acumulado c antes de ella, añade en orden: c+mfe, c-mae, c+pnl_net.
   gross_pnl = suma(pnl_net + cost); cost = suma(cost); n_trades = len(trades).
   Lista vacía -> marks = [0.0], n_trades 0, gross 0, cost 0.
4. shift(day, delta) -> DayPath nuevo: la marca de salida de la operación k (k=1..n) y todas las posteriores
   suman k*delta. gross_pnl suma n*delta. Para saber qué marca es la salida de cada operación, guarda en DayPath
   un campo exit_idx: tuple[int, ...] (índices de las marcas de salida) que rellena from_trades.
5. Tests exactos:
   - from_trades(d, [TradeSpec(100,150,40,2.5), TradeSpec(-50,20,60,2.5)]).marks == [0,150,-40,100,120,40,50],
     n_trades 2, gross_pnl 55.0, cost 5.0, exit_idx (3,6), validate() no lanza;
   - shift(esa, 10).marks == [0,150,-40,110,130,50,70] y gross_pnl 75.0;
   - TradeSpec(200,150,40,0) lanza ValueError;
   - from_trades(d, []).marks == [0.0].
PARA al terminar.
```

### 4.4 FUT-B1 · Coste de datos (equipo del operador, `E:\trading-lab`; solo metadatos, gratis)

```text
TAREA FUT-B1. Lee docs/futures/03_ARQUITECTURA_FUTURES.md sección 3.1 y src/tradinglab/discovery/fetch_databento.py
(solo las funciones _client, _get_json, _metadata_params). NO modifiques fetch_databento.py.
Ficheros permitidos (nuevos): scripts/futures_data_cost.py, docs/futures/evidencia/databento_costes_2026-11.json,
docs/futures/evidencia/databento_costes_2026-11.md.

1. El script importa _client, _get_json, _metadata_params de tradinglab.discovery.fetch_databento.
   Para cada fila de esta tabla llama SOLO a metadata.get_record_count, metadata.get_billable_size y metadata.get_cost
   (dataset GLBX.MDP3, símbolo f"{raiz}.v.0", stype_in continuous). NUNCA llames a timeseries.get_range.
   | esquema    | raíces                     | inicio     | fin        |
   | ohlcv-1m   | NQ MNQ ES MES GC MGC       | 2019-01-01 | 2026-11-27 |
   | definition | NQ MNQ ES MES GC MGC       | 2019-01-01 | 2026-11-27 |
   | trades     | NQ MNQ ES MES GC MGC       | 2019-01-01 | 2026-11-27 |
   | tbbo       | NQ MNQ ES MES              | 2019-01-01 | 2026-11-27 |
   | mbp-1      | NQ MNQ                     | 2025-11-27 | 2026-11-27 |
   | mbp-10     | NQ MNQ                     | 2026-10-27 | 2026-11-27 |
   | mbo        | NQ MNQ                     | 2026-11-16 | 2026-11-23 |
   Si una llamada falla, guarda el error literal en esa fila ("Sin datos: <error>") y sigue con la siguiente.
2. Guarda el JSON (una fila por esquema y raíz: schema, root, symbol, start, end, records, billable_bytes, cost_usd, error)
   y una tabla Markdown con los mismos campos y el total por esquema.
3. Ejecuta: .\.venv\Scripts\python.exe scripts\futures_data_cost.py
   La clave sale de Credential Manager; no la imprimas nunca.
4. No escribas tests en esta tarea (el script usa la red y la clave real).
5. En WORKER_REPORTS\FUT-B1.md copia la tabla. No recomiendes compras: decide el operador. PARA.
```

### 4.5 FUT-B3 · Manifiesto de lo que ya hay (equipo del operador, `E:\trading-lab`; solo lectura de datos)

```text
TAREA FUT-B3. Lee docs/futures/03_ARQUITECTURA_FUTURES.md sección 3.2.
Ficheros permitidos (nuevos): scripts/futures_manifest.py, docs/futures/evidencia/manifest_futuros.jsonl,
docs/futures/evidencia/manifest_futuros.md.

1. Recorre SOLO data\cache\databento\*.parquet (lectura). Por fichero: ruta, tamaño en bytes, sha256 del fichero,
   filas, primera y última marca de tiempo (UTC), columnas, si existe la columna instrument_id (sí/no),
   raíz Databento según ROOT_TO_INTERNAL invertido (US100->NQ, US500->ES, US30->YM, XAUUSD->GC, EURUSD->6E,
   GBPUSD->6B, USDJPY->6J), timeframe del nombre (M1/H1).
2. No modifiques ni copies los parquet. No abras ningún otro directorio.
3. Escribe una línea JSON por fichero y una tabla Markdown.
4. Ejecuta: .\.venv\Scripts\python.exe scripts\futures_manifest.py
5. WORKER_REPORTS\FUT-B3.md con la tabla. PARA.
```

## 5. Siguiente paso de Claude

Con OP-1 aprobado: revisar FUT-A1/A2 cuando lleguen y preparar los prompts de A3-A5. En paralelo, FUT-R1
(reglas oficiales de las seis firmas) y FUT-E1 (plataformas), que son investigación propia.
