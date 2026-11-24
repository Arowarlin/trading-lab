# RESULTADO — DIAG-carriles · por qué la demo no coincide con el backtest

Modelo: DeepSeek V4.1 Flash. Solo lectura: no se editó ni commiteó nada en
`E:\trading-lab`, no se operó, no se enviaron ni cerraron órdenes, no se
activaron bots ni tareas, no se tocaron setfiles/config/código protegido, no se
ejecutaron campañas ni OOS, sin push y sin borrar. La única escritura es este
archivo. Las bases se leyeron desde copias con `sqlite3.backup` en
`%TEMP%\diag-carriles\`:

- `lab.db`: 15.962.112 bytes.
- `discovery.db`: 11.378.688 bytes.

MT5 attach-only verificado antes y después: login **1515349730** / servidor
**FTMO-Demo** (balance 99.532,47 · equity 99.448,75). Había **1 posición abierta**
(`XAUUSD`, magic 20261191, ticket 590518079); no se tocó. No se envió ninguna
orden.

## 1. EA us100-ftmo1: ¿qué corre en el terminal frente al motor congelado?

### 1.1 Evidencia de versión y setfile

El terminal y el repo **no tienen el mismo EA**:

| Archivo | Terminal `MQL5\Experts\TradingLab\US100_FTMO1` | Repo `integrations\mt5\us100_ftmo1` | ¿Igual? |
|---|---|---|---|
| `US100_EA.mq5` raw / normalizado | `69b1cf03…` / `043adf2e…` | `7563bbf9…` / `bbd1e1d5…` | No |
| `US100_EntryManager.mqh` | `044777e7…` | `6ec33dc5…` | No |
| `US100_ExitManager.mqh` raw / normalizado | `8c2bde81…` / `8c2bde81…` | `62a31623…` / `89fc721d…` | No |
| `US100_MarketAnalysis.mqh` | `c4e7f8f5…` | `c4e7f8f5…` | Sí |
| `US100_Strategy.mqh` | `7a42e8d3…` | `7a42e8d3…` | Sí |
| `US100_RiskManager.mqh` | `bf5ac90e…` | `bf5ac90e…` | Sí |
| `Shared_FTMO_Risk.mqh` | `c2a44b69…` | `c2a44b69…` | Sí |
| `Shared_Logger.mqh` | `25c55ec1…` | `25c55ec1…` | Sí |
| `US100_FTMO_v3_challenge.set` | `12703dd0…` | `3f2b0fc5…` | No |

- Terminal `US100_EA.mq5:13`: `#property version "1.00"`.
- Repo `US100_EA.mq5:14`: `#property version "3.20"`.
- Terminal setfile: **no tiene** `InpEarlyClose` ni `InpHolidays`
  (`US100_FTMO_v3_challenge.set` termina en `InpDashboard`; 1.722 bytes).
- Repo setfile: sí los tiene (`US100_FTMO_v3_challenge.set:15-16`; 2.083 bytes).
- El `.ex5` del terminal está compilado el `2026-11-14 17:39` junto al `.mq5`
  del `17:38`; el log de compilación `compile_dynrisk.log` incluye los mismos
  `.mqh`.
- El `lifecycle_bots` de `ea:us100-ftmo1` congeló `setfile_sha256=3f2b0fc5…` y
  `code_sha256=5f8f0751…`, que corresponden al **repo v3.2**, no al terminal.
  `replica_sha256=fcfd6fa8…` sí coincide con `ea_us100_engine.py`.
- `criteria_preview()` en `E:\trading-lab` confirma: `setfile_sha256=3f2b0fc5…`,
  `code_sha256=5f8f0751…`, `replica_sha256=fcfd6fa8…`, `engine_version=3.2`,
  hash `f490642ba7a1f71b`.

Hashes completos de los cuatro archivos que deciden:

```text
US100_EA.mq5        terminal 69b1cf03fd865a39a1421c7d63ec7dd449ae925891b3b396c09e5dd820ae0bb8
                    repo     7563bbf9b44b630ab190e3a79a981e5f35b84d2b425735f1c74737af012efba0
US100_EntryManager  terminal 044777e791e1fb584ede325d0a8f675084b07d738baa776350ff231dde693c8a
                    repo     6ec33dc589b6e80ee1049594a14c218a05744b27d35cbcedced8950dec3cad7f
US100_ExitManager   terminal 8c2bde81c666a80293d780e5615af936ef21ba59551b6d752de66ca149eb3fee
                    repo     62a3162384cbc9652eed016fd827f57ce57f7aefa28740d4add5c0f6bbd57d9c
set v3_challenge    terminal 12703dd0b9fe9c58d79f108702bbb6bf3fbd39b8afc4b276718a18a184310735
                    repo     3f2b0fc5f5fe099e43464875d92781b86a33930f637fb3cb1ed3ceb58ffa430c
```

