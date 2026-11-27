# FUT-3 · Arquitectura objetivo futures-first, datos, backtesting, plataformas y ADR

**Fecha:** 2026-11-27 · **Autor:** Claude Code · **Estado:** propuesta, **pendiente de aprobación del
operador** (cambiar la arquitectura requiere su visto bueno). Nada de esto está implementado.

## 1. Principios

1. **Evolucionar, no reconstruir.** El código nuevo va en paquetes nuevos; `discovery/`, `prop/`,
   `execution/mt5.py` y los carriles en producción no se tocan sin el procedimiento de `AGENTS.md`.
2. **USD y contratos enteros** para futuros. La R queda como unidad de informe, no de contabilidad.
3. **Identidad de datos explícita**: raíz + contrato + `instrument_id` + esquema + hash. Nunca un
   nombre de CFD para un futuro.
4. **Separar lo realizado de lo simulado** en datos, informes y pantallas.
5. **El núcleo no depende de una plataforma.** NinjaTrader 8 es el primer adaptador de referencia, no
   el centro.
6. **Una herramienta por problema** (`01_MATRIZ_TECNOLOGIA.md §3`).

## 2. Componentes: qué se conserva, refactoriza, sustituye o construye

| # | Componente | Hoy | Decisión | Dónde |
|---|---|---|---|---|
| 1 | Futures Market Data Core | `fetch_databento.py` (OHLCV, sin `instrument_id`), `futures_roll.py` (heurística) | **Construir** núcleo nuevo; el viejo queda para campañas existentes | `src/tradinglab/futures/data/` |
| 2 | Quantitative Research Core | `discovery/` (31 k líneas) + `tl3/` | **Conservar**; extender con plantillas de futuros y método de prueba única | `discovery/`, `tl3/` |
| 3 | Strategy Engine | DSL + compiler de `discovery` | **Conservar** para barras; añadir declaración de contrato, sesión y tipo de orden | `discovery/dsl.py` (con versión) |
| 4 | Signal Engine | señales dentro de `fastbt`/`forward_intraday` | **Construir** emisor de tickets independiente del motor | `src/tradinglab/futures/signals/` |
| 5 | Risk Engine | `prop/guard.py` (FTMO, %), `risk.py` | **Construir** motor de futuros (USD, contratos, firma, perfil); el guard FTMO sigue igual | `src/tradinglab/futures/risk/` |
| 6 | Portfolio Manager (cuentas) | `propfund/router.py`, `accounts.yaml` | **Construir** el estado de cuentas de futuros dentro del motor EV (§5.7 del encargo) | `src/tradinglab/prop_economics/portfolio.py` |
| 7 | Execution Core | `execution/` (MT5 producción, paper, ProjectX dry-run) | **Construir** contrato `OrderIntent → Adapter`; ProjectX se adapta a él y pasa a keyring | `src/tradinglab/platforms/` |
| 8 | Platform Adapters | ProjectX (dry-run) | **Construir** NT8 (primero), Tradovate y ProjectX sobre el contrato | `src/tradinglab/platforms/<plataforma>/` + `integrations/ninjatrader8/` |
| 9 | Prop Firm Rules Engine | `propfund/registry.py` + `firms.yaml` (reglas de futuros vacías) | **Construir** esquema de programas en USD con versión y caducidad; se enlaza a `firms.yaml` por `firm_id` | `config/prop_economics/programs/`, `prop_economics/rules.py` |
| 10 | Backtesting Engine | `fastbt` (barras, numba) | **Conservar** como nivel 1 (cribado) + guardas de futuros; **construir/adoptar** nivel 2 de eventos tras FUT-X1/X3 | §4 |
| 11 | Forward Testing Engine | `NASDAQ_EDGE/tools/forward_daily.py`, `forward_intraday.py` | **Conservar**; el forward NQF no se toca | — |
| 12 | Monitoring | `heartbeat.py`, `guardian.py`, `task_health.py`, alertas | **Conservar** | — |
| 13 | Dashboard | `web.py` (3.141 líneas) + `webui/` | **Extender** con vistas de futuros y separación realizado/simulado (Task H) | `web.py` sub-rutas nuevas |
| 14 | Storage | SQLite (`lab.db`, `discovery.db`, `tl3_research.db`) + Parquet | **Conservar**; añadir DuckDB solo como motor de consulta sobre Parquet | `data/futures/` |
| 15 | Audit Logs | `audit.append_hashed` | **Conservar** y usar en cada ticket y orden | — |

## 3. Arquitectura de datos de futuros

### 3.1 Niveles de datos y qué hipótesis permiten

