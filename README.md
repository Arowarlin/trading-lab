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
| F13 | Paper continuo 4-8 semanas | ⏳ |
| F14 | Investigación automática (`lab research`) | ✅ barrido + OOS + DSR + PBO + walk-forward + regímenes |
| F15 | Datos de ticks Dukascopy / spread real forex | ⏳ |

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
| **Resumen** | equity, cash, retorno, drawdown, curva de equity, pipeline datos→señal→riesgo→ejecución, calendario macro, estado de LM Studio/MT5/FTMO, tareas programadas, últimas decisiones y órdenes. |
| **Mercado** | watchlist desde caché local, sparklines, breadth, retorno 1/5/20d y detalle por activo. **No descarga datos.** |
| **Sala** | oficina pixel con los 10 roles de TradingAgents, estados en vivo, burbujas, tablero y acceso al detalle de cada rol. |
| **Cuentas** | paper interno, Alpaca paper, FTMO demo y TopstepX/ProjectX, con equity, cash, posiciones y estado. |
| **Bots** | catálogo, enabled/disabled, propuestas, evaluación con backtest, archivo reversible y última señal. |
| **Agentes** | historial lite/deep con rating, confianza, duración y tesis; detalle en modal; runs deep en curso o terminados. |
| **Research** | ranking, PBO global y por activo, walk-forward, gate de regímenes, propuestas (`enabled: false`) y casi propuestas. Clic en una fila para el detalle. |
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

- reutiliza el panel si está actualizado;
- detecta un servidor viejo (sin `portfolio/costs`) y lo reinicia;
- abre con un `?v=` para evitar caché del navegador;
- no activa bots ni envía órdenes.

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

---

## 4b. Información continua (`intel`)

Fase 4 inicial: RSS de Yahoo Finance, saneado y almacenado en SQLite. **No hay
herramientas de ejecución en esta capa** y todo el texto entra como
`trusted=false`.

```powershell
.\.venv\Scripts\lab.exe intel fetch
.\.venv\Scripts\lab.exe intel status
.\.venv\Scripts\lab.exe intel fred --days 90
.\.venv\Scripts\lab.exe intel calendar
```

- `news_items`: URL, fuente, hora UTC, hash, título/resumen recortados.
- `news_scores`: esquema creado; scoring con Qwen pendiente.
- `macro_events`: FRED + eventos manuales. El guard usa `news_blackout_min`
  sobre esta tabla.
- **Decisión FinBERT:** no se incorpora por ahora. `ProsusAI/finbert` tiene
  licencia **CC-BY-NC-SA 4.0** (no comercial); el análisis inicial de noticias
  se hará con Qwen. No se descarga ningún modelo nuevo.
- `wrap_untrusted()` delimita el texto y ordena al LLM no seguir instrucciones
  contenidas; hay test de prompt injection.
- Tarea **`TradingLab-Intel`** a las 07:10; logs en `logs/intel/`.

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

- Pendiente Fase 4: scoring barato, OpenBB, reintentos por fuente y proveedor
  de noticias alternativo.

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

La infraestructura está implementada, pero **la descarga M15 real está
bloqueada ahora mismo**: el terminal FTMO demo está conectado y el mercado
cerrado, y no hay offset de servidor cacheado (`offset_source=unknown`). No se
inventa el offset ni se descargan datos de otra fuente.

```powershell
# con el mercado abierto y offset resuelto:
lab mt5 fetch EURUSD --timeframe M15 --bars 50000
lab mt5 fetch EURUSD --timeframe H1 --bars 20000
lab research-intraday --symbol EURUSD --timeframe M15
```

- Cachea velas ya corregidas a UTC por `MT5Broker.rates` en
  `data/cache/mt5/EURUSD_M15.parquet`.
- Modela spread por hora desde la columna `spread`, más slippage conservador y
  comisión. Si no hay spread realista, marca `spread_reliable=false` y los
  resultados como **no confiables**.