Conclusión de versión: el terminal corre un EA/setfile **v3** (sin cierres
tempranos ni festivos NYSE), mientras el forward congelado y
`ea_us100_engine.py` son **v3.2**. No es el mismo código.

### 1.2 Qué hizo el EA real

Los logs del terminal están en hora local del terminal (-04); la BD guarda UTC.

| Fecha | Log del EA | Fila de `fills` | Motor `ea_us100_engine` |
|---|---|---|---|
| 11-16 | `20261116.log:1` 10:55:04 · `US100_EA (US100.cash,M5)` · `SELL 9.32 @ 27495.23 · SL 27602.45 · TP 27119.95 · riesgo 999.29 USD (1.00%) · Confluencia SHORT score 70` | 14:55:04Z sell 9.32 @ 27495.13 | 11:00 NY **long** 27479.68 |
| 11-18 | `20261118.log:1-4` 09:51:56 · `US100_EA (US100.cash,M15)` · arranque; 11:55:01 · `SELL 7.87 @ 26982.63 · SL 27109.66 · TP 26538.03 · riesgo 999.73 USD (1.00%) · Confluencia SHORT score 90` | 15:55:00Z sell 7.87 @ 26981.13 | 10:00 NY **long** 27165.78 |

El EA real **vendió** los dos días, con score de confluencia SHORT 70 y 90. El
motor congelado dio **largo** los dos días. El log del 11-18 confirma además que
el EA estaba en un gráfico **M15**, no M5; el código usa `PERIOD_M5` para las
velas (`US100_EA.mq5:252,263,291`), así que el gráfico M15 no es la causa
principal de la señal, pero es una desviación de montaje: el carril congelado
espera M5.

### 1.3 ¿Error de signo del módulo drift?

No. La cadena de signo es correcta:

- `execution/mt5.py:944-953`: `DEAL_TYPE_BUY=0 → "buy"`, `DEAL_TYPE_SELL=1 →
  "sell"`.
- `mt5_fills.py:90-120`: guarda `fills.side` tal cual (`buy`/`sell`).
- `drift.py` (worktree R7b) `_entry_side`: `sell → -1`, `buy → +1`.
- `load_ea_trades` usa ese `side` y el motor exporta `d=1` largo / `d=-1`
  corto (`ea_us100_engine.py:361-366`).
- El log del EA dice `SELL`, la fila de `fills` dice `sell` y el precio de
  entrada coincide (27495.13 vs 27495.23; 26981.13 vs 26982.63).

Por tanto el 0/2 de R7b es una **deriva real del EA**, no un error de signo del
medidor. La causa es que el terminal no ejecuta el binario/setfile congelado.

## 2. EURUSD forward: línea de tiempo de las señales perdidas/tardías

La tarea `TradingLab-IntradayForward` corre cada 5 min y actúa en los primeros
5 min de cada vela M15 (`config/schedule.yaml` no la define; la tarea real:
trigger `PT5M`, `intraday_forward_execute.ps1`, `MultipleInstances=IgnoreNew`,
`ExecutionTimeLimit=PT4M`). La señal se evalúa a las :02/:17/:32/:47 UTC.

### 2.1 11-13: la tarea corrió 40 veces; el bloqueo fue freshness

- Backtest: señal `2026-11-13T07:15Z` short, entrada 1.10654, R +1.47.
- Vivo: `signals` 07:17:27 short 1.10642 `blocked freshness: datos viejos:
  259 min sin refrescar (falla a 60 min)`; siguió bloqueado todo el día.
- `forward_execute_20261113.log`: **40 INICIO / 40 FIN**, de 04:02 a 16:17 UTC.
  La tarea no llegó tarde: corrió completa.
- `data_freshness` EURUSD M15: última fila antes de 07:17 =
  `2026-11-13T02:58:40Z` (`last_bar_utc=2025-01-03T23:45Z`); la siguiente no
  llega hasta `2026-11-13T18:48:11Z`. Hay un hueco de **15 h 50 min** sin
  registro de frescura.
- Causa: **datos/frescura**, no el horario de la tarea. El registro de frescura
  no se actualizó durante la ventana de Londres.

