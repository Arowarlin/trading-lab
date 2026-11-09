# TradingLab

Entorno multi-bot de trading sobre **TradingAgents** y **Trading-R1**, con LLM local
(LM Studio / Qwen3.8-27B), ejecución en **Alpaca paper** (acciones) y **MetaTrader 5**
(forex), con motor de reglas para **cuentas de fondeo** (FTMO).

> Regla del proyecto: nada de dinero real hasta completar la fase de paper trading
> (4-8 semanas) con métricas positivas y el kill-switch probado.

---

## 1. Estado actual

| Fase | Descripción | Estado |
|---|---|---|
| F0 | Infraestructura, venvs, repos, `uv`, `bun` | ✅ |
| F1 | LM Studio sirviendo el modelo | ✅ descargado, cargado y `llm-test` OK |
| F2 | Repos instalados y verificados | ✅ TradingAgents · ⚠ Trading-R1 requiere WSL |
| F3 | Núcleo del lab: config, SQLite, datos, riesgo | ✅ |
| F4 | Backtester + estrategias deterministas | ✅ |
| F5 | Alpaca paper + ejecución | ✅ validado (cuenta ACTIVE, equity 100k) |
| F6 | TradingAgents como fuente de señal | ✅ `lite` validado (77 s) · `deep` opcional |
| F7 | Trading-R1 (informes/Telegram) | ⏳ requiere WSL |
| F8 | Dashboard y observabilidad | ✅ `lab dashboard` (HTML) + `lab web` (consola v2: mercado, research, decisiones, repos) |
| F9 | Núcleo multi-activo (forex, futuros, acciones) | ✅ |
| F10 | MT5: datos, sizing, órdenes, hora de servidor | ✅ demo validada (abrir/cerrar) |
| F11 | Motor de reglas de fondeo (FTMO) | ✅ guard + Monte Carlo + fuente contrastada |
| F12 | Futuros (Topstep + ProjectX) | ✅ adaptador y CLI en dry-run · ⏳ cuenta y guard |
| F13 | Paper continuo 4-8 semanas | ✅ activo en paper · tarea `TradingLab-F13` lunes 22:20 |
| F14 | Investigación automática (`lab research`) | ✅ barrido + OOS + DSR + PBO + walk-forward + regímenes |
| F15 | Datos de ticks Dukascopy / spread real forex | ✅ descarga/decodifica ticks · ⏳ integración en research |

---

## 2. Estructura

```
E:\trading-lab\
├─ .venv\            Python 3.13 · laboratorio (datos, backtest, riesgo, ejecución)
├─ .venv-ta\         Python 3.13 · TradingAgents 0.7.1 (aislado)
├─ .venv-r1\         Python 3.12 · Trading-R1 0.1.0 (aislado; en Windows no arranca)
├─ config\
│   ├─ lab.yaml      modo, riesgo, broker, LLM, MT5, fondeo
│   ├─ bots.yaml     catálogo de bots
│   └─ prop.yaml     reglas de fondeo por firma y fase (FTMO)
├─ src\tradinglab\
│   ├─ config.py     settings tipados (YAML + .env)
│   ├─ db.py         SQLite: órdenes, fills, posiciones, equity, señales, LLM calls
│   ├─ instruments.py specs: tick, tick_value, contrato, lote, sizing por riesgo
│   ├─ data\         descarga + caché parquet (yfinance)
│   ├─ strategies\   trend, trend-ls, meanrev
│   ├─ backtest.py   motor con comisión y slippage
│   ├─ risk.py       sizing por ATR, límites y kill-switch
│   ├─ execution\    PaperBroker · Alpaca · MT5 · ProjectX
│   ├─ prop\         rules (firmas/fases), guard (bloqueo), simulator (Monte Carlo)
│   ├─ research.py   barrido de parámetros + OOS + propuestas (no auto-activa)
│   ├─ llm.py        cliente OpenAI-compatible con log de llamadas
│   ├─ agents\       puente a TradingAgents
│   ├─ reporting.py  dashboard HTML estático
│   ├─ web.py        panel web local (API JSON + acciones seguras)
│   ├─ webui\        interfaz del panel (HTML/CSS/JS, sin CDNs)
│   └─ cli.py        comandos `lab`
├─ docs\             arquitectura y auditoría de repos de referencia
├─ scripts\
│   ├─ run_tradingagents.py
│   ├─ research_daily.ps1
│   ├─ backup.ps1
│   └─ lab.ps1
├─ vendor\           repos clonados (TradingAgents, Trading-R1)
├─ data\             caché, lab.db, informes de agentes
└─ logs\
```

---

## 3. Comandos

```powershell
cd E:\trading-lab
.\.venv\Scripts\lab.exe doctor          # diagnóstico completo
.\.venv\Scripts\lab.exe doctor --network

.\.venv\Scripts\lab.exe fetch NVDA --start 2018-01-01
.\.venv\Scripts\lab.exe backtest SPY --strategy trend
.\.venv\Scripts\lab.exe backtest AAPL --strategy meanrev --start 2020-01-01

.\.venv\Scripts\lab.exe run SPY --strategy trend --dry-run   # señal sin orden
.\.venv\Scripts\lab.exe run SPY --strategy trend             # orden paper

.\.venv\Scripts\lab.exe orchestrate --dry-run                # todos los bots del catálogo
.\.venv\Scripts\lab.exe orchestrate --bot trend-spy         # solo uno
.\.venv\Scripts\lab.exe orchestrate --include-disabled      # incluye los apagados

.\.venv\Scripts\lab.exe agent NVDA --date 2026-11-05         # decisión LLM (lite)
.\.venv\Scripts\lab.exe agent NVDA --mode deep                # TradingAgents completo
.\.venv\Scripts\lab.exe agent-run NVDA --dry-run             # decisión + orden

.\.venv\Scripts\lab.exe status
.\.venv\Scripts\lab.exe report
.\.venv\Scripts\lab.exe dashboard                            # reports/dashboard.html
.\.venv\Scripts\lab.exe web                                  # panel web en vivo
.\.venv\Scripts\lab.exe bots
.\.venv\Scripts\lab.exe llm-test

# Forex con MetaTrader 5
.\.venv\Scripts\lab.exe mt5 status
.\.venv\Scripts\lab.exe mt5 price EURUSD
.\.venv\Scripts\lab.exe mt5 size EURUSD --risk-usd 500 --stop-pips 20
.\.venv\Scripts\lab.exe mt5 run EURUSD --strategy trend-ls --execute
.\.venv\Scripts\lab.exe mt5 positions
.\.venv\Scripts\lab.exe mt5 close <ticket> --execute

# Cuentas de fondeo
.\.venv\Scripts\lab.exe prop rules
.\.venv\Scripts\lab.exe prop status --from-mt5
.\.venv\Scripts\lab.exe prop size EURUSD --risk-pct 0.005 --stop-pips 20
.\.venv\Scripts\lab.exe prop check --lots 1.5 --stop-pips 20 --equity 98000
.\.venv\Scripts\lab.exe prop simulate SPY --strategy trend --phase challenge

# Investigación automática (ranking + propuestas, sin activar nada)
.\.venv\Scripts\lab.exe research --start 2015-01-01

# Kill-switch, alertas y reconciliación
.\.venv\Scripts\lab.exe killswitch status
.\.venv\Scripts\lab.exe killswitch test
.\.venv\Scripts\lab.exe killswitch reset
.\.venv\Scripts\lab.exe alerts status
.\.venv\Scripts\lab.exe alerts check
.\.venv\Scripts\lab.exe alerts test
.\.venv\Scripts\lab.exe reconcile

# Ciclo de vida de bots
.\.venv\Scripts\lab.exe bots list
.\.venv\Scripts\lab.exe bots evaluate           # añade --apply para archivar no aptos deshabilitados
.\.venv\Scripts\lab.exe bots propose mi-bot --strategy trend --universe QQQ
.\.venv\Scripts\lab.exe bots archive mi-bot --yes
.\.venv\Scripts\lab.exe bots restore mi-bot

# Decisiones LLM y resultados forward
.\.venv\Scripts\lab.exe decisions update
.\.venv\Scripts\lab.exe decisions report

# Información continua (solo lectura, sin ejecución)
.\.venv\Scripts\lab.exe intel fetch
.\.venv\Scripts\lab.exe intel status
.\.venv\Scripts\lab.exe intel fred --days 90
.\.venv\Scripts\lab.exe intel calendar
.\.venv\Scripts\lab.exe intel event FOMC --at 2026-12-09T19:00:00+00:00

# SEC EDGAR (User-Agent obligatorio; caché y rate limit)
.\.venv\Scripts\lab.exe sec status
.\.venv\Scripts\lab.exe sec cik NVDA
.\.venv\Scripts\lab.exe sec filings NVDA --limit 10
.\.venv\Scripts\lab.exe sec facts NVDA

# Reproducibilidad y secretos
uv sync --frozen --extra dev --extra mt5
.\.venv\Scripts\python.exe scripts\migrate_secrets.py --status
```

Atajo: `.\scripts\lab.ps1 <comando>`.

---

## 3b. Panel web local (TradingLab Console)

`lab web` sirve una consola en vivo en **http://127.0.0.1:8420** con todo el
laboratorio en una sola página. Está pensada para el día a día: no hay que
recordar comandos para ver qué está pasando.

```powershell
# arrancar y abrir el navegador
.\.venv\Scripts\lab.exe web

# sin abrir el navegador (útil para dejarlo en segundo plano)
.\.venv\Scripts\lab.exe web --no-open

# otro puerto
.\.venv\Scripts\lab.exe web --port 8430

# atajo
.\scripts\web.ps1
```

Qué muestra:

| Pestaña | Contenido |
|---|---|
| **Dashboard** | KPIs, distribución cash/posiciones, top performers de bots, calendario mensual de PnL, curva de equity, pipeline datos→señal→riesgo→ejecución, calendario macro, estado de LM Studio/MT5/FTMO, tareas programadas, últimas decisiones y órdenes. |
| **Mercado** | watchlist desde caché local, sparklines, breadth, retorno 1/5/20d y detalle por activo. **No descarga datos.** |
| **Sala** | oficina pixel con los 10 roles de TradingAgents, estados en vivo, burbujas, tablero y acceso al detalle de cada rol. |
| **Cuentas** | paper interno, Alpaca paper, FTMO demo y TopstepX/ProjectX, con equity, cash, posiciones y estado. |
| **Fondo** | límite de firma (solo lectura), propio editable, efectivo, uso del día, colchón, historial, kill-switch global, exposición agregada, capital por bolsillo y presupuesto de clúster. |
| **Bots** | catálogo, enabled/disabled, propuestas, evaluación con backtest, archivo reversible y última señal. |
| **Agentes** | historial lite/deep con rating, confianza, duración y tesis; detalle en modal; runs deep en curso o terminados. |
| **Research** | ranking, PBO global y por activo, walk-forward, gate de regímenes, propuestas (`enabled: false`), casi propuestas y **resultados por perfil** (swing, forex/CFD, futuros). Clic en una fila para el detalle. |
| **Decisiones** | retorno forward por rating, hit rate y aviso de muestra insuficiente. |
| **Riesgo** | guard de FTMO (colchón restante, suelos, límites usados), reglas activas, cuenta MT5 y estado de TopstepX/ProjectX. |
| **Repos** | auditoría de AutoHedge, Vibe-Trading y FinceptTerminal: licencia, qué se adoptó y qué no. |
| **Registros** | logs de dry-run, agentes, backups y tareas, con visor integrado. |

La página se refresca sola cada **8 s** (pausada si la pestaña está oculta). El
servidor escucha solo en **127.0.0.1** por defecto (no se publica en la red) y
usa la biblioteca estándar de Python: no añade FastAPI/Flask ni CDNs externos.

La consola incluye una **paleta de comandos** con `Ctrl+K` para navegar, buscar
activos de la watchlist y abrir el detalle de research. La barra de estado
muestra modo, hora de Praga, datos, PBO/WF, commit git y última actualización.

La gráfica de equity tiene rangos **1M/3M/6M/1A/Todo**, tooltip al pasar el
ratón, eje de fechas, línea base y área. La pestaña **Cuentas** reúne las cuatro
cuentas; **Bots** permite evaluar, proponer y archivar (sin borrar) con un clic.

**Acciones disponibles (nunca envían órdenes):**

- **Dry-run ahora**: ejecuta `orchestrate --dry-run`, calcula señales y escribe
  `data/dryrun/*.json` y `logs/dryrun/*.log`.
- **Analizar con lite**: lanza `agent <ticker> --mode lite` (1-3 min con el 27B)
  y deja el resultado en `data/agent_runs/`.

Ambas se ejecutan en segundo plano; el panel muestra el progreso y enlaza el
log. Los bots con `enabled: false`, las propuestas de research y el modo live
siguen requiriendo activación humana explícita desde `config/*.yaml` o la CLI.

Si el puerto está ocupado, usa `--port`. La tarea **`TradingLab-Web`** ya está
registrada y arranca el panel al iniciar sesión (sin abrir el navegador). Para
quitarla:

```powershell
Unregister-ScheduledTask -TaskName "TradingLab-Web" -Confirm:$false
```

> El panel consulta MT5 (solo lectura) y LM Studio. Si el terminal no está
> abierto, la tarjeta de riesgo muestra el error y sigue funcionando el resto.

### Acceso directo

`TradingLab Console.lnk` (raíz del repo) abre el panel con doble clic. El
lanzador `scripts/open_console.ps1`:

- calcula un **build hash** de código, UI y `config/*.yaml`;
- reutiliza el panel solo si `/api/health` tiene ese mismo build;
- si el servidor está viejo o no responde, lo reinicia automáticamente;
- regenera el `.lnk` en cada apertura;
- abre con `?v=<build>` para evitar caché;
- si cambia el build con el panel abierto, el frontend se recarga solo.

Si algo falla, muestra un cuadro de error. También puedes recrear el acceso
directo con `scripts/create_console_shortcut.ps1`.

### Repos de referencia y arquitectura

- [`docs/arquitectura.md`](docs/arquitectura.md): cómo encaja el árbol propuesto
  `C:\TradingLab` (agents/engines/research/execution/risk/monitoring) con el
  laboratorio actual y qué integrar después.
- [`docs/auditoria-repos-2026-11-06.md`](docs/auditoria-repos-2026-11-06.md):
  auditoría de `pixel-hedge-fund` (sin licencia; solo inspiración),
  `company-pixel-office` (MIT; idea de roster) y `FinRobot` (Apache-2.0;
  principio de cálculo determinista + narración LLM).
- [`docs/fase6_futuros_intradia.md`](docs/fase6_futuros_intradia.md): diseño de
  futuros intradía, perfil, stub ProjectX y validación parcial con ES=F/NQ=F.
- [`docs/fred_calendar.md`](docs/fred_calendar.md): verificación de FRED,
  release IDs de CPI/NFP, fechas futuras, limitación de hora y fallback stale.
- [`docs/auditoria-repos-2026-11-07.md`](docs/auditoria-repos-2026-11-07.md):
  auditoría de AutoHedge (MIT), Vibe-Trading (MIT) y FinceptTerminal (AGPL-3.0);
  qué se adoptó en la consola y qué se descartó por licencia o riesgo.
- [`docs/backups.md`](docs/backups.md): keyring, restauración verificada,
  restic vs Kopia y copia externa cifrada.
- [`docs/dependencias.md`](docs/dependencias.md): versiones verificadas y
  política de dependencias.

