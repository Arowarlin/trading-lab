# SOFTWARE_ARCHITECTURE — Arquitectura objetivo reutilizando lo existente

## Mapa objetivo y módulos actuales

| Capa | Módulos existentes | Cambio |
|---|---|---|
| Data engine | `data/`, `intraday.load_bars`, conectores de FRED y CFTC | Ninguno |
| Data quality | `datacheck.py`, crosscheck MT5/Dukascopy | Añadir un hash de la versión de datos al registro de cada prueba |
| Cost model | `costs.py`, `broker_costs.py`, `costs.yaml` | **Unificar** en una interfaz `CostModel` con entrada, salida y carry (nuevo `costmodel.py`) |
| Strategy engine | `strategies/`, familias de `intraday.py`, `swing.py` | Ninguno |
| Backtest | `backtest.py` (diario), `run_event_backtest` (eventos), `ea_us100_engine` | Inyectar `CostModel` y no duplicar motores |
| Optimization | `optimize.py` (Optuna) | Límites de trials y meseta |
| Validation | `validation.py`, `walkforward.py`, `research.deflated_sharpe` | Nuevo `stats.py` con `dsr_from_returns`, que pasa a ser la única puerta de entrada |
| Risk | `risk.py`, `risk_budget.py`, `prop/guard.py`, `killswitch.py` | Riesgo agregado por símbolo y clúster |
| Portfolio | `portfolio.py` | Igual riesgo por estrategia hasta tener 3 validadas |
| Execution | `execution/`, MT5, Alpaca, guardián MQL5 | Registro de EAs externos en el guardián |
| Forward monitoring | `forward_intraday.py`, `lifecycle.py`, `f13.py` | Pre-registro con hash, común para todos |
| Lifecycle | `lifecycle.py`, cementerio | Máquina de estados formal (ver VALIDATION_PROTOCOL) |

## Deuda técnica real (no solo tamaño)

- `cli.py`, con 10 236 líneas, mezcla parseo de comandos con lógica de negocio (por ejemplo, el cálculo del DSR previo en `cli.py:9680`). Hay que mover la lógica a módulos y dejar el CLI como capa fina. Es un cambio mecánico y con riesgo bajo, pero **no es prioritario**.
- `web.py` (3060) y `ai_trader.py` (3712): mismo patrón. Se dividen solo al tocarlos por otra razón.
- Los cálculos estadísticos están repetidos: `_sharpe` existe en `walkforward`, `ea_us100`, `optimize`, `intraday` y `backtest`, con anualizaciones distintas (252 o barras por año). **Esa duplicación es la causa directa del error del DSR.** Hay que centralizarlos en `stats.py`.
- SQLite en modo WAL: correcto para varios procesos lectores. Falta un `busy_timeout` explícito en todas las conexiones, porque hay varias tareas programadas escribiendo a la vez.

## Rendimiento

- Las rejillas y los backtests son independientes entre sí: se pueden repartir con `concurrent.futures.ProcessPoolExecutor` usando 16 núcleos. Solo hay que aplicarlo donde un barrido tarde más de 5 minutos.
- Llamadas al LLM: el carril IA hace una sesión por ventana, que es razonable. Hay que evitar llamarlo cuando no hay ningún setup elegible: el filtro determinista va primero.