### 2.2 11-18 y 11-20: la regla max-trades es de cuenta, no por bot

- 11-18: backtest señal 14:45 short; vivo 14:47:27 short
  `guard de cuenta: máximo de operaciones diarias alcanzado (1)`.
- 11-20: backtest señal 07:15 short; vivo 07:17:30 short, mismo motivo.
- En ambos días, **USDJPY ya había entrado a las 02:47 UTC**:
  - `orders` 11-18 02:47:28 `forward:usdjpy-tokyo-breakout-forward` sell USDJPY
    filled (ticket 586676544).
  - `orders` 11-20 02:47:31 idem (ticket 588731852).
- `forward_intraday.py:1334-1341` calcula `max_trades = min(bot 1, perfil,
  cuenta) = 1`; `:1416-1431` pasa `trades_today=account_trades` y
  `max_trades_per_day=max_trades`.
- `_today_trade_count(..., bot_id=None)` (`forward_intraday.py:402-441`) cuenta
  **todos** los `forward:%`, no solo el bot actual.
- `config/intraday_forward.yaml:32` dice “máximo 1 trade/día por bot”;
  `config/profiles.yaml:16` y `config/accounts.yaml:31` permiten 4/día por
  cuenta. El guard aplica el 1 del bot a **toda la cuenta**, así que USDJPY
  consume el cupo y EURUSD queda fuera.
- Causa: **regla max-trades account-wide no modelada en el backtest por
  carril**, no datos ni tarea tarde.

### 2.3 11-12 y 11-16: entradas tardías

**11-12** (backtest 08:15 short; demo 13:32 short, +317 min):
- `forward_execute_20261112.log` primera línea `09:02:22` local =
  `13:02:22Z`; 29 INICIO / 28 FIN. No hay traza de corridas antes de 13:02Z.
- 13:17:24Z: `blocked freshness: datos viejos: 679 min sin refrescar`
  (última fila `01:58:47Z`).
- 13:24:09Z: nueva fila de `data_freshness` (aunque con
  `last_bar_utc=2025-01-03T23:45Z`).
- 13:32:27Z: `open_short executed`.
- Causa: **la tarea no dejó corridas antes de 13:02Z + el refresco de frescura
  llegó a las 13:24Z**. El retraso de 317 min no es max-trades.

**11-16** (backtest 09:00 short; demo 15:32 short, +392 min):
- `forward_execute_20261116.log` tiene **una sola línea**:
  `10:17:25` local = `14:17:25Z INICIO`, sin FIN.
- La fila de `fills` es 14:55:04Z; la de `signals` es 15:32:28Z. El log de
  `execute` no contiene ninguna de las dos.
- `data_freshness` 14:17:19Z y 15:08:36Z tienen `last_bar_utc=2025-01-03` /
  `2025-03-14` (filas viejas); 15:32 ya tiene `last_bar_utc=2026-11-16T15:30Z`.
- Causa: **no hay traza de corridas de la tarea programada antes de 14:17Z ni
  de la entrada de 15:32Z**. La señal de 09:00 no se evaluó; no se puede
  atribuir a freshness porque a las 15:32 la fila era actual. Es una brecha de
  ejecución/trazabilidad (posible corrida manual/signal-only o log perdido).
- El JSON de R7b puso como “primer bloqueo” un `closed ticket=… corte de
  sesión` por un falso positivo de `_blocked_context` (el token “sesión” también
  aparece en un cierre). No fue un bloqueo de entrada.

### 2.4 Frescura: dos defectos de fondo

1. `data_freshness` mezcla fuentes/procesos y solo se indexa por
   `(symbol, timeframe)`. Hay filas con `fetched_at_utc` reciente y
   `last_bar_utc=2025-01-03` o `2025-03-14` (p. ej. 11-16 16:03:27Z). El
   `check` (`freshness.py:301-307`) usa la edad de **la descarga**, no la de la
   barra; una descarga reciente de un histórico viejo puede dar `ok`.
2. El forward depende de `check_freshness` (`forward_intraday.py:1150-1166`)
   antes de su propio `_stale(last_close, ...)` (`:634-636`, usado en
   `:1225-1239`). Si otra corrida escribe una fila vieja como última, el
   forward se bloquea aunque sus velas sean actuales; al revés, una descarga
   histórica reciente puede desbloquearlo con velas viejas.

## 3. us100-trend-d1: ¿puede entrar con el horario actual?

No, con el horario actual no puede.