La Sala pixel es arte propio (HTML/CSS/SVG). No se copió código ni arte de los
repos auditados; si en el futuro se usan assets MIT, se conservará su licencia.

---

## 4. LM Studio (listo)

**Qwen3.8-27B Q4_K_M** está descargado y validado. Configuración actual
(RX 6800 = 16 GB VRAM): contexto **16.384**, parallel **1**, KV cache Q8_0,
flash attention ON, temperature 0.2, identificador `qwen3.8-27b`, TTL 24 h.

| Ajuste | Valor | Motivo |
|---|---|---|
| GPU offload | ~28-32 capas (o "max") | 27B Q4 no cabe entero; el resto va a RAM |
| Context length | **16384** | 32k baja a ~1,25 tok/s; 16k va a ~5 tok/s |
| KV cache quant | Q8_0 | ahorra VRAM |
| Flash attention | ON | velocidad |
| mmproj | no cargar | visión innecesaria, ahorra 0,9 GB |
| Temperature | 0.2 | reproducibilidad |

Arrancar servidor y cargar el modelo:

```powershell
$lms = "$env:LOCALAPPDATA\Programs\LM Studio\resources\app\.webpack\lms.exe"
& $lms server start --port 1234
& $lms load qwen3.8-27b --context-length 16384 --parallel 1 `
  --identifier qwen3.8-27b --ttl 86400 --yes
& $lms ps
.\.venv\Scripts\lab.exe llm-test
```

> El servidor no arranca solo al reiniciar Windows. Si `lab agent` falla con
> error de conexión, ejecuta los dos comandos de arriba.
>
> Con 16 GB de VRAM y 27B en Q4 espera **1-5 tok/s** según contexto y offload.
> Un run de TradingAgents multi-agente puede tardar **horas**; por eso existe el
> modo `lite` y el diseño usa el LLM 1 vez al día.

### Agente diario: `lite` vs `deep`

- **`lite` (por defecto)**: una sola llamada al LLM con un resumen técnico
  compacto (precio, retornos 1-120 d, SMA20/50/200, RSI14, ATR, máximo/mínimo
  de 52 semanas, volumen y volatilidad). Validado con NVDA: **77-95 s**.
- **`deep`**: TradingAgents multi-agente con herramientas. Tesis más larga,
  pero horas de cómputo y mucho más contexto; úsalo de noche o con un modelo
  mayor.

El rating se traduce a fracción de posición (`Buy`=1.0, `Overweight`=0.5,
`Hold`=no tocar, `Underweight`/`Sell`=0). `agent-run` aplica ese tamaño con el
risk engine y el broker paper. La decisión y el contexto numérico quedan en
`data/agent_runs/`.

### Comparación lite vs deep (etapa 6)

Cada decisión guarda su procedencia: `decision_outcomes` añade `analysts` y
`duration_s`, y `agent_comparisons` conserva rating, confianza, objetivo,
modelo, hash de prompt, duración y errores saneados de ambas fuentes.

```powershell
lab agent-compare SPY
lab agent-compare SPY --date 2026-01-05 --retrospective
lab agent-compare --report
lab decisions report
```

- Solo se compara el día actual; una fecha pasada exige `--retrospective` y
  queda **excluida** del reporte forward.
- Si el run con todos los analistas falla, se prueba uno a uno y se usa el
  primero que funcione. El reporte muestra acuerdo, matriz lite→deep,
  diferencia media de objetivo y estadísticas por fuente.
- Con menos de **30 comparaciones** el resultado se marca como **muestra
  insuficiente**; sin retornos a 20 días se muestra “sin datos”, no cero.
- `scripts/deep_compare_nightly.ps1` rota un activo por noche. La tarea
  **`TradingLab-DeepCompare`** quedó registrada el 2026-11-09 a las 02:30
  (estado `Ready`); solo mide, no envía órdenes ni activa bots.

Evidencia: `pytest tests/test_agent_compare.py tests/test_decisions.py
tests/test_scripts.py -q` → **19 passed**; suite completa **474 passed**;
`ruff` limpio; `lab doctor` OK con WARN conocidos. No se lanzó ningún deep
real: los tests usan runners simulados.

### Validación de esquema y comparación de modelos (etapa 5)

- `chat_json` valida el subconjunto de JSON Schema usado por los agentes
  (objetos, arrays, enums, requeridos, tipos, rangos y campos extra). El
  resultado queda en `llm_calls.schema_ok`/`schema_error`, sin guardar el texto
  completo del modelo.
- `lab llm status` muestra llamadas validadas, fallidas y los últimos errores
  por modelo. Un fallo de esquema no se convierte en una decisión válida.
- `lab llm compare TICKER --models actual,candidato` ejecuta dos modelos lite
  con el mismo prompt y fecha. Guarda rating, confianza, duración, hashes y
  errores saneados en `lite_model_comparisons`; **no cambia el modelo por
  defecto**. `lab llm report` agrega acuerdo y confianza; con menos de 30
  comparaciones marca muestra insuficiente.
- La comparación real contra un MoE ~30B queda pendiente: LM Studio solo tiene
  cargado `qwen/qwen3.8-27b` y un modelo de embeddings.

```powershell
lab llm status
lab llm compare SPY --models qwen/qwen3.8-27b,moe-30b
lab llm report
```

---

## 4b. Información continua (`intel`)

Fase 4: RSS de Yahoo Finance y Finnhub, saneado y almacenado en SQLite. **No
hay herramientas de ejecución en esta capa** y todo el texto entra como
`trusted=false`.

```powershell
.\.venv\Scripts\lab.exe intel fetch --retries 2
.\.venv\Scripts\lab.exe intel finnhub --limit 20
.\.venv\Scripts\lab.exe intel score --limit 20 --batch-size 8
.\.venv\Scripts\lab.exe intel status
.\.venv\Scripts\lab.exe intel providers --check
.\.venv\Scripts\lab.exe intel fred --days 90
.\.venv\Scripts\lab.exe intel calendar
```

- `news_items`: URL, fuente, hora UTC, hash, título/resumen recortados.
- `news_scores`: sentimiento (-1..1) y relevancia (0..1) por noticia, modelo y
  versión. El scoring con Qwen usa el texto delimitado como no confiable y es
  idempotente; una respuesta inválida no genera puntuaciones inventadas.
- `macro_events`: FRED + eventos manuales. El guard usa `news_blackout_min`
  sobre esta tabla.
- **RSS**: reintentos con backoff solo para 429/5xx/red; 401/404 no se
  reintentan. Si todas las fuentes fallan, `lab intel fetch` devuelve error.
- **Finnhub** es el proveedor alternativo. `lab intel providers --check` valida
  la clave con una lectura de SPY sin imprimirla. OpenBB no está instalado y no
  se añade como dependencia.
- **Decisión FinBERT:** no se incorpora. `ProsusAI/finbert` tiene licencia
  **CC-BY-NC-SA 4.0** (no comercial); el análisis se hace con Qwen.
- `wrap_untrusted()` delimita el texto y ordena al LLM no seguir instrucciones
  contenidas; hay test de prompt injection.
- Tarea **`TradingLab-Intel`** a las 07:10; logs en `logs/intel/`.

`scripts/intel_daily.ps1` acepta `-Finnhub` y `-Score`; la tarea registrada
actual no los activa, así que la ingesta RSS sigue igual hasta que se cambie
manualmente. El modelo de scoring se toma de `config/intel.yaml`
(`qwen/qwen3.8-27b`) sin cambiar el default de `lab.yaml`.

Verificación real del 2026-11-09: Finnhub respondió `ok`, se guardaron 10
noticias nuevas y `lab intel score --limit 2 --model qwen/qwen3.8-27b` puntuó
3/3 sin inválidas ni ausentes. Quedaron 88 pendientes; latencia real 62-96 s
por lote.

### FRED y calendario macro

`lab intel fred` sincroniza CPI y Employment Situation (NFP) desde FRED y
guarda los eventos en `macro_events` con impacto `high`:

- La clave se lee de keyring/.env (`FRED_API_KEY`); **nunca se imprime**.
- Los `release_id` se descubren por nombre con `/fred/releases`; no están
  inventados. Observado el **2026-11-07**:
  - **CPI = 10**
  - **Employment Situation (NFP) = 50**
- Las fechas se leen con `/fred/release/dates` y
  `include_release_dates_with_no_data=true`.
  - **Con** el flag aparecen fechas futuras: CPI 2026-11-10 y 2026-12-10;
    NFP 2026-12-04 (observado el 2026-11-07).
  - **Sin** el flag, FRED devuelve solo fechas históricas: desaparecen las
    programadas futuras. Por eso el flag es obligatorio.
  - FRED devuelve **solo fecha**, no hora. Para el guard se usa la convención
    operativa **08:30 America/New_York** (hora habitual de estos releases);
    es una convención documentada, no un campo de FRED.
- Caché local en `data/cache/fred/` (12 h), rate limit de 0,6 s entre
  peticiones (100/min, por debajo de las 120/min de FRED) y deduplicación en
  `macro_events`.
- Si FRED falla, se usan los eventos guardados y se devuelve estado `stale`.
  Si no hay guardados, también es `stale` con 0 eventos: **nunca se interpreta
  como “sin eventos”**.
- **FOMC sigue siendo manual**: se copia del calendario oficial de la Reserva
  Federal (<https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm>) y
  se inserta con `lab intel event FOMC --at ...`.

- Fase 4: scoring Qwen, reintentos por fuente y Finnhub implementados. OpenBB
  no se instala; si se necesita, se evaluará en un venv separado.

---

## 4c. SEC EDGAR (`lab sec`)

Cliente de solo lectura para `data.sec.gov`:

- **User-Agent obligatorio** con contacto (`SEC_USER_AGENT`); sin él no se hace
  ninguna petición.
- **Rate limit** de 4 req/s (0,25 s entre peticiones), por debajo del máximo.
- **Caché local** en `data/cache/sec/`; si SEC falla y hay caché se devuelve
  `stale`, nunca datos inventados.
- **Estados explícitos**: `ok`, `empty` (respuesta válida sin filings/facts),
  `unconfigured`, `error`, `stale`, `not_found`.
- Resuelve **CIK/ticker** con `company_tickers.json`.
- Extrae **10-K, 10-Q y 8-K** de `submissions` y facts XBRL de `companyfacts`
  (Revenues, NetIncomeLoss, Assets, Liabilities, Equity, Cash, EPS).
- Cada consulta queda en `sec_fetches` con fecha, endpoint, estado, HTTP y caché.

```powershell
lab sec status
lab sec cik NVDA
lab sec filings NVDA --limit 10
lab sec facts NVDA
```

> Si SEC no responde, el comando termina con error o `stale`; no interpreta la
> falta de datos como “sin noticias” ni inventa cifras.

---

## 5. Alpaca paper (conectado)

Las claves paper ya están en `.env` y el adaptador está validado:

- `lab doctor` → `Alpaca OK · paper=True · equity=100.000 · ACTIVE`.
- Para usarlo como broker de acciones, cambia en `config/lab.yaml`
  `execution.broker: alpaca` (y deja `mode: paper`).
- Alpaca solo opera acciones/ETF de EE.UU.; el forex va por MT5 y los futuros
  por ProjectX/Tradovate.

Salvaguardas del adaptador: `mode: live` exige además `ALLOW_LIVE=YES`.
`PaperBroker` (simulador local) sigue siendo el broker por defecto y el
recomendado para validar lógica antes de tocar Alpaca.

> Las claves son de paper: no mueven dinero. Aun así, no las publiques ni las
> subas a git. Si alguna vez generas claves live, trátalas como dinero.

### TradeStation SIM (preparado, esperando API Key)

TradeStation será la alternativa a IBKR para acciones/ETF, opciones y futuros.
Su WebAPI v3 tiene un entorno SIM real:

```text
https://sim-api.tradestation.com/v3
```

El adaptador ya está en **solo lectura**: refresh OAuth, cuentas, balances,
posiciones y quotes. `lab tradestation setup` guarda Client ID, Client Secret,
refresh token y Account ID en **keyring**; `lab tradestation auth-url` genera la
URL OAuth y `lab tradestation exchange` intercambia el código por un refresh
token sin imprimirlo. `status`, `accounts` y `positions` comprueban la conexión.
Las funciones de órdenes solo responden `dry_run` y no envían nada.

Bloqueado hasta que soporte TradeStation habilite la API Key. La cuenta de
trading por sí sola no basta. No se asume forex en esta API; para FX/CFD se
mantiene MT5 demo.

---

## 6. Forex, MT5 y cuentas de fondeo (FTMO)

### Conexión

El adaptador se conecta al terminal que ya esté abierto (validado con Darwinex Demo).
Requisitos: terminal abierto, sesión iniciada y **Algo Trading** activado.

```powershell
.\.venv\Scripts\lab.exe mt5 status     # cuenta, margen, permisos y desfase del servidor
.\.venv\Scripts\lab.exe mt5 price EURUSD
```

Credenciales opcionales en `.env` si quieres que el bot abra el terminal solo:

```
MT5_LOGIN=...
MT5_PASSWORD=...
MT5_SERVER=Darwinex-Demo
MT5_PATH=C:\Program Files\Darwinex MetaTrader 5\terminal64.exe
MT5_REQUIRE_DEMO=1
```

> Al pasar a la demo de FTMO hay que cambiar `MT5_LOGIN` y `MT5_SERVER` a los
> de esa cuenta. Si no coinciden, el guard rechazará la orden (es lo deseado).

### Guard de identidad (antes de cada orden)

Idea adoptada de Vibe-Trading. El adaptador **rechaza la cuenta** si no es la
esperada, en vez de limitarse a avisar:

- si `MT5_LOGIN` está definido, el login real debe coincidir;
- si `MT5_SERVER` está definido, el servidor debe coincidir;
- con `require_demo: true` (por defecto) una cuenta **real** se rechaza aunque
  `ALLOW_LIVE=YES` esté puesto;
- la comprobación se repite justo antes de `order_send`, por si la cuenta
  cambió en caliente.

`lab mt5 status` muestra `identity_ok`. Cerrar posiciones no pasa por el guard:
en una emergencia, bloquear un cierre sería peor que el riesgo de identidad.
Además, `lab mt5 run` **aplana toda la cuenta** si detecta que el equity ya
cruzó el suelo efectivo: bloquear órdenes nuevas no protege una posición abierta.

### Hora del servidor (crítico)

Los servidores MT5 **no van en UTC**: muchos usan GMT+2 en invierno y GMT+3 en
verano. El adaptador autodetecta el desfase comparando un tick fresco con UTC y
convierte velas, posiciones y deals a UTC real. Un **tick viejo ahora se
rechaza** (antes podía producir un offset negativo falso con el mercado
cerrado). Se puede fijar a mano con `mt5.server_utc_offset_hours`.

El offset se detecta al conectar y se guarda en `data/cache/mt5_offset.json`
(por servidor y login). Con el mercado cerrado, si no hay tick fresco, se usa
el último offset conocido; si tampoco existe, `mt5 status` lo marca como
`unknown` y los históricos piden configurarlo a mano. Un proceso de larga
duración debe reconectar después de un cambio de hora. El reset diario de FTMO
no usa ese offset: se calcula con `Europe/Prague` y `tzdata`, y está cubierto
por tests a ambos lados de los cambios de hora de EE. UU. y Europa
(`tests/test_timezone.py`).

### Motor de reglas (`prop/`)

`config/prop.yaml` define firma, fase y límites. **Es una plantilla**: verifica
cada valor en el contrato vigente de tu firma.

`PropGuard.evaluate()` devuelve `allowed=False` cuando una orden rompería:

- límite de pérdida diaria (sobre balance o equity, según firma);
- pérdida máxima (`static`, `trailing_eod` o `trailing_intraday`);
- objetivo de beneficio alcanzado (deja de abrir riesgo);
- máximo de lotes, posiciones o riesgo abierto;
- consistencia (aviso, no bloqueo, porque se aplica al payout);
- **blackout de noticias** (`news_blackout_min`): bloquea aperturas dentro de
  la ventana antes/después de un evento de alto impacto en `macro_events`;
- **fin de semana** (`weekend_holding=false`): bloquea aperturas desde el corte
  del viernes y exige aplanar antes del cierre;
- **rollover** (`rollover_blackout_min`): bloquea aperturas alrededor del cierre
  diario del servidor en futuros/CFD.

### Perfiles y guard de cuenta

`config/profiles.yaml` define `swing_equity`, `intraday_fx` e
`intraday_futures` con temporalidad, horario, riesgo máximo por operación,
máximo de operaciones diarias y criterios mínimos de validación. Cada bot de
`config/bots.yaml` declara su `profile`; **sin perfil no se ejecuta**.

`evaluate_account()` suma el riesgo abierto de todos los bots de la misma
cuenta y el riesgo propuesto antes de cada apertura, además de las pérdidas
agregadas del día. Cerrar o reducir siempre está permitido. El informe
`horizons.json` incluye la matriz de correlación diaria entre bots y avisa de
los pares con |correlación| > 0,7.

`lab research-clusters` agrupa esos pares y aplica un presupuesto por clúster
(`max_cluster_risk_pct`, 1% por defecto). En el top 10 actual, **9 de 10
variantes caen en un mismo clúster**; el panel Research muestra los clústeres y
el guard rechaza aperturas que superen el presupuesto agregado. `trend-spy` y
`qqq-trend-f13` están en el clúster estático **`trend_equity`**: no se ejecutan
ambos como apuestas independientes. Es informativo para seleccionar bots, no
activa nada.

`friday_cutoff_hour` se interpreta en la zona local de la firma
(`reset_tz`, por defecto `Europe/Prague`) y cubre los cambios de hora. Cerrar o
reducir posiciones **nunca** se bloquea, ni por calendario ni por sesión.

El `buffer_pct` (10%) hace que el bot pare antes del límite real: de 5.000 USD
diarios de FTMO solo usa 4.500.

```powershell
.\.venv\Scripts\lab.exe prop rules
.\.venv\Scripts\lab.exe prop status --from-mt5
.\.venv\Scripts\lab.exe prop size EURUSD --risk-pct 0.005 --stop-pips 20
.\.venv\Scripts\lab.exe prop simulate SPY --strategy trend --phase challenge
```

El sizing **no** usa porcentaje del nocional: usa
`lotes = riesgo_$ / (distancia_stop × valor_del_tick)`, redondeando siempre hacia
abajo al step del bróker.

### Bot de forex

```powershell
# 1) señales y sizing sin enviar nada
.\.venv\Scripts\lab.exe mt5 run EURUSD --timeframe H1 --strategy trend-ls

