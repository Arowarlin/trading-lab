# RESULTADO · F12a — exportador MQL5 determinista

Fecha: 2026-11-23 (la suite cruzó la medianoche del 22 al 23). Worktree
`C:\Users\PC\.local\share\opencode\worktree\tl2-f12`, rama `tl2-f12-export`
sobre `043e979`. Sin campañas (ni borrador), sin approve/run/confirm/supersede,
sin OOS, sin push, sin merge, sin tareas programadas, sin borrar archivos y sin
tocar archivos protegidos ni del carril EA/ftmo_risk.

## Hecho

- Nuevo `src/tradinglab/discovery/export_mql5.py`: convierte un AST del DSL en
  un EA MQL5 determinista + `manifest.json` con sha256. Cabecera con hash del
  genoma, plantilla/versión, versión del exportador, símbolo/TF, cuenta, firma,
  magic y riesgo. Sin fechas ni rutas absolutas.
- Nuevo `src/tradinglab/discovery/export_samples.py`: 3 estrategias sintéticas,
  barras M5 sintéticas con semilla fija (40 días hábiles) y trazas de paridad
  para `fastbt`.
- Nuevo comando `lab discovery export-mql5 --strategy-id ID | --spec FICHERO
  --out reports/export/` (solo se añadieron líneas en `cli.py`).
- Cobertura de los 31 bloques de `blocks.py`: 30 con traducción MQL5 y
  `vwap_distance` rechazado de forma explícita (`bloque vwap_distance no
  exportable`). Los nodos `htf` y los instrumentos con huso distinto de
  `America/New_York` también se rechazan, nunca se aproximan.
- Reglas replicadas: señal en barra cerrada y entrada en el open siguiente,
  una posición a la vez, stop/objetivo de `fastbt`, `flat_at`, salida por
  tiempo, señal opuesta, BE/trailing desde la barra siguiente, magic derivado
  del hash, sesión NY con DST de EE. UU. (2003+). Riesgo por operación y
  pérdida diaria/total como inputs del EA, con defaults leídos de
  `config/propfund` (cuenta/firma); `sizing.risk_per_trade_r` se anota como
  evaluación en R pero el tamaño usa el `per_trade_risk_pct` del perfil.
- 3 samples en `tests/fixtures/f12_export/generated/`: `.mq5`, manifest y
  `.trace.csv`; los `.mq5` llevan `InpEmitTrace=true` para emitir la misma
  traza en el Tester. Documentación de la comparación en
  `docs/tradinglab2/14_F12A_EXPORT_MQL5.md`.
- 62 tests nuevos en `tests/test_discovery_export_mql5.py`: determinismo,
  manifest/sha256, golden de los 3 samples, bloque no soportado, HTF, huso no
  NY, mercado distinto, magic estable, cobertura de los 31 bloques, todos los
  tipos de nodo, traza determinista, `--spec`, `--strategy-id` y CLI.

## 1. Compilación MQL5

**No se compiló con MetaEditor.** No se abrió MetaEditor ni MetaTrader 5, no se
invocó `MetaEditor64.exe`, no se creó ningún `.ex5` y no se escribió en
`MQL5/Files` ni en ninguna carpeta de MT5. No hay ruta de compilación ni log de
compilación que reportar.

Los llamados "arreglos de compilación" salieron de revisión estática del texto
MQL5 generado y de tests de estructura, no de un compilador:

- declarar `struct EmaState`/`AdxState` antes de las variables globales de
  estado (el primer borrador las ponía antes del `struct`);
- devolver `double` en `PrevSessionLevelAt`, `PrevDayLevelAt`,
  `OpeningRangeAt` y `DonchianLevelAt` (estaban declaradas `bool`, lo que
  habría devuelto 0/1 en vez del precio);
- aritmética `long` en `ServerToUtc`/`ServerToNy` para no castear offsets
  negativos a `datetime`;
- guardas de rango en `AtrPctRankAt` y paso de `long` a `datetime` en
  `SessionDayKey`.

Nada de eso se validó con el compilador de MQL5; queda para el operador.

## 2. Determinismo y manifest

| Sample | sha256 del .mq5 | Magic | Entradas de traza |
|---|---|---|---:|
| `synthetic_trend` | `b80fab8a9251880929c299ef002a07ec4a7d17e0f812c6916ecda51070c17801` | 507577745 | 44 |
| `synthetic_reversion` | `0adcca88e8023110c66f16619a7a468eabd6ba84e6aa213aa3f3b7892644c726` | 122596831 | 20 |
| `synthetic_breakout` | `9bc5618e8dc38ab83348720aae73a5c8cc9d1689908e98b219422255beae10dd` | 556374321 | 36 |

