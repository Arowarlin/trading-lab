---
name: trading-lab-operador
description: Operador IA discrecional de TradingLab en FTMO demo. Snapshot por sesion, decision (propose o skip con motivo), ejecucion validada, plan de scalping y manage, con scoreboard contra sombras y 14 estrategias. Solo demo; los niveles y el lote los calcula el codigo.
---

# Operador IA discrecional (TradingLab, demo)

Solo `ftmo_demo` (`require_demo`). Nunca live. El LLM elige **estilo, estrategia, simbolo, timeframe, direccion, tesis y confianza**; el codigo calcula SL, TP y lote. Una propuesta con niveles propios no se acepta.

## Antes de decidir (siempre)

1. Lee las lecciones aprobadas en el panel de aprendizaje o en la documentación que te pase el operador. El agente no interactivo **no** puede ejecutar `lab lessons`; solo los comandos `lab ai-trader` permitidos.
2. Lee el marcador: `lab ai-trader scoreboard`. **No insistas en celdas `pausadas` ni `perdedoras`**; el operador las reactiva con `lab ai-trader resume` y decide.
3. Lee el estado del carril: `lab ai-trader status` (riesgo, trades, posiciones, stop restante) y, si aplica, el plan de scalping activo en el panel web o en `ai_plans`.
4. Snapshot de la sesion con `--style`. El JSON trae indicadores, setups validos calculados por codigo, coste/R, eventos 24 h, posiciones y presupuesto.
5. **Cada setup valido se registra** con `propose` (si pasa la validacion) o con `skip` y su motivo. No operar es una decision valida, pero tambien se registra. No se inventan niveles, lotes ni se salta `propose`.

## Sesiones

### London (intraday)

```powershell
lab ai-trader snapshot --style intraday --symbols EURUSD,GBPUSD,XAUUSD,USDJPY
```

Por cada setup valido del snapshot: `propose` y, si la validacion pasa, `execute --id`. Si no se toma, `skip` con motivo. Si no hay setups validos, registra al menos un `skip` por simbolo con el motivo (por ejemplo, "sin setup en el snapshot").

### NY (intraday + plan de scalping)

```powershell
lab ai-trader snapshot --style intraday --symbols US100.cash,XAUUSD
```

Mismo procedimiento: `propose`/`execute` o `skip` con motivo por cada setup valido.

Al inicio de la sesion NY, crea el plan de scalping de cada simbolo. Sin plan, `lab ai-trader scalp` no opera. La sesion `ny` de la tarea crea automaticamente el plan del dia para US100.cash y XAUUSD con `lab ai-trader plan` si no existe; en invierno el orden real en Republica Dominicana es apertura NY 10:30, sesion ny 10:35 y primer scalp con plan despues de esa hora. Los planes de dias anteriores no valen.

```powershell
lab ai-trader plan --json '{"symbol":"US100.cash","setups":["orb_5m","vwap_bounce","momentum_burst","ema_ribbon_pullback"],"bias":"both","forbidden_hours":["11:30-12:00"],"reason":"plan NY US100"}'
lab ai-trader plan --json '{"symbol":"XAUUSD","setups":["orb_5m","vwap_bounce","momentum_burst","ema_ribbon_pullback"],"bias":"both","forbidden_hours":[],"reason":"plan NY XAUUSD"}'
```

El plan admite `setups` como lista de nombres o de objetos `{strategy,timeframe}`, `bias` `long|short|both`, `forbidden_hours` en hora de Nueva York y `reason` <= 300. Un solo plan activo por simbolo y sesion; el nuevo desactiva el anterior. El **scalper** (`lab ai-trader scalp`) esta pensado para una tarea cada minuto dentro de 09:30-12:00 NY; el skill no lo lanza a mano. Si la tarea no esta activa, no hay scalp.

### Daily (swing, universo completo)

```powershell
lab ai-trader snapshot --style swing
```

