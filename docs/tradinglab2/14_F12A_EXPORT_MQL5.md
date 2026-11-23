# F12a · Exportador MQL5 determinista

Convierte una estrategia del DSL de discovery (genoma + plantilla + parámetros)
en un EA MQL5 autónomo. No registra campañas, no lee OOS, no envía órdenes y
no ejecuta el Tester: solo escribe el `.mq5`, su `manifest.json` y, si se pide,
una traza de señales en Python.

## Comando

```powershell
$env:PYTHONPATH="$PWD\src"
.\.venv\Scripts\lab.exe discovery export-mql5 --strategy-id 123 --out reports/export
.\.venv\Scripts\lab.exe discovery export-mql5 --spec ruta\estrategia.yaml --account CFD-001 --out reports/export
```

`--spec` acepta un YAML con `strategy:` (AST), `template:` y `account:`, o un
AST suelto. La cuenta se puede pasar con `--account`; si el perfil no declara
pérdida diaria/total, el exportador falla y pide `--daily-loss`/`--max-loss`
(no inventa límites).

El nombre del archivo se deriva del símbolo, TF, cuenta y los 12 primeros
caracteres del hash del genoma. La cabecera incluye hash del genoma, plantilla
y versión, versión del exportador, símbolo/TF, cuenta, firma, magic y riesgo.
El manifest incluye el sha256 del `.mq5`, el magic, los bloques usados y el
perfil de riesgo aplicado. No hay fechas ni rutas absolutas: la misma entrada
produce exactamente los mismos bytes.

## Cobertura de bloques

| Estado | Bloques |
|---|---|
| Exportables | `sma`, `ema`, `rsi`, `atr`, `zscore`, `macd`, `adx`, `bollinger_pct`, `stochastic`, `cci`, `donchian_pos`, `keltner_pos`, `realized_vol`, `atr_pct_rank`, `range_compression`, `swing_high`, `swing_low`, `bos_up`, `bos_down`, `choch_up`, `choch_down`, `engulfing`, `pin_bar`, `inside_bar`, `range_expansion`, `trending`, `ranging`, `vol_high`, `vol_low`, `session_return` |
| No exportable | `vwap_distance` (depende de `tickvol` o volumen unitario del dataset; el EA no puede saber cuál usó el backtest) |

Los niveles `prev_session_*`, `prev_day_*`, `opening_range_*` y `donchian_*`
también se exportan. Un nodo `htf` falla con error claro porque la rejilla HTF
del backtest está anclada a las 17:00 de Nueva York y la del servidor MT5 no
tiene por qué coincidir. Un instrumento cuyo `session_tz` no sea
`America/New_York` también se rechaza: el EA implementa Nueva York con DST
(reglas de EE. UU. desde 2003, incluidas las anteriores a 2007).

## Reglas que replica el EA

- Señal en barra cerrada y entrada en el open de la barra siguiente.
- Una sola posición a la vez (mismo símbolo y magic); las señales con posición
  abierta se ignoran.
- Stop y objetivo con las mismas fórmulas que `fastbt`: ATR/porcentaje/fijo,
  RR/porcentaje/fijo; BE y trailing desde la barra siguiente; `flat_at`;
  salida por tiempo; salida por señal opuesta.
- Sesión, `flat_at`, días de la semana y claves de día en hora de Nueva York.
- Magic estable de 9 dígitos derivado del hash del genoma.
- Riesgo por operación y pérdida diaria/total como **inputs** del EA, con
  valores por defecto leídos de `config/propfund` (cuenta y firma objetivo).
  El `sizing.risk_per_trade_r` del DSL se anota en la cabecera como evaluación
  en R, pero el tamaño real usa `per_trade_risk_pct` del perfil. La pérdida
  total se mide desde el equity inicial y la diaria desde el equity al inicio
  del día de sesión. Al alcanzarlas se bloquean entradas nuevas.

El EA no fija spread, comisión ni slippage: los aplica el broker. Tampoco puede
decidir el orden de un stop y un objetivo tocados en la misma barra; `fastbt`
prioriza el stop, el broker puede hacer otra cosa. Por eso la paridad que se
compara es la de **señales** (barra, dirección, entrada, stop, objetivo), no la
de fills.

## Traza de paridad

Los tres samples sintéticos están en `tests/fixtures/f12_export/generated/`:

| Estrategia | Bloques |
|---|---|
| `synthetic_trend` | `ema`, stop ATR, objetivo RR |
| `synthetic_reversion` | `bollinger_pct`, `rsi`, stop ATR |
| `synthetic_breakout` | `opening_range_high`, `bos_up`, `range_expansion`, stop porcentual |

Cada `.mq5` trae `InpEmitTrace=true` por defecto. Al ejecutarlo en el Tester,
escribe `InpTraceFile` (por defecto `<SIMBOLO>_<TF>_<CUENTA>_trace.csv`) en
`MQL5/Files` con las columnas:

```text
bar_time,side,entry,stop,target
```

El `.trace.csv` de Python se genera con el mismo DSL y `fastbt` sobre barras
sintéticas con semilla fija (`tradinglab.discovery.export_samples`). Para
comparar:

1. Importar en el Tester las mismas barras sintéticas (o las barras reales del
   mismo periodo) y poner `InpServerUtcOffsetMinutes` al desfase del servidor
   respecto a UTC (`0` si las barras están en UTC; `120` para GMT+2; `180` para
   GMT+3).
2. Ejecutar el Tester con `InpEmitTrace=true` y copiar el CSV generado.
3. Comparar por `bar_time` con tolerancia `1e-6` en precios. Una diferencia de
   barra o de dirección es un fallo de lógica, no de redondeo. Una diferencia
   solo en `target` o `stop` de menos de `1e-6` es ruido de coma flotante.

El Tester no se ejecuta desde este repositorio: lo lanza el operador cuando
quiera. Las barras sintéticas se regeneran con:

```powershell
$env:PYTHONPATH="$PWD\src"
.\.venv\Scripts\python.exe -m tradinglab.discovery.export_samples --out tests/fixtures/f12_export/generated
```

## Límites conocidos

- El EA calcula los indicadores con estado desde la primera barra del gráfico.
  El Tester debe cargar historial anterior al periodo de señales; si empieza en
  seco, EMA/ADX y los niveles de sesión anterior no coinciden con Python.
- `bos_up`/`bos_down` buscan el pivote más reciente dentro de
  `InpPivotScanBars` (5000 por defecto). Si no hay pivote en esa ventana, la
  condición es falsa; no se inventa un nivel.
- No se replican barras ausentes: si el terminal se salta velas, el EA actualiza
  los indicadores pero no reejecuta las señales intermedias.
- La sesión se calcula con reglas de DST de EE. UU.; un instrumento con
  `session_tz` distinto de `America/New_York` se rechaza en vez de aproximarse.
- `InpServerUtcOffsetMinutes` es un desfase **fijo** del servidor respecto a
  UTC. Si el servidor cambia de hora (GMT+2/GMT+3), usa el desfase del periodo
  que vas a comparar o importa barras UTC en el Tester; el EA no adivina las
  reglas DST del broker.
- El EA no abre si el lotaje calculado queda por debajo del mínimo del
  símbolo o por encima del máximo; esa entrada no aparece en su traza aunque
  Python la haya trazado.
- La pérdida diaria se ancla al equity del primer bar del día de sesión que ve
  el EA. Si el EA arranca a mitad de día, no conoce el equity de apertura real;
  en el Tester conviene empezar al inicio del día.
- El EA es demo/paper. No activa bots, no envía órdenes desde el exportador y
  no sustituye a `trader-risk` ni al router del Prop Fund.