Dos exportaciones de la misma estrategia producen los mismos bytes y el mismo
sha256. El manifest incluye `file` (solo basename), `sha256`, `magic`,
`strategy_hash`, bloques usados, cuenta/firma, `drawdown_mode`, riesgo y
`trace_file`; no incluye timestamps ni rutas absolutas. Los fixtures generados
llevan `tests/fixtures/f12_export/.gitattributes` con `generated/** -text` para
que el checkout no convierta LF a CRLF y el sha del manifest siga siendo el del
`.mq5`.

## 3. Cobertura bloque → MQL5

| Bloque | Exportable | Nota |
|---|---|---|
| `sma` | sí | media simple |
| `ema` | sí | EMA recursiva con estado, semilla = primer cierre |
| `rsi` | sí | media simple de ganancias/pérdidas (como pandas) |
| `atr` | sí | media simple del TR |
| `zscore` | sí | media/desviación muestral |
| `macd` | sí | dos EMA |
| `adx` | sí | EWM con `ignore_na=False` replicado |
| `bollinger_pct` | sí | bandas y ancho |
| `stochastic` | sí | %K |
| `cci` | sí | desviación absoluta media |
| `donchian_pos` | sí | posición en el canal |
| `keltner_pos` | sí | EMA + ATR |
| `vwap_distance` | **no** | depende de `tickvol` o volumen unitario del dataset; no se aproxima |
| `realized_vol` | sí | desviación de retornos |
| `atr_pct_rank` | sí | rank porcentual con empates |
| `range_compression` | sí | rango/ATR |
| `swing_high` | sí | pivote confirmado y desplazado |
| `swing_low` | sí | pivote confirmado y desplazado |
| `bos_up` | sí | cierre sobre el último swing high |
| `bos_down` | sí | cierre bajo el último swing low |
| `choch_up` | sí | BOS up con cambio |
| `choch_down` | sí | BOS down con cambio |
| `engulfing` | sí | envolvente |
| `pin_bar` | sí | pin bar |
| `inside_bar` | sí | inside bar |
| `range_expansion` | sí | rango > mult × media previa |
| `trending` | sí | ADX > umbral |
| `ranging` | sí | ADX < umbral |
| `vol_high` | sí | rank ATR% > pct |
| `vol_low` | sí | rank ATR% < pct |
| `session_return` | sí | open(start) → close(end) |

Niveles: `prev_session_*`, `prev_day_*`, `opening_range_*` y `donchian_*`
también traducidos. Un `htf` falla con `nodo htf no exportable`; un `session_tz`
distinto de `America/New_York` falla con `huso ... no exportable`.

## 4. Samples y trazas

`tests/fixtures/f12_export/generated/` contiene los 3 `.mq5`, sus manifests y
sus `.trace.csv` (44/20/36 entradas). La traza de Python sale de ejecutar el
mismo DSL con `fastbt` sobre `synthetic_bars(seed=11)`; la del EA sale de
`InpEmitTrace=true` y escribe `bar_time,side,entry,stop,target`. La comparación
(documentada en el doc 14) es por `bar_time` con tolerancia 1e-6 en precios.
No se ejecutó el Tester.

## 5. Tests

- Módulo nuevo: **62 passed** (`pytest -q -p no:randomly
  tests/test_discovery_export_mql5.py`).
- Suite completa del worktree: **1664 passed, 10 failed, 1 skipped, 1 warning
  en 5635.37 s (1:33:55)**. Ningún fallo es del módulo nuevo; sus 62 tests
  pasaron dentro de la suite.
- `ruff check src/tradinglab/discovery tests`: **All checks passed**.
- `lab propfund verify`: **4 OK** (`ai_trader`, `ea_us100_ftmo1`,
  `ftmo_forward`, `ftmo_risk`).
- `count_tests` sobre una copia de `E:\trading-lab\data\lab.db` +
  `discovery.db`: **1703** (643 de campañas de discovery). El PARALELO esperaba
  1676; la DB principal tiene 27 pruebas más desde que se escribió la fase
  (probablemente la otra sesión, C1-prep/forward). Se leyó con `sqlite3.backup`
  y no se escribió en la DB principal.

