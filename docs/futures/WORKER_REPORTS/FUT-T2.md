# FUT-T2 · Servidor MCP `tradinglab-state` de solo lectura

**Fecha:** 2026-11-28 · **Modelo:** DeepSeek V4.1 Flash · **Worktree:** `E:\tl-fut-mcp` (rama `fut-mcp`, base `f837d4d`)
**Documentos leídos:** `AGENTS.md`, `docs/futures/OPENCODE_PROMPTS.md` (BLOQUE COMÚN + P3),
`docs/futures/02_EXTENSIONES_CLAUDE_CODE.md §4`, `docs/futures/research/dashboard_model.md §1`.

## Hecho

1. **Parada obligatoria del paso 1:** `import mcp` fallaba (`ModuleNotFoundError: No module named 'mcp'`).
   Se pidió aprobación y el operador autorizó `mcp==2.3.0` + `pyproject.toml` + `uv.lock` + `.venv` del worktree.
2. Extra nuevo `mcp = ["mcp==2.3.0"]` en `pyproject.toml`; `uv lock` y `uv sync --frozen --extra dev --extra mcp`
   crean `E:\tl-fut-mcp\.venv` (Python 3.12.16) donde `tradinglab` resuelve a `E:\tl-fut-mcp\src`.
3. Servidor `tradinglab-state` con **cuatro herramientas de solo lectura** y transporte stdio:
   - `programs(today=None)` → `prop_economics.registry.registry_report`
   - `ranking()` → `prop_economics.scoring.score_firms`
   - `alerts(today=None, warn_days=7)` → `prop_economics.alerts.collect_alerts`
   - `ledger_summary(today=None)` → `data/prop_economics/ledger.db` con `open_ledger(..., readonly=True)`
     (URI `mode=ro`); si el fichero no existe devuelve `{"status": "Sin datos", "path": ...}` y **no lo crea**.
4. Fecha por defecto en hora de Nueva York (`America/New_York`), igual que `prop_economics/cli.py`, para no
   usar `date.today()` (regla DTZ de ruff).
5. `__init__.py` exporta `mcp_server` de forma perezosa (PEP 562): así no se carga el submódulo al arrancar y
   `python -m tradinglab.mcp_state.server` no emite `RuntimeWarning`.
6. Prueba de humo real (fuera del repo, en `%TEMP%`): cliente MCP oficial lanzando el servidor por stdio.

## Ficheros

| Fichero | Estado |
|---|---|
| `src/tradinglab/mcp_state/__init__.py` | nuevo |
| `src/tradinglab/mcp_state/server.py` | nuevo |
| `tests/test_mcp_state.py` | nuevo (6 tests) |
| `pyproject.toml` | extra `mcp = ["mcp==2.3.0"]` (aprobado) |
| `uv.lock` | regenerado por `uv lock` (aprobado) |
| `docs/futures/WORKER_REPORTS/FUT-T2.md` | este informe |

## Salida literal

```text
> ruff check src\tradinglab\mcp_state tests\test_mcp_state.py
All checks passed!
```

```text
> pytest -q tests\test_mcp_state.py
......                                                                   [100%]
6 passed in 1.37s
```

```text
> python -m tradinglab.cli doctor
| Frescura          | FAIL   | 17/17 fallan - EURUSD H1 (sin datos), EURUSD   |
| Telegram remoto   | WARN   | sin configurar                                 |
| Carpeta logs      | WARN   | E:\tl-fut-mcp\logs                             |
| TradingAgents     | WARN   | E:\tl-fut-mcp\vendor\TradingAgents             |
| Trading-R1        | WARN   | E:\tl-fut-mcp\vendor\Trading-R1                |
| Deep LLM          | WARN   | sin configurar: el deep se corre bajo demanda  |
| MetaTrader 5      | WARN   | Falta el paquete MetaTrader5                   |
| Riesgo abierto    | WARN   | Falta el paquete MetaTrader5                   |
| Reglas fondeo     | WARN   | plantilla FTMO en config/prop.yaml             |
```