| Nivel | Esquema Databento (Confirmado en el cliente) | Contenido | Permite | Hoy |
|---|---|---|---|---|
| L0 | `ohlcv-1m`, `ohlcv-1h` | barras sin bid/ask | NY open por barras, contexto | NQ M1 2010-2018; H1 2010-2026 |
| L1a | `trades` | cada operación con lado agresor | delta, CVD, footprint, clusters de volumen, agotamiento | **Sin datos** |
| L1b | `tbbo` / `mbp-1` / `bbo-1s` | mejor bid/ask (en cada trade o continuo) | spread real, coste a la apertura, delta con cotización | **Sin datos** |
| L2 | `mbp-10` | 10 niveles de libro | DOM, profundidad, reposición de liquidez | **Sin datos** |
| L3 | `mbo` | cada orden | icebergs, posición en cola, fills de límites realistas | **Sin datos** |
| Ref. | `definition`, `statistics`, `status` | contratos, vencimientos, settlement, halts | rolls exactos, festivos reales, límites de precio | **Sin datos** |

**Regla (ADR-F05):** ninguna hipótesis de order flow se evalúa con L0. Si un indicador de order flow se
aproxima con barras, se etiqueta `proxy` y no puede aprobar nada.

### 3.2 Almacenamiento

```text
data/futures/                         (fuera de git, en E:\trading-lab\data)
  raw/<proveedor>/<dataset>/<esquema>/<raiz>/<AAAA-MM-DD>.dbn.zst   inmutable, tal como llega
  norm/<esquema>/<raiz>/<contrato>/<AAAA>.parquet                  UTC ns, ts_event y ts_recv
  derived/<tipo>/<raiz>/<version>/...                              barras, footprint, continuos
  catalog/manifest.jsonl                                           una fila por fichero: sha256,
                                                                   proveedor, esquema, licencia,
                                                                   rango, filas, generador y versión
```

- **Identidad:** raíz (`NQ`, `MNQ`…), contrato (`NQZ6`), `instrument_id`, esquema, proveedor.
- **Tiempo:** UTC en nanosegundos. Fecha de sesión CME: la sesión de D empieza a las 17:00 hora de
  Chicago de D−1 (18:00 ET); la conversión usa `zoneinfo` con `America/Chicago` y `America/New_York`,
  así que el cambio de horario se resuelve solo. Sesión regular de índices: 09:30-16:00 ET (**No
  verificado** para cada producto; se deriva de los datos como hace hoy `derive-sessions`).
- **Rolls:** tabla generada desde `definition` (vencimientos) y volumen diario por contrato, con la regla
  declarada por raíz (calendario o volumen). Nunca desde el resultado de una estrategia.
- **Continuos:** sin ajustar para ejecución y costes; ajustado por diferencia para señales, siempre con la
  tabla de rolls citada por hash.
- **Calendario:** festivos y cierres tempranos desde `status`/`statistics` cuando existan; mientras
  tanto `discovery.calendars` con el aviso FUT-08.
- **Licencias:** una suscripción de datos no autoriza redistribuir ni operar. Los términos concretos de
  Databento para CME (uso interno, no visualización, redistribución) están **No verificados**:
  **requieren confirmación del proveedor** antes de la compra.

### 3.3 Calidad

Cada dataset nuevo pasa la skill `futures-data-audit` (huecos, duplicados, timestamps no monótonos,
trades fuera del bid/ask, lado agresor ausente, cambios de contrato) y queda en el manifiesto con su hash.

## 4. Arquitectura de backtesting

| Nivel | Motor | Para qué | Fills | Límite |
|---|---|---|---|---|
| 1 · Cribado | `fastbt` (barras, numba) | descartar ideas baratas | mercado al open siguiente; stop con hueco; **objetivo/límite: trade-through ≥ 1 tick** (nuevo, con versión de motor) | no aprueba nada que use límites a ≤ N ticks |
| 2 · Validación | simulador de eventos (propio en `futures/sim/`, o Nautilus/hftbacktest si ganan FUT-X1/X3) | todo candidato antes del forward | cola FIFO o probabilística, latencia, parciales, contratos enteros | necesita L1/L3 |
| 3 · Forward | `forward_daily` / paper | evidencia limpia | reales de la plataforma demo | tiempo |

**Contrato de salida común** (lo consume el motor EV): lista de operaciones y una `DayPath` por sesión
con la trayectoria de P&L de 1 contrato (`04_SPEC_PROP_EV.md §2`).

## 5. Riesgo, ejecución automática y semiautomática

```text
Señal ─▶ OrderIntent ─▶ RiskCheck(firma, programa, perfil, contratos, noticias, DLL, emergency stop)
                              │
                ┌─────────────┴─────────────┐
     automation_permission = allowed   prohibited / conditional no cumplida
                │                           │
        Adapter (demo/sim)          Ticket semiautomático ─▶ confirmación humana ─▶ el humano opera
                │                           │
                └──────── audit.append_hashed (cada paso) ─────┘
```

- El **ticket** muestra: setup, dirección, entrada, stop, objetivo, contratos, riesgo en USD, R:R,
  reglas de la cuenta en ese momento (colchón al MLL, DLL restante, ventana de noticias), invalidación y
  la explicación de la señal.
- La permisión de automatizar sale del registro (`firms.yaml → automation`). Hoy: Apex y Take Profit
  Trader `prohibited` (fuentes secundarias en parte, `needs_verification`); Topstep `conditional` (API
  TopstepX, no en Live Funded, sin VPS). **Confirmado** como contenido del registro; vigencia **No
  verificada**.