# 2) enviar (demo)
.\.venv\Scripts\lab.exe mt5 run EURUSD --timeframe H1 --strategy trend-ls --execute
```

Flujo: velas H1 del terminal → señal long/short → ATR → sizing → **guard de
fondeo** → orden con SL/TP. Si el guard bloquea, no se envía.

### Advertencias

- Muchas firmas permiten bots pero prohíben HFT, latencia y tick scalping. Verifica.
- FTMO resetea a las 00:00 de Praga; el servidor MT5 suele ir 1 h por delante.
- **F11b implementado:** `news_blackout_min` (eventos altos de `macro_events`),
  `weekend_holding` + `friday_cutoff_hour` (hora de Praga) y
  `rollover_blackout_min` (cierre diario de futuros/CFD). Los valores de FTMO
  están en `config/prop.yaml`; verifícalos en el contrato. Cerrar/reducir
  siempre está permitido.
- `ALLOW_LIVE=YES` sigue siendo obligatorio para cuentas reales.

---

## 6b. Futuros (ProjectX / TopstepX)

Firma elegida: **Topstep** (50K para empezar), porque es la única con API oficial
documentada. Apex prohíbe la automatización y MFFU no tiene API oficial. El
análisis completo está en `reports/futures/firms.md`.

### Credenciales

```
PROJECTX_USERNAME=...
PROJECTX_API_KEY=...
PROJECTX_ACCOUNT_ID=...
PROJECTX_REQUIRE_SIMULATED=1
```

La API key se genera en el dashboard de TopstepX. El adaptador no guarda
contraseñas y exige una cuenta **simulada** por defecto.

### Comandos

```powershell
.\.venv\Scripts\lab.exe futures status
.\.venv\Scripts\lab.exe futures contracts NQ
.\.venv\Scripts\lab.exe futures order MNQ --side buy --size 1 `
    --stop-loss-ticks 40 --take-profit-ticks 80        # dry-run: solo valida

.\.venv\Scripts\lab.exe futures positions
.\.venv\Scripts\lab.exe futures close <contract_id>    # dry-run
```

Para enviar de verdad hay que añadir `--execute`. Una cuenta real exige además
`require_simulated: false` y `ALLOW_LIVE=YES`.

### Reglas operativas

- Topstep **no permite VPS/VPN** para el flujo de órdenes: el bot corre en este PC.
- Un contrato activo por símbolo; nunca contratos vencidos.
- Stop obligatorio en ticks; sin stop no se envía la orden.
- El guard debe bloquear aperturas cerca del MLL, pero **permitir cerrar**.
- Consistencia 55%: el mejor día no puede superar ese porcentaje del beneficio
  total al pedir payout.
- Preset **Topstep 50K** añadido en `config/prop.yaml` como plantilla inactiva
  (`enabled: false`, `template: true`); no cambia la firma activa FTMO. Verifica
  cada valor en el contrato vigente antes de usarlo.
- Pendiente: descarga de barras vía `/api/History/retrieveBars` para backtest
  de futuros.

---

## 6c. Intradía forex/CFD (`lab mt5 fetch` / `lab research-intraday`)

La etapa **9.5 se reabrió y corrigió**. `MT5Broker.rates` ya no resta un offset
global: infiere el offset de cada semana desde los bordes de sesión y aplica el
offset de cada barra. El método está en `execution/mt5_offsets.py`:

- Para cada semana ISO toma la primera barra (apertura del domingo) y la última
  (cierre del viernes) en hora de servidor.
- Las compara con la apertura/cierre de **17:00 America/New_York**; de ahí sale
  el offset, redondeado a media hora.
- Confirma el cambio contra las transiciones de EE. UU.: apertura semanal
  **22:00 UTC** con GMT+2 y **21:00 UTC** con GMT+3.
- Rellena semanas festivas/incompletas con el tramo detectado más cercano.
- `lab mt5 fetch` imprime los tramos y guarda
  `data/cache/mt5/EURUSD_<TF>.offsets.json`.

`lab mt5 spec` verificó el 2026-11-09 las especificaciones reales de
**XAUUSD** (tick 0,01; contrato 100; volumen mínimo 0,01) y **US100.cash**
(tick 0,01; contrato 1; volumen mínimo 0,01), con `trade_mode=4` y
`filling_mode=3`. La API Python de MT5 no expone horarios de sesión: el
`24/5 UTC` del catálogo es una referencia, no una verificación del bróker.

Datos corregidos:

- **M15**: 50.000 barras, 2024-11-04 01:45 → 2026-11-08 23:45 UTC; 5 tramos
  (+2/+3).
- **H1**: 20.000 barras, 2023-08-21 14:00 → 2026-11-08 23:00 UTC; 8 tramos.
- Parquet UTC, ordenado, sin duplicados, `NaN` en cierre ni OHLC inválido.
- Spread real: mediana 1 punto M15 / 2 puntos H1; `spread_reliable=True`.

El informe anterior, generado con offset constante, queda conservado como
**no fiable: offset constante** en
`reports/research/intraday_offset_constante.json` y `.md`; no se borró.

Validación por activo (etapa 3), con coste conservador y DSR global:

| Activo | Barras | Familias | n_trials DSR | PBO | WF | Pasan | Mejor neto | Equilibrio | Calibrado |
|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 50.000 | range_reversal, london_pullback | 57 | 0,0 % | fallido | 0/24 | −5,86 | 0,23 bps | 3,07 bps |
| USDJPY | 50.000 | session_trend, tokyo_breakout | 81 | 2,1 % | fallido | 0/24 | −4,03 | 0,14 bps | 2,28 bps |
| XAUUSD | 50.000 | asian_rev, overlap_breakout | 93 | 8,5 % | fallido | 0/12 | −0,23 | 1,61 bps | 2,08 bps |
| US100.cash | 50.000 | orb_ny, trend_intraday | 117 | 37,2 % | fallido | 0/24 | −0,28 | 1,57 bps | 2,01 bps |

**Ningún activo pasa.** XAUUSD y US100.cash se acercan al equilibrio, pero el
coste calibrado sigue por encima del coste de equilibrio; US100 además supera
el PBO máximo (37,2 % > 30 %). No se relajó ningún umbral.

- Comisiones oficiales: Forex (EURUSD/USDJPY) **2,50 USD/lote/lado**
  (0,217/0,250 bps), metales (XAUUSD) **0,0007 % del volumen/lado**
  (0,070 bps) e índices (US100.cash) **0**; fuentes FTMO “Trading Update |
  25 Sep 2025” y “Zero Commissions on Indices” (2025-08-01/2025-11-04).
- Spread real por hora medido por activo; slippage explícito **0,5/2,0 bps
  por lado** (optimista/conservador).
- Coste de equilibrio y tabla Sharpe a **0/0,5/1/2/3 bps** en cada
  `reports/research/intraday_<ACTIVO>/intraday.md` y en Research.
- Cada una de las **84 variantes nuevas** quedó en `strategy_trials`; el
  contador único DSR terminó en **117** pruebas. El barrido EURUSD inicial
  (orb/pullback/asian_rev, 0/28, −6,78) queda como histórico registrado y su
  diagnóstico zero-cost (+1,34 bruto) no se usa para aprobar.
- Alineación de sesiones verificada: aperturas semanales 22:00/21:00 UTC
  (forex) y 23:00/22:00 UTC (metales/índices).

No se relajó ningún umbral, no se activó ningún bot y no se enviaron órdenes.
Un candidato solo avanza con el escenario conservador; 0 bps es diagnóstico.

```powershell
# datos corregidos por periodo (M15 de los 4 activos)
lab mt5 fetch EURUSD --timeframe M15 --bars 50000
lab mt5 fetch USDJPY --timeframe M15 --bars 50000
lab mt5 fetch XAUUSD --timeframe M15 --bars 50000
lab mt5 fetch US100.cash --timeframe M15 --bars 50000

# informe por activo
lab research-intraday --symbol EURUSD --timeframe M15 --out reports/research/intraday_EURUSD
lab research-intraday --symbol USDJPY --timeframe M15 --out reports/research/intraday_USDJPY
lab research-intraday --symbol XAUUSD --timeframe M15 --out reports/research/intraday_XAUUSD
lab research-intraday --symbol US100.cash --timeframe M15 --out reports/research/intraday_US100

# diagnóstico de costes (no usar para aprobar)
lab research-intraday --symbol EURUSD --timeframe M15 `
  --commission-bps 0 --slippage-bps 0 --slippage-optimistic-bps 0 `
  --zero-spread --out reports/research/intraday_zero_costs
```

- Cachea velas ya corregidas a UTC en `data/cache/mt5/EURUSD_M15.parquet`.
- `config/costs.yaml` contiene la comisión oficial por activo y el supuesto de
  slippage. Si falta la comisión de un activo, se marca **sin verificar** y no
  se inventa: `run_intraday` no continúa con ese símbolo.
- Modela spread por hora desde la columna `spread`. Si no hay spread realista,
  marca `spread_reliable=false` y los resultados como **no confiables**.
- Estrategias: ruptura de rango de apertura (Londres/NY), tendencia con
  retroceso y reversión del rango asiático; cada una con rejilla acotada.
- Pasa por DSR, PBO, walk-forward y regímenes con los mismos umbrales; reporta
  trades y cuántas pasan (puede ser cero). Monte Carlo a 22/44/120 días.

Evidencia: `pytest tests/test_mt5_offsets.py tests/test_intraday.py -q` →
**15 passed**; suite completa **428 passed**; `ruff` limpio; `lab doctor` OK.
Los tests sintéticos cubren el cambio de hora de EE. UU. (offset +2/+3), que
una sesión de 08:00 UTC siga siendo 08:00 UTC y el coste de equilibrio.

Futuros intradía: perfil definido y proveedor ProjectX como **stub**; no se
implementa descarga de pago. Ver `docs/fase6_futuros_intradia.md`.

### Cementerio de estrategias y presupuesto (etapa 1)

Todo lo que se prueba queda registrado en la tabla `strategy_trials`, **también
lo fallido**:

| Campo | Contenido |
|---|---|
| `family` | familia de estrategia (`ORB`, `PULLBACK`, `ASIAN_REV`…) |
| `hypothesis` | por qué debería funcionar |
| `symbol` | activo probado |
| `params` | parámetros exactos |
| `ts` / `window_start` / `window_end` | fecha y ventana evaluada |
| `result` | métricas, DSR, PBO, WF, régimen y curva de costes |
| `outcome` / `reason` | `passed`/`failed` y **motivo de descarte** |
| `source` / `run_id` / `lesson_id` | origen, pasada y lección asociada |

- El **contador único del DSR** (`count_tests`) suma lecciones, trials de
  Optuna, lecturas del holdout, cada fila de `strategy_trials` y los bots
  incubados. Después del barrido EURUSD M15 pasó de 5 a **33** pruebas.
- **Aviso de reoptimización**: si la familia ya se descartó sobre la misma
  ventana, `lab research-intraday` avisa antes de repetir.
- **Presupuesto semanal por activo**: `config/research_budget.yaml`
  (5 intentos por activo y semana ISO). Agotado, el comando se detiene salvo
  `--force`.
- **Hipótesis nuevas**: nacen en `lessons` como `proposed` (`lab lessons add
  --author qwen|humano`); Qwen solo redacta y nunca ejecuta.

```powershell
lab research-trials              # cementerio, presupuesto y contador DSR
lab research-trials --symbol EURUSD --limit 50
```

Evidencia: `pytest tests/test_trials.py tests/test_intraday.py -q` → **18
passed**; suite completa **436 passed**; `ruff` limpio; `lab doctor` OK;
`lab f13 config-check` OK antes y después de la etapa (hash
`54b420360f17c75d…` sin cambios).

### Universo intradía y bots declarados (etapa 2)

El perfil `intraday_fx` queda limitado a cuatro activos. Los nombres exactos
se **descubren en MT5** y se guardan en la tabla `asset_aliases`:

| Canónico | Símbolo broker | Clase |
|---|---|---|
| NASDAQ | `US100.CASH` | índice |
| XAUUSD | `XAUUSD` | metales |
| EURUSD | `EURUSD` | forex |
| USDJPY | `USDJPY` | forex |

