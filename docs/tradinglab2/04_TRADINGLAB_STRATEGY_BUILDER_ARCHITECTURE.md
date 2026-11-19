# 04 · Strategy Builder: lenguaje de reglas, bloques y motor rápido

Paquete nuevo: `src/tradinglab/discovery/` (no toca nada protegido).

## 1. Representación: árbol de reglas (AST) en JSON

Cada estrategia es un documento JSON validado con pydantic (`discovery/dsl.py`), con hash estable
(`sha256` del JSON canónico ordenado) para deduplicar.

```json
{
  "dsl_version": "1",
  "instrument": "US100", "market": "cfd", "timeframe": "M5",
  "session": {"tz": "America/New_York", "start": "09:35", "end": "11:30", "flat_at": "15:45"},
  "long_entry":  {"op": "and", "args": [
      {"op": "gt", "left": {"ind": "ema", "src": "close", "n": 20}, "right": {"ind": "ema", "src": "close", "n": 50}},
      {"op": "gt", "left": {"ind": "rsi", "n": 14}, "right": {"const": 55}},
      {"op": "gt", "left": {"ind": "atr_pct_rank", "n": 14, "lookback": 100}, "right": {"const": 0.6}},
      {"op": "cross_up", "left": {"price": "close"}, "right": {"level": "prev_session_high"}}
  ]},
  "short_entry": null,
  "exit": {"stop": {"type": "atr", "mult": 1.5, "n": 14},
           "target": {"type": "rr", "rr": 2.0},
           "breakeven": {"at_r": 1.0}, "trailing": null,
           "time_exit_bars": 48, "opposite_signal": false},
  "sizing": {"risk_per_trade_r": 1.0},
  "limits": {"max_trades_per_day": 2, "cooldown_bars": 5}
}
```

### Nodos

| Tipo | Ejemplos | Devuelve |
|---|---|---|
| Lógicos | `and`, `or`, `not` | bool |
| Comparación | `gt`, `lt`, `ge`, `le`, `between` | bool |
| Cruces | `cross_up`, `cross_down` | bool |
| Temporales | `held_for(cond, n)`, `within_bars(cond, n)`, `time_between`, `weekday_in` | bool |
| Indicador | `{"ind": nombre, ...params}` | float |
| Nivel | `prev_session_high/low`, `opening_range_high/low`, `prev_day_high/low`, `donchian_high/low` | float |
| Precio | `open/high/low/close`, `range`, `body` | float |
| Patrón | `engulfing`, `pin_bar`, `inside_bar`, `bos_up/down`, `choch_up/down`, `range_expansion` | bool |
| Régimen | `trending(adx_n, thr)`, `ranging`, `vol_high(pct)`, `vol_low(pct)` | bool |
| Multi-timeframe | `{"tf": "H1", "expr": ...}` alineado con la última barra **cerrada** del TF superior | igual que `expr` |

Validación semántica (`dsl.validate`): tipos correctos (bool vs float), periodos en rangos declarados,
profundidad ≤ `max_depth` y nodos ≤ `max_nodes` (control de complejidad), sin comparar un indicador
consigo mismo, sin TF superior no alineado, sesión dentro del horario del instrumento.
Las combinaciones absurdas se rechazan **antes** de evaluar.

## 2. Bloques (catálogo `discovery/blocks.py`)

Reutiliza `indicators.py` (sma, ema, atr, zscore, rsi) importándolo. Añade en `discovery/indicators_ext.py`:
macd, adx, bollinger, stochastic, cci, donchian, keltner, vwap_session, realized_vol, atr_pct_rank,
range_compression, swing_high/low (pivotes con confirmación a la derecha: **se desplazan `right` barras**
para no mirar el futuro), bos/choch derivados de pivotes confirmados.

Cada bloque declara: parámetros y rangos, tipo de salida, `warmup` (barras mínimas), coste de cómputo y
`lookahead_safe = True` verificado por test (la salida en t no cambia si se alteran barras > t).

## 3. Compilador → señales vectorizadas

`discovery/compiler.py::compile(strategy, bars) -> Signals(long_entry: np.ndarray[bool], short_entry: ..., valid_from: int)`

- Evalúa el AST con numpy sobre arrays (caché de indicadores por `(bloque, params)` dentro del lote).
- Todas las señales se calculan con **barras cerradas**; la entrada se ejecuta en el **open de la barra siguiente**
  (misma convención que `backtest_intraday` y el EA).
- Fuera de sesión o antes de `warmup` la señal es False.

## 4. Motor rápido con salidas reales: `discovery/fastbt.py`

El motor vectorizado existente (`backtest_intraday`) no modela SL/TP. 2.0 añade un motor de eventos
**compilado con numba** (`@njit`, CPU, sin CUDA; compatible con AMD), con **fallback a Python puro**
idéntico si numba no está instalado.

Semántica (copiada de `run_event_backtest` y del motor del EA, verificada por paridad):

- Entrada a mercado en el open de t+1; long paga spread (ask), short no (bid).
- SL y TP en la misma barra → **SL** (conservador). Stop con hueco → peor precio entre stop y open.
- BE y trailing se recalculan al cierre y aplican desde la barra siguiente.
- Salida forzada (`flat_at`, fin de sesión, `time_exit_bars`), `max_trades_per_day`, `cooldown_bars`.
- Coste: **CFD** = spread horario medido (suelo `broker_spreads`) + comisión (`propfund/costs.py`) + slippage;
  **futuros** = comisión + exchange/clearing/NFA por lado + slippage en ticks × tick_value (nunca spreads MT5).
- Salida: lista de operaciones (entrada, salida, R, pnl, motivo), serie diaria de R, métricas.

**Paridad obligatoria** (`tests/test_discovery_parity.py`):
1. Señales simples traducidas a serie objetivo → mismo retorno que `backtest_intraday` (tolerancia 1e-9).
2. Órdenes con SL/TP → mismas operaciones que `run_event_backtest` en fixtures sintéticos con huecos y empates.

## 5. Plantillas (templates)

`config/discovery/templates/*.yaml`: esqueletos con huecos que el GA rellena (p. ej. "apertura NY con
filtro de volatilidad", "reversión de rango asiático", "ruptura de sesión con confirmación HTF").
Las plantillas limitan el espacio a estructuras con causa de mercado y reducen combinaciones absurdas.

## 6. Dependencias nuevas (justificadas)

| Paquete | Por qué | Alternativa si no se aprueba |
|---|---|---|
| `numba` | Bucle de eventos 50–200× más rápido en CPU AMD, sin GPU | Fallback Python (lento, solo lotes pequeños) |

Nada más: NSGA-II se implementa en el propio paquete (~300 líneas, ver doc 05) para controlar la
genealogía; Optuna ya está instalado para el optimizador.
