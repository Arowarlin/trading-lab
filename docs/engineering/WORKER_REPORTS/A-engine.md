# A-engine · Auditoría del motor de backtest (`discovery/fastbt.py`)

- **ID tarea:** ENG-A1
- **SHA:** adc0eec
- **Fecha:** 2026-11-26
- **Worker:** A (Backtest Engine Auditor)
- **Modo:** solo lectura. `fastbt.py` está congelado (EDGE-2 en curso): aquí solo se describen defectos y se reproducen; no se corrige nada.
- **Datos:** solo barras sintéticas. No se ha usado ningún precio de mercado. No se ha ejecutado ninguna campaña, `research*`, `discovery run` ni barrido.
- **Scripts y salidas:** `/tmp/claude-0/-home-user-trading-lab/89310f7f-0a4e-5602-b5a9-56cac624406b/scratchpad/A/` (scratchpad de la sesión: se puede borrar al reiniciar). Ejecutados con `/home/user/trading-lab/.venv/bin/python` y numba disponible.
- **Alcance:** `fastbt.py` (`_core`, `_calendar_core`, `_session_mask`, `_prepare`, `run`), con `resample.py`, `timeframes.py`, `specs.py`, `compiler.Signals` e `indicators.atr` en lo que el motor usa.
- **Documentos previos leídos:** `.orquestador/COLA-MOTOR-FLAT.md`, `docs/audit_2026/QUANT_ENGINE_AUDIT.md` y `docs/tradinglab2/01_TRADINGLAB_FORENSIC_AUDIT.md`. Ninguno de los dos últimos revisa `fastbt` a fondo. `QUANT_ENGINE_AUDIT §8` dice «Look-ahead: no se encontró», pero se refiere a otros motores.

## Resumen por severidad

| ID | Sev. | Estado | Tema |
|---|---|---|---|
| A-01 | HIGH | NUEVO | `weekdays` usa el día civil de la **etiqueta** de la vela. En D1 (etiqueta 17:00 NY del día anterior) la sesión del lunes queda fuera de `allowed` y de `allowed_entry`. |
| A-02 | HIGH | CONOCIDO(COLA-MOTOR-FLAT), ampliado | Mientras la posición «duerme», el stop y el objetivo no se evalúan en las velas con `allowed=False`: sesgo optimista. |
| A-03 | MEDIUM | NUEVO | Fuera de D1, la señal pendiente se cancela al cambiar el día civil. En sesiones de 24 h, la última vela del día (H4 21:00 NY, H1 23:00…) nunca abre operación. |
| A-04 | MEDIUM | NUEVO | En `_calendar_core`, la salida de calendario se evalúa **antes** que el stop en la vela de salida: sesgo optimista en `month_turn`. |
| A-05 | MEDIUM | NUEVO (latente) | `manage_end = max(end, flat)` falla en sesiones que cruzan medianoche con `flat_at` antes de las 00:00: las entradas posteriores al flat quedan sin gestión. |
| A-06 | LOW | NUEVO | `_calendar_core` difiere de `_core`: no rechaza un objetivo inválido, el objetivo corto CFD no exige el ASK, y `set_backend()` no lo conmuta (`backend()` informa mal). |
| A-07 | LOW | NUEVO | Una operación que entra en la última vela (`entry_i == end_idx`) se descarta en silencio aunque `close_at_end=True`. |
| A-08 | LOW | NUEVO | Si hay señal long y short en la misma vela, siempre gana el long. |
| A-09 | LOW | NUEVO | En `close_signal` (solo paridad), un long no se cierra cuando la señal pasa directamente a short. |
| A-10 | LOW | NUEVO | En sesiones que cruzan medianoche, la vela que abre exactamente a `session_end` (p. ej. 03:00) pertenece al `day_id` siguiente pero sigue en la ventana de entrada. |

La paridad entre Python y Numba es **bit a bit** en 300 escenarios aleatorios de `_core` (6.523 operaciones) y en 100 de `_calendar_core`. Detalle en «Comprobado y correcto».

---

## Confirmado con reproducción

### A-01 · HIGH · NUEVO · `weekdays` evaluado sobre el día civil de la etiqueta (D1, H4 y sesiones nocturnas)