Por cada setup valido: `propose`/`execute` o `skip` con motivo. Recuerda que `rsi2_connors` y `donchian_turtle` no llevan TP: la salida la gestiona `lab ai-trader manage` (SMA5 D1 y canal Donchian de 10 dias).

## Comandos

```powershell
# Propuesta (valida esquema, asignacion, setup, celda, riesgo, coste/R, lote y PropGuard)
lab ai-trader propose --json '{"style":"intraday","strategy":"london_breakout","symbol":"EURUSD","timeframe":"H1","side":"buy","thesis":"...","confidence":3}'

# Ejecucion demo con el magic del estilo y SL/TP en el broker
lab ai-trader execute --id <proposal_id>

# Decision de no operar (motivo <= 200, confidence 1-5)
lab ai-trader skip --json '{"style":"intraday","strategy":"ema_pullback","symbol":"USDJPY","timeframe":"H1","reason":"sin retroceso a EMA21","confidence":3}'

# Manage sin LLM: BE 0,5R, trailing 1 ATR, protección por avance al TP
# (50 % -> BE, 80 % -> 50 % del trayecto al TP), Donchian 10d, salida SMA5
# y cierres de sesión. El scalp también lo ejecuta cada minuto, antes de
# buscar setups, para que el candado del scalp no deje sin turno a AI-Manage.
lab ai-trader manage

# Marcador por estilo x estrategia x simbolo x timeframe, sombras e IC 90%
lab ai-trader scoreboard
```

`propose` rechaza con `estrategia desconocida`, `fuera de ventana`, `celda pausada`, `stop diario`, `coste/R`, `volumen < minimo` o `PropGuard`. Un rechazo queda en `ai_decisions`; no se reintenta a ciegas.

La protección por TP usa el **mejor extremo alcanzado** desde la entrada: al **50 %** del trayecto mueve el SL a **breakeven**; al **80 %** lo mueve al **50 % del trayecto** (mitad del beneficio objetivo). Nunca aleja el stop ni lo deja del lado equivocado del mercado; si el precio ya devolvió el tramo del 80 %, cae a breakeven cuando ese nivel sigue siendo válido. Aplica al carril IA; el EA externo tiene su propia gestión.

## Estrategias por sesion

| Sesion | Estilo | Simbolo | Estrategias asignadas |
|---|---|---|---|
| London | intraday | EURUSD, GBPUSD | `london_breakout` H1, `ema_pullback` H1 |
| London | intraday | XAUUSD | `liquidity_sweep` H1 |
| London | intraday | USDJPY | `ema_pullback` H1 |
| NY | intraday | US100.cash | `orb_ny` M15, `vwap_reversion` M15, `bollinger_squeeze` H1 |
| NY | intraday | XAUUSD | `liquidity_sweep` H1 |
| NY | scalping | US100.cash, XAUUSD | `ema_ribbon_pullback` M1, `vwap_bounce` M5, `orb_5m` M5, `momentum_burst` M1 |
| Daily | swing | US100.cash | `rsi2_connors` D1, `donchian_turtle` D1, `trend_pullback` H4 |
| Daily | swing | XAUUSD | `donchian_turtle` D1, `inside_bar` D1, `trend_pullback` H4 |
| Daily | swing | EURUSD, GBPUSD | `inside_bar` D1, `trend_pullback` H4 |
| Daily | swing | USDJPY | `donchian_turtle` D1, `trend_pullback` H4 |

Fuera de esta asignacion, `propose` rechaza. Los estilos tienen riesgo propio: scalping 0,25 % y stop 1 %; intraday 0,5 % y stop 1 %; swing 1 % y stop 1 %, con riesgo abierto maximo 2 %. El stop global del carril es 3 % y el maximo de posiciones abiertas es 5; cada estilo tiene ademas su propio `max_open` de 2. Swing limita a 2 trades/dia y coste/R 0,05.