- Config: `config/intraday_forward.yaml:63-82`: H4, `entry_start: "00:00"`,
  `entry_end: "04:00"`, `force_exit: null` (swing).
- Tarea: `scripts/intraday_forward_execute.ps1:38`:
  `$inUs100 = $minuteOfDay -ge 240 -and $minuteOfDay -le 244` → **04:00-04:04
  UTC**; `:121-129` solo invoca `us100-trend-d1` en esa ventana.
- Las velas H4 del bróker están alineadas a **02:00, 06:00, 10:00, 14:00,
  18:00, 22:00 UTC** (verificado con MT5 H4 y el offset de
  `execution/mt5_offsets.py`), no a 00:00/04:00.
- A las **04:02 UTC** la última vela cerrada abre a las **22:00 del día
  anterior** (cierra 02:00); `_bar_in_entry_window`
  (`forward_intraday.py:621-631`) compara la hora de apertura contra
  00:00-04:00 → **False**.
- A las **06:02 UTC** la última vela cerrada abre a las **02:00** (cierra
  06:00); 02:00 sí está en 00:00-04:00 → **True**.
- Evidencia viva: `signals` `2026-11-13T04:02:30Z` buy 1.0
  `blocked outside_entry_window`; `forward_execute_20261113.log` primera línea
  `04:02:24Z`. La señal de `2026-11-12T12:54` fue una corrida manual/`--force`
  fuera de la ventana, no la tarea programada.

Conclusión: la tarea se ejecuta **2 h antes** de que exista la vela H4 que la
regla espera. Con el `entry_start/end` actual, la ventana válida sería evaluar a
**06:00-06:04 UTC** (la vela 02:00-06:00). Cambiar solo `$inUs100` a
06:00-06:04 bastaría; cambiar la ventana a 02:00-06:00 también, pero entonces
hay que moverla en los dos sitios.

## 4. Contador DSR: 1060 vs 1730

`count_tests` (`learning.py:165-217`) suma:

| Componente | Valor |
|---|---:|
| `lesson_tests` | 0 |
| `optimization_trials` | 93 |
| `holdout_reads` | 4 |
| `strategy_trials` con `counted=1` | 501 |
| `campaign_registry` (`SUM(n_total)`) | 460 |
| `count_incubated` | 2 |
| `discovery_tests(discovery_db)` | 670 |
| **Total con discovery** | **1730** |

- `count_tests(lab_copy, discovery_db=disc_copy)` = **1730**.
- `discovery_tests(disc_copy)` = `{"campaigns": 670, "holdout_reads": 0,
  "total": 670}`.
- Los 670 de discovery: 27 + 440 + 32 + 27 + 144 = 670. El de 144 es
  `disc-US100.CASH-M5-20261121171711-303e5662`, `status=invalid` pero
  `approved_at=2026-11-21T17:17:12Z`; `discovery_tests` cuenta toda campaña
  aprobada que no esté `superseded` (`campaigns.py:929-970`). Si el operador
  decide que una campaña `invalid` no debe contar, el número sería **1586**;
  con la regla actual es 1730.

Por qué R7b dijo 1060:

- R7b ejecutó `count_tests` desde el worktree `tl2-r7b`; `ROOT` era el worktree
  y `DEFAULT_DISCOVERY_DB` = `<worktree>\data\discovery.db`. Ese archivo no se
  copió/no existía en el worktree, así que `discovery_tests(None)` devolvió 0.
  Resultado: 0+93+4+501+460+2 = **1060**.
- El operador ejecuta `count_tests(DEFAULT_DB)` desde `E:\trading-lab`;
  `DEFAULT_DISCOVERY_DB` = `E:\trading-lab\data\discovery.db` → 1730.
- **El contador global correcto es 1730**, no 1060. El 1060 fue un artefacto de
  la copia incompleta del worktree, no un cambio de R7b. Para reproducirlo:
  copiar `lab.db` **y** `discovery.db` y llamar
  `count_tests(lab_copy, discovery_db=disc_copy)`.

## 5. Arreglos propuestos (NO aplicados)