- **Archivo:línea:** `fastbt.py:1584-1587` (`weekday = np.isin(local.day_of_week, weekdays)`) y `fastbt.py:1612-1613` (`allowed`/`allowed_entry` = ventana `& weekday`). Lo agravan `fastbt.py:873` (con `allow_next_day=1` la señal pendiente no caduca) y `fastbt.py:945` (ATR de la vela de la señal).
- **Función:** `_session_mask`, `_core` y `_calendar_core`.
- **Descripción:** `resample_session` etiqueta cada vela con su **apertura**. Una D1 de la sesión del lunes se etiqueta «domingo 17:00 NY», como ya documenta `.orquestador/RESULTADO-tom-anclaje.md` para el compilador. `_session_mask` filtra `weekdays=(0..4)` con el día de la semana local de esa etiqueta, así que:
  1. la vela de la sesión del **lunes** tiene `allowed=False` y `allowed_entry=False`;
  2. no se entra en ella: en `month_turn`, si el día hábil N cae en lunes, la entrada se pierde;
  3. una posición abierta **no evalúa stop ni objetivo** en esa vela (véase A-02);
  4. una señal en la sesión del viernes no entra al open del lunes. Como en D1 `allow_next_day_entry=True`, queda pendiente y entra al open del **martes**, con el ATR del jueves por la noche.

  Lo mismo pasa en H4 con las velas de domingo 17:00 y 21:00 NY, que son el inicio de la semana. En las sesiones que cruzan medianoche (18:00→03:00), la mitad de domingo de la sesión del lunes queda fuera, pero la parte de 00:00 a 02:45 del lunes sí entra. Con `session_tz=Asia/Tokyo` (USDJPY) la etiqueta 17:00 NY es sábado 06:00-07:00 en Tokio, y la sesión que se pierde es la del **viernes**.

  `jobs.py:77`, `campaigns.py:446` y `feasibility.py:549` fijan `weekdays=(0,1,2,3,4)`. `specs.py:76` activa `allow_next_day_entry` en D1.
- **Evidencia:** `a01_d1_weekday.py` y `a01b_calendar_monday.py` (salidas en `a01_out.txt` y `a01b_out.txt`).

  ```
  Etiquetas D1 de resample_session (NY): Sun 17:00, Mon, Tue, Wed, Thu
  allowed      : [0 1 1 1 1]
  allowed_entry: [0 1 1 1 1]
  Caso A: señal en la sesión del viernes (pos 4) -> entra en pos 6 (sesión del martes), no en pos 5
    long in#6 2024-03-11 17:00-04:00 ... reason=end_of_data
  Caso B: long con stop 98; la sesión del lunes (pos 5) tiene low=90
    weekdays 0..4: long in#2 ... out#9 @100 reason=end_of_data R=0.0   <- no salta el stop
    weekdays 0..6: long in#2 ... out#5 @98  reason=stop R=-1.0
  month_turn, N = lunes 30-sep-2024 (vela 'Sun 2024-09-29 17:00'):
    weekdays (0..4): trades=0
    weekdays (0..6): 1 trade, calendar_exit
  ```

  Ningún test lo detecta: `tests/test_discovery_templates_h4d1.py:24` genera las D1 a medianoche UTC (`date_range(..., freq="1D", tz="UTC")`), no con la etiqueta 17:00 NY real.
- **Impacto técnico:** en D1, una de cada cinco sesiones no existe para el motor, ni para entrar ni para gestionar. Las señales del viernes se ejecutan un día tarde y con un ATR viejo.
- **Impacto estadístico:** hay dos efectos. (a) La ceguera del stop en la vela del lunes es **optimista**: un stop tocado el lunes que se recupera no cuenta, y el hueco solo se cobra si persiste al open del martes. (b) Las entradas perdidas o retrasadas cambian la muestra de forma no aleatoria, siempre el mismo día de la semana: para `turn_of_month`, todos los meses cuyo día N es lunes. El signo de (b) no se conoce. Afecta a `ts_momentum_d1`, `d1_extension_reversion`, `turn_of_month` y a las plantillas de 24 h en H4.
- **Corrección mínima propuesta:** evaluar `weekdays` sobre el **día de sesión**, no sobre el día civil de la etiqueta. Para TF ≥ H4 o barras de `resample_session`, ese día es `session_day + 1` con corte a las 17:00 NY. Para sesiones que cruzan medianoche, es el `day_id` ya calculado. Como mínimo, no aplicar `weekday` a `allowed`: la gestión de una posición abierta no debe depender del día. Hay que versionar el motor, porque esto cambia resultados.
- **Test de regresión propuesto:** D1 sintético generado con `resample_session` de M1 de lunes a viernes (etiquetas de domingo a jueves a las 17:00 NY). Se afirma que (1) `allowed_entry` es True en las 5 sesiones; (2) un long con el stop perforado en la sesión del lunes sale por `stop` en esa vela; (3) una señal del viernes entra al open de la sesión del lunes; (4) `month_turn` con N en lunes produce 1 operación. Repetirlo con `session_tz=Asia/Tokyo`.

