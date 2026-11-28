# Prompts para OpenCode · cola vigente (2026-11-28)

**Modelo para todos:** DeepSeek V4.1 Flash (OpenCode Go).

**Ya están hechos por Claude; NO lanzar:** FUT-A1…A10, A1b, H1-H3, O1-O6, J1-J3, J4 (lado Python),
P1-P6, M1-M3, C1, D2/D3 (código), B1/B3 (scripts). La tabla de `05_COLA_Y_ROADMAP.md §3` dice dónde está
cada uno.

## 0. Cómo se usan

- **Cadena S (en orden, sin parar).**
  - Se ejecuta en el PC del operador (`E:\trading-lab`).
  - Cada paso termina con su informe `docs/futures/WORKER_REPORTS/<ID>.md`.
  - El siguiente empieza solo si el anterior terminó en verde.
  - **S4 tiene una parada obligatoria** para el operador: compilar en NinjaTrader.
- **Carriles P (en paralelo con la cadena S y entre sí).**
  - Cada uno va en su propio worktree y ninguno toca ficheros de otro.
  - Dentro de un carril, los pasos van en orden.
- **Siempre:** pegar primero el BLOQUE COMÚN y después el prompt.
- **Al terminar cada tarea:** Claude la revisa con el agente `tradinglab-reviewer`.

| Carril | Pasos (en orden) | Worktree | Puede ir a la vez que |
|---|---|---|---|
| **S** · PC del operador | S1 verificación → S2 coste de datos → S3 manifiesto → S4 puente NT8 en Sim101 | `E:\trading-lab` (rama `claude/vibrant-mayer-r46s0o`) | P1, P2, P3 |
| **P1** · Research A en código | P1a FUT-C2 detectores y conteo → P1b FUT-C3 evaluador | `E:\tl-fut-ra` | S, P2, P3 |
| **P2** · descarga de datos en código | P2 FUT-B2 (sin descargar nada real) | `E:\tl-fut-data` | S, P1, P3 |
| **P3** · servidor MCP de solo lectura | P3 FUT-T2 | `E:\tl-fut-mcp` | S, P1, P2 |

**Bloqueado, no lanzar:**
- **Descargas reales** de Databento: esperan a OP-4, con el coste de S2 delante.
- **D2 y C2 con datos reales:** esperan a los datos.
- **D3 y C3 con datos reales:** esperan a que el operador registre FUT-RB-1 y FUT-RA-1.
- **FUT-X1…X3:** esperan a OP-6.

## 1. BLOQUE COMÚN (pegar siempre antes de cada prompt)

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
7. Nada live: solo cuentas Sim/Playback/demo. Nunca ALLOW_LIVE.
AL TERMINAR (en este orden):
  .\.venv\Scripts\Activate.ps1
  ruff check <tus rutas>
  pytest -q <tus tests>
  Escribe docs\futures\WORKER_REPORTS\<ID>.md con: Hecho / ficheros / salida literal de ruff y pytest /
  Aviso / Siguiente. Haz commit de tus rutas y de ese informe. PARA.
```

## 2. Cadena S (PC del operador, en orden)

### S1 · FUT-V0 · Verificación en Windows

```text
TAREA FUT-V0. No escribas código. Ficheros permitidos: docs\futures\WORKER_REPORTS\FUT-V0.md.
1. git fetch origin claude/vibrant-mayer-r46s0o ; git switch claude/vibrant-mayer-r46s0o
   (si hay cambios locales sin commit, PARA y dímelo; no hagas stash ni reset).
2. uv sync --frozen --extra dev --extra discovery
3. ruff check .
4. pytest -q -m "not network and not mt5 and not lmstudio and not alpaca and not credentials"
   (tarda ~30 min; copia la última línea literal).
5. .\.venv\Scripts\lab.exe doctor   (copia solo las filas FAIL y WARN).
6. .\.venv\Scripts\lab.exe propecon programs --today 2026-12-01
   .\.venv\Scripts\lab.exe propecon ranking
7. Informe con las salidas literales. Si pytest tiene fallos, lista los nombres y PARA (no los arregles).
```

### S2 · FUT-B1 · Coste exacto de datos (solo metadatos, gratis)

```text
TAREA FUT-B1. El script ya existe: scripts\futures_data_cost.py (NO lo modifiques).
Ficheros permitidos: docs\futures\evidencia\databento_costes_2026-11.json y .md (los escribe el script),
docs\futures\WORKER_REPORTS\FUT-B1.md.
1. .\.venv\Scripts\python.exe scripts\futures_data_cost.py
   (la clave sale de Credential Manager; NUNCA la imprimas).