### Fallos de la suite completa, uno por uno

Ninguno es del módulo nuevo. Clasificación:

1. `tests/test_discovery_noise.py::test_noise_five_campaigns` —
   `CampaignError: campaña no registrada: noise-5` en `mark_done` tras seeds
   1-4. Test lento pre-existente; `RESULTADO-R2k.md` ya documentó el mismo
   `mark_done` (`noise-full-1y`) y no se reprodujo en 30/30. Es un fallo de
   entorno/flake del worktree, no de F12a. La repetición individual se lanzó
   aparte y se detuvo al cerrar la fase para no dejar procesos; no fue
   concluyente. No se tocó el test ni `campaigns.py`.
2. `tests/test_ea_forward.py::test_criterios_del_ea_congelados_con_hash` —
   entorno del worktree: `criteria_hash` `7292c0077bba120b` vs `FROZEN_HASH`
   `f490642ba7a1f71b`. Los blobs de git son idénticos a E:; el checkout del
   worktree escribió CRLF (`core.autocrlf=true`) y E: tiene LF, y
   `criteria_hash` hashea bytes crudos sin normalizar. Archivos afectados:
   `US100_EntryManager.mqh`, `US100_MarketAnalysis.mqh`, `US100_Strategy.mqh`,
   `Shared_FTMO_Risk.mqh`, `Shared_Logger.mqh`, `US100_FTMO_v3_challenge.set` y
   `src/tradinglab/nyse_calendar.py`. No falta un archivo versionado; si acaso,
   faltaría un `.gitattributes` con `eol=lf` (no existe y no se añadió porque
   tocaría el carril EA). En `E:\trading-lab` `tests/test_ea_forward.py` pasa
   **10/10**. No se modificó `FROZEN_HASH` ni `ea_forward.py` ni nada del EA.
3. `tests/test_ea_forward.py::test_pre_registro_no_admite_otro_hash` — mismo
   desajuste de bytes por CRLF/LF; E: pasa.
4. `tests/test_ea_forward.py::test_el_reloj_arranca_en_el_primer_fill` — mismo;
   E: pasa.
5. `tests/test_ea_lab_candidate.py::test_pre_registro_tiene_tres_veredictos_y_hash_estable`
   — mismo desajuste de bytes en docs/EA por CRLF/LF; en E: pasa.
6. `tests/test_ea_lab_session_equivalence.py::test_documentos_incluyen_el_hash`
   — mismo; en E: pasa.
7. `tests/test_fund_web.py::test_api_limits_apretar_aflojar_y_firma` —
   `TimeoutError` del cliente HTTP contra el servidor local. Pasa
   individualmente en el worktree y en E:; fue contención de recursos de la
   suite de 1:33 h (la otra sesión también usa disco/CPU), no lógica.
8. `tests/test_fund_web.py::test_killswitch_global_requiere_confirmacion` —
   mismo timeout; pasa individualmente.
9. `tests/test_model_compare.py::test_error_de_modelo_se_sanea` —
   `date.today()` `2026-11-23` vs `decision_date` `2026-11-22`: la suite cruzó
   la medianoche. Falla igual en E: ahora, así que es reloj/fecha, no F12a.
10. `tests/test_optimize.py::test_run_optuna_sintetico_suma_trials_y_no_toca_holdout`
    — `dsr_global is None`. Falla también individualmente en el worktree y
    pasa en E: (12 passed en el lote de clasificación). El worktree está en
    `043e979` y no tiene los cambios posteriores de C1-prep/C1-fix en
    `src/tradinglab/discovery/campaigns.py`; es baseline del worktree, no F12a.

## 6. Git

```text
$ git status --short
(sin cambios)
```

```text
$ git log --oneline -5
4b58a85 tl2: F12a - fixtures sin conversion CRLF
a6fba1e tl2: F12a - golden tolerante a CRLF
e3c9ab6 tl2: F12a - exportador MQL5 determinista
043e979 tl2: R2k - arreglos previos a campaña
d94e625 tl2: R2i-b - onboarding multi-timeframe
```