### A-02 · HIGH · CONOCIDO(.orquestador/COLA-MOTOR-FLAT.md), ampliado · la posición dormida no tiene stop

- **Archivo:línea:** `fastbt.py:991` (`if pos != 0 and allowed[i]:` protege stop, objetivo, flat y tiempo), `fastbt.py:876-877` (salidas al open, también con `allowed[i]`) y `fastbt.py:1093` (BE y trailing).
- **Función:** `_core`.
- **Descripción:** COLA-MOTOR-FLAT describe que `flat_at` no dispara en TF no alineados y que la posición «duerme». Lo que no dice es que, mientras duerme, el motor **no evalúa** stop, objetivo ni `time_exit` en ninguna vela con `allowed=False`: la noche, el fin de semana y la parte previa a `session_start` del día siguiente. Al volver a la sesión solo mira el `low`/`high` de esa vela, y el hueco se cobra a `min(stop, open)`. Las excursiones nocturnas que tocan el stop y se recuperan no cuentan. El EA exportado tiene el SL en el servidor, que está activo las 24 h, así que en esas operaciones el backtest y el EA divergen. A-01 crea el mismo efecto en D1 sin que haga falta el fallo de flat.
- **Evidencia:** `a04_sleep_stopblind.py` (`a04_out.txt`). H1, sesión 09:30-15:55 y `flat_at` 15:55. Vela de las 20:00 NY con low=90 y stop=99:

  ```
  velas con flat_flag: []
  allowed en la vela 20:00 NY: False
  flat_at=15:55: long in#5 14:00 ... out#27 (día siguiente 12:00) @100 reason=end_of_data R=0.0
  flat_at=15:00: long in#5 14:00 ... out#6 15:00 @100 reason=force_exit R=0.0
  ```

  El script `a02_midnight.py` reproduce el mismo efecto con A-05.
- **Impacto:** el sesgo es **optimista** en todas las operaciones dormidas: las 291 de H-2026-013 que cita la COLA y todas las plantillas de 24 h en M15, M30, H1 y H4. Además, el R de esas operaciones se mide con un stop que en la práctica no existía durante la noche.
- **Corrección mínima propuesta:** separar la gestión de la ventana de sesión. Con posición abierta, evaluar stop y objetivo en **todas** las velas, como hace un SL de servidor, y reservar `allowed` para las salidas discrecionales (señal opuesta y fin de señal). El `flat_mode="no_overnight"` de la COLA evita que la posición duerma, pero no corrige `legacy`, ni A-01, ni los fines de semana de las plantillas multi-día. Esto se puede añadir a la COLA como un modo o versión del motor.
- **Test de regresión propuesto:** el escenario de `a04` con dos aserciones: con `legacy`, documentar `end_of_data`; con el modo nuevo, la salida es `stop` en la vela de las 20:00 a 99.

### A-03 · MEDIUM · NUEVO · la última vela del día civil nunca abre operación (no D1)

- **Archivo:línea:** `fastbt.py:873` (`if allow_next_day == 0 and pending != 0 and day_id[i] != pending_day: pending = 0`) y `fastbt.py:1592-1610` (`day_id` = día civil local, salvo que la sesión cruce medianoche).
- **Función:** `_core`.
- **Descripción:** `specs.py:76` solo activa `allow_next_day_entry` en D1. En el resto de TF, una señal en la última vela del día civil local se cancela al pasar a la primera vela del día siguiente. En sesiones de 24 h (`00:00-23:59`, que usan `trend_pullback_mtf`, `vol_squeeze_breakout`, `donchian_vol_h4` y `fix_reversal`), esa vela está dentro de la ventana de entrada y su señal es válida, pero **nunca** se ejecuta: en H4 es la vela de 21:00 NY (1 de cada 6), en H1 la de 23:00, y en M15 la de 23:45. El EA (`export_mql5.py`, `EntryWindowAllows(1) && EntryWindowAllows(0)`) sí entraría.
- **Evidencia:** `a06_h4_daychange.py` (`a06_out.txt`). Barras de `resample_session` de lunes a jueves, con una señal por hora de cada día:

  ```
  H4 hora_señal_NY: (señales, operaciones) -> {1:(3,3), 5:(3,3), 9:(3,3), 13:(3,3), 17:(4,4), 21:(4,0)}
  H1 ... 22:(4,4), 23:(4,0)
  ```
