# TradingLab

Entorno multi-bot de trading sobre **TradingAgents** y **Trading-R1**, con LLM local
(LM Studio / Qwen3.8-27B) y ejecución en **Alpaca paper**.

> Regla del proyecto: nada de dinero real hasta completar la fase de paper trading
> (4-8 semanas) con métricas positivas y el kill-switch probado.

---

## 1. Estado actual

| Fase | Descripción | Estado |
|---|---|---|
| F0 | Infraestructura, venvs, repos, `uv`, `bun` | ✅ |
| F1 | LM Studio sirviendo el modelo | ⏸ descarga pausada al 33 % |
| F2 | Repos instalados y verificados | ✅ TradingAgents · ⚠ Trading-R1 requiere WSL |
| F3 | Núcleo del lab: config, SQLite, datos, riesgo | ✅ |
| F4 | Backtester + estrategias deterministas | ✅ |
| F5 | Alpaca paper + ejecución | ⏳ faltan claves |
| F6 | TradingAgents como fuente de señal | ✅ código · ⏳ falta modelo |
| F7 | Trading-R1 (informes/Telegram) | ⏳ requiere WSL |
| F8 | Dashboard y observabilidad | ⏳ |
| F9 | Paper trading continuo | ⏳ |

---

## 2. Estructura

```
E:\trading-lab\
├─ .venv\            Python 3.13 · laboratorio (datos, backtest, riesgo, ejecución)
├─ .venv-ta\         Python 3.13 · TradingAgents 0.7.1 (aislado)
├─ .venv-r1\         Python 3.12 · Trading-R1 0.1.0 (aislado; en Windows no arranca)
├─ config\
│   ├─ lab.yaml      modo, riesgo, broker, LLM
│   └─ bots.yaml     catálogo de bots
├─ src\tradinglab\
│   ├─ config.py     settings tipados (YAML + .env)
│   ├─ db.py         SQLite: órdenes, fills, posiciones, equity, señales, LLM calls
│   ├─ data\         descarga + caché parquet (yfinance)
│   ├─ strategies\   trend, meanrev
│   ├─ backtest.py   motor con comisión y slippage
│   ├─ risk.py       sizing por ATR, límites y kill-switch
│   ├─ execution\    PaperBroker persistente
│   ├─ llm.py        cliente OpenAI-compatible con log de llamadas
│   ├─ agents\       puente a TradingAgents
│   └─ cli.py        comandos `lab`
├─ scripts\
│   ├─ run_tradingagents.py
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

.\.venv\Scripts\lab.exe agent NVDA --date 2026-11-05         # solo decisión LLM
.\.venv\Scripts\lab.exe agent-run NVDA --dry-run             # decisión + orden paper

.\.venv\Scripts\lab.exe status
.\.venv\Scripts\lab.exe report
.\.venv\Scripts\lab.exe bots
.\.venv\Scripts\lab.exe llm-test
```

Atajo: `.\scripts\lab.ps1 <comando>`.

---

## 4. Siguiente paso: terminar LM Studio

1. Abre LM Studio → pestaña **My Models** / descargas.
2. La descarga de **Qwen3.8-27B Q4_K_M** está **pausada en 5,54 GB de ~16,5 GB**.
   Pulsa **resume**. El CLI no puede reanudarla (`artifact does not exist`).
3. Cuando termine, carga el modelo con estos ajustes (RX 6800 = 16 GB VRAM):

| Ajuste | Valor | Motivo |
|---|---|---|
| GPU offload | ~28-32 capas (o "max") | 27B Q4 no cabe entero; el resto va a RAM |
| Context length | 16384 (subir a 32768 si aguanta) | TradingAgents usa prompts largos |
| KV cache quant | Q8_0 | ahorra VRAM |
| Flash attention | ON | velocidad |
| mmproj | no cargar | visión innecesaria, ahorra 0,9 GB |
| Temperature | 0.2 | reproducibilidad |

4. Arranca el servidor: `lms server start --port 1234`
5. Verifica: `lms ps` y `curl http://127.0.0.1:1234/v1/models`
6. Ajusta `LAB_LLM_MODEL` en `.env` al id exacto que devuelva `/v1/models`
   (probablemente `qwen3.8-27b`).
7. Prueba: `.\.venv\Scripts\lab.exe llm-test`

> Con 16 GB de VRAM y 27B en Q4 espera **8-15 tok/s**. Un run de TradingAgents con
> 2 analistas y 1 ronda de debate: **20-60 min**. Por eso el diseño usa el LLM
> 1 vez al día y los bots deterministas para todo lo demás.

---

## 5. Siguiente paso: Alpaca paper

1. Crea cuenta en <https://alpaca.markets> → *Paper Trading*.
2. Genera API keys (paper) y pégalas en `E:\trading-lab\.env`:
   ```
   ALPACA_API_KEY=...
   ALPACA_SECRET_KEY=...
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   ```
3. Cambia en `config/lab.yaml`: `execution.broker: alpaca`.
4. `.\.venv\Scripts\lab.exe doctor` debe mostrar `Alpaca keys OK`.

El adaptador de ejecución real (Alpaca) es la siguiente pieza de código: hoy
`PaperBroker` simula fills localmente, que es lo correcto para validar la lógica.

---

## 6. Trading-R1 en Windows

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

## 7. Programación diaria (Windows Task Scheduler)

Ejemplo: señal + orden paper cada día laborable a las 15:45 ET (21:45 CET).

```powershell
$action = New-ScheduledTaskAction -Execute "E:\trading-lab\.venv\Scripts\lab.exe" `
  -Argument "run SPY --strategy trend" -WorkingDirectory "E:\trading-lab"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 21:45
Register-ScheduledTask -TaskName "TradingLab-SPY" -Action $action -Trigger $trigger
```

Para TradingAgents, programa `agent-run` de madrugada (tarda mucho) y sin solapar tickers.

---

## 8. Riesgo y realidad

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

## 9. Roadmap restante

1. **F5** adaptador Alpaca (órdenes, posiciones, account) + reconciliación.
2. **F6b** validar TradingAgents end-to-end con el 27B y medir latencia real.
3. **F7** Trading-R1 en WSL: informe pre-market + Telegram.
4. **F8** dashboard (Streamlit/FastAPI) con equity, posiciones, señales y latencia LLM.
5. **F9** paper continuo 4-8 semanas → comparar contra SPY y decidir.