```text
$ git diff --stat 043e979
 docs/tradinglab2/14_F12A_EXPORT_MQL5.md            |  127 ++
 src/tradinglab/cli.py                              |   90 +
 src/tradinglab/discovery/export_mql5.py            | 2249 ++++++++++++++++++++
 src/tradinglab/discovery/export_samples.py         |  203 ++
 tests/fixtures/f12_export/.gitattributes           |    1 +
 tests/fixtures/f12_export/README.md                |   19 +
 .../generated/synthetic_breakout.manifest.json     |   35 +
 .../f12_export/generated/synthetic_breakout.mq5    | 1169 ++++++++++
 .../generated/synthetic_breakout.trace.csv         |   37 +
 .../generated/synthetic_reversion.manifest.json    |   34 +
 .../f12_export/generated/synthetic_reversion.mq5   | 1171 ++++++++++
 .../generated/synthetic_reversion.trace.csv        |   21 +
 .../generated/synthetic_trend.manifest.json        |   33 +
 .../f12_export/generated/synthetic_trend.mq5       | 1158 ++++++++++
 .../f12_export/generated/synthetic_trend.trace.csv |   45 +
 tests/test_discovery_export_mql5.py                |  366 ++++
 16 files changed, 6758 insertions(+)
```

No aparece ningún archivo protegido ni del carril EA/ftmo_risk. Commit principal
`e3c9ab6` (`tl2: F12a - exportador MQL5 determinista`) y dos commits pequeños de
robustez de tests; tag `tl2-f12a` en `4b58a85`. Sin push y sin merge.

## 7. Data del worktree

Las copias de `data/` (`lab.db`, `discovery.db` y
`cache/{mt5,ea,ea_lab,discovery,phase5,sec,fred,ticks,cot}`) son solo para tests
y están ignoradas por git; `git status --short` está vacío. Los tests usan
`ROOT` del worktree (verificado: `tradinglab.config.ROOT` =
`...\worktree\tl2-f12`). Entre la copia previa y el final, la DB del worktree
cambió en `data_freshness` (+4) y `signals` (+2), tablas de forward/EA; la DB de
E: cambió en las mismas tablas (+6/+4), compatible con la otra sesión. No se
observaron cambios de F12a en tablas de discovery/campañas de E:. No se añadió
ningún archivo de `data/` a git.

## Aviso

- No se compiló MQL5 con MetaEditor; la compilación real y el Tester quedan para
  el operador. El repo solo entrega texto MQL5 y trazas.
- `vwap_distance` y `htf` no se exportan (motivos arriba); no hay aproximación
  silenciosa.
- El EA usa `InpServerUtcOffsetMinutes` fijo para pasar de hora del servidor a
  UTC; si el broker cambia de hora (GMT+2/GMT+3), hay que ajustar el desfase del
  periodo o importar barras UTC. El DST de Nueva York sí se calcula.
- El EA calcula indicadores con estado desde la primera barra del gráfico. El
  Tester debe cargar historial previo; si arranca en seco, EMA/ADX/niveles
  previos no coinciden con Python.
- No se replican barras ausentes ni el orden de stop/objetivo cuando ambos se
  tocan en la misma barra; los fills y costes los pone el broker. La paridad
  comparada es la de señales, no la de fills.
- `bos_up`/`bos_down` buscan el pivote más reciente dentro de
  `InpPivotScanBars` (5000 por defecto); si no hay pivote, la condición es
  falsa y no se inventa un nivel.
- El EA no abre si el lotaje calculado queda por debajo del mínimo o por encima
  del máximo del símbolo; esa entrada no aparece en su traza.
- La pérdida diaria se ancla al equity del primer bar del día de sesión que ve
  el EA; si arranca a mitad de día no conoce el equity de apertura real.
- Los 5 fallos de hash del EA y el de `test_optimize` son de entorno/baseline
  del worktree, no del módulo nuevo; los 62 tests de F12a pasan y los tests
  equivalentes pasan en `E:\trading-lab`.
- `count_tests` es 1703, no 1676; confirmar el +27 con la otra sesión antes de
  fijar un nuevo baseline.

## Siguiente

- Revisar el diff y el doc 14. Decidir si se compila el `.mq5` en MetaEditor y
  se compara la traza en el Tester (no se hizo aquí).
- Si se acepta, merge local de `tl2-f12-export` a la rama principal por el
  operador; no se hizo.
- Valorar si se quiere añadir soporte `htf`/`vwap_distance` en una fase
  posterior (requiere fijar la rejilla HTF y la fuente de volumen).
- Confirmar el `count_tests` actual (1703) y los cambios de C1-prep/C1-fix
  antes de usarlo como baseline.
