# FUT-E1 · Matriz de plataformas (NinjaTrader 8, Tradovate, ProjectX)

**Fecha:** 2026-11-28 · **Autor:** Claude Code · **Fuentes:** documentación oficial de las
plataformas (no de las firmas), leída el 2026-11-28. Estados de `03 §6`:
- **V:** verificado con una prueba real en demo. Todavía **ninguna** celda llega a V.
- **PV:** documentado oficialmente o implementado en el repo, sin probar.
- **NA:** no disponible.
- **NI:** no investigado.
- **RL:** requiere licencia.
- **RC:** requiere confirmación del proveedor.

## 0. Acceso a las fuentes (comprobado antes de descargar)

| Plataforma | `robots.txt` | Términos sobre acceso automatizado | Cómo se leyó |
|---|---|---|---|
| NinjaTrader (`docs.ninjatrader.com`, `developer.ninjatrader.com`) | permite todo; `ClaudeBot` explícitamente `Allow: /` | no hay términos web publicados en las rutas habituales; la documentación ofrece `llms.txt` y páginas `.md` para clientes de IA | 12 páginas `.md` sueltas, con 1 s de pausa |
| Tradovate (`api.tradovate.com`) | permite todo | el EULA (`/terms-and-eula/`) no prohíbe leer la web; regula el software | el bundle de la documentación (Redoc) |
| ProjectX (`projectx.com`, `gateway.docs.projectx.com`) | sin restricciones | **prohíbe** scraping, *data mining* y *spiders, crawlers, robots* (Terms of Use §6) | **no se descarga nada más**; esta columna sale del adaptador del repo y de las fichas de Topstep. El resto, con navegador (operador) |
| CME (`www.cmegroup.com`) | conexión fallida desde el contenedor | — | **Sin datos** (pendiente) |

SHA-256 de las copias leídas (16 primeros caracteres; copias en el scratchpad de la sesión, no en git):
- `tv_index.js`: `3cf33a05ff429c7f`;
- licencia de la API de NinjaTrader: `04f42267bb097bc4`;
- `onmarketdata`: `99ba8b4a2c675a26`;
- `onmarketdepth`: `184c67e01f163c23`;
- `order_flow_volumetric_bars`: `b99b901b2a7de3e6`;
- `developing_for_tick_replay`: `997a4d301cf02756`;
- `unmanaged_approach`: `59dbce2a018992b3`;
- `managed_approach`: `8272e7b8dc2a445b`;
- precios de NinjaTrader: `8f025b055a494aef`;
- términos de ProjectX: `7b17965b1c4e3fa0`.

## 1. Matriz

| Capacidad | NinjaTrader 8 (NinjaScript) | Tradovate (API REST + WebSocket) | ProjectX / TopstepX (API Gateway) |
|---|---|---|---|
| Histórico | **PV**. Velas del proveedor conectado. `OnMarketData` no se llama en histórico salvo con **Tick Replay**, que solo reproduce el último trade con el mejor bid/ask de ese momento | **PV**. `md/getChart` con `MinuteBar`, `Tick`, `DailyBar`, `Volume`, `Range`… | **PV** (repo): `/api/History/retrieveBars` exige suscripción (`data/futures.py`) |
| Tiempo real L1 (bid, ask, last) | **PV**. `OnMarketData()` en el orden correcto en cada cambio | **PV**. `md/subscribeQuote` | **NI** (documentación no leída por sus términos) |
| DOM (L2) | **PV**. `OnMarketDepth()`, **solo en tiempo real** («not called on historical data») | **PV**. `md/subscribeDOM`; la profundidad «may vary depending on available data» | **NI** |
| Time & sales / ticks | **PV**. `MarketDataType.Last` en `OnMarketData` | **PV**. Gráfico `Tick` con `elementSize = 1` | **NI** |
| Footprint / order flow | **PV + RL**. *Order Flow Volumetric Bars*: `BarDelta`, `CumulativeDelta`, `GetAskVolumeForPrice`, `GetBidVolumeForPrice`, `MaxSeenDelta`… Order Flow+ va **incluido en el plan Lifetime** de NinjaTrader; con la licencia que da cada firma: **Sin datos** | **NA** como rasgo nativo de la API. Se construiría desde ticks (hipotético). `md/subscribeHistogram` da volumen por precio | **NI** |
| Enviar / modificar / cancelar | **PV**. Gestionado (`EnterLong`…, señales) o **no gestionado** (`SubmitOrderUnmanaged`, `ChangeOrder`, `CancelOrder`); no se mezclan | **PV**. `order/placeorder`, `order/modifyorder`, `order/cancelorder`. **Obligatorio `isAutomated: true`** en las órdenes que no pone una persona | **PV** (repo): `/api/Order/place`, `/api/Order/searchOpen`; limit, market, stop, stop-limit, trailing y join (`execution/projectx.py`); **solo dry-run, nunca contra el servidor** |
| Brackets / OCO | **PV**. `SetStopLoss`/`SetProfitTarget` (gestionado) y estrategias ATM (`StartAtmStrategy`) | **PV**. `order/placeOSO` (`bracket1` + `bracket2` = OCO), `order/placeOCO`, `orderstrategy/startorderstrategy` | **PV** (repo): `stop_loss_ticks`/`take_profit_ticks`. TopstepX: distancia mínima de 4 ticks (ficha de Topstep) |
| Posiciones y cuenta | **PV**. Clase `Account`; la posición de la estrategia y la de la cuenta pueden diferir (documentado) | **PV**. Endpoints `position/*` y `account/*` | **PV** (repo): `/api/Position/searchOpen`, `/api/Account/search`, `/api/Position/closeContract` |
| Simulado / live | **PV**. Simulación gratuita (Sim101) en todos los planes; Market Replay y datos en tiempo real exigen una cuenta de NinjaTrader con fondos (página de precios) o la licencia de la firma | **PV**. `demo.tradovateapi.com` (simulación) / `live.tradovateapi.com`; `md.tradovateapi.com` y `md-demo` para datos | **PV** (repo): guarda de cuenta simulada; live exige `ALLOW_LIVE=YES` |
| Requisitos de acceso | **RL**. Licencia de NT8 (la dan MFF y Bulenox; TPT pide «Paid NinjaTrader License»; Topstep y Alpha no soportan NT8) | **RL/RC**. La API exige «a LIVE account with more than $1000 in equity», suscripción **API Access** y clave. **En cuentas de firma: RC** | **RL**. Topstep: API 29 USD/mes (14,50 con el código `topstep`); prohibida en la cuenta LFA |
| Límites de tasa y conexiones | **NA** en local; dependen de la conexión (CQG, Rithmic o Tradovate): **Sin datos** | **PV**. Límites por hora, minuto y segundo; responde 429 o penalización `p-ticket`/`p-time`. **1 conexión simultánea por cliente** (más, con suscripción). Cifras exactas: **Sin datos** (FAQ en GitHub, no leída) | **PV** (fichas): «fair-use limits» sin cifras; una sesión por dispositivo |
| Restricción sobre los datos | — | Licencia de la API de NinjaTrader/Tradovate: el contenido en caché **se borra o refresca en 24 h** | Términos: prohibido el *data mining* o recopilar contenido de los servicios |
| Fidelidad de backtest | La documentación avisa: Tick Replay «was NOT designed to provide accuracy in backtesting concerning order fills» | — | — |