2. Comprueba que el .md tiene una fila por esquema y raíz y la tabla de totales.
3. Informe: copia la tabla de totales. NO recomiendes compras: decide el operador (OP-4). PARA.
```

### S3 · FUT-B3 · Manifiesto con hash de los datos existentes

```text
TAREA FUT-B3. El script ya existe: scripts\futures_manifest.py (NO lo modifiques).
Ficheros permitidos: docs\futures\evidencia\manifest_futuros.jsonl y .md, docs\futures\WORKER_REPORTS\FUT-B3.md.
1. .\.venv\Scripts\python.exe scripts\futures_manifest.py
2. No modifiques, copies ni muevas ningún parquet. Informe con la tabla del .md. PARA.
```

### S4 · FUT-J4b · Puente NinjaTrader 8 en Sim101 (parada obligatoria para el operador)

```text
TAREA FUT-J4b. Lee docs\futures\research\execution_spec.md §5 y la cabecera de integrations\nt8\TradingLabBridge.cs.
Ficheros permitidos: docs\futures\WORKER_REPORTS\FUT-J4b.md y la COPIA de TradingLabBridge.cs en
%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\ (copiar, nunca mover ni borrar).
1. Copia integrations\nt8\TradingLabBridge.cs a %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\.
2. PARA y escribe exactamente esto al operador:
   "En NinjaTrader: New > NinjaScript Editor > abre TradingLabBridge y pulsa F5 (compilar). Si hay errores,
   cópialos aquí. Si compila: abre un gráfico de MNQ, añade la estrategia TradingLabBridge con la cuenta
   Sim101, BridgeDir = E:\trading-lab\data\futures\nt8_bridge, MaxContracts = 1, y actívala.
   Responde OK NT8 cuando esté activa."
3. Si el operador pega errores de compilación: NO los corrijas tú; cópialos literalmente en el informe y PARA
   (los corrige Claude).
4. Tras "OK NT8": mira el último precio de MNQ en el gráfico (te lo da el operador) y ejecuta:
   .\.venv\Scripts\python.exe scripts\nt8_bridge_smoke.py --account Sim101 --price <precio> --stop-pts 20
5. Informe: salida literal (risk_ok, intent en cola y ack). Si no hay ack en 60 s, dilo y PARA.
   Nunca uses otra cuenta que Sim101/Playback.
```

## 3. Carriles en paralelo

### P1a · FUT-C2 · Research A: detectores y conteo sin desenlaces (worktree `E:\tl-fut-ra`)

```text
TAREA FUT-C2. Lee docs\futures\research\RA_spec.md §3, §4 y §5 (hipótesis A, C, D, E, H, I) y
src\tradinglab\futures\orderflow.py (NO lo modifiques).
Ficheros permitidos (nuevos): src\tradinglab\futures\research_a.py, tests\test_futures_research_a.py.
1. Entrada: bars = orderflow.minute_bars(...) (columnas open, high, low, close, volume, delta, cvd; índice minuto NY)
   y refs = orderflow.rolling_refs(bars) (medV, medRng, s_delta). Tick 0.25 (NQ/MNQ).
2. detect(bars, refs, footprints, hypothesis) -> list[dict] con minute, side (+1/-1), stop. SIN desenlaces.
   Reglas EXACTAS de RA_spec §5 (z = delta / s_delta; R30 = máximo/mínimo de las 30 velas anteriores):
   A: z <= -3 y close >= open y volume >= 2*medV -> largo, stop = low - tick (simétrica: z >= 3, close <= open -> corto, stop = high + tick).
   C: t0 = argmax(high[t-30..t-1]); high_t > high_t0 y cvd_t < cvd_t0 - sC -> corto, stop high + tick (sC = 1.4826*MAD de cvd_t - cvd_{t-30} en las 20 sesiones previas; simétrica).
   D: >= 3 niveles consecutivos con buy(k) >= 3*sell(k-1) y buy(k) >= medL, y close >= (high+low)/2 -> largo, stop = nivel más bajo - tick.
   E: close > max(R30) + tick y delta < 0 -> corto, stop = high + tick (simétrica).
   H: close > max(R30) + tick y z >= 2 y cvd_t - cvd_{t-30} > 0 -> largo, stop = low - tick (simétrica).
   I: volume >= 3*medV y (high-low) >= 2*medRng y signo(delta) == signo(close-open) != 0 -> esa dirección, stop = extremo opuesto ± tick.
   Ventana 09:45-15:30 NY; máximo 3 eventos por sesión e hipótesis, separados >= 15 minutos.
3. count_events(...) -> DataFrame por (hypothesis, year): events, cost_filter (stop < 4.2 puntos), tradable.
   PROHIBIDO cualquier columna de P&L, R, salida u objetivo alcanzado.
4. Tests EXACTOS con velas sintéticas construidas a mano (no trades): para cada hipótesis, un día donde la señal
   salta en un minuto conocido (assert minute, side, stop); un día donde no salta; la regla de 15 minutos
   (dos señales a 10 min -> solo cuenta la primera); filas >= 2024-01-01 descartadas; test sobre los nombres de
   columnas de count_events. PARA.