```powershell
lab mt5 aliases     # descubre y guarda los alias (solo lectura de mercado)
```

- El guard rechaza **aperturas** de cualquier otro símbolo en `intraday_fx`,
  tanto en el orquestador como al previsualizar una orden del modo operador.
  **Cierres y reducciones nunca se bloquean.**
- `config/intraday_bots.yaml` (nuevo) declara **8 bots** con
  `enabled: false`, `profile: intraday_fx`, `timeframe: M15`, familia y
  rejilla propia por activo:
  - Nasdaq: `orb_ny`, `trend_intraday`.
  - XAUUSD: `asian_rev`, `overlap_breakout`.
  - EURUSD: `range_reversal`, `london_pullback`.
  - USDJPY: `session_trend`, `tokyo_breakout`.
- `load_bots` carga `bots.yaml` **más** `intraday_bots.yaml`; no se tocó
  `bots.yaml`. Los bots siguen desactivados y las familias pendientes se
  bloquean sin enviar órdenes.

Evidencia: `pytest tests/test_asset_aliases.py tests/test_intraday_bots.py -q`
→ **7 passed**; suite completa **443 passed**; `ruff` limpio; `lab doctor` OK;
`lab f13 config-check` OK antes y después (hash `54b420360f17c75d…` sin
cambios).

Evidencia etapa 3: `pytest tests/test_intraday.py tests/test_mt5_offsets.py
tests/test_asset_aliases.py tests/test_intraday_bots.py -q` → **28 passed**;
suite completa **448 passed**; `ruff` limpio; `lab doctor` OK; `lab f13
config-check` OK (mismo hash). Sin activar bots, sin órdenes y sin relajar
umbrales.

---

## 6d. Fondo personal: cuentas, límites y panel

Objetivo: operar varias cuentas (capital propio y fondeo) con bots asignados por
perfil de activo y límites de riesgo editables desde la consola, sin tocar
`prop.yaml`, sin activar bots y sin enviar órdenes.

### Cuentas y reglas

`config/accounts.yaml` guarda la **identidad** de cada cuenta. Los límites
editables viven en SQLite (`account_limit_history`), con historial de fecha,
cuenta, campo, valor anterior, valor nuevo y origen; por eso **no cambian el
hash de F13**.

| Cuenta | Tipo | Firma / fase | Estado | Bolsillo | Diario | MaxDD | Trade | Abierto | Trades/día |
|---|---|---|---|---|---|---|---|---|---|
| `paper_main` | capital propio | — | active | swing_equity | 5.00% | 10.00% | 1.00% | 2.00% | 5 |
| `alpaca_paper` | capital propio | — | active | swing_equity | 3.00% | 8.00% | 0.75% | 1.50% | 3 |
| `ftmo_demo` | fondeo | FTMO / challenge | demo | intraday_fx | 5.00% | 10.00% | 0.50% | 2.00% | 4 |
| `topstep_template` | fondeo | Topstep / challenge | template | intraday_futures | 2.00% | 4.00% | 0.25% | 1.00% | 3 |

Reglas duras:

- **Límite efectivo = mínimo** entre el de la firma (`prop.yaml`, solo lectura)
  y el propio. Un valor propio mayor que el de la firma se rechaza.
- **Apretar** un límite es inmediato. **Aflojar** exige `--confirm`/confirmación
  explícita y aplica desde el siguiente día hábil (espera configurable).
- Con **F13 congelado o iniciado solo se permite apretar**. Aflojar se rechaza
  con un mensaje claro.
- Cerrar o reducir posiciones nunca se bloquea; el guard solo frena aperturas.
- `topstep_template` es una plantilla **inactiva**: no hay cuenta ni credenciales.

```powershell
lab fund accounts
lab fund set ftmo_demo --daily-loss 0.04
lab fund set paper_main --daily-loss 0.06 --confirm   # aflojar: siguiente día hábil
lab fund history ftmo_demo
```

### Seguridad de la consola

- Los `POST` requieren el token de `/api/session` en `X-CSRF-Token`; sin token
  válido devuelven **403**. También se valida `Host`/`Origin` y solo se acepta
  `127.0.0.1`.
- Hay una **lista blanca** de rutas de escritura (`WRITE_ROUTES`). No existe
  ningún endpoint para activar bots, cambiar `enabled`, enviar órdenes ni
  modificar los límites de la firma.
- El kill-switch global se puede **activar** desde el panel con confirmación y
  resetear con confirmación explícita; no activa bots.
- Evidencia: `pytest tests/test_web_security.py tests/test_fund_web.py -q`.

### Pestaña Fondo

Muestra por cuenta el límite de firma (solo lectura), el propio editable, el
efectivo, el uso del día, el colchón diario y de drawdown, y el historial.
Incluye kill-switch global, exposición agregada (solo notional reportado; MT5 no
publica notional por posición y no se estima) y capital por bolsillo. Los
clústeres de correlación comparan el riesgo reservado por los bots activos con
su presupuesto y avisan si lo superan.

### Resultados por perfil

La tabla también está en **Research → Resultados por perfil**.

| Perfil | Estado | Retorno | Sharpe | MaxDD | Pasa FTMO 120d | Breach | Nota |
|---|---|---|---|---|---|---|---|
| `swing_equity` | validado | 81.1% | 1.03 | -9.2% | 70.6% | 3.5% | cartera de 3 bots; 0/10 variantes frágiles a 2/20 bps |
| `intraday_fx` | validado · sin edge | — | — | — | — | — | 4 activos M15; 0/84 pasan; mejor XAU −0,23; equilibrio < calibrado; WF fallido; DSR 117 |
| `intraday_futures` | stub | — | — | — | — | — | ProjectX sin credenciales/suscripción; proxy diario ES=F/NQ=F |

### Etapa 5 completada y corregida (intradía forex/CFD)

La primera ejecución usó un offset constante y quedó marcada como **no fiable:
offset constante** (`reports/research/intraday_offset_constante.*`), sin
borrarla. La versión corregida infiere +2/+3 por semana desde los bordes
semanales y confirma las transiciones de EE. UU. (apertura 22:00 UTC en
invierno, 21:00 en verano). Datos: M15 50.000 barras y H1 20.000, spread real.

Con la conversión corregida y costes calibrados, **0/84 variantes pasan** en
los cuatro activos. El mejor Sharpe neto es **−0,23** en XAUUSD, pero su coste
de equilibrio (1,61 bps) sigue por debajo del calibrado (2,08 bps); US100.cash
queda en −0,28 con equilibrio 1,57 frente a 2,01 bps y PBO 37,2 %. EURUSD y
USDJPY son claramente negativos (−5,86 y −4,03). El walk-forward falla en los
cuatro y no se relajó ningún umbral. Solo avanza el escenario conservador; no
se activó ningún bot.

### Resumen final de decisiones

- Se eligieron **3 bots** (no 10) para los tests de concurrencia y la cartera
  simulada: bastan para probar el guard agregado, el clúster `trend_equity` y el
  presupuesto del 1% sin inflar la superficie de prueba.
- La identidad de cuentas queda en YAML; los límites editables en SQLite con
  historial. Así la consola puede editar sin entrar en el hash de F13.
- El guard siempre usa el **mínimo** firma/propio; nunca se puede ampliar un
  límite de la firma desde la consola.
- F13 está **activo en paper**; `qqq-trend-f13` tiene `enabled: true` y la
  tarea `TradingLab-F13` está registrada con primera ejecución el **lunes
  2026-11-09 a las 22:20**. El ciclo diario solo opera en paper.
- Etapa 5 (intradía forex/CFD) completada y corregida: offset por periodo,
  datos M15/H1 reales y resultado sin edge robusto; los commits ya están
  publicados en `origin/master` y con backup verificado.

---

### Presupuesto de riesgo por activo (etapa 4)

`config/risk_budget.yaml` define, por activo, el **riesgo abierto** (1,00 %),
la **rebanada inicial** por bot (0,25 %) y la **máxima** (0,50 %); el clúster
USD tiene un tope del 1,50 %.

- El guard suma el riesgo **firmado** por activo: largos positivos y cortos
  negativos se compensan. Rechaza aperturas que superen el presupuesto del
  activo, la rebanada del bot o el tope total (siempre ≤ límite efectivo
  firma/propio). **Cierres y reducciones nunca se bloquean.**
- **Clúster USD**: EURUSD largo y USDJPY corto comparten dirección; muestra la
  exposición neta y el peor caso con todos los stops.
- **Apagón de noticias**: `macro_events` filtrado por eventos USD (CPI, NFP,
  FOMC, PCE, Fed…) y BoJ/JPY para USDJPY, ventana ±30 min. Sin datos →
  “sin datos”; no se inventan eventos.
- **Rebanadas**: bajar es inmediato; subir exige operador armado y
  confirmación, se rechaza para el bot F13 congelado y queda en historial
  reversible.

```powershell
lab risk-budget status
lab risk-budget set --asset EURUSD --bot eurusd-range-reversal --slice-pct 0.001
lab risk-budget set --asset EURUSD --bot eurusd-range-reversal --slice-pct 0.002 --armed --confirm
lab risk-budget revert <history_id>
lab risk-budget news --symbol EURUSD
```

Evidencia: `pytest tests/test_risk_budget.py tests/test_intraday_bots.py -q`
→ **14 passed**; suite completa **458 passed**; `ruff` limpio; `lab doctor` OK.

### Incubadora y ciclo de vida (etapa 5)

`config/lifecycle.yaml` define la puerta y los criterios congelados. Estados:
`candidato → incubando → evaluado → promovible`, más `rechazado` y
`archivado`; **no existe ningún estado de dinero real**.

- Puerta: datacheck ok, N mínimo de operaciones, coste de equilibrio
  **≥1,5×** el calibrado y sin régimen catastrófico. Solo marca **elegible**.
- Al pasar a `incubando` se congelan ventana, trades mínimos, Sharpe forward,
  slippage máximo, deriva y brechas de guard, con hash.
- `lab lifecycle status|report`: progreso, trades, Sharpe/expectancy forward,
  slippage real vs supuesto, deriva y brechas. Al cerrar la ventana propone
  **promovible** o **rechazado**; la decisión final es humana.
- Límite de 3 bots incubando; cada uno suma una prueba al contador DSR.

```powershell
lab lifecycle status
lab lifecycle report --bot eurusd-range-reversal
```

Evidencia: `pytest tests/test_lifecycle.py -q` → **7 passed**; suite completa
**465 passed**; `ruff` limpio; `lab doctor` OK.

---

## 6e. Diario de operaciones (etapa 1)

**Solo lectura sobre `lab.db`.** No crea tablas ni escribe. Reconstruye
operaciones cerradas emparejando `fills` con `orders` y consumiendo lotes
**FIFO por `(bot, ticker)`**. Si un bróker solo registró órdenes, no hay fill o
no hay lote de entrada, se muestra **sin datos**; no se inventan precios ni PnL.
La cuenta y el perfil salen de `config/bots.yaml`; un bot desconocido deja
`account`/`profile` como `sin datos` y no se le atribuye capital.

Métricas por operación y por grupo (bot, cuenta, perfil, activo, día u hora):

- Retorno = PnL neto / capital atribuido de las cuentas presentes. Si hay
  operaciones sin cuenta, el retorno se muestra como **sin datos**.
- Win rate, profit factor, expectancy, best/worst trade y payoff.
- Sharpe/Sortino/Calmar con PnL diario y anualización 252; MaxDD sobre la curva
  de PnL acumulado. Con menos de 2 días, **sin datos**.
- Distribución de retornos por operación: min, P5, P25, mediana, P75, P95, max,
  media, desviación y histograma de 10 bins.
- Aviso explícito de muestra insuficiente si **N < 30**.

Concentración:

- Top 3 operaciones / beneficio neto y top 3 / beneficio bruto.
- Mejor día / beneficio neto, comparado con `consistency_pct` de `prop.yaml`
  (FTMO: sin regla; Topstep: 55% como plantilla, no activa).

```powershell
lab journal
lab journal --bot trend-spy --since 2026-01-01 --group-by day
lab journal --account paper_main --group-by account
lab journal --ticker SPY --until 2026-12-31
```

La pestaña **Diario** de la consola ofrece los mismos filtros (bot, cuenta,
perfil, activo, desde/hasta y agrupación), resumen, concentración, distribución,
tabla agrupada y las últimas operaciones cerradas.

Evidencia: `pytest tests/test_journal.py -q` → **7 passed**;
`lab journal` sobre el `lab.db` actual → “sin datos: no hay operaciones
cerradas” (1 fill abierto, 0 ventas), sin escribir en la base.

---

## 6f. Modo operador (etapa 7)

La consola puede operar **solo paper/demo**, y solo cuando está **armada**.

- **Desarmada por defecto.** Armar exige PIN verificado con el keyring del
  sistema (`lab operator pin`), caduca a los 15 min (`operator.arm_minutes`) y
  se desarma al reiniciar el servidor. El PIN tiene **6–12 dígitos**; uno corto
  antiguo no se borra, pero `lab operator status` avisa de que debe rotarse. El
  PIN nunca se escribe en `.env`, logs ni auditoría.
- **Bloqueo persistente:** los fallos y el bloqueo por `operator.max_pin_attempts`
  / `operator.lock_seconds` viven en SQLite (`operator_pin_state`), así que
  sobreviven a reinicios del servidor y se comparten entre procesos.
- **Solo si está armada:** ejecutar el orquestador de un bot, enviar una orden
  paper/demo, cerrar posición, aplanar cuenta y activar/desactivar un bot.
- **Rechazo duro** si `mode=live`, si la cuenta no es `paper/demo/simulated` o
  si `MT5 require_demo=False`. La consola no puede cambiar `ALLOW_LIVE`.
- **Dos pasos:** el preview muestra cuenta, símbolo, lado, tamaño, precio, SL,
  riesgo %, equity y colchón restante; devuelve un token de **un solo uso** que
  caduca en 60 s (`operator.confirm_seconds`). Si cambia el precio o el estado,
  el token no coincide y hay que previsualizar de nuevo.
- **Mismos guards que la CLI:** `evaluate_account`, límites efectivos,
  kill-switch, blackout de noticias y guard de identidad del bróker. Cerrar o
  reducir nunca se bloquea, ni siquiera con el kill-switch activo.
- **Kill-switch:** activar siempre está permitido; resetear exige confirmación
  + PIN. No se puede resetear desde una petición sin PIN.
- **Activación de bots:** `bot_runtime_state` + `bot_runtime_history` en SQLite,
  sin editar `config/*.yaml`. `enabled` efectivo = YAML **AND** runtime. Si F13
  está congelado o iniciado, su bot no se puede activar ni modificar desde la
  consola y el hash de F13 no cambia.
- **Auditoría:** `console_actions` guarda acción, parámetros saneados, resultado,
  hora y OK/NO. Se ve en **Operador → Auditoría** y en **Registros**. Nunca
  guarda PIN ni tokens.
- **Rechazo de origen no-UI:** además de CSRF, Host/Origin y lista blanca, los
  endpoints `/api/operator/*` exigen `X-Operator-Client: console`; no hay
  endpoints para contenido del LLM/noticias, ejecución de código, copy trading
  ni conexiones EA.

**La consola NO puede:** operar en live, cambiar `ALLOW_LIVE`, editar YAML,
activar el bot de F13 congelado/iniciado, resetear el kill-switch sin PIN,
ejecutar código, crear bots con IA, hacer copy trading ni conectar EAs. Si
`f13.status` falla, el bot se considera **bloqueado** y el error saneado queda
en `console_actions`.