- **Impacto:** se elimina siempre la misma franja horaria (en H4, la apertura asiática de 21:00 a 01:00 NY). El sesgo no tiene signo conocido, pero es sistemático, y el backtest no coincide con el EA en esas señales.
- **Corrección mínima propuesta:** cancelar la señal pendiente solo cuando la vela siguiente no esté en la **misma sesión**. En sesiones de 24 h, la sesión es la de 17:00 NY o ninguna. También vale tratar `allow_next_day_entry=True` cuando la ventana de entrada es de 24 h.
- **Test de regresión propuesto:** H4 sintético con `resample_session` y una señal en la vela de 21:00 NY. Se afirma que la entrada ocurre al open de la vela de 01:00 NY.

### A-04 · MEDIUM · NUEVO · `_calendar_core`: la salida de calendario va antes que el stop

- **Archivo:línea:** `fastbt.py:1291-1303` (`if exit_target >= 0 and i >= exit_target: ... reason = 8` antes de `elif allowed[i]:` con stop y objetivo).
- **Función:** `_calendar_core` (`month_turn`).
- **Descripción:** en la vela de salida se cierra a `close[i]` aunque el `low` de esa vela haya perforado el stop. En `_core` el stop siempre va primero.
- **Evidencia:** `a05_calendar_order.py` (`a05_out.txt`):

  ```
  calendar_exit en la vela 3 con low=90 < stop=98: out#3 @100.0 reason=calendar_exit R=0.0
  misma vela un día antes de la salida (ex=4):    out#3 @98.0  reason=stop R=-1.0
  ```
- **Impacto:** sesgo **optimista** en `turn_of_month`. Es pequeño porque el stop es de catástrofe (3×ATR), pero va siempre en la misma dirección.
- **Corrección mínima propuesta:** evaluar el stop y el objetivo antes que la salida de calendario en la vela de salida, con la misma regla de hueco al peor precio.
- **Test de regresión propuesto:** el escenario de `a05`: se afirma `reason == "stop"` y `exit_price == 98` cuando la vela de salida perfora el stop.

### A-05 · MEDIUM · NUEVO (latente) · `manage_end = max(end, flat)` en sesiones que cruzan medianoche

- **Archivo:línea:** `fastbt.py:1582` (`manage_end = end_s if flat_s is None else max(end_s, flat_s)`) y `fastbt.py:1566`, que solo valida `flat_at` cuando `start < end`.
- **Función:** `_session_mask`.
- **Descripción:** con una sesión de 18:00→03:00 y `flat_at` 23:00, el resultado es `max(03:00, 23:00) = 23:00`. La ventana de gestión se reduce a 18:00-23:00, pero la de entrada sigue siendo 18:00-03:00. Una entrada después de las 23:00 se queda sin gestión (stop, objetivo y flat) hasta las 18:00 del día siguiente. El `max` solo es válido cuando `start < end`. Hoy ninguna plantilla lo dispara (`asia_range_reversion` usa `flat_at` 02:45), pero nada impide esa configuración y no hay ningún aviso.
- **Evidencia:** `a02_midnight.py` (`a02_out.txt`):

  ```
  Sun 03 23:00 allowed=1 entry=0 flat=1
  Sun 03 23:30 allowed=0 entry=1 flat=0      <- se puede entrar, pero no gestionar
  Mon 04 00:00 allowed=0 entry=1 flat=0
  run flat_at=23:00: long in 00:00, low 95 a la 01:00 con stop 99 -> out 06:00 @100 reason=end_of_data
  control flat_at=02:45:                                   -> out 01:00 @99 reason=stop
  ```