`lab doctor` no tiene relación con este cambio: el FAIL de «Frescura» es que el worktree está recién creado y
no tiene los datos del PC del operador; los WARN (Telegram, MT5, vendor, deep LLM) son del entorno, no del
servidor MCP.

Prueba de humo por stdio (script de `%TEMP%`, no forma parte del repo):

```text
tools: ['alerts', 'ledger_summary', 'programs', 'ranking']
ledger_summary: ["type='text' text='{\n  \"status\": \"Sin datos\",\n  \"path\": \"E:\\\\tl-fut-mcp\\\\data\\\\prop_economics\\\\ledger.db\"\n}' ..."]
programs: ["type='text' text='{\n  \"programs_by_firm\": {\n    \"topstep\": [\n      \"topstep_50k_combine_xfa\"\n    ],\n    \"myfundedfutures\": [\n      \"myfundedfutures_rapid_50k\"\n    ],\n    \"lucid\": [\n ...
ranking: ["type='text' text='{\n  \"ranking\": [\n    {\n      \"firm\": \"myfundedfutures\",\n      \"plan\": \"Rapid\",\n      \"covered_weight\": 1.0,\n      \"partial\": 3.55,\n      \"complete\": true,\n      \"total ...
alerts: {"result": [{"alert": "rules_unknown", "program": "lucid_flex_50k", "keys": ["fees.consistency_addon", ...]}]}
```

Tests (todos sintéticos, sin red y sin escribir fuera de `tmp_path`):

- las cuatro herramientas están registradas y devuelven JSON serializable (`json.dumps(..., allow_nan=False)`);
- `ledger_summary` sobre un libro sintético con cifras exactas: `costs_paid=500.0`, `received=900.0`,
  `net_real=400.0`, `capital_max_exposed=500.0`, `pipeline={requested:1000, approved:1000, processed:900,
  received:900, in_transit:0}`, `times_days` con mediana y máximo de 2,0 días en los tres tramos,
  `by_firm`/`by_account` = `{costs:500, received:900, net:400}`, `received_local={"EUR":800.0}`,
  `n_payouts` con 1 recibido;
- `INSERT` y `DELETE` con la conexión del servidor → `sqlite3.OperationalError` y sha256 del `.db` sin cambios;
- libro ausente → `{"status": "Sin datos"}` sin crear fichero ni directorio;
- las herramientas no tocan `config/` ni `data/` del repo (tamaño y mtime de cada fichero idénticos).

## Aviso

- **Dependencia nueva:** `mcp==2.3.0` (MIT) arrastra `mcp-types`, `httpx2`, `starlette`, `sse-starlette`,
  `uvicorn`, `pywin32`, `opentelemetry-api`, `pyjwt`, `jsonschema` y `python-multipart`. Es un extra
  opcional: `uv sync --frozen` sin `--extra mcp` no lo instala y el resto del repo queda igual.
- **API v2:** `mcp.server.MCPServer` sustituye a `FastMCP`; una futura actualización de major romperá el
  servidor. Está fijado a `2.3.0`.
- **`data/prop_economics/ledger.db` no existe en este worktree** → `ledger_summary` responde «Sin datos».
  El libro real solo lo escribe el operador con `lab propecon ledger add`.
- **No verificado:** registrar el servidor en un cliente real (Claude Desktop / OpenCode). La prueba de
  humo usa el cliente MCP oficial por stdio, no un host.
- No se ha ejecutado `lab campaign run`, `lab research*` ni ninguna descarga; no hay `git push`.
- Los datos de `programs` y `ranking` salen de `config/prop_economics/` tal cual; no se ha inventado nada.

## Siguiente

1. Revisión de Claude con `tradinglab-reviewer` (ficheros permitidos, cifras, ruff y pytest).
2. Si pasa: actualizar la cola (`05_COLA_Y_ROADMAP.md §3`) y `OPENCODE_PROMPTS.md`.
3. Registrar el servidor en un host MCP real (`.mcp.json` o equivalente) queda pendiente de decisión del
   operador: no estaba en los ficheros permitidos de esta tarea.
