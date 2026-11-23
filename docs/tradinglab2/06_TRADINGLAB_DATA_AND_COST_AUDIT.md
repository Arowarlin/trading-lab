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