- **Impacto:** si se usa, es **optimista** (stop ciego) y las operaciones duermen.
- **Corrección mínima propuesta:** calcular el fin de la gestión en tiempo relativo al inicio: `manage_rel = max((end-start)%día, (flat-start)%día)`. Además, rechazar o avisar cuando `flat_at` cae antes de `session_end` en una sesión que cruza medianoche, o excluir de la ventana de entrada las velas posteriores al flat.
- **Test de regresión propuesto:** máscara de 18:00→03:00 con `flat_at` 23:00. Se afirma que `allowed_entry` es False entre 23:00 y 03:00, o bien que `allowed` es True en esas velas.

### A-06 · LOW · NUEVO · `_calendar_core` no es coherente con `_core`

- **Archivo:línea:** `fastbt.py:1259-1267` (un objetivo inválido pone `has_target = False` y la operación se abre igualmente); `fastbt.py:1316-1319` (corto: `hit_target = low <= tgt_p` sin la comprobación del ASK que `_core` hace en `fastbt.py:1006-1010`); `fastbt.py:1456-1470` (`set_backend` solo reasigna `_core_compiled`).
- **Evidencia:** `a05_calendar_order.py`:

  ```
  objetivo fijo 50 en un long: _calendar_core -> 1 trade (sin objetivo); _core -> trades=0 rejected=1
  corto CFD, spread 50 bps, objetivo 99.6, low BID 99.5 (ASK 99.9975):
    _calendar_core -> out @99.6 reason=target R=+0.40
    _core          -> no toca el objetivo; end_of_data R=-0.5
  ```

  En `a_parity.py`, después de `set_backend('python')`, `backend()` devuelve `python`, pero `_calendar_core_compiled` sigue siendo numba.
- **Impacto:** el objetivo corto sin ASK es **optimista**, aunque `turn_of_month` es solo long y hoy no hay impacto real. El objetivo inválido aceptado y la etiqueta de backend errónea son problemas de trazabilidad.
- **Corrección mínima propuesta:** reutilizar en `_calendar_core` las mismas reglas que `_core` (rechazo y ASK) y conmutar los dos núcleos en `set_backend`.
- **Test de regresión propuesto:** los dos escenarios anteriores en ambos núcleos, con la aserción de que dan el mismo resultado. Y `set_backend("python")` debe implicar `_calendar_core_compiled is _calendar_core`.

### A-07 · LOW · NUEVO · operación abierta en la última vela descartada

- **Archivo:línea:** `fastbt.py:1121-1123` (`if close_at_end == 1 and pos != 0 ...: if last > entry_i:`), y lo mismo en `fastbt.py:821-823`.
- **Descripción:** una señal en la penúltima vela entra al open de la última. Si en esa vela no salta el stop ni el objetivo, la operación no se registra, aunque `close_at_end=True`. Con `end_index` (cortes IS/OOS en `feasibility`, `fitness` y `robustness`), pasa en cada corte.
- **Evidencia:** `a07_edges.py` caso [7]: `trades=0 rejected=0`.
- **Impacto:** se pierde una operación por corte y su coste de entrada. El sesgo es despreciable, pero el conteo de operaciones es inexacto.
- **Corrección mínima propuesta:** con `last == entry_i`, cerrar a `close[last]` (`bars_held=0`), o no aceptar la entrada en `end_idx`. Cualquiera de las dos, pero de forma explícita.
- **Test propuesto:** señal en `n-2` con `close_at_end=True`. Se afirma 1 operación con `reason == "end_of_data"` (o 0 operaciones con el rechazo contado).

### A-08 · LOW · NUEVO · señales long y short simultáneas: siempre long

- **Archivo:línea:** `fastbt.py:1108-1117` (`if ... long_sig[i]: pending = 1 / elif ... short_sig[i]`), `fastbt.py:788` y `fastbt.py:1247`. `compiler.compile` no resuelve el conflicto (`compiler.py:505-506`).
- **Evidencia:** `a07_edges.py` caso [6]: `long in#1`.
- **Impacto:** inclina la muestra hacia el long en las estrategias espejo cuando las dos condiciones se cumplen a la vez. En la práctica es raro.
- **Corrección propuesta:** si las dos señales son True, no operar o contarlo como conflicto, igual en el EA.
- **Test propuesto:** las dos señales en la misma vela. Se afirma 0 operaciones o un contador de conflictos igual a 1.

### A-09 · LOW · NUEVO · `close_signal` no gira de long a short

