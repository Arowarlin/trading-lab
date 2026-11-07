# Arquitectura: del árbol propuesto al laboratorio real

El árbol propuesto para `C:\TradingLab` es una buena **mapa mental** de un
laboratorio multi-activo. No conviene mover el proyecto actual a esa ruta de
golpe: los venvs, las tareas programadas, `.env` y las rutas absolutas ya
funcionan desde `E:\trading-lab`. Primero se consolida el núcleo; después se
migra si hace falta.

## árbol propuesto vs. realidad

| Propuesto | Hoy en `E:\trading-lab` | Estado |
|---|---|---|
| `agents/TradingAgents` | `vendor/TradingAgents` + `src/tradinglab/agents/` | ✅ integrado (lite/deep) |
| `agents/Trading-R1` | `vendor/Trading-R1` | ⏳ requiere WSL |
| `agents/FinRobot` | — | 🔎 auditado; integración futura como proveedor de research |
| `agents/FinGPT` | — | ⏳ no necesario para el alcance actual |
| `engines/LEAN`, `engines/NautilusTrader` | `src/tradinglab/backtest.py` | 🔎 motores propios ligeros; evaluar solo si se necesita intradía/ejecución avanzada |
| `research/vectorbt`, `qlib`, `FinRL-X` | `src/tradinglab/research.py` | ✅ research propio con OOS y Monte Carlo; `vectorbt` es el siguiente benchmark razonable |
| `strategies/{stocks,forex,futures,crypto,commodities}` | `src/tradinglab/strategies/` + `config/bots.yaml` | ✅ acciones/forex; futuros en adaptador; crypto fuera de alcance |
| `data/{raw,normalized,historical,features}` | `data/cache/`, `data/lab.db` | ✅ parquet + SQLite; separar `raw/` y `features/` solo si crece |
| `execution/{tradestation,interactivebrokers,mt5,crypto}` | `src/tradinglab/execution/{paper,alpaca,mt5,projectx}.py` | ✅ paper, Alpaca paper, MT5 demo, ProjectX dry-run |
| `risk/{position_sizing,drawdown,exposure,order_validation}` | `src/tradinglab/risk.py` + `src/tradinglab/prop/` | ✅ sizing ATR, kill-switch, guard FTMO |
| `monitoring/{logs,performance,alerts}` | `src/tradinglab/web.py`, `logs/`, `reports/` | ✅ panel web en vivo |
| `reports/` | `reports/` | ✅ research, futuros, capturas |
| `infrastructure/{database,docker}` | `data/lab.db`, `scripts/` | ✅ SQLite; Docker opcional |

## Decisión

1. **No duplicar el árbol con carpetas vacías.** La estructura propuesta se usa
   como mapa; el código sigue en el paquete `tradinglab`, que es pequeño y
   testeable.
2. **Un solo repositorio** (`trading-lab`) con el panel, el motor, los agentes,
   los adaptadores y la documentación. Los repos de terceros van a `vendor/`
   (ignorado por git) o se instalan como dependencias.
3. **Integraciones futuras, en este orden:**
   - `FinRobot` como *research provider* opcional (DCF/comps/IC memo), sin
     reemplazar el flujo lite/deep.
   - `vectorbt` como benchmark del backtester, no como dependencia del bot diario.
   - `LEAN`/`NautilusTrader` solo si se pasa a intradía o se necesita un motor de
     órdenes más serio.
   - `TradeStation`/`IBKR` solo si el broker lo exige; hoy Alpaca paper + MT5 demo
     + ProjectX dry-run cubren el alcance.
4. **Riesgo y execution primero.** Cualquier motor nuevo debe pasar por el mismo
   `PropGuard`, el kill-switch y el modo paper antes de conectarse a algo real.

## Si se quiere migrar a `C:\TradingLab`

Sería un proyecto aparte, con estos pasos:

1. Crear el árbol y mover el código manteniendo `pyproject.toml`.
2. Recrear los venvs (no copiarlos) y reinstalar `uv pip install -e .`.
3. Actualizar rutas de `config/lab.yaml`, `.env`, tareas programadas y backups.
4. Validar `lab doctor`, `lab web`, tests y un dry-run antes de borrar el original.
5. Mantener una copia de seguridad completa (zip) antes de mover nada.

Hasta entonces, la fuente de verdad es `E:\trading-lab`.