- Perfiles de riesgo separados: `evaluation`, `funded`, `payout_producing`, `personal`.
- **Emergency stop** global y por cuenta; ninguna orden si el estado del riesgo no se puede leer.

## 6. Matriz de capacidades de plataformas (inicial)

Estados: **V** verificado · **PV** parcialmente verificado · **NA** no disponible · **NI** no
investigado · **RL** requiere licencia · **RC** requiere confirmación del proveedor.

| Capacidad | NinjaTrader 8 | Tradovate | ProjectX (TopstepX) |
|---|---|---|---|
| Histórico / tiempo real | NI | NI | PV: `/api/History/retrieveBars` exige suscripción (`data/futures.py`) |
| Tick, bid/ask, DOM, time & sales | NI | NI | NI |
| Footprint | NI (los indicadores de NT8 lo dibujan; la licencia necesaria es NI) | NA en la API (Hipotético) | NI |
| Enviar / modificar / cancelar | NI | NI | PV: `/api/Order/place`, `searchOpen`; tipos limit/market/stop/stop-limit/trailing/join (`execution/projectx.py`); **solo dry-run, nunca probado contra el servidor** |
| Brackets | NI | NI | PV: `stop_loss_ticks`/`take_profit_ticks` en el adaptador |
| Posiciones y cuenta | NI | NI | PV: `/api/Position/searchOpen`, `/api/Account/search` |
| Simulado / live | NI | NI | PV: guard de cuenta simulada; live exige `ALLOW_LIVE=YES` |
| Permisos de automatización | según firma | según firma | Topstep: API con suscripción, no en LFA (registro, 2026-11-19) |
| Licencias | RL (licencia de NT8 y datos) | RC | RC (suscripción API) |
| Límites de tasa | NI | NI | NI |

La matriz se completa en FUT-E1 (investigación de Claude con documentación oficial) y cada "V" exige
una prueba real en demo.

## 7. Programas de investigación A y B

| | Research A · Microestructura y order flow | Research B · NY open |
|---|---|---|
| Campaña | `FUT-RA-<n>` | `FUT-RB-<n>` |
| Datos mínimos | L1a `trades` (+ L1b para spread); L3 solo para fills de límites | L0 M1 2019+ y L1b para el coste en la apertura |
| Bloqueo | **compra de datos** (decisión 5 de `ESTADO.md`) | **contaminación** de NQ/US100 2010-2026 (FUT-11) |
| Método | prueba única prerregistrada por hipótesis (ENG-1 R1), sin barridos | ídem; en NQ, evidencia solo en forward; ES/MES y GC/MGC como campo limpio (US500 ya se usó en la prueba de transferencia del EA: contaminación parcial) |
| Coste a superar | ~0,25 R con stops de 5 pt en MNQ (`00_AUDITORIA_REPO.md §4`) | según stop; se calcula en el prerregistro |
| Ventaja mínima | la que fije el motor EV (μ\*) por programa | ídem |

**Independencia (ADR-F07):** contadores, campañas, informes y decisiones separados. Un híbrido solo se
estudia cuando A y B hayan pasado cada uno su validación.

## 8. Decisiones de arquitectura (ADR)

| ID | Decisión | Motivo | Alternativa descartada |
|---|---|---|---|
| **ADR-F01** | Futures-first. Los carriles CFD/FX se **congelan** (sin desarrollo nuevo) y llegan a sus controles prerregistrados | Apagarlos no ahorra nada y destruye evidencia | Apagar el EA y `ai_trader` ya |
| **ADR-F02** | Contabilidad de futuros en USD y contratos enteros | Las reglas de las firmas son en USD y el redondeo cambia el riesgo | Seguir en R |
| **ADR-F03** | Motor EV nuevo `prop_economics/`, separado de `prop/` | `prop/` es producción (guard FTMO) y modela % diarios | Ampliar `prop/simulator.py` |
| **ADR-F04** | Contrato de datos con identidad + hash; continuos desde `definition` | FUT-06/07 | Seguir infiriendo rolls |
| **ADR-F05** | Order flow solo con L1+; los proxies de barras no aprueban | E-06 | Usar VWAP/volumen de barras como order flow |
| **ADR-F06** | NY open en NQ: evidencia de forward; ortogonales con marca de contaminación | FUT-11 | Reabrir la historia |
| **ADR-F07** | A y B independientes hasta validar cada una | Encargo §6.1 | Combinar para rescatar una línea |
| **ADR-F08** | Ejecución por `OrderIntent → RiskCheck → Adapter/Ticket`, NT8 primero | multiplataforma | Lógica de órdenes dentro de cada estrategia |
| **ADR-F09** | Reglas de firma versionadas con `consulted_at`, `effective_from`, `expires_after_days` (defecto 30) y certeza; el motor **rechaza** reglas caducadas | las reglas cambian | Reglas sin fecha |
| **ADR-F10** | Multiple testing: contador único global + Bonferroni sobre las lecturas del OOS-2 por línea (ENG-S2) | ENG-1 D-03 | DSR con N = población |