- Estrategias: ruptura de rango de apertura (Londres/NY), tendencia con
  retroceso y reversión del rango asiático; cada una con rejilla acotada.
- Pasa por DSR, PBO, walk-forward y regímenes con los mismos umbrales; reporta
  trades y cuántas pasan (puede ser cero). Monte Carlo a 22/44/120 días.

Los tests usan datos sintéticos. El informe real `intraday.md/json` se generará
cuando MT5 pueda determinar el offset con el mercado abierto o se configure
`mt5.server_utc_offset_hours` verificado.

Futuros intradía: perfil definido y proveedor ProjectX como **stub**; no se
implementa descarga de pago. Ver `docs/fase6_futuros_intradia.md`.

---

## 7. Trading-R1 en Windows

Trading-R1 usa `fcntl`, `os.O_NOFOLLOW` y `os.getuid()`: **no funciona en Windows**.
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

**Estado: no iniciado.** El bot elegido es `qqq-trend-f13`
(`config/bots.yaml`, `enabled: false`):

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
lab f13 status          # no iniciado + criterios
lab f13 freeze          # congela hash/criterios; NO activa el bot
lab f13 report          # snapshot + F13 vs SPY vs backtest + slippage
lab f13 signal-check    # señal viva vs recalculada
lab f13 config-check    # hash congelado vs actual
lab f13 check           # paradas duras + alerta
```

La activación del bot requiere aprobación humana explícita; `freeze` no cambia
`enabled: false`.

### Automatización F13 preparada (NO registrada)

No existe ninguna tarea F13 registrada. Los scripts están listos para que los
revises y decidas:

- `scripts/f13_daily.ps1`: preflight (aborta si F13 sigue “no iniciado”),
  ejecuta `lab orchestrate --bot qqq-trend-f13` **sin `--dry-run`**, después
  `lab reconcile` y `lab f13 check`. Cada paso queda en `logs/f13/`.
- `scripts/register_f13_task.ps1`: crea la tarea `TradingLab-F13` L-V a las
  **22:20 hora local de Praga** (después del cierre de EE. UU.). **No se ha
  ejecutado**.

Comando que ejecutarás tú cuando toque:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:\trading-lab\scripts\register_f13_task.ps1
```

El script diario no envía órdenes mientras el bot siga `enabled: false`; el
orquestador ignora bots deshabilitados. La activación real exige editar
`config/bots.yaml` a mano. `lab f13 status` debe seguir mostrando “no iniciado”
hasta que tú ejecutes `freeze`.

---

## 12. Roadmap restante

1. ~~**F6** validar un `agent` real y medir latencia~~ → `lite` validado (77-95 s);
   `deep` queda como opción nocturna.
2. **F12** futuros: ~~elegir firma y adaptador~~ → Topstep + ProjectX en dry-run.
   Preset Topstep 50K añadido como plantilla inactiva; faltan abrir la cuenta,
   validar el MLL y las barras históricas.
3. **F9c** backtester con sesiones, rollover y contratos continuos (los cortos ya están).
4. **F11b** filtros de noticias, viernes y rollover en el guard → ✅ implementado
   (`news_blackout_min`, `weekend_holding`, `friday_cutoff_hour`,
   `rollover_blackout_min`) con tests de FOMC/NFP/CPI y cambios de hora.
5. **F13** paper continuo 4-8 semanas → comparar contra SPY y decidir.
6. **F7** Trading-R1 en WSL para el informe pre-market + Telegram.
7. **F15** datos de ticks Dukascopy para modelar spread real en forex.

---

## 13. Repositorio remoto

- GitHub privado: **https://github.com/Arowarlin/trading-lab**
- Rama `master` conectada a `origin/master`.
- El panel web es local (`127.0.0.1`); no se despliega en GitHub Pages.
- `.env` está en `.gitignore` y **nunca** se sube. Los zips de backup nuevos
  **no** contienen `.env`; no se comparten ni se suben a la nube.

