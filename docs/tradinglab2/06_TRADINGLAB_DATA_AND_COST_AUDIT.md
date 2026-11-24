# 06 · Datos y costes: auditoría y requisitos para el motor genético

**Regla:** el motor genético no corre sobre un instrumento cuyo dataset no haya pasado `datacheck` y el
informe de calidad de `discovery/data_quality.py`.

## 1. Estado por instrumento

| Instrumento | Fuente | Histórico | Estado |
|---|---|---|---|
| US100.cash | MT5 FTMO | M5 desde 2017-12 (≈368k velas) | ✅ apto |
| US500.cash | MT5 FTMO | M5 desde 2017-12 | ✅ apto (spread medido 0,81 bps) |
| US30, GER40, XAUUSD, EURUSD, GBPUSD, USDJPY, GBPJPY | MT5 FTMO | por descargar/validar con la misma rutina | 🟡 |
| NQ, MNQ, ES, MES, GC, MGC | **Ninguna** (`data/futures.py` es un stub) | — | ⚪ bloqueado |

## 2. Futuros: proveedor recomendado

- **Databento** (`GLBX.MDP3`): OHLCV 1 min con contratos individuales, créditos iniciales gratuitos.
  Proveedor nuevo `discovery/data_databento.py` (no edita `data/futures.py`), clave en keyring
  (`DATABENTO_API_KEY`), **estimación de coste antes de descargar** y descarga solo con aprobación.
- **Contrato continuo**: construido localmente con roll por volumen o fecha fija (5 días hábiles antes
  del vencimiento), **ajuste por diferencia** para señales y precios **no ajustados** para ejecución y
  costes. Se guardan ambos y la tabla de rolls.
- **Símbolos** (`discovery/fetch_databento.py`): NQ→US100, ES→US500, YM→US30, GC→XAUUSD,
  6E→EURUSD, 6B→GBPUSD y 6J→USDJPY. El 6J cotiza USD por JPY; USDJPY se obtiene invirtiendo
  barra a barra (`open=1/open`, `high=1/low`, `low=1/high`, `close=1/close`) y conservando el volumen.
- **ProjectX**: queda para ejecución en Practice cuando haya API (doc 08, fase 10).

## 3. Controles de calidad (`discovery/data_quality.py`)

Reutiliza `datacheck.check_frame` y añade: duplicados, OHLC inválido, huecos intradía en sesión,
festivos con datos, cierres tempranos, zona horaria declarada vs observada, `point/digits`, cobertura de
los tres tramos (IS/OOS-1/OOS-2) y, para futuros, continuidad en los rolls. Resultado
`ok/warn/fail` guardado con el **hash del dataset**; cada estrategia del databank referencia ese hash.

## 4. Costes

| Mercado | Componentes | Fuente |
|---|---|---|
| CFD | spread por hora (suelo `broker_spreads`), comisión por lote o % de volumen, slippage, swap si hay noche | `propfund/costs.py`, `config/costs.yaml` (FTMO verificado) |
| Futuros | comisión por lado, exchange + clearing + NFA, slippage en ticks × tick_value | `propfund/costs.py::estimate_futures`; comisiones de firma **pendientes de verificar** |

- El fitness usa el perfil **conservador** (p75); la matriz por firma usa el perfil de **cada cuenta**.
- Falta de dato = "Sin datos" → el individuo es no factible (no se inventa coste).
- CFD y futuros nunca comparten modelo de coste ni se trasladan sin marcarlo como **transferencia**.

## 5. Modelo de ejecución v2 (BID/ASK)

Las barras de Discovery son **BID**. El modelo v1 cobraba el spread en la
entrada y otra vez en toda salida que no fuera por objetivo, y disparaba el
stop de un corto con el máximo BID. El modelo v2 cobra **un solo spread por
operación** y dispara el stop del corto con el ASK.

| Operación | Coste v2 (bps por barra) |
|---|---|
| Largo · entrada | `comm + slip + spread[entrada]` |
| Largo · stop, tiempo, señal, flat, fin | `comm + slip` |
| Largo · objetivo | `comm` |
| Corto · entrada | `comm + slip` |
| Corto · stop, tiempo, señal, flat, fin | `comm + slip + spread[salida]` |
| Corto · objetivo | `comm` (el precio del objetivo ya es un nivel ASK) |

- **Stop de un corto:** se dispara si
  `high[i] + high[i]·spread_bps[i]/1e4 >= stop_p`. El precio de salida es
  `max(stop_p, open_ask)` con `open_ask = open + open·spread/1e4`; en esa ruta
  el spread ya está en el precio y **no** se vuelve a sumar al coste.
- **Objetivo de un corto:** se comprueba con `low + spread`, como en v1.
- `CostPanel` lleva `spread_bps`, `slip_bps` y `comm_bps` por barra. `entry_bps`,
  `stop_bps` y `target_bps` quedan como propiedades de compatibilidad para la
  v1.
- `Trade` añade `spread_r`, `slip_r` y `comm_r`; su suma menos `swap_r` es
  `r_cost` (tolerancia 1e-9). En futuros, `comm_r` incluye el coste por
  contrato (`2·fut_price/riesgo`) porque el spread es 0.
- **Versión:** `cost_model_version` se guarda en el `config_json` al registrar
  (2 por defecto en campañas nuevas). Una campaña sin el campo se carga como
  **1**, de modo que las antiguas se reproducen igual. `jobs`, `fitness`,
  `drift`, `robustness`, `levels`, `feasibility` y `basket` la pasan a
  `fastbt.run`; `CostBook` aplica las mismas reglas por cuenta y versión.
- `FuturesCosts` mantiene `spread = 0`: su coste sigue en `fut_price`.

### Comparación antes/después (solo coste, sin rendimiento)

`feasibility` sobre las specs de referencia, v1 frente a v2
(`reports/discovery/t10-feasibility-v1-v2.json`):

| Spec | v1 cost_R min / med / max | v2 cost_R min / med / max | Factibles v1 / v2 |
|---|---|---:|---:|
| `q2-fix-eurusd-h1` | 0,0327 / 0,0359 / 0,0392 | 0,0306 / 0,0337 / 0,0367 | 6/6 · 6/6 |
| `q2-fix-gbpusd-h1` | 0,0285 / 0,0328 / 0,0378 | 0,0238 / 0,0262 / 0,0286 | 6/6 · 6/6 |
| `q2-fix-usdjpy-h1` | 0,0330 / 0,0371 / 0,0415 | 0,0284 / 0,0319 / 0,0357 | 6/6 · 6/6 |
| `q1-rebote-us500-d1` | 0,0306 / 0,0515 / 0,0744 | 0,0250 / 0,0483 / 0,0653 | 15/27 · 15/27 |
| `r9b-tom-us500-d1` | 0,0327 / 0,0473 / 0,0641 | 0,0274 / 0,0424 / 0,0592 | 9/9 · 9/9 |

La caída es la esperada al eliminar un spread completo por operación. No se
calcula expectativa, PF ni percentil: solo coste. La tabla no cambia ningún
veredicto histórico; T40 reevaluará con campañas nuevas.
