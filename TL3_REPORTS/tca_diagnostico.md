# TL3-D · D5b Diagnóstico de la TCA

Solo lectura: no se modifica `execution/mt5.py`, `execution/paper.py`, `lab.db` ni la tabla `tca`. Nada de este bloque suma al contador.

## 1. Causa

**Confirmada.** `execution/mt5.py:772-783` registra:

- `signal_px=price` y `order_px=price`, donde `price` es el precio de la petición en el momento del envío, no el precio de la decisión.
- `fill_px = result.price or price`: si MT5 devuelve 0, cae al precio pedido.
- `slippage_bps=tca_slip(price, fill_px, side)` y no se pasa `latency_ms`.

`execution/paper.py:140-155` hace lo mismo con `signal_px=price`, `order_px=price`, `fill_px=fill_px` y, además, `slippage_bps=self.slippage_bps` (el supuesto del modelo, no una medida). `tca.record_fill` guarda `ts_utc` como hora de registro, no de fill.

Consecuencia: la TCA solo mide el desvío entre el envío y la ejecución en el mismo tick; nunca entre la decisión y la ejecución. Si `result.price` es 0 o igual a `price`, el resultado es 0 por construcción.

## 2. Conteos

- Filas: **68**; `slippage_bps=0`: **66**; `fill_px` nulo: **2**; `latency_ms` nulo: **68**; sin `bid`/`ask`/`requested_price`: **58**.

| Bot | Símbolo | Filas | Slippage 0 | `fill_px` nulo | Sin bid/ask/requested |
|---|---|---:|---:|---:|---:|
| ai:discrecional | XAUUSD | 1 | 1 | 0 | 1 |
| ai:intraday | GBPUSD | 2 | 2 | 0 | 1 |
| ai:intraday | US100.CASH | 1 | 1 | 0 | 0 |
| ai:intraday | USDJPY | 1 | 1 | 0 | 0 |
| ai:scalping | US100.CASH | 26 | 26 | 0 | 24 |
| ai:scalping | XAUUSD | 20 | 20 | 0 | 17 |
| forex:trend-ls | EURUSD | 1 | 1 | 0 | 1 |
| forex:trend-ls | XAUUSD | 1 | 1 | 0 | 1 |
| forward:eurusd-london-pullback-forward | EURUSD | 7 | 7 | 0 | 6 |
| forward:usdjpy-tokyo-breakout-forward | USDJPY | 3 | 3 | 0 | 2 |
| manual:addon | XAUUSD | 1 | 1 | 0 | 1 |
| manual:analista | US100.CASH | 1 | 1 | 0 | 1 |
| manual:analista | XAUUSD | 1 | 1 | 0 | 1 |
| qqq-trend-f13 | QQQ | 2 | None | 2 | 2 |

Las 2 filas de `qqq-trend-f13` no tienen `fill_px`; las otras 66 filas tienen slippage 0. Todas las filas tienen `latency_ms` nulo.

## 3. Slippage decisión → ejecución

No hay un precio de decisión unible sin suposiciones en las tablas que mira D5b:

- `ai_decisions`: 150 decisiones `take`, 101 con `entry`; no hay `proposal_id`/`order_id` y las 48 recientes lo tienen nulo.
- `orders`: 75 órdenes market, 0 con `limit_price`.
- `signals`: 1535 filas, 2 con `run_id`; no hay `order_id`.
- `fills` de IA: 81 filas, 81 con `order_id` nulo; `tca.fill_id` nulo en 68 de 68.

Sí existe un enlace exacto para las operaciones de IA: `ai_trades.entry` (precio de la propuesta/decisión) y `fills.price` (fill real), unidos por bot, símbolo, lado, magic y una ventana temporal única. Se exige **una sola** fila candidata; si hay 0 o >1, es **Sin datos**.

| Ventana | n | Mediana bps | p95 bps | Mediana puntos | p95 puntos | Media R | Mediana R |
|---|---:|---:|---:|---:|---:|---:|---:|
| ≤5 s | 42 | 0.157 | 2.307 | 6.0 | 360.0 | +0.0083 | +0.0039 |
| ≤20 s | 45 | 0.440 | 2.263 | 12.0 | 360.0 | +0.0114 | +0.0076 |

Sin datos con la ventana de 20 s: #4, #30, #31.

Por símbolo (ventana de 20 s):

| Símbolo | n | Mediana bps | p95 bps |
|---|---:|---:|---:|
| GBPUSD | 2 | 1.031 | 1.133 |
| US100.cash | 25 | 0.666 | 2.138 |
| USDJPY | 1 | 0.440 | 0.440 |
| XAUUSD | 17 | 0.107 | 2.219 |

