# Instrumentos: XAUUSD y GC

Son instrumentos **distintos** y no se mezclan en un mismo backtest.

| Campo | XAUUSD | GC |
|---|---|---|
| Clase | `cfd` (spot del bróker) | `futures` (CME) |
| Serie | `XAUUSD.SPOT` | `GC.FUT` |
| Fuente | `mt5` | `projectx` |
| Sesión | 24/5 | 24/5 con pausa 17:00–18:00 ET |
| Zona | `UTC` | `America/New_York` |
| Tick | 0.01 | 0.10 |
| Contrato | 100 oz | 100 oz |
| Tick value | 1.00 USD | 10.00 USD |
| Spread | **Sin datos** (verificar con el bróker) | **Sin datos** (verificar con el mercado) |

`validate_universe(["XAUUSD", "GC"])` lanza `InstrumentError`: distinta clase de
activo. `validate_universe(["SPY", "QQQ"])` es válido (misma clase, series
distintas).

## Bid/ask

`data/base.normalize` conserva `bid`, `ask`, `mid` y `spread` si vienen en el
DataFrame; si hay bid/ask y faltan mid/spread, los calcula. Las barras MT5 que
solo traen `spread` conservan esa columna. No se inventan bid/ask ni spreads.

No se descargan series nuevas en esta etapa. Si no hay caché: **Sin datos**.