```powershell
lab operator pin       # guarda/rota el PIN en keyring (entrada oculta)
lab operator status    # PIN, mode y enabled efectivo por bot
```

Evidencia: `pytest tests/test_operator.py -q` → **17 passed**; cubre sin armar
(403), PIN corto/bloqueo persistente, live/plantilla rechazadas, orden fuera de
límite, cierre con kill-switch activo, token caducado/reutilizado, F13 intacto y
auditoría sin secretos.

---

## 6g. Shell de consola y dashboard

La barra lateral es oscura, **colapsable** (icono-only) y recuerda el estado en
`localStorage`. Agrupa todas las vistas existentes en seis secciones:

| Sección | Vistas |
|---|---|
| **Principal** | Dashboard, Mercado, Activo |
| **Laboratorio** | Bots, Incubadora, Research, Agentes |
| **Portafolios** | Cuentas, Fondo, Diario |
| **Riesgo y fondeo** | Riesgo, Operador |
| **Inteligencia** | Sala, Decisiones |
| **Sistema** | Repos, Registros |

El **Dashboard** mantiene la curva de equity, pipeline, calendario macro,
sistema, agentes y órdenes, y añade:

- **Tarjetas KPI** con equity, cash, posiciones, retorno, PnL del mes, MaxDD y
  llamadas LLM. Si falta un dato: **Sin datos**.
- **Distribución de balance**: barra cash vs posiciones y, si hay equity
  reportado, desglose por cuenta (Fondo).
- **Top performers**: bots evaluados ordenados por Sharpe, con retorno, MaxDD y
  trades. Sin evaluaciones → **Sin datos**.
- **Calendario mensual de PnL**: deriva el PnL diario de los cierres de equity,
  permite mes anterior/siguiente y marca días positivos/negativos. Sin al menos
  dos cierres diarios → **Sin datos**.

No hay CDNs, frameworks, logos ni textos de terceros; solo HTML/CSS/JS propio,
stdlib y `127.0.0.1`. Se conservan todas las pestañas, rutas, CSRF, Host/Origin
y la lista blanca `WRITE_ROUTES`.

### Rediseño visual v3

**Etapa 1 · Tokens y barra HUD.** Paleta grafito, acento cian y colores
semánticos separados para ganancia (`--positive`), pérdida (`--negative`) y
alerta (`--alert`); radios, sombras y espaciado como variables. Números
`tabular-nums` con monoespaciada del sistema y etiquetas en mayúsculas. La barra
HUD queda fija arriba con modo PAPER, sesión/reloj de Praga, LED de kill-switch,
estado F13, salud de datos y operador armado con cuenta atrás; mientras el
operador está armado, un borde ámbar recorre toda la consola. Todos los datos
salen de `/api/overview` y `/api/operator` ya existentes: no se añadió ninguna
ruta ni endpoint.

Inventario congelado en [`docs/ui_inventory.json`](docs/ui_inventory.json):
17 vistas, 267 ids, 34 llamadas `/api/*`, 6 secciones y 17 pestañas. El test
`test_inventario_ui_base_sigue_completo` falla si desaparece una vista, pestaña,
id o llamada; las dos vistas nuevas se añadieron sin retirar ninguna anterior.
Capturas Chrome de las 15 pestañas originales antes/después en
`reports/ui/` (ignorado por git).

Evidencia: `pytest tests/test_console_shell.py -q` → **5 passed**; suite completa
**410 passed**; `ruff` limpio; `lab doctor` OK.

### Etapa 7 · Activo, incubadora y lite/deep

- **Activo** unifica en una ficha el precio de la caché local, tendencia, bots
  asignados (con última señal y Sharpe), decisiones lite/deep y ciclo de vida.
  Los alias `US100.cash`/`NASDAQ` y `GOLD`/`XAUUSD` se agrupan; si no hay
  parquet, el precio se muestra como **Sin datos**.
- **Incubadora** muestra estados, progreso, trades, Sharpe forward, deriva,
  brechas, propuesta y el historial `lifecycle_events`. Es solo lectura: no
  activa bots ni envía órdenes.
- **Agentes** etiqueta cada run como `lite` o `deep`, muestra sus analistas y
  añade acuerdo, matriz lite→deep y tabla por fuente. **Decisiones** añade el
  desglose por fuente con N total y N con retorno a 20 días.
- No se añadió ninguna ruta `/api/*`: la vista usa `/api/overview` y
  `/api/market`; `overview` incorpora `lifecycle` y `agent_comparisons`.

Evidencia: `pytest tests/test_web.py tests/test_console_shell.py
tests/test_console_js.py tests/test_agent_compare.py tests/test_lifecycle.py -q`
→ **46 passed**; suite completa **477 passed**; `ruff` limpio; `lab doctor` OK
con WARN conocidos; `lab f13 config-check` OK (hash sin cambios).

**Etapa 2 · Componentes.** Tarjetas KPI con delta y mini-sparkline de series
reales (equity, retorno, PnL y drawdown; “sin serie” cuando el payload no
trae historial). Gauges de colchón diario, colchón de drawdown y salud de
cuenta, con la marca del límite y los datos de `fund.accounts[].usage` y
`fund.health`; sin datos → **Sin datos**. Chips de estado con icono además de
color. Tablas con cabecera fija y densidad cómoda/compacta persistida en
`localStorage` con `try/catch`. Skeletons iniciales, punto de pulso al
refrescar y transición corta al cambiar un número; todo desactivado con
`prefers-reduced-motion`.

Evidencia: `pytest tests/test_console_shell.py -q` → **6 passed**; suite completa
**411 passed**; `ruff` limpio; `lab doctor` OK. Capturas de las 15 pestañas en
`reports/ui/stage2` y diff en `reports/ui/stage2_diff.json`.

**Etapa 3 · Gráficas SVG.** La curva de equity usa SVG propio con área
degradada cian, cruz de lectura, marcas de operaciones reales y bandas de
régimen si el payload las trae. Si no hay bandas históricas, la leyenda dice
**Sin datos de régimen histórico** y no se dibuja nada inventado. El PnL diario
y la correlación entre bots son mapas de calor con escala divergente
ámbar/cian apta para daltónicos; la correlación resalta los pares por encima
del umbral. Fuentes: `overview.account.equity_curve`, `overview.account.orders`,
`overview.regime` y `overview.research.horizons.correlations`.

Evidencia: `pytest tests/test_console_shell.py -q` → **7 passed**; suite completa
**412 passed**; `ruff` limpio; `lab doctor` OK. Smoke del SVG con una copia
temporal de la DB y 40 snapshots: línea, marcas y cruz visibles; `data/lab.db`
real no se tocó. Capturas de las 15 pestañas en `reports/ui/stage3` y diff en
`reports/ui/stage3_diff.json`.

**Etapa 4 · Accesibilidad y rendimiento.** Contraste AA, `:focus-visible`
visible, enlace **Saltar al contenido**, `aria-current` en la pestaña activa y
navegación de la barra lateral con flechas/Home/End. **Ctrl+K** sigue intacto.
El refresco de 8 s compara una huella del payload (sin `generated_at`) y solo
re-renderiza la vista si cambió; en la prueba CDP no hubo mutaciones de `#kpis`
en 9,5 s. Responsive verificado a 390 px sin desbordamiento horizontal. La Sala
pixel conserva `#office-floor`, `renderSala()` y su comportamiento.

Evidencia: `pytest tests/test_console_shell.py -q` → **8 passed**; suite completa
**413 passed**; `ruff` limpio; `lab doctor` OK. Capturas de las 15 pestañas en
`reports/ui/stage4`, móvil en `reports/ui/stage4/overview_mobile.png` y diff en
`reports/ui/stage4_diff.json`. Ctrl+K y flechas verificados con Chrome CDP.

### Ajustes de formato y métricas (2026-11-08)

- Los gauges de colchón dibujan lo que **queda** (`1 - used`), no lo usado:
  `used=0` → arco completo; `used=0.8` → 20 % y estado **AL LÍMITE**.
- Cero negativo: porcentajes que redondean a `-0.00 %` se muestran como
  `0.00 %`, con tono neutro y sin flecha roja (`clampZero`/`toneFor`).
- Moneda con separador de miles forzado (`useGrouping: "always"`):
  `9.973,51 US$`.
- Salud de cuenta: si la cobertura es <100 %, el estado es
  **PARCIAL · cobertura N%** y el tono es de aviso; el centro muestra `100`
  sin `/100` para no pisar el arco.
- Top performers pasa a **Evaluaciones de backtest (no reales)**, visible, con
  nota: `qqq-trend-f13` muestra **864 eventos de PnL realizado**, no 864
  operaciones redondas. Causa: `backtest.py` cuenta `len(realized)` y el bot
  rebalancea a diario para mantener su exposición objetivo; cada reducción
  parcial genera un evento. No se cambió la lógica del backtest.
- Régimen sin datos usa una fila compacta (`panel-compact`), no un panel alto.

Evidencia: `pytest tests/test_console_js.py tests/test_console_shell.py -q` →
**11 passed**; suite completa **416 passed**; `ruff` limpio; `lab doctor` OK.
Los tests JS extraen y ejecutan `pct`, `money`, `toneFor`, `gaugeCardHtml` y
`cushionStatus` del propio HTML.

---

## 6h. Multiverse por operación (10.2)

Monte Carlo que **reordena las operaciones, no los días**: 1.000 permutaciones
con semilla fija `42`. Para cada path se calcula la curva de equity desde el
capital de la cuenta y se comparan los límites efectivos.

- Curvas **p5/p50/p95** y MaxDD esperado, mediano, peor 5% y peor observado.
- Probabilidad de romper **límite diario**, **límite máximo** y **cualquiera**.
  El límite diario conserva el número de operaciones por día original
  (`bloques_por_dia`); si no hay días, evalúa la peor operación
  (`por_operacion`). La base se muestra en la UI.
- Visible en **Diario**, una simulación por cuenta, y en **Run Detail**.
- Run Detail lee el sidecar `artifacts/<hash>.trades.parquet` que genera
  `lab research` (PnL y día por operación). Los artefactos antiguos sin sidecar
  muestran **Sin datos**; no se derivan operaciones de la curva de equity.
- Sin datos si hay menos de 2 operaciones. N<30 se marca como muestra
  insuficiente.

Evidencia: `pytest tests/test_multiverse.py -q` → **7 passed**; suite completa
**279 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6i. Deriva live vs backtest (10.3)

Panel **Bots → Deriva live vs backtest** y comando `lab drift`. Es **solo
informativo**: no bloquea bots ni órdenes.

- Por cada bot compara el Sharpe y la expectancy del **Diario** con la última
  evaluación de backtest (`bot_evaluations`).
- Intervalos **bootstrap 95%** (1.000 remuestreos, semilla 42). Mínimo **20
  operaciones live** antes de opinar; con menos: **Sin datos**.
- Slippage real (fills vs señal) contra el supuesto del backtest
  (`execution.slippage_bps`, 5 bps por defecto) y los máximos de F13
  (`max_slippage_bps_p50/p95`). Mínimo 5 fills.
- Estados: **ok / vigilar / deriva**. Se explica el motivo de cada uno.
- La expectancy de backtest se guarda en la nueva columna
  `bot_evaluations.expectancy`; las evaluaciones antiguas sin ella muestran
  **Sin datos**.

```powershell
lab drift
lab drift --min-trades 30
```

Evidencia: `pytest tests/test_drift.py -q` → **5 passed**; suite completa
**284 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6j. Salud de cuenta y libro de capital (10.4)

### Salud 0-100

Score determinista por cuenta con pesos en
`config/lab.yaml → fund_health.weights` (30% colchón diario, 30% colchón de
drawdown, 15% racha, 15% deriva, 10% concentración):

- **Colchón diario/drawdown**: `100 × (1 − uso del límite)`.
- **Racha**: `100 × (1 − pérdidas seguidas / max_streak)`.
- **Deriva**: `ok=100`, `vigilar=50`, `deriva=0`; se usa el peor bot de la
  cuenta.
- **Concentración**: `100 × (1 − top3/neto / max_concentration)`, solo con neto
  positivo.

Si falta un componente se ignora y se muestra **cobertura** y `partial`; si no
hay ninguno, **Sin datos**. El desglose completo está en **Fondo → Salud de
cuenta**, no solo el número.

### Libro de capital y TWR

- Tabla `account_cash_flows` (depósito/retiro, importe, fecha, nota, origen).
- `lab fund flow-add paper_main --amount 1000 --kind deposit --note "..."`
  y `lab fund flows [cuenta]`.
- TWR diario: `r = (equity_fin − flujo_neto) / equity_inicio − 1`; los depósitos
  suman y los retiros restan. El retorno del fondo es el TWR ponderado por
  capital, con cobertura y cuentas incluidas.
- Solo se calcula con al menos 2 cierres diarios de equity locales; el resto
  muestra **Sin datos** (no se inventa una curva para MT5/Alpaca).

Evidencia: `pytest tests/test_health.py -q` → **5 passed**; suite completa
**289 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6k. Streak lock y pausa (10.5)

Pausa de **aperturas** por racha perdedora o pérdida diaria propia. Cerrar y
reducir **nunca** se bloquean.

- Umbrales por cuenta en SQLite (`account_risk_config`) con historial
  (`account_risk_history`), fuera del hash de F13.
- Defaults: **3 pérdidas seguidas** y **2% de pérdida diaria** del tamaño de
  cuenta. La pausa se latcha hasta reanudación explícita.
- Apretar umbrales es inmediato. Aflojar exige `--confirm` y **F13 no
  congelado/iniciado**; con F13 solo se aprieta.
- Reanudar exige confirmación y también se rechaza con F13 congelado. El reset
  no reactiva nada: solo permite volver a abrir.
- Guard integrado en `orchestrator.run_bot` y en el modo operador: si la cuenta
  está en pausa, la apertura se bloquea; el cierre sigue permitido.
- Fondo muestra el badge **PAUSA de aperturas**, motivo y botón **Reanudar**.

```powershell
lab fund pause-status
lab fund pause-set paper_main --max-losses 2 --daily-loss-pct 0.015
lab fund pause-set paper_main --max-losses 4 --confirm   # aflojar
lab fund pause-resume paper_main --confirm
```

Evidencia: `pytest tests/test_riskpause.py -q` → **4 passed**; suite completa
**295 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6l. Aprendizaje controlado (10.6)

- Tabla `lessons`: `proposed/approved/rejected`, hipótesis, evidencia, autor
  (`qwen|humano`), acción y trazabilidad de aplicación/reversión.
- **Qwen solo redacta**; el texto de noticias/LLM entra como no confiable.
  Ninguna lección se aplica sin aprobación humana desde **Aprendizaje**.
- **Auto-aplicación** solo para acciones `reduce_risk` (apretar límites); guarda
  el estado anterior y se puede revertir. Cualquier otra acción se rechaza.
- **Holdout sellado** en `learning_holdout` (config `learning.holdout_start/end`,
  hash y fecha de sellado). `record_test` rechaza cualquier ventana que lo pise.
- Cada prueba registrada incrementa el contador global (`lesson_tests`) que se
  suma a `n_trials` del DSR en los nuevos `lab research`.
- **Campeón/retador** en paper: se propone con `kind=challenger`, queda en
  `proposed` y no activa ni cambia `enabled`.