El `fill_px` de la TCA **no es el fill real** en 43 de 45 operaciones comparables: mediana de |diferencia| 0.426 bps, máximo 2.899 bps. Ejemplo: #15, TCA 26899.43 frente a fill real 26907.23 (780 puntos de US100, 2.899 bps).

Para los bots que no son de IA no hay precio de decisión: `tca.signal_px` es el precio de envío y `orders.limit_price` es nulo, así que su decisión → ejecución es **Sin datos**; el envío → fill de la TCA es ~0 por construcción.

### Comparación con T5-bis

T5-bis atribuye **+0.0661 R** a la entrada, medido como `sim_entry − ai_trades.entry` (la decisión), no como `sim_entry − fill`. El fill real fue **+0.0114 R** peor que la decisión (media, ventana de 20 s); por tanto, la entrada simulada frente al fill real es ~**+0.0547 R**. La mayor parte del componente de entrada es la regla de entrada de la simulación, no la ejecución. No se rehace T5 y las cifras agregadas de C1/T5 no cambian.

## 4. Lectores de `tca.slippage_bps`

| Lector | Qué hace | Efecto con el valor actual |
|---|---|---|
| `ai_trader.py:3209` (`_slippage_avg`) | `AVG(slippage_bps)` por bot y símbolo; llena `slippage_avg` del marcador de celdas. | Muestra 0 bps; no es un coste ni un gate (solo se imprime en `cli.py:9759`). |
| `ai_distill.py:1260` (`_forward_validation`) | `AVG(slippage_bps)` por bot; exige n≥10 y `avg ≤ max_slippage_bps` (3.0) y ≤ el supuesto. | Pasa siempre con 0; la validación forward no puede detectar slippage. |
| `tca.py:211-215` (`build_tca`) | p50/p95/EWMA y estado `ok`/`vigilar`/`deriva`. | p50≈0 → `ok`; con <5 fills, `sin datos`. |
| `tca.py:250-280` (`_alert_transitions`) | Envía `tca_drift` solo al pasar a `deriva`. | Nunca se dispara con 0. |
| `tca.py:296-312` (`attach_to_drift`) | Añade `tca_status` y EWMA a las filas de deriva. | Informativo; no cambia el estado de deriva. |
| `web.py:2044-2062` (`/api/tca`) | Panel TCA. | Muestra `ok`. |
| `cli.py:8654-8679` (`lab tca`) | Tabla de slippage/latencia. | Muestra 0 bps y latencia Sin datos. |
| `discovery/slippage_measured.py:286-291` | Fuente `tca`: usa `order_px`/`fill_px` para celdas y propuesta de costes (`costs.measured.yaml`). | También mide ~0; la propuesta subestima el coste. No se ejecutó en este bloque. |

## 5. Propuesta de corrección (no aplicada)

1. **`signal_px`**: pasar el precio de la decisión/propuesta (el que genera la señal o el plan), no el precio de la petición. Si no existe, pasar `None` y dejar `slippage_bps` nulo; nunca 0.
2. **`fill_px`**: usar el precio del deal ejecutado. Si MT5 devuelve 0, dejar `None`; no caer a `price`.
3. **`latency_ms`**: capturar la hora de la decisión y la del fill y pasar la diferencia en ms. Como mínimo, medir envío → fill y etiquetarlo como tal; no llamarlo decisión → ejecución.
4. **Paper**: registrar el coste esperado en `expected_cost_bps` y la medida real en `slippage_bps`; no etiquetar `self.slippage_bps` como slippage medido.
5. **Filas antiguas**: no borrar ni reescribir. Añadir una marca `measurement`/`tca_version` (o una vista `tca_measured`) que excluya las filas sin `latency_ms` o sin `bid`/`ask`/`requested_price`, y hacer que los consumidores lean la vista. Las filas viejas quedan para auditoría.
6. **Producción**: `execution/mt5.py` es la ejecución del forward y de `ai_trader`. Aplicar esto exige otra cola con aprobación del operador: línea base (`lab propfund baseline --reason`), test de regresión, `docs/CHANGELOG-produccion.md` y tag `tl2-<id>-pre`.

## Límites

- No se modificó `execution/mt5.py`, `execution/paper.py`, `tca.py`, `lab.db` ni la tabla `tca`.
- No se enviaron órdenes ni se abrió MT5.
- No se ejecutó `discovery/slippage_measured` ni se escribió `costs.measured.yaml`.