```

### P1b · FUT-C3 · Research A: evaluador único (mismo worktree, tras P1a)

```text
TAREA FUT-C3. Lee RA_spec.md §4 y §7. Ficheros permitidos (nuevos): src\tradinglab\futures\research_a_eval.py,
tests\test_futures_research_a_eval.py. Usa research_a.detect (NO lo modifiques).
1. Fills con cotizaciones L1b (DataFrame quotes: ts_event, bid, ask, bid_size, ask_size) y trades:
   entrada a mercado al ask (largo) o bid (corto) en t_señal + L (L = 0.5 s; estrés 1 s);
   stop: se dispara con el primer trade en el stop o más allá y se llena al bid (largo) en t_disparo + L;
   objetivo 1.5 R: se llena solo si un trade lo ATRAVIESA 1 tick; salida por tiempo a los 15 min al bid/ask;
   stop y objetivo en el mismo segundo -> stop.
2. R_net = (dir*(salida-entrada)*2 - 2*comisión) / (|entrada-stop|*2); comisión 0.75 por lado (dato del operador).
3. t agrupado por sesión (CR1). Criterios (a) t >= t_crit, (b) media > 0 con +1 tick por lado, (c) media > 0 con
   L = 1 s, (d) mismo signo en 2019-06..2021-06 y 2021-07..2023-12 -> veredicto literal de RA_spec §7.
4. Tests EXACTOS sintéticos: entrada al ask en t+L; stop disparado por trade y llenado al bid; objetivo tocado
   sin atravesar -> no se llena; t CR1 de una serie conocida. NO lo ejecutes con datos reales. PARA.
```

### P2 · FUT-B2 · Descarga y normalización en código (worktree `E:\tl-fut-data`; NO descargar nada)

```text
TAREA FUT-B2. Lee docs\futures\03_ARQUITECTURA_FUTURES.md §3.2 y src\tradinglab\discovery\fetch_databento.py
(solo _client y _get_json; NO lo modifiques).
Ficheros permitidos (nuevos): src\tradinglab\futures\data_download.py, tests\test_futures_data_download.py.
1. plan(rows) -> lista de trabajos (dataset GLBX.MDP3, schema, symbol "<raíz>.v.0", start, end).
2. download(job, client, out_root, *, approved_by_operator: bool) -> Path. Si approved_by_operator es False ->
   RuntimeError("OP-4 sin aprobar"). Llama a timeseries.get_range con encoding=csv. Destino inmutable:
   data/futures/raw/databento/GLBX.MDP3/<schema>/<raíz>/<start>_<end>.csv.zst; si ya existe con el mismo sha256 -> no
   descarga; si existe con otro hash -> error (nunca sobrescribir).
3. Manifiesto: añade una línea a data/futures/catalog/manifest.jsonl (sha256, proveedor, schema, raíz, rango, filas,
   generador y versión).
4. normalize_trades(csv) -> parquet con ts_event (UTC ns), price, size, side, instrument_id (columnas literales de
   Databento; si falta una -> error "Sin datos: <columna>").
5. Tests con un cliente FALSO (sin red): sin aprobación -> RuntimeError; idempotencia por hash; conflicto de hash ->
   error; manifiesto con una línea por fichero; normalización de un CSV de 3 filas con valores exactos.
   PROHIBIDO ejecutar download con el cliente real. PARA.
```

### P3 · FUT-T2 · Servidor MCP `tradinglab-state` de solo lectura (worktree `E:\tl-fut-mcp`)

```text
TAREA FUT-T2. Lee docs\futures\02_EXTENSIONES_CLAUDE_CODE.md (sección MCP) y
docs\futures\research\dashboard_model.md §1.
Ficheros permitidos (nuevos): src\tradinglab\mcp_state\__init__.py, src\tradinglab\mcp_state\server.py,
tests\test_mcp_state.py.
1. Si "import mcp" falla, PARA y pide aprobación para añadir la dependencia (no la instales tú).
2. Herramientas de SOLO LECTURA: programs() (prop_economics.registry.registry_report), ranking()
   (prop_economics.scoring.score_firms), alerts() (prop_economics.alerts.collect_alerts),
   ledger_summary() (abre data/prop_economics/ledger.db con open_ledger(..., readonly=True); si no existe ->
   "Sin datos"). Ninguna herramienta escribe ficheros ni bases de datos.
3. Tests: cada herramienta devuelve JSON serializable; ledger_summary con un libro sintético en tmp_path;
   intentar escribir con la conexión del servidor -> sqlite3.OperationalError. PARA.
```

## 4. Después de cada entrega

- Claude revisa con el agente `tradinglab-reviewer`: ficheros permitidos, cifras exactas, `ruff` y
  `pytest`.
- Si la revisión pasa, Claude actualiza la cola (`05 §3`) y este documento.