| # | Problema | Archivo(s) | ¿Protegido? | Cambio propuesto | ¿Autorización? |
|---|---|---|---|---|---|
| 1 | EA real v3 ≠ congelado v3.2 | `integrations/mt5/us100_ftmo1/US100_EA.mq5`, `US100_EntryManager.mqh`, `US100_ExitManager.mqh`, `US100_FTMO_v3_challenge.set`; terminal `MQL5\Experts\TradingLab\US100_FTMO1\*`; `config/mt5_eas.yaml` | Sí (`ea_us100_ftmo1`) | Copiar/compilar en el terminal el EA+setfile v3.2 del repo; o re-congelar explícitamente el v3 real. Verificar hashes contra `lifecycle_bots.criteria`. Adjuntar en M5. | Sí, operador |
| 2 | Max-trades de cuenta aplicado como si fuera por bot | `src/tradinglab/forward_intraday.py:1334-1341`, `:1416-1431` | Sí (`ftmo_forward`) | Separar `bot_max` (1) y `account_max` (4): el chequeo `bot_trades >= bot_max` sigue por bot; `evaluate_account` recibe `trades_today=account_trades` con `max_trades_per_day=account_max`. Test de USDJPY+EURUSD mismo día. | Sí, operador |
| 3 | Frescura global contamina el forward | `src/tradinglab/freshness.py` (no protegido); `src/tradinglab/execution/mt5.py` (protegido); `src/tradinglab/forward_intraday.py` (protegido); migración de `data_freshness` | Parcial | Clave por cuenta/fuente (`account`/`broker`), no solo `(symbol,timeframe)`; fallar si `last_bar_utc` es viejo aunque `fetched_at` sea reciente; no silenciar errores de `record`; que el forward use la edad de `last_close` como puerta principal. | Sí para los protegidos; revisar `freshness.py` |
| 4 | `us100-trend-d1` nunca entra | `scripts/intraday_forward_execute.ps1:38` (y `:121-129`); alternativa `config/intraday_forward.yaml:63-82` | Sí (`ftmo_forward`) | Mover `$inUs100` a **06:00-06:04 UTC** (la vela 02:00-06:00); o cambiar la ventana a 02:00-06:00 en ambos sitios. | Sí, operador |
| 5 | Sin traza de la tarea en 11-16/18/20 | `scripts/intraday_forward_execute.ps1` | Sí (`ftmo_forward`) | Escribir `INICIO`/`FIN` y un `run_id` en cada pasada (aunque salga por ventana), y correlacionarlo con `signals`/`orders`. | Sí, operador |
| 6 | Contador DSR mal copiado | Ninguno (metodología) | No | Copiar `lab.db` + `discovery.db` y llamar `count_tests(..., discovery_db=...)`; o ejecutar desde `E:\trading-lab`. Corregir R7b: 1730. | No (solo lectura) |

No se aplicó ninguno. No se cambiaron umbrales, campañas, OOS ni tareas.

## Aviso

- La copia de `lab.db` se hizo al inicio del diagnóstico; `E:\trading-lab` puede
  haber avanzado después (otra sesión). El `count_tests` 1730 es el de las
  copias; si el operador ejecuta sobre la DB viva puede variar.
- El histórico de deals de MT5 solo conserva desde `2026-11-19 19:42Z`; los
  deals de 11-16/18 no están en MT5. La evidencia de dirección del EA son sus
  logs de terminal y las filas de `fills`.
- El EA log está en hora local del terminal (-04); las conversiones a UTC se
  hicieron sumando 4 h (11-16 10:55→14:55Z; 11-18 11:55→15:55Z).
- El EA usa `PERIOD_M5` internamente aunque el gráfico sea M15; el M15 del
  11-18 es una desviación de montaje, no la causa principal de la señal.
- La señal de `us100-trend-d1` del 11-12 12:54 no es de la tarea programada
  (fuera de `$inUs100`); parece manual/`--force`.
- El 670 de discovery incluye 144 de una campaña `invalid` aprobada; el 1730 es
  correcto con la regla actual, pero el operador puede decidir excluirla (1586).

## Siguiente

1. Decidir el EA: actualizar el terminal al v3.2 congelado o re-congelar el v3
   real. Mientras no coincidan los hashes, el forward del EA no es evidencia.
2. Decidir la regla max-trades: 1 por bot o 1 por cuenta. Si es por bot, corregir
   `forward_intraday.py`; si es por cuenta, modelarla en el backtest.
3. Corregir la frescura por cuenta/fuente y la edad de la barra; hoy una fila
   de otro proceso puede bloquear o desbloquear el forward.
4. Mover la evaluación de `us100-trend-d1` a 06:00-06:04 UTC (o cambiar la
   ventana a 02:00-06:00) y añadir un test de la barra H4 02:00-06:00.
5. Corregir R7b: el DSR global es 1730, no 1060.
6. No se aplicó nada: cualquier cambio en archivos protegidos, tareas o
   setfiles requiere autorización explícita del operador.