- `lab lessons list|show|add|approve|reject|test|challenger|apply|revert|holdout`.

Evidencia: `pytest tests/test_learning.py -q` → **6 passed**; suite completa
**301 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6m. Reportes CSV/HTML (10.7)

Historiales **solo por archivo**, generados desde datos reales del laboratorio:

- `reports/exports/journal_*.csv|html`, `drift_*`, `learning_*`.
- Validación de formato (`csv|html`), salida confinada a `reports/`, límite de
  filas y **nunca** secretos, PIN, tokens ni `.env`.
- Vista previa en CLI y en **Registros → Reportes CSV/HTML** (lectura, sin
  inyección de HTML).

```powershell
lab reports journal --format html
lab reports drift --format csv --min-trades 20
lab reports learning --format csv
lab reports list
lab reports preview reports/exports/archivo.csv
```

Evidencia: `pytest tests/test_exports.py -q` → **4 passed**; suite completa
**305 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6n. Catálogo único de instrumentos (6.4)

`instruments.py` es el catálogo único por clase (`equity`, `forex`, `futures`,
`cfd`). Cada instrumento declara tick, contrato, moneda, lote, **fuente de
datos**, **sesión** y **zona horaria**.

- `lab instruments [--class ...] [--validate]`.
- `GET /api/instruments` y panel **Mercado → Catálogo único**.
- `validate_catalog()` detecta duplicados, fuentes/sesiones vacías y
  especificaciones imposibles; los futuros exigen `tick_value`.
- CFD solo se registra con especificación verificada del bróker; no se inventan
  índices, horarios ni tick values.
- `get_instrument` conserva fuente/sesión al resolver sufijos de bróker.

Evidencia: `pytest tests/test_instruments.py -q` → **9 passed**; suite completa
**307 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6o. Agentes por mercado y coordinador determinista (6.5)

`config/market_agents.yaml` define por mercado (equity, forex, futures, cfd)
etiqueta, perfil, analistas y peso máximo. El routing valida la clase real del
símbolo con el catálogo antes de llamar al agente existente:

- `run_market_agent("equity", "SPY", mode="lite|deep")`; un símbolo de otra
  clase se rechaza.
- `coordinate(signals)` combina ratings/confianza de forma **determinista**:
  topes por símbolo y mercado, gross máximo y cash residual. No ejecuta órdenes
  ni activa bots.
- CLI `lab markets list` y `lab markets coordinate señales.json`.
- API `/api/markets` y panel **Agentes → Agentes por mercado**.

Evidencia: `pytest tests/test_market_agents.py -q` → **5 passed**; suite completa
**312 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6p. Un mercado a la vez y mini-F13 (6.6)

`config/market_pilots.yaml` define un piloto por mercado. **Seleccionar un
piloto no activa bots, no congela F13 y no envía órdenes**: solo limita qué
mercado puede abrir posiciones.

- Equity: piloto `qqq-trend-f13` **activo en paper** (bot `enabled:true`; tarea
  F13 registrada para el lunes 2026-11-09 22:20).
- Forex/CFD y futuros: `blocked` con motivo explícito (sin M15/H1 real u
  ProjectX sin credenciales).
- `select_pilot` mantiene **un solo mercado activo**; cambiar de piloto
  desactiva el anterior y deja historial. `clear_pilots` lo apaga.
- Gate en `orchestrator.run_all` y en aperturas del modo operador. Cerrar o
  reducir nunca se bloquea.
- CLI `lab markets pilots`, `pilot-select`, `pilot-clear`; API `/api/markets` y
  panel **Agentes → Pilotos / mini-F13**.
- El hash de F13 y `enabled` de los bots no cambian al seleccionar.

Evidencia: `pytest tests/test_market_pilots.py -q` → **4 passed**; suite completa
**317 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6q. Reentrenamiento walk-forward y registry (7.2)

Modelo base **ridge determinista en numpy**, sin dependencias nuevas:

- Features: retornos 1/5/20, volatilidad 20, distancia a SMA20/SMA50 y rango 20.
- Reentrenamiento **walk-forward** con ventanas móviles; cada fold entrena con
  pasado y evalúa solo el tramo posterior. Sin lookahead.
- `model_registry` guarda versión, features, ventanas, métricas, coeficientes,
  hash, estado y autor. `model_registry_history` audita promociones/rollbacks.
- Todo modelo nace **challenger**; promover o hacer rollback exige confirmación.
  **No activa bots ni cambia `enabled`**.
- CLI: `lab models train|list|show|promote|rollback|compare|qlib`.
- API `/api/models` y panel **Aprendizaje → Model registry**.
- Qlib se comprueba en `.venv-qlib`; no se instala ni se añade a `.venv`.

Estado real: challenger SPY v1 registrado (`hash b61f4e53…`), sin promoción ni
activación. Evidencia: `pytest tests/test_models.py -q` → **3 passed**; suite
completa **320 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6r. Fase 8 cerrada (motor de eventos)

Se evaluó NautilusTrader 1.231.0 y se decidió **no adoptarlo**: sin v2 estable,
coste alto de migración y datos de pago, y el backtester propio cubre F13 y
research diario. No se añaden dependencias (`nautilus`, `databento`, IBKR).
Gate para reabrir: F13 activo + datos intradía reales + necesidad demostrada de
rollover/eventos; la PoC iría en un venv separado.

Evidencia: `pytest tests/test_engine_decision.py -q` → **2 passed**; suite
completa **322 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6s. Versionado de límites y capital por bot (7.3)

- `account_limit_versions`: snapshot numerado de límites propios/efectivos con
  hash, autor y motivo. El rollback exige confirmación.
- Con F13 congelado/iniciado, un rollback que **afloje** se rechaza; apretar sí
  se permite. El aflojamiento respeta la espera al siguiente día hábil de
  `set_limits`.
- `bot_capital_limits` + `bot_capital_history`: capital máximo por bot en SQLite,
  con historial. El orquestador recorta `desired` para no superar ese capital.
- CLI: `lab fund snapshot|versions|rollback` y `lab bots capital|capital-set`.
- No edita YAML, no activa bots y no cambia el hash de F13.

```powershell
lab fund snapshot paper_main --reason "antes de ajustar"
lab fund versions paper_main
lab fund rollback paper_main --version 1 --confirm
lab bots capital-set trend-spy --max-capital 50000
lab bots capital
```

Evidencia: `pytest tests/test_limit_versions.py -q` → **3 passed**; suite
completa **325 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 6t. Job semanal de lecciones (7.1)

- Analiza `decision_outcomes` con `return_20d`; solo opina si n≥30 por rating.
- **Qwen solo redacta** la hipótesis; la evidencia numérica se guarda aparte.
- Crea lecciones en estado **`proposed`**; no aprueba, no aplica y no activa
  bots. Si no hay muestra o el LLM falla: **Sin datos**, sin propuestas.
- Deduplica por texto de hipótesis para no repetir la misma lección.
- CLI `lab lessons weekly`; script `scripts/lessons_weekly.ps1` (no registrado).
- El panel **Aprendizaje** sigue siendo el único sitio de aprobación humana.

Evidencia: `pytest tests/test_learning.py -q` → **8 passed**; suite completa
**408 passed**; `ruff` limpio; `lab doctor` OK con avisos conocidos.

---

## 7. Trading-R1 en Windows

Trading-R1 usa `fcntl`, `os.O_NOFOLLOW` y `os.getuid()`: **no funciona en Windows**.
Estado 2026-11-09: WSL **no está instalado** en este equipo; el repositorio
`vendor/Trading-R1` está presente, pero no se puede ejecutar hasta instalar
WSL2 + Ubuntu. No se ha descargado ni configurado ninguna clave Tauric.

Opciones, en orden recomendado:

1. **WSL2** (recomendado):
   ```powershell
   wsl --install -d Ubuntu
   ```
   Dentro de Ubuntu:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   uv venv --python 3.12 ~/.venv-r1
   uv pip install --python ~/.venv-r1/bin/python trading-r1
   export TR1_VLLM_BASE_URL=http://$(ip route show default | awk '{print $3}'):1234/v1
   export TR1_VLLM_MODEL=qwen3.8-27b
   ~/.venv-r1/bin/trading-r1 --profile vllm
   ```
   (En Windows 11 con *mirrored networking*, `localhost:1234` también funciona.)

2. Contenedor Linux (requiere Docker Desktop, no instalado).

3. Parchear `trading_r1/state/fileio.py` para Windows. No recomendado: hay más
   supuestos Unix en el proyecto.

### Fallback nativo sin WSL

Mientras WSL no esté listo, `lab premarket` genera el informe diario con Qwen
local, datos de la caché, calendario macro y envío opcional a Telegram. No usa
Trading-R1, no activa bots y no envía órdenes.

```powershell
lab premarket --tickers SPY,QQQ,NVDA --out logs\premarket\premarket.md
lab premarket --tickers SPY,QQQ,NVDA --send
```

La tarea `TradingLab-Premarket` (L-V 07:45) es opcional y se registra con
`scripts/register_premarket_task.ps1`. El script `scripts/resume_after_reboot.ps1`
reabre Windows Terminal y la sesión exacta de OpenCode después del reinicio.

---

## 8. Programación diaria (Windows Task Scheduler)

Ejemplo: señal + orden paper cada día laborable a las 15:45 ET (21:45 CET).

```powershell
$action = New-ScheduledTaskAction -Execute "E:\trading-lab\.venv\Scripts\lab.exe" `
  -Argument "run SPY --strategy trend" -WorkingDirectory "E:\trading-lab"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 21:45
Register-ScheduledTask -TaskName "TradingLab-SPY" -Action $action -Trigger $trigger
```

Para TradingAgents, programa `agent-run` de madrugada (tarda mucho) y sin solapar tickers.

---

## 9. Investigación automática (`lab research`)

El bucle que "mejora los bots" sin activarlos solo. Barre activos × estrategias ×
parámetros × escala de exposición, valida out-of-sample y escribe un ranking.

```powershell
# barrido completo (6 activos, 3 estrategias, ~2-4 min)
.\.venv\Scripts\lab.exe research --start 2015-01-01

# más rápido, para probar
.\.venv\Scripts\lab.exe research --symbols SPY,QQQ --strategies trend --paths 500
```

Qué hace:

1. descarga datos y ejecuta el backtest long/short (con comisión y slippage);
2. simula cada variante contra las reglas de `config/prop.yaml` (Monte Carlo
   **block bootstrap** con bloques de 5 días);
3. puntúa `pasa − revienta` con el Sharpe como desempate;
4. reserva el último 30% de la muestra para validación OOS;
5. calcula el **Deflated Sharpe Ratio (DSR)**, un **walk-forward global** con
   train 504 / test 126 días y el **PBO/CSCV** sobre una matriz de retornos
   diarios alineada por fecha (16 bloques contiguos → 12.870 combinaciones
   train/test). Además calcula `regime_report`/`regime_gate` por variante para
   2018, 2020 y 2022;
6. escribe `reports/research/latest.md`, `latest.json` y `proposals.{md,json}`;
7. guarda en `reports/research/artifacts/<hash>.parquet` la curva de **equity**
   de cada variante y la de **buy&hold** del mismo activo. El JSON incluye
   `artifact` y `artifact_rows`, pero **no cambia ningún criterio**.

### Run Detail en el panel

Al hacer clic en una fila de Research se abre el detalle de la variante con:

- curva de equity de la variante frente a buy&hold;
- curva de drawdown de ambas;
- retorno total, max drawdown, Sharpe y número de operaciones;
- PBO, walk-forward, regímenes y motivos de bloqueo.

Las gráficas son SVG propio del panel, sin librerías ni CDNs. Si el artefacto
no existe o está vacío, el panel muestra **“sin datos”** y no inventa curvas.

### Monte Carlo por horizonte y exposición

```powershell
.\.venv\Scripts\lab.exe research-horizons --top 10 --paths 2000
```

Simula el top 10 del ranking con el simulador Monte Carlo existente:

- horizontes **22, 44 y 120 días hábiles**;
- exposiciones **0,5×, 1× y 2×**;
- **FTMO 100k 2-step** y **Topstep 50K** (plantilla, no activa);
- salida en `reports/research/horizons.md` y `horizons.json`;
- el panel Research muestra las tablas por firma/exposición.

Es **solo informativo** y no cambia criterios de propuesta. Incluye una tabla
de qué retorno diario y volatilidad harían falta para pasar en 22 días con
pass ≥ 50% y breach < 15% (retornos iid normales, sin costes ni intradía).

### Cartera simulada y costes

```powershell
lab portfolio-simulate --top 10 --paths 2000
lab research-costs --top 10
```

- `portfolio-simulate` elige como máximo 2 variantes por clúster, las
  equipondera y simula la cartera contra FTMO/Topstep. Salida:
  `reports/research/portfolio.md` y `.json`.
- `research-costs` reejecuta el top 10 con comisión/slippage 0/0, 1/5, 2/10 y
  2/20 bps. Salida: `reports/research/costs.md` y `.json`.

Resultado actual de la cartera: **3 bots** (2 del clúster trend + GLD),
retorno 81,1%, Sharpe 1,03, MaxDD -9,2%. FTMO 120d: 70,6% pasa / 3,5%
revienta. Topstep 50K sigue siendo mucho más restrictivo.

Costes: **0 de 10 variantes frágiles** con 2/20 bps; el drag de costes es
5,8–10,2 puntos porcentuales sobre el retorno total de la muestra. No cambia
ningún criterio de propuesta.

Criterios de propuesta: pasa ≥ 35%, revienta ≤ 15%, OOS ≥ 25%, Sharpe > 0,
≥ 20 trades, **DSR ≥ 90%**, **WF positivos ≥ 2/4**, **PBO ≤ 30% global y por
activo**, **walk-forward global con veredicto `ok`**, **régimen aprobado en
2018/2020/2022** y **mediana de la familia de parámetros ≥ 35%** (evita proponer
un pico aislado). Si el PBO no se puede calcular (muestra insuficiente o menos de
2 variantes), **no se propone nada**. Un régimen sin datos **no aprueba**. Las
variantes que fallan solo los controles nuevos van a **“casi propuestas”** con
el motivo; las que tienen pocas operaciones también, sin activarse. **Ninguna
propuesta se activa sola**: van con `enabled: false` y hay que revisarlas,
añadirlas a `config/bots.yaml` y volver a simular con datos intradía.

### Umbrales del walk-forward

`WalkForwardResult.verdict()` devuelve **solo `ok` o `fallido`**. `fallido`
incluye muestra insuficiente y cualquier criterio no superado. Los umbrales
son fijos y **no se relajan para obtener propuestas**:

| Criterio | Umbral |
|---|---:|
| Folds válidos | ≥ 3 |
| Sharpe stitched (OOS concatenado) | > 0,00 |
| Fracción de folds con Sharpe OOS > 0 | ≥ 50% |
| Eficiencia mediana OOS/IS | ≥ 0,30 |
| Rank percentil mediano de la variante elegida | ≥ 50% |
| Estabilidad entre folds consecutivos | ≥ 30% |

En el barrido actual el fold que falla es **estabilidad: 17% < 30%**; por eso
el veredicto es `fallido`, no por el Sharpe ni por la eficiencia.

### DSR y número de pruebas

El DSR usa `n_trials = len(results)`, es decir,
**activos × estrategias × parámetros × exposiciones**. Con el barrido completo
son **192 pruebas**; si se añade un activo o una estrategia, crece de forma
proporcional. Se guarda en `latest.json` como `dsr_n_trials` y
`dsr_trial_sr_std`, y cada resultado conserva los mismos campos.