## 2. Consecuencias para el laboratorio

1. **Los datos de investigación salen solo de Databento**, con licencia.
   - Ni NinjaTrader/Tradovate (caché máxima de 24 h) ni ProjectX (prohíbe recopilar) sirven para
     construir históricos.
   - Encaja con la decisión del operador: solo futuros, sin mezclar fuentes.
2. **Los fills los calcula el motor del laboratorio**, nunca el backtester de NT8: Tick Replay no
   garantiza fills, como admite su propia documentación.
3. **Orden de adaptadores de ejecución.** El núcleo no depende de ninguna plataforma (principio 5 de
   `03_ARQUITECTURA_FUTURES.md`):

   | Prioridad | Adaptador | Firmas que cubre (según las fichas) | Motivo |
   |---|---|---|---|
   | 1 | **NinjaTrader 8** (puente NinjaScript no gestionado) | MFF (licencia incluida), Bulenox (licencia gratis en el Master), TradeDay, Lucid (por CQG), Tradeify (por confirmar), TPT (licencia de pago) | el que más firmas cubre de las que permiten automatizar |
   | 2 | **ProjectX** (ya hay adaptador en dry-run) | Topstep (el único camino para bots) | el adaptador existe; falta probarlo en la demo |
   | 3 | **Tradovate API** | ninguna confirmada | exige cuenta live propia ≥ 1.000 USD y suscripción a la API; en cuentas de firma es RC |
   | — | **Ticket semimanual** | Alpha Futures, TPT, Apex y Earn2Trade mientras no estén verificadas | decisión del operador: en las que no aceptan bots, ejecución semimanual o réplica |

4. **Etiqueta de automatización.** Tradovate exige `isAutomated: true`. El contrato `OrderIntent` (FUT-J0)
   tiene que llevar `origin ∈ {automated, semi_manual}` y cada adaptador lo traduce. Una orden
   semimanual la confirma siempre una persona.
5. **El order flow en vivo con NT8** (`OnMarketData`/`OnMarketDepth`) es posible, pero el DOM **no** se
   puede reproducir en histórico dentro de NT8. Las hipótesis de RA-2 (L2) se validan con `mbp-10` de
   Databento y en NT8 solo se ejecutan.

## 3. Pendiente

| ID | Qué | Quién | Estado |
|---|---|---|---|
| FUT-E2 | Documentación de ProjectX (L1, DOM, límites, WebSocket) leída **con navegador**; copiar los fragmentos citados en `docs/futures/evidencia/` | operador | READY |
| FUT-E3 | Horarios y especificaciones de CME (apertura y liquidación de GC; MES y MGC) | Claude, cuando `www.cmegroup.com` responda, revisando antes sus términos; si no, el operador | BLOCKED (sin conexión) |
| FUT-E4 | Cifras de los límites de tasa de Tradovate (FAQ en GitHub) | Claude | READY (bajo valor: Tradovate queda en tercera prioridad) |
| FUT-J0 | Contrato `OrderIntent` → `RiskCheck` → adaptador/ticket, con `origin` | Claude | READY (desbloqueado por esta matriz) |
| — | Convertir cada PV en **V** con una prueba en demo (Sim101, demo de Tradovate, TopstepX en simulación) | OpenCode, tras FUT-J0 | BACKLOG |