- **Archivo:línea:** `fastbt.py:800` (solo sale cuando `long_sig == 0 and short_sig == 0`).
- **Descripción:** si la señal pasa directamente de long a short, la posición sigue long hasta que las dos señales sean 0. `backtest_intraday` (`intraday.py:376`) usaría `pos = -1`. Solo afecta al modo de paridad, que ninguna campaña usa (`close_signal` solo aparece en `tests/test_discovery_parity.py`).
- **Evidencia:** `a07_edges.py` caso [12]: el long de la vela 0 sale en la vela 4 con `signal_end` y el tramo short de las velas 2-3 no aparece.
- **Corrección propuesta:** salir (y girar) cuando el lado de la señal cambia.
- **Test propuesto:** paridad del ledger con una serie objetivo `[1,1,-1,-1,0]` frente a `backtest_intraday`.

### A-10 · LOW · NUEVO · la vela de `session_end` en sesiones que cruzan medianoche

- **Archivo:línea:** `fastbt.py:1577-1578` (ventana inclusiva `seconds <= finish`) y `fastbt.py:1609` (`before_end = seconds < end_s`, estricto).
- **Descripción:** en 18:00→03:00, la vela de las 03:00 está en la ventana de entrada, pero `day_id` la asigna a la sesión siguiente. Eso reinicia `day_count` (`max_trades_per_day`) y cancela la señal pendiente de las 02:30. En `asia_range_reversion` no tiene efecto porque `flat_at` 02:45 quita esa vela de la entrada, pero con otro `flat_at` sí lo tendría.
- **Evidencia:** `a07_edges.py` caso [13]: `('02:30', day 0, entry 1), ('03:00', day 1, entry 1)`.
- **Corrección propuesta:** usar el mismo criterio de borde en los dos sitios (`<=` en `before_end`, o una ventana exclusiva en el fin).
- **Test propuesto:** con `max_trades_per_day=1`, una entrada a las 00:00 y otra señal a las 02:30 que entraría a las 03:00. Se afirma una sola operación por sesión.

---

## Sospecha no reproducida

- **S-1 · HTF con duración fija y DST** (`compiler.py:106-112`, `_htf_positions`). Una vela HTF D1 se considera cerrada en `inicio + 24h`. En una sesión de 25 h (cambio de hora de otoño), eso es 1 h antes del cierre real: un *look-ahead* de 1 h. Para CFD/FX el cambio ocurre el domingo a las 02:00 local, dentro del fin de semana sin datos, así que no se ha podido construir un caso realista con horario de mercado. Solo afectaría a fuentes que coticen en fin de semana. Test propuesto: H1 sintético 24/7 alrededor del 3-nov-2024 y una HTF D1, comprobando que ninguna barra base ve la HTF antes de `etiqueta_siguiente`.
- **S-2 · El EA gira con la señal opuesta, el motor no** (fuera de alcance: `export_mql5.py`, `OnNewBar`). Tras `CloseOurPosition()` por señal opuesta, el EA pone `has_position=false` y puede abrir el lado contrario en la misma vela. `_core` pone `pending=0` (`fastbt.py:930`) y no gira, como confirma `a07_edges.py` caso [9]. Además, el EA cierra con la señal opuesta sin comprobar `opposite_signal`. No se ha ejecutado el EA. Queda para el worker de exportación y paridad del EA.

---

## Comprobado y correcto (con evidencia)