### PBO y variantes planas

El PBO se calcula sobre retornos diarios. Una columna con desviación típica
diaria ≤ `1e-10` se marca como **plana**. En EURUSD=X hay **0 de 16 variantes
planas** (la menor std es 0,00168), así que el PBO de 96,0% **no está
distorsionado por varianza cero**. El PBO recalculado excluyendo planas es
también 96,0%; se guarda como `pbo_excluding_flat` y es **solo informativo**.
No cambia el criterio de propuesta.

### Regímenes frente a buy & hold

`latest.md` incluye una tabla de **drawdown por régimen** que compara la
variante con comprar y mantener el mismo activo en 2018/2020/2022. Es
**informativo** y no forma parte del `regime_gate`; el gate sigue exigiendo
datos y retorno positivo en los tres regímenes.

Salida real (2026-11-07, FTMO 100k 2-step, horizonte 120 días, 192 resultados
= 96 variantes únicas × 2 escalas):

- **0 propuestas** y **0 casi propuestas**: ninguna variante pasa todos los
  filtros antiguos y nuevos a la vez.
- **PBO CSCV global 24,8% (ok).** Por activo: QQQ 7,5%, SPY 14,4% e IWM 26,3%
  son aceptables; **GLD 40,9%, TLT 46,0% y EURUSD=X 96,0% están sobreajustados**
  y sus candidatos quedan bloqueados aunque pasen DSR. EURUSD=X no tiene
  variantes planas (0/16).
- **Walk-forward global: `fallido`.** 19 folds, Sharpe stitched 0,55, 63% de
  folds positivos, eficiencia 0,49, rank mediano 59% y **estabilidad 17%** (las
  variantes elegidas cambian demasiado entre folds). Falla solo la estabilidad.
- **DSR:** `n_trials = 192`, σ(Sharpe) de las pruebas guardada en
  `latest.json`. El DSR elimina los 18 candidatos que antes pasaban: eran
  variantes correlacionadas de `trend`, no 18 edges independientes.
- **Régimen:** el mejor candidato (SPY `trend` fast=20 slow=200, 0.5×) tiene DSR
  59,3%, pero 2022 cae **-11,2%** y el gate lo bloquea.
- Mejor DSR: QQQ `trend` fast=20 slow=100, 0.5× → DSR 92,5%, pero solo 18
  trades y 20,4% de breach; no cumple muestra/riesgo.
- `trend-ls` y `meanrev` no superan a `trend` en esta muestra.

Decisión: se mantiene `min_trades=20` y no se propone nada hasta que un
candidato pase DSR, walk-forward y PBO con muestra suficiente. El PBO
reemplaza al cálculo simplificado por bloques (16% entonces); ahora usa
retornos diarios alineados y 12.870 combinaciones CSCV.

> **Nota sobre el PBO:** con ~11 años de datos diarios el PBO de una sola
> muestra es ruidoso (en ruido puro puede variar aproximadamente entre 0,12 y
> 0,73). Se interpreta como **alarma**, no como prueba de edge. Un régimen sin
> datos **no aprueba**.

Advertencias: elegir el mejor de cientos de variantes sesga el resultado al
alza; OOS es un filtro mínimo, no una garantía. La muestra 2015-2026 (y su
último 30%) es mayoritariamente alcista, así que un OOS alto mide un régimen
favorable, no robustez entre regímenes. El Monte Carlo usa retornos diarios, así
que el riesgo intradía real es mayor.

### Programarlo a diario

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File E:\trading-lab\scripts\research_daily.ps1" `
  -WorkingDirectory "E:\trading-lab"
$trigger = New-ScheduledTaskTrigger -Daily -At 07:00
Register-ScheduledTask -TaskName "TradingLab-Research" -Action $action -Trigger $trigger
```

Los logs quedan en `logs/research/`.

---

## 10. Copias de seguridad y secretos

Los secretos viven en **Windows Credential Manager** con `keyring` (servicio
`tradinglab`). `.env` sigue como **fallback local**, pero ya **no se copia** en
los zips. Precedencia: variable de shell > keyring > `.env`.

```powershell
# migrar los secretos actuales de .env a Credential Manager
.\.venv\Scripts\python.exe scripts\migrate_secrets.py

# ver claves (nunca muestra valores)
.\.venv\Scripts\python.exe scripts\migrate_secrets.py --status

