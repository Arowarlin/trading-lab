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
| F8 | Dashboard y observabilidad | ✅ `lab dashboard` (HTML) |
| F9 | Núcleo multi-activo (forex, futuros, acciones) | ✅ |
| F10 | MT5: datos, sizing, órdenes, hora de servidor | ✅ demo validada (abrir/cerrar) |
| F11 | Motor de reglas de fondeo (FTMO) | ✅ guard + Monte Carlo + fuente contrastada |
| F12 | Futuros (ProjectX/Tradovate) | ⏳ pendiente de firma y cuenta |
| F13 | Paper continuo 4-8 semanas | ⏳ |
| F14 | Investigación automática (`lab research`) | ✅ barrido + OOS + propuestas |

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
│   ├─ execution\    PaperBroker · Alpaca · MT5
│   ├─ prop\         rules (firmas/fases), guard (bloqueo), simulator (Monte Carlo)
│   ├─ research.py   barrido de parámetros + OOS + propuestas (no auto-activa)
│   ├─ llm.py        cliente OpenAI-compatible con log de llamadas
│   ├─ agents\       puente a TradingAgents
│   └─ cli.py        comandos `lab`
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
```

Atajo: `.\scripts\lab.ps1 <comando>`.

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

Los servidores MT5 **no van en UTC**: el de Darwinex iba en GMT+2. El adaptador
autodetecta el desfase comparando un tick fresco con UTC y convierte velas,
posiciones y deals a UTC real. Sin esto, el reset del límite diario de FTMO se
calcula con 1-3 horas de error. Se puede fijar a mano con
`mt5.server_utc_offset_hours`.

### Motor de reglas (`prop/`)

`config/prop.yaml` define firma, fase y límites. **Es una plantilla**: verifica
cada valor en el contrato vigente de tu firma.

`PropGuard.evaluate()` devuelve `allowed=False` cuando una orden rompería:

- límite de pérdida diaria (sobre balance o equity, según firma);
- pérdida máxima (`static`, `trailing_eod` o `trailing_intraday`);
- objetivo de beneficio alcanzado (deja de abrir riesgo);
- máximo de lotes, posiciones o riesgo abierto;
- consistencia (aviso, no bloqueo, porque se aplica al payout).

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
- Si el contrato restringe noticias o fin de semana, hay que añadir ese filtro
  antes de operar de verdad (`news_blackout_min`, `weekend_holding`).
- `ALLOW_LIVE=YES` sigue siendo obligatorio para cuentas reales.

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
2. simula cada variante contra las reglas de `config/prop.yaml` (Monte Carlo);
3. puntúa `pasa − revienta` con el Sharpe como desempate;
4. reserva el último 30% de la muestra para validación OOS;
5. escribe `reports/research/latest.md`, `latest.json` y `proposals.{md,json}`.

Criterios de propuesta: pasa ≥ 35%, revienta ≤ 15%, OOS ≥ 25%, Sharpe > 0 y
≥ 20 trades. **Ninguna propuesta se activa sola**: van con `enabled: false` y
hay que revisarlas, añadirlas a `config/bots.yaml` y volver a simular con datos
intradía.

Salida esperada (2026-11-05, FTMO 100k 2-step, horizonte 120 días):

- mejor variante del ranking: QQQ `trend` fast=20 slow=100, exposición 0.35× →
  pasa 68,8%, revienta 6,2% (no se propone: 17 trades < 20);
- mejor propuesta: QQQ `trend` fast=50 slow=200, 0.35× → pasa 67,3%,
  revienta 7,1%, OOS 88,1%;
- el mismo `trend` a exposición 1.0× revienta ~36%: **el tamaño de posición
  importa más que la señal**;
- `trend-ls` y `meanrev` no superan a `trend` en esta muestra.

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

## 10. Copias de seguridad

Script: `scripts/backup.ps1`. Destino: **`F:\TradingLabBackups`**. Guarda un zip
con código, `config`, `tests`, `scripts`, informes, `data\lab.db`, historial git
y `.env`, más un `LEEME_BACKUP.txt` con las instrucciones de restauración.
Retención: los **20** zips más recientes.

```powershell
# manual
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:\trading-lab\scripts\backup.ps1

# ver copias
Get-ChildItem F:\TradingLabBackups | Sort-Object LastWriteTime -Descending
```

Tarea programada **`TradingLab-Backup`**: todos los días a las **13:00** y
**19:00** (se ejecuta aunque el equipo estuviera apagado, en el siguiente
arranque). Comprobar:

```powershell
Get-ScheduledTask -TaskName "TradingLab-Backup" | Get-ScheduledTaskInfo
```

Restaurar en un PC nuevo:

1. Descomprimir el zip en `E:\trading-lab`.
2. `uv venv --python 3.13 .venv` y `uv pip install -e .`
3. Revisar `.env` (Alpaca, MT5, LLM) y `lab doctor`.
4. Reinstalar los venvs de TradingAgents/Trading-R1 si se usan.

> **El zip contiene `.env` con claves.** No lo subas a la nube ni lo compartas.
> F: es un disco local: si el PC se pierde físicamente, esta copia también.
> Para protección externa, copia el zip a un disco USB cifrado.

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

## 12. Roadmap restante

1. ~~**F6** validar un `agent` real y medir latencia~~ → `lite` validado (77-95 s);
   `deep` queda como opción nocturna.
2. **F12** futuros: elegir firma (Topstep/Apex) y adaptador ProjectX/Tradovate.
3. **F9c** backtester con sesiones, rollover y contratos continuos (los cortos ya están).
4. **F11b** filtros de noticias, viernes y rollover en el guard.
5. **F13** paper continuo 4-8 semanas → comparar contra SPY y decidir.
6. **F7** Trading-R1 en WSL para el informe pre-market + Telegram.
7. **F14** datos de ticks Dukascopy para modelar spread real en forex.