| Punto | Cómo se verificó | Resultado |
|---|---|---|
| **Paridad Python/Numba de `_core`** | `a_parity.py`: 300 escenarios aleatorios con huecos, señales long/short/simultáneas, stop atr/pct, objetivo None/rr/pct, BE, trailing, `time_exit`, señal opuesta, fin de señal, `max_trades_per_day`, cooldown, `allow_next_day`, `close_at_end`, `end_index`, costes v1/v2 y 4 sesiones (incluida la que cruza medianoche). Se comparan 15 campos por operación con `==` exacto. | `casos=300 trades=6523 discrepancias=0` |
| **Paridad de `_calendar_core`** | `a_parity.py`: 100 escenarios D1 llamando directamente a `_calendar_core` (Python) y `_calendar_core_compiled` (Numba), con `np.array_equal` sobre todas las salidas. | `discrepancias=0` |
| **Sin look-ahead en la entrada** | `a07` [4]: la vela de la señal tiene high 150 y low 50. La entrada es `open[i+1]` y el stop no mira esa vela. El ATR del stop es `atr[pending_sig_i]` (`fastbt.py:945`), causal (`indicators.atr`: TR con `close.shift(1)` y `rolling` hacia atrás). | Correcto |
| **SL antes que TP en la misma vela** | `a07` [1]: high 102 y low 98 con stop 99 y objetivo 101 dan `stop @99`. | Conservador, correcto |
| **Hueco a través del stop** | `a07` [2]: open 97 con stop 99 sale a 97 (`min(stop, open)`, `fastbt.py:1017`). En el corto v2 se usa `max(stop, open_ask)`. | Peor precio, correcto |
| **Hueco a través del objetivo** | `a07` [3]: open 103 con objetivo 101 sale a 101. | Conservador (no mejora el fill) |
| **Salida en la vela de entrada** | `a07` [5]: entra al open y el low de la misma vela toca el stop: `in#1 out#1 stop`. Es correcto porque todo el rango de la vela es posterior al open. | Correcto |
| **BE y trailing desde la vela siguiente** | `a07` [8]: el `close` de la vela 1 llega a 0,6R. En la vela 1 el stop sigue en 99 (low 99,95, sin salida). En la vela 2 el stop está en 100 y sale a 100. | Correcto |
| **Señal opuesta y fin de señal** | Usan `sig[i-1]` y salen al `open[i]` (`fastbt.py:876-890`). `a07` [9]: sale al open de la vela siguiente a la señal opuesta, sin girar. | Sin look-ahead |
| **`time_exit_bars`** | `a07` [10]: N=2, entrada en la vela 1, salida al close de la vela 3. Coincide con `BarsHeld()` del EA (`export_mql5.py:1460-1465`): cierra al open de `e+N+1`, que es el close de `e+N`. | Coherente con el EA |
| **Cooldown y `max_trades_per_day`** | `a07` [11]: cooldown 3 contado desde la entrada da entradas en 1, 4 y 7 (igual que `CooldownAllows` del EA). Con máximo 1 por día, 1 operación. | Correcto |
| **DST en la máscara** | `a08_dst.py`: la sesión 09:35-11:30 con flat 15:45 da las mismas horas locales de entrada, gestión y flat el 8 y el 11 de marzo y el 1 y el 4 de noviembre de 2024 (−05:00 y −04:00). `resample_session` ancla la rejilla a las 17:00 NY con la zona horaria (`resample.py:68-75`). | Correcto |
| **Cierre al final del histórico** | La operación abierta se cierra a `close[end_idx]` con `reason=end_of_data` y el coste de salida del modelo (v2: spread solo si es corto) (`fastbt.py:1121-1155`). Visto en `a01`, `a02` y `a05`. Hay una excepción (A-07). | Correcto salvo A-07 |
| **Contabilidad de costes v2** | Long: spread en la entrada. Corto: spread en la salida, o en el ASK del stop y del objetivo, y `spread_r=0` en esos casos (`fastbt.py:1955-1965`). `a05`: corto `end_of_data` con un spread de 50 bps da R = −0,5 con `risk` del 1 %. | Coherente |
| **Mismo test del repo** | `pytest -q tests/test_discovery_fastbt.py::test_flat_at_uses_instrument_timezone` | 1 passed |

Notas de diseño, que no son defectos:
- El cierre por `flat_at` se ejecuta al `close` de la vela marcada. En M5 con flat a las 15:45, la salida es a las 15:50. En M15, a las 16:00 (sigue en COLA-MOTOR-FLAT).
- La ventana de entrada incluye la vela que abre exactamente a `session_end` (`<=`).
- El cooldown que bloquea descarta la señal; no la guarda.

---

## Lista de scripts (scratchpad, solo sintético)

Todos en `/tmp/claude-0/-home-user-trading-lab/89310f7f-0a4e-5602-b5a9-56cac624406b/scratchpad/A/`:
`common.py`, `a01_d1_weekday.py`, `a01b_calendar_monday.py`, `a02_midnight.py`, `a04_sleep_stopblind.py`, `a05_calendar_order.py`, `a06_h4_daychange.py`, `a07_edges.py`, `a08_dst.py` y `a_parity.py`, con sus `*_out.txt`.

El nombre de los scripts no coincide con el ID: `a02_midnight.py` reproduce A-05, `a04_sleep_stopblind.py` reproduce A-02 y `a06_h4_daychange.py` reproduce A-03.