# backup + verificación automática
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:\trading-lab\scripts\backup.ps1
```

`scripts/backup.ps1` guarda un zip en **`F:\TradingLabBackups`** con código,
`config`, `tests`, `scripts`, `docs`, informes, `data\lab.db`, historial git y
`.env.example`. Retención: los **20** zips más recientes. Al terminar ejecuta
`scripts/restore_test.ps1`, que restaura en una carpeta temporal y comprueba:

1. archivos mínimos y `data\lab.db`;
2. que no haya `.env` dentro del zip;
3. que no aparezcan valores reales de secretos;
4. que no haya asignaciones de secretos en `src/config/scripts/tests`;
5. `PRAGMA integrity_check` de SQLite.

Tarea programada **`TradingLab-Backup`**: todos los días a las **13:00** y
**19:00**. Comprobar:

```powershell
Get-ScheduledTask -TaskName "TradingLab-Backup" | Get-ScheduledTaskInfo
```

Otras tareas activas: **`TradingLab-DryRun`** (L-V 22:15), **`TradingLab-Web`**
(al iniciar sesión), **`TradingLab-Intel`** (diaria 07:10),
**`TradingLab-Agents`** (L-V 22:45, lite sobre SPY/QQQ/NVDA, sin órdenes) y
**`TradingLab-LMStudio`** (al iniciar sesión; arranca LM Studio y carga
`qwen3.8-27b` con 16k de contexto).

Restaurar en un PC nuevo:

1. Descomprimir el zip en `E:\trading-lab`.
2. `uv sync --frozen --extra dev --extra mt5`.
3. Reintroducir secretos con `scripts\migrate_secrets.py` o un `.env` local
   (en un PC nuevo no existe el Credential Manager del usuario anterior).
4. `lab doctor`.

> **Backups antiguos:** dos zips de `F:\TradingLabBackups` (`20261106_202735` y
> `20261106_204317`) todavía contienen `.env` (verificado 2026-11-07: 1 entrada
> cada uno). **No se han borrado** porque la regla del proyecto exige
> confirmación. Los zips nuevos ya no lo incluyen.
>
> **F: es local.** Si se pierde el PC, se pierde la copia. Mantén una segunda
> copia cifrada en un disco externo. Evaluación restic/Kopia y recomendación en
> [`docs/backups.md`](docs/backups.md).

---

## 11. Riesgo y realidad

- Un LLM **no predice precios**. TradingAgents produce una tesis; su valor está en
  estructurar información, no en acertar la dirección.
- Los backtests con datos diarios y sin costes de borrow son optimistas. Este motor
  ya aplica comisión (1 bp) y slippage (5 bps), pero sigue siendo una simplificación.
- `max_position_pct`, `max_gross_exposure`, `daily_loss_limit_pct` y `max_drawdown_pct`
  están en `config/lab.yaml`. El kill-switch se evalúa antes de cada orden.
- **Nunca** subas `.env` a git. Las claves de Alpaca paper no mueven dinero, pero las
  live sí.
- Empieza con 1-3 tickers. Añadir bots antes de validar uno solo multiplica los errores.

---

## 11b. Kill-switch, alertas y reconciliación

### Kill-switch persistente

`lab killswitch` implementa un estado en SQLite que sobrevive a reinicios:

- se activa por **pérdida diaria** (`daily_loss_limit_pct`) o **drawdown máximo**
  (`max_drawdown_pct`), usando el equity actual antes de cada apertura;
- una vez activo **no se desactiva** porque el equity se recupere;
- bloquea aperturas, pero **permite cerrar/reducir**;
- `lab killswitch reset` exige confirmación explícita;
- la web muestra un aviso rojo y el estado en Resumen/Riesgo.

```powershell
lab killswitch status   # estado persistido + evaluación actual
lab killswitch test     # escenarios sintéticos, sin tocar la DB
lab killswitch reset    # pide confirmación
```

### Alertas

Canal recomendado: **ntfy** (sin bot, solo topic). También soporta Telegram.
Configura en `.env`:

```ini
ALERTS_ENABLED=1
ALERT_CHANNEL=ntfy
NTFY_URL=https://ntfy.sh
NTFY_TOPIC=tu-topic-privado
# NTFY_TOKEN=...
# ALERT_CHANNEL=telegram
# TELEGRAM_BOT_TOKEN=...
# TELEGRAM_CHAT_ID=...
ALERT_COOLDOWN_S=300
HEALTHCHECKS_URL=   # latido opcional
```

Eventos: bloqueo de guard, kill-switch, fallo de LM Studio/Alpaca/MT5, desfase
broker vs DB, dry-run no ejecutado y backup fallido. `lab alerts check` prueba
servicios; `lab alerts test` envía una prueba. Nunca se imprimen tokens.

### Latido y reconciliación

- `scripts/dryrun_daily.ps1` y `scripts/backup.ps1` hacen `lab alerts heartbeat`
  al terminar bien (si `HEALTHCHECKS_URL` está configurado).
- `lab reconcile` compara equity y posiciones del broker con `lab.db`, guarda
  una fila en `reconciliation` y alerta cualquier diferencia.
- La web muestra kill-switch, último latido y última reconciliación.

---

## 11c. F13: pilot operativo en paper

**Estado: activo en paper.** El bot elegido es `qqq-trend-f13`
(`config/bots.yaml`, `enabled: true`). Activado el **2026-11-07** con inicio
**2026-11-09** (hash re-congelado `54b42036…`); sin live y sin órdenes en la
activación. La aprobación fue humana y explícita. El estado real vive en SQLite
(`f13_config`); `config/f13.yaml` solo contiene los criterios.

Backup verificado tras la activación:
`F:\TradingLabBackups\trading-lab_20261107_223737.zip` (22,85 MB, PASS, sin
`.env`, SQLite `ok`).

- QQQ, estrategia `trend`, `fast=50 slow=200 regime=200`, exposición **0.35**.
- Evidencia de `lab research`: 21 trades, pasa 65,5%, revienta 7,2%,
  OOS 83,5%, mediana de familia 64,9%.
- **Aviso:** tras añadir DSR, `lab research` deja **0 propuestas**. Este bot
  sirve como **pilot operativo**, no como validación de edge. No se promociona.
- Se descartó `trend-ls` (más trades pero 13,4% de breach y el orquestador
  actual no ejecuta cortos) y la variante de 18 trades (muestra insuficiente).

### Criterios (config/f13.yaml)

**Ventana: 8 semanas.** Con 21 trades en ~11 años, la esperanza en 8 semanas es
**0–3 trades**. Por eso F13 mide **operativa**, no edge:

- ≥95% de ciclos diarios ejecutados;
- ≥95% de reconciliaciones OK;
- 100% de señales vivas coincidentes con la recalculada;
- slippage mediano ≤10 bps y p95 ≤25 bps;
- error de tamaño ≤1 acción;
- hash de `config/*.yaml` sin cambios;
- cero breaches de guard/kill-switch y cero órdenes no autorizadas.

**Paradas duras:** cualquier breach o kill-switch, orden no autorizada/intento
live, diferencia de reconciliación no explicada, cambio de hash o dos ciclos
diarios perdidos.

**Regla de decisión:** si la operativa pasa, se **extiende** el paper a 6 meses
o ≥20 trades antes de opinar sobre edge. Si falla una parada dura, se detiene y
se revisa. F13 nunca pasa a dinero real.

```powershell
lab f13 status          # activo + criterios
lab f13 freeze          # congela hash/criterios; NO activa el bot
lab f13 activate        # activa en paper y re-congela el hash; pide confirmación
lab f13 report          # reporte diario en reports/f13/ (solo lectura)
lab f13 signal-check    # señal viva vs recalculada
lab f13 config-check    # hash congelado vs actual
lab f13 check           # paradas duras + alerta
```

La activación del bot requiere aprobación humana explícita; `freeze` no activa
el bot. `activate` es el paso controlado y ya se ejecutó.

`lab f13 report` genera `reports/f13/YYYY-MM-DD.json`, su versión Markdown y
`latest.json`/`latest.md`. Resume **ciclos ejecutados** (un ciclo por fecha con
dry-run), **reconciliaciones OK**, **slippage p50/p95**, **error de tamaño**,
**hash congelado/actual** y los criterios de `config/f13.yaml`. Es **solo
lectura**: no conecta al broker, no envía órdenes, no activa bots y no modifica
SQLite. Si el último lunes esperado dentro de la ventana F13 no tiene ciclo,
marca `f13_monday_missed` y envía la alerta; no hace falta esperar al chequeo
de 72 h.

`lab readiness` muestra en una sola tabla los días de F13 en paper, decisiones
totales/con retorno 20d, cuántas faltan para la muestra mínima de 30, fallos de
esquema LLM y macro de las próximas 48 h. No cambia umbrales ni opera.

> **Activación controlada:** `lab f13 activate` exige F13 congelado, hash OK,
> `mode=paper` y que el bot aún no esté activo. Edita **solo** la línea
> `enabled` de `config/bots.yaml`, re-congela el hash con la nueva configuración
> y audita `f13_activate`. No live y no envía órdenes al activar.

### Automatización F13 registrada

La tarea `TradingLab-F13` está registrada para **L-V 22:20 hora local de Praga**
(después del cierre de EE. UU.), con próxima ejecución **2026-11-09 22:20**.
Hoy está `Ready`, sin ejecutar todavía:

- `scripts/f13_daily.ps1`: preflight (aborta si F13 sigue “no iniciado”),
  ejecuta un **dry-run** para dejar evidencia del ciclo, después
  `lab orchestrate --bot qqq-trend-f13` **sin `--dry-run`**, `lab reconcile`,
  `lab f13 check` y `lab f13 report`. Cada paso queda en `logs/f13/`; el
  reporte diario queda en `reports/f13/`.
- `scripts/register_f13_task.ps1`: crea la tarea `TradingLab-F13` L-V a las
  **22:20 hora local de Praga**. Ya ejecutado; no se registra desde el bot.

El script diario solo opera en paper. El bot está `enabled: true`; las
aperturas siguen pasando por kill-switch, calendario, sesión, guard y límites.
No hay ninguna ruta a live.

---

## 11d. Control remoto por Telegram

Puente local para recibir resúmenes y, opcionalmente, enviar instrucciones a
OpenCode desde el móvil. Usa **long polling**: no abre puertos ni necesita IP
pública. El token vive en Windows Credential Manager (keyring), nunca en `.env`.

- **Solo el chat/usuario autorizado**; ignora otros chats y reenviados.
- **Modo `commands` por defecto**: `/status`, `/f13`, `/decisions`, `/ping`,
  `/pause`, `/resume`, `/mode`, `/new`, `/continue`, `/push`, `/backup`,
  `/pushbackup`, `/confirm`, `/cancel`.
- **Push/backup con aprobación humana en dos pasos**: la orden genera un código
  de 6 dígitos válido 5 minutos; solo `/confirm <código>` ejecuta. `/push`
  muestra antes el **diffstat y la lista de archivos**. El agente automático no
  puede hacer push.
- **Modo `agent` opcional**: ejecuta `opencode run --agent telegram` con un
  agente restringido: sin live, sin `.env`, sin borrar, sin push, sin tocar
  `config/`, `data/` ni activar F13.
- El resumen final del agente se envía a Telegram en el mismo formato
  **Hecho / 1..N / Aviso / Siguiente**.
- El PC debe estar encendido y con la sesión de Windows iniciada.

Pasos rápidos:

```powershell
cd E:\trading-lab
.\.venv\Scripts\lab.exe telegram setup      # token oculto + chat ID + keyring
.\.venv\Scripts\lab.exe telegram enable
.\.venv\Scripts\lab.exe telegram mode agent --yes   # opcional
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\register_telegram_task.ps1
Start-ScheduledTask -TaskName TradingLab-Telegram
```

Guía completa, seguridad y solución de problemas: `docs/telegram.md`.

---

## 11e. Calidad de datos y gate de research

`lab datacheck <símbolo> [--timeframe]` valida la caché parquet **sin descargar
ni inventar datos**: huecos de calendario, duplicados, barras fuera de orden,
OHLC inconsistente, saltos extremos, zona horaria declarada, ajuste
ajustado/no ajustado y presencia de `bid`/`ask`/`mid`/`spread`.

- Resultado **ok / aviso / falla**, con motivos y fechas de ejemplo.
- `aviso` no bloquea; **`falla` sí**: `lab research` no propone candidatos para
  un activo que falla el datacheck.
- El estado viaja en `latest.json`/`proposals.json` y se muestra en la pestaña
  **Research** y en **Run Detail**.
- Test de look-ahead: estrategias e indicadores se comparan en una serie
  truncada contra la completa; la señal en `t` no puede cambiar.
- No se añaden dependencias.

```powershell
lab datacheck SPY --timeframe 1d
lab datacheck EURUSD=X --json
lab research --symbols SPY --strategies trend
```

Estado real de la caché: SPY/QQQ `aviso` (3,6% de huecos de calendario por
festivos y ajuste no declarado en cachés antiguas); EURUSD=X `falla` por 88
barras OHLC inconsistentes y queda excluido de propuestas; GC aún **Sin datos**.

Evidencia: `pytest tests/test_datacheck.py tests/test_lookahead.py
tests/test_research.py -q` → **30 passed**; suite completa **375 passed**;
`ruff` limpio; `lab doctor` OK.

---

## 11f. Métricas informativas: SQN, Recovery y ruina

Se añaden a **Diario**, **backtest** y **research** sin tocar los criterios de
propuesta. Con **N < 30** se muestran con aviso de muestra insuficiente.

- **SQN** = `sqrt(N) · media(R) / desv(R)`. En el diario `R` es el retorno por
  operación (proxy: no se guarda el riesgo inicial de cada trade); el backtest
  usa el retorno de cada operación cerrada.
- **Recovery Factor** = `PnL neto / |max drawdown USD|`. Si no hay drawdown,
  **Sin datos**.
- **Riesgo de ruina** = `((1-edge)/(1+edge))^unidades`, con
  `edge = p - (1-p)/payoff` y `unidades = 1/f`. Supuestos: operaciones
  independientes, `p` y `payoff` constantes, riesgo fijo del **1%** por
  operación y ruina = perder todo el capital. Si `edge <= 0`, ruina = 100%.
- Se muestran en las tarjetas del Diario, en **Run Detail** y en la sección
  “Métricas informativas” del informe research.
- No son criterios de propuesta: DSR, PBO, walk-forward, regímenes y datacheck
  siguen mandando.

Evidencia: `pytest tests/test_metrics.py tests/test_journal.py
tests/test_engine.py tests/test_research.py -q` → **33 passed**; suite completa
**396 passed**; `ruff` limpio; `lab doctor` OK. Sin dependencias nuevas.

---

## 11g. Régimen de mercado informativo

`regimes.py` clasifica el mercado con reglas **causales** de tendencia y
volatilidad; no usa datos futuros y no activa ni desactiva bots.

- Etiquetas: `trend_up`, `trend_down`, `range`, `unknown` (warmup 200) y
  volatilidad `low`/`high` frente a su mediana de 252 días.
- Métricas: estabilidad de etiquetas, duración media, cambios, falsos cambios a
  5 días y retraso de detección (referencia centrada solo para evaluación).
- `lab regimes QQQ [--bot ...]` muestra el régimen actual, el rendimiento del
  activo y, opcionalmente, el de un bot por régimen.
- Dashboard: panel “Régimen de mercado” con etiqueta actual, volatilidad,
  estabilidad, retraso y rendimiento por régimen.
- Selector por régimen: **`proposed` / `enabled:false` / no aplicado**. No
  cambia el estado de ningún bot.
- GMM/HMM: evaluados (hmmlearn 0.3.3 y scikit-learn 1.9.1, BSD-3) pero **no
  adoptados**: no están instalados y el clasificador por reglas es suficiente
  para esta muestra. Sin dependencias nuevas.

Estado actual QQQ (2026-11-06): `trend_down`, volatilidad `high`; selector
propuesto `flat`. Evidencia: `pytest tests/test_regimes.py tests/test_web.py -q`
→ **23 passed**; suite completa **396 passed**; `ruff` limpio; `lab doctor` OK.

---

## 11h. Validación de modelos: Purged K-Fold y CPCV

- `PurgedKFold(n_splits, purge, embargo)` y `CombinatorialPurgedCV` en
  `models.py`; ningún índice de entrenamiento cae en test, purge o embargo.
- `train_purged_cv` valida el ridge con folds purgados; no registra ni promueve
  modelos y no activa bots.
- Test que comprueba intersección vacía y bloqueo de purge/embargo, además del
  número de combinaciones CPCV.
- **Meta-labeling y triple barrera**: solo `docs/meta_labeling.md` con
  requisitos de muestra (≥500 eventos; ≥100 por clase) y datos; no se
  implementan todavía. F13 no depende de ello.
- Sin dependencias nuevas.

Evidencia: `pytest tests/test_models.py -q` → **6 passed**; suite completa
**396 passed**; `ruff` limpio; `lab doctor` OK.

---

## 11i. Oro y series por instrumento

`XAUUSD` (CFD spot del bróker) y `GC` (futuros) son instrumentos distintos, con
serie, fuente, sesión, zona horaria y spread propios:

- `XAUUSD`: `cfd`, serie `XAUUSD.SPOT`, fuente `mt5`, 24/5 UTC, tick 0.01,
  contrato 100 oz, tick value 1 USD. Spread **Sin datos** (verificar bróker).
- `GC`: `futures`, serie `GC.FUT`, fuente `projectx`, 24/5 con pausa ET, zona
  `America/New_York`, tick 0.10, tick value 10 USD. Spread **Sin datos**.
- `validate_universe` rechaza mezclar clases en un mismo backtest
  (`XAUUSD`+`GC` falla; `SPY`+`QQQ` pasa).
- `normalize` conserva `bid`/`ask`/`mid`/`spread`; si hay bid/ask y faltan
  mid/spread, los calcula. Las barras MT5 con `spread` lo conservan.
- No se descargan series nuevas. Sin caché: **Sin datos**.

Evidencia: `pytest tests/test_instruments.py tests/test_data_normalize.py -q`
→ **14 passed**; suite completa **396 passed**; `ruff` limpio; `lab doctor` OK.
Sin dependencias nuevas.

---

## 11j. Biblioteca de conocimiento

`docs/biblioteca/library.yaml` es la fuente única de **18 fichas originales**;
`docs/biblioteca/README.md` se genera desde ella y `lab library list|show`
permite consultarlas sin abrir el repositorio. Incluye **ResearchGate**,
**Google Scholar** y **SSRN** como fuentes de investigación científica para
consulta manual: no se automatiza scraping, no se saltan paywalls y no se
consideran evidencia peer-reviewed por sí solas.

Cada ficha incluye nombre, categoría, problema, enlace oficial, licencia,
versión, fecha de revisión, dependencias, datos/costes, ventajas, riesgos,
pruebas hechas en TradingLab y estado (`adoptada`/`evaluada`/`descartada`) con
motivo.

- **Adoptadas**: DSR, PBO, walk-forward, Monte Carlo, FRED, SEC EDGAR, yfinance
  y LM Studio.
- **Evaluadas**: Optuna y QuantStats (adopción prevista en la Etapa 7).
- **Descartadas**: Qlib, hmmlearn, VectorBT, Backtrader y LEAN, con motivo
  explícito (dependencias, licencia o falta de ventaja demostrada).
- No se copia texto de terceros; los enlaces y licencias se revisan antes de
  añadir una dependencia.

```powershell
lab library list
lab library list --status descartada
lab library show dsr
```

Evidencia: `pytest tests/test_library.py -q` → **4 passed**; suite completa
**531 passed**; `ruff` limpio; `lab doctor` OK. Sin dependencias nuevas ni
automatización de scraping.

---

## 11k. Optuna y QuantStats (Etapa 7)

- **Optuna 5.0.0 (MIT)** con walk-forward en `lab optimize`: el tramo final
  sellado (2025-01-01…2026-11-07) **no se usa para elegir parámetros**; solo se
  evalúa una vez al final y se marca `used_for_selection: false`.
- Cada trial se registra en `optimization_trials` y **suma al contador
  `n_trials` del DSR**. Gates: DSR ≥90%, PBO ≤30% y walk-forward aprobado. Si
  falla cualquiera, **no se propone nada**. Las propuestas nacen `proposed` /
  `enabled: false`; no activan bots.
- **QuantStats 0.0.86 (Apache-2.0)** genera un HTML por propuesta frente a SPY
  en `reports/research/quantstats/`; es **solo lectura** y no altera criterios
  ni propuestas. Se integra al final de `lab research`.
- Dependencias documentadas en `docs/dependencias.md`; `uv.lock` actualizado y
  smoke test con pandas 3.1.1 / numpy 2.5.4. QuantStats emite un warning de
  matplotlib, no un fallo.
- Smoke real: 3 trials en SPY → DSR 100%, PBO 80,3%, WF fallido → **0
  propuestas**. El gate funciona.

Evidencia: `pytest tests/test_optimize.py tests/test_quantstats_report.py
tests/test_learning.py -q` → **12 passed**; suite completa **408 passed**;
`ruff` limpio; `lab doctor` OK. Sin activar bots ni tocar `.env`.

---

## 11l. Holdout de una sola lectura

El tramo sellado se evalúa **una vez por configuración**
`sha256(symbol + strategy + params)`. La segunda petición devuelve el resultado
guardado sin recalcular; cada lectura se registra en SQLite y suma una prueba
extra al contador del DSR.

- Primera lectura: evalúa y guarda en `holdout_evaluations`.
- Segunda lectura: `cached=1`, incrementa `reads` y registra `holdout_reads`.
- `lab lessons holdout` muestra lecturas, configuraciones, última lectura y
  configuraciones más leídas; `lab lessons weekly` y Research muestran el
  contador.
- Ninguna ruta usa el holdout para elegir parámetros: el desarrollo termina
  antes de `2025-01-01` y los `optimization_trials` lo verifican.
- Si el evaluador falla o no hay datos, no se guarda como evaluación válida.

Prueba real: primera lectura `SPY/trend` → **1 lectura / 1 configuración**;
la repetición cacheada se cubre en tests. Evidencia:
`pytest tests/test_learning.py tests/test_optimize.py tests/test_web.py -q` →
**29 passed**; suite completa **408 passed**; `ruff` limpio; `lab doctor` OK.

---

## 11l. Ticks Dukascopy y backtest con sesiones

**Ticks.** `lab ticks fetch` descarga archivos `.bi5` de Dukascopy, los
descomprime (LZMA), decodifica registros de 20 bytes y guarda un parquet en
`data/cache/ticks/`. No envía órdenes ni descarga datos de pago.

```powershell
lab ticks fetch EURUSD --day 2025-01-10 --hours 14
lab ticks fetch USDJPY --day 2025-01-10 --hours 8-16
lab ticks summary EURUSD --day 2025-01-10
lab ticks spread EURUSD --day 2025-01-10
lab research-intraday --symbol EURUSD --tick-spread data/cache/ticks/EURUSD_20250110.parquet
```

- Precio = entero × point del símbolo; `--point` permite símbolos fuera del
  mapa (`EURUSD`, `USDJPY`, `XAUUSD`).
- 404 = mercado cerrado o archivo vacío: se muestra **Sin datos**, no se
  inventan ticks.
- Descarga secuencial con `--interval` (0,5 s por defecto); un 429 espera al
  menos 5 s antes de reintentar. No lanzar varias descargas en paralelo.
- Verificación real: EURUSD 2025-01-10 14:00 UTC → **15.997 ticks**, spread
  mediano **0,29 bps**; parquet generado. La descarga de un día completo quedó
  pendiente: Dukascopy devolvió **HTTP 429** al intentar el lote; se reintentará
  secuencialmente más tarde, no se fuerza el rate limit.

**Backtest.** `backtest.run` acepta `session=("09:30","16:00")`,
`session_tz` y `flat_dates` para cerrar fuera de sesión o en días de
rollover/vencimiento. También está expuesto en CLI:

```powershell
lab backtest QQQ --session 09:30-16:00 --session-tz America/New_York
lab futures stitch --old NQH26.parquet --new NQM26.parquet --roll 2026-03-20 --out NQ.continuous.parquet
```

`continuous.stitch_continuous` une contratos ajustando el salto por ratio o
diferencia; los tests cubren ambos métodos.

Evidencia: `pytest tests/test_ticks.py tests/test_continuous.py
tests/test_engine.py -q` → **18 passed**; suite completa **531 passed**;
`ruff` limpio. Sin descarga de datos de pago ni órdenes.

---

## 12. Roadmap restante

1. ~~**F6** validar un `agent` real y medir latencia~~ → `lite` validado (77-95 s);
   `deep` queda como opción nocturna.
2. **F12** futuros: ~~elegir firma y adaptador~~ → Topstep + ProjectX en dry-run.
   Preset Topstep 50K añadido como plantilla inactiva; faltan abrir la cuenta,
   validar el MLL y las barras históricas.
3. ~~**F9c** backtester con sesiones, rollover y contratos continuos~~ → ✅
   `session`/`flat_dates` opcionales en `backtest.run` y `continuous.stitch_continuous`
   con ajuste ratio/difference; los cortos ya estaban.
4. **F11b** filtros de noticias, viernes y rollover en el guard → ✅ implementado
   (`news_blackout_min`, `weekend_holding`, `friday_cutoff_hour`,
   `rollover_blackout_min`) con tests de FOMC/NFP/CPI y cambios de hora.
5. **F13** paper continuo 4-8 semanas → comparar contra SPY y decidir.
6. **F7** Trading-R1 en WSL para el informe pre-market + Telegram → ⏳ WSL no
   instalado; no se puede ejecutar todavía.
7. ~~**F15** datos de ticks Dukascopy para modelar spread real en forex~~ → ✅
   descarga, decodificación e integración del spread horario en research;
   pendiente repetir el barrido real con el nuevo modelo de costes.

---

## 13. Repositorio remoto

- GitHub privado: **https://github.com/Arowarlin/trading-lab**
- Rama `master` conectada a `origin/master`.
- El panel web es local (`127.0.0.1`); no se despliega en GitHub Pages.
- `.env` está en `.gitignore` y **nunca** se sube. Los zips de backup nuevos
  **no** contienen `.env`; no se comparten ni se suben a la nube.