El **slippage** se mide en precio por simbolo (`slippage_price`): US100.cash 1,0; XAUUSD 0,15; EURUSD 0,00005; GBPUSD 0,00005; USDJPY 0,005. El coste/R usa `2 x slippage_price`; si falta el simbolo, `propose` y `scalp` rechazan con `Sin datos de slippage`.

La cuenta tiene un **stop diario de 0,04** que suma la perdida realizada y la flotante de todos los magics del forward, `us100-trend-d1` y los tres estilos IA. Al tocarlo, ningun carril abre hasta el reset de FTMO; el panel muestra lo consumido por cada carril.

## Sombras y marcador

- Cada operacion real tiene una **sombra aleatoria** con semilla fija por id y los mismos niveles/trailing; nunca se envia al broker.
- En scalping hay ademas una **sombra sin plan**: el lado contrario al real, con los mismos niveles, como contrafactual de lo que el bias/horas prohibidas habrian excluido.
- El marcador usa solo filas `source=forward` y separa por `playbook_version`: cada cambio de playbook reinicia la muestra de la celda. Muestra n, hit rate, R medio, expectativa, coste/R, slippage, diferencia vs cada sombra con IC bootstrap del 90 % y estado `explorando` (n<30), `ganadora`, `perdedora` o `neutral`.
- Una celda perdedora (n>=30 e IC90 superior < 0) la pausa `lab ai-trader learn` al final del daily; no insistir. La reactivacion es manual o queda como leccion `proposed`.

## Aprendizaje diario

`lab ai-trader learn` corre al final de la sesion daily, sin LLM. Solo aplica
cambios que reducen riesgo (pausa, exclusion de hora/dia/condicion del snapshot
y mitad de riesgo por simbolo), maximo 2 por semana, sube `playbook_version` y
actualiza el YAML y este skill. Reactivar una celda, subir riesgo o ampliar
estrategias/activos/estilos queda como leccion `proposed` para el operador. El
LLM no ejecuta `learn`; solo lee el marcador y las lecciones aprobadas.

## Destilacion semanal

`lab ai-trader distill` corre los domingos 12:00 DOM, sin LLM y sin broker.
Solo toma celdas ganadoras del carril IA (n>=30 e IC90 del R > 0); en scalping
exige ademas que el plan (bias/horas) supere a la sombra sin plan. Aprende un
filtro legible de profundidad <=2 sobre el snapshot con numpy, sin sklearn, y
lo valida con y sin filtro: backtest completo con costes, DSR (cada destilacion
suma 2 pruebas), PBO, walk-forward y Monte Carlo FTMO.

El bot candidato `ai-<estrategia>-<simbolo>-<tf>` nace `enabled: false`, con el
riesgo de su estilo, `origin: destilado de ia-discrecional` y el filtro escrito
en la configuracion. Si pasa, queda incubando 60 dias con >=15 trades, Sharpe
forward >0, slippage <=3 bps y 0 breach. La celda IA equivalente pasa a
`destilada` y el LLM deja de operarla. En scalping la promocion exige ademas
ticks Dukascopy de las mismas horas. Nunca pasa a piloto/live sin el operador.

## Reglas que no se negocian

- Solo demo; si el broker no esta en demo, se para.
- No editar archivos ni configuracion desde el skill. No cambiar `enabled`, magics, riesgo ni playbook.
- No operar sin `propose`, sin plan de scalping, con celda pausada/perdedora/destilada, stop diario tocado, coste/R fuera de limite o datos `Sin datos`.
- No repetir simbolo con posicion abierta del carril; maximo 5 abiertas en total.
- No inventar niveles, lotes ni resultados. Si falta un dato, se registra `skip` con el motivo.
- El `scalp` no lo decide el LLM: ejecuta el plan validado y registra `take`/`skip`/`no_setup`. El LLM solo crea el plan y opera las sesiones discrecionales.
