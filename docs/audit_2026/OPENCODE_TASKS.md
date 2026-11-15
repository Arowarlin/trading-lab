# OPENCODE_TASKS — Tareas pequeñas y ejecutables

Modelo: **DeepSeek V4.1 Flash** (OpenCode Go). Una tarea por sesión.

Cada tarea termina con ruff, pytest, `lab doctor`, `lab f13 config-check`, una entrada en PLAN.md, un commit y **sin push**. Ninguna ejecuta campañas ni suma pruebas al DSR. Las que cambian `enabled` o los límites dejan el cambio **preparado** y es el operador quien lo aprueba.

---

## T01 · P0 · Corregir las unidades del DSR

- **Problema:** las cuatro llamadas a `deflated_sharpe` pasan un Sharpe anualizado con `n_obs` en días.
- **Evidencia:** con el ejemplo de Bailey y López de Prado (2014), la función correcta da 0,9004 y el lab da 0,99999994. La mejor de 1040 series de ruido obtiene 0,9999998.
- **Archivos:** se crea `src/tradinglab/stats.py`. Se modifican `research.py`, `optimize.py`, `ea_us100.py`, `campaign.py` y `learning.py` (columna nueva) y se crea `tests/test_stats_dsr.py`.
- **Diseño:** `dsr_from_returns(returns, trial_srs_per_period, n_trials) -> dict(dsr, sr_period, sr0_period, skew, kurt, n_obs, metric_version="dsr_v2")`. Calcula el Sharpe **por periodo** sin anualizar y la curtosis no excesiva. `trial_srs_per_period` también va sin anualizar. `deflated_sharpe` se mantiene como función interna. Las cuatro llamadas pasan a usar `dsr_from_returns`.
- **Campaña:** se elimina `sr_std = |SR|/√bars` y se usa la desviación de los Sharpes por periodo de todas las celdas de descubrimiento de esa campaña.
- **Tests:**
  1. El ejemplo publicado (SR anual 2,5 → 2,5/√250; T = 1250; asimetría −3; curtosis 10; N = 100; V = 0,5/250) da 0,9004 ± 0,001.
  2. Con semilla fija, la mejor de 500 series de ruido da DSR < 0,95.
  3. Una serie con una media claramente positiva y N = 2 da DSR > 0,95.
  4. Cualquier llamada que pase un Sharpe mayor que 1 por periodo con datos diarios lanza `ValueError` (protección contra unidades mal puestas).
- **Aceptación:** los cuatro módulos guardan `dsr_v2` y `metric_version`. Los valores antiguos se conservan, marcados como `dsr_v1_invalid_units`.
- **Rollback:** revertir el commit. No se toca ningún dato.

## T02 · P0 · Recalcular el DSR v2 del historial (solo lectura de datos)

- **Depende de:** T01.
- **Qué hace:** `lab stats recompute-dsr --dry-run` recorre los resultados guardados que tienen retornos o artefactos de equity y calcula `dsr_v2` **sin volver a ejecutar ningún backtest** ni sumar pruebas. Por defecto escribe solo un informe en `reports/audit/dsr_v2.md`. Con `--write`, añade la columna en la base de datos.
- **Aceptación:** el informe lista el EA, F13 y los candidatos de las campañas A y B, cada uno con su DSR v1 y su DSR v2. Si falta la serie, escribe **Sin datos**.

## T03 · P0 · Magics del EA en el guardián y en el stop de cuenta

Es el punto 1 del prompt anterior. Si ya está hecho, solo se verifica. `guardian.json` y `account_daily_stop` incluyen los `managed_magics` de `config/mt5_eas.yaml` de la cuenta.

- **Test:** una posición flotante del EA empuja la cuenta al límite, se bloquean las aperturas del lab y se emite una alerta critical.

## T04 · P0 · PBO de confirmación de campaña

- `campaign.py:2548`: cuando hay una sola variante, guarda `pbo = None` y `pbo_reason = "no_aplica_1_variante"`, y quita el `except` silencioso.
- Se añade el PBO de **descubrimiento** sobre la matriz completa de celdas de la campaña, guardado una vez por campaña.
- **Test:** con una sola celda aparece la razón; con una matriz de 10 variantes sale un valor entre 0 y 1.

## T05 · P0 · Preparar la desactivación de los forwards con Sharpe negativo

- Crea `config/proposals/disable_fx_forward.yaml` con el diff propuesto (`enabled: false` en los magics 20261151 y 20261152) y su justificación.
- **No** modifica `intraday_forward.yaml`. El operador lo aplica con `lab proposals apply disable_fx_forward --confirm`. Si no existe ese comando, la tarea lo documenta para aplicarlo a mano.

## T06 · P1 · Swap y financiación en los backtests

- Añade `swap_long` y `swap_short` por símbolo en `costs.yaml` (en puntos o en porcentaje anual; se leen de `mt5.symbol_info` y quedan en **Sin datos** si no hay MT5), más el triple swap del miércoles.
- `backtest.run(..., carry=CostModel)` descuenta el carry por cada noche con posición. `run_event_backtest` hace lo mismo para las posiciones que cruzan el rollover.
- **Test:** una posición larga de 3 noches con un miércoles en medio paga 5 veces el swap diario.
- **Aceptación:** el informe de us100-trend-d1 se puede regenerar con el swap incluido (no se ejecuta en esta tarea).

## T07 · P1 · Spread en las entradas limitadas y los objetivos (CFD y FX con barras BID)

- En el motor de eventos, una compra limitada exige `low + spread_h ≤ level` y el objetivo de un corto exige `low + spread_h ≤ target`, usando el spread de esa hora.
- Se activa con `asset_class in {"cfd","fx"}`. Para acciones no cambia nada.
- **Test:** una barra en la que el BID toca el nivel pero el ASK no, no se llena.

## T08 · P1 · Contabilidad por operación en backtest.py

- Atribuye a cada operación su comisión de entrada (proporcional al cierre) y cuenta las operaciones como **viajes completos**: de 0 a una posición y de vuelta a 0, o un giro.
- Las métricas de equity (Sharpe y DD) no cambian, porque los costes ya se restan del cash.
- **Test:** con una entrada, una reducción parcial y un cierre, `num_trades` es 1 y el PnL de la operación incluye las dos comisiones.

## T09 · P1 · Zonas horarias

- Sustituye `datetime.now()` y `date.today()` por `datetime.now(timezone.utc)`, o por `ZoneInfo("America/New_York")` cuando la lógica es de sesión, en los 37 sitios.
- Añade una regla de ruff (`DTZ`) para evitarlo en el futuro.
- **Test:** un test con la hora congelada (`freezegun` no está disponible, así que se usa monkeypatch) en el cambio de horario de marzo comprueba la ventana de sesión de F13.

## T10 · P2 · Optuna con informe honesto

- Renombra en el informe "OOS Sharpe" a `wf_selected_sharpe`.
- Añade la mediana de los 20 mejores trials (meseta) y un aviso si el mejor supera la mediana en más de un 50 %.
- `trials` tiene un máximo de 200 por estudio, salvo con `--allow-large`.

## T11 · P2 · Informe de robustez del EA sin pruebas nuevas

- Con las 8 variantes ya registradas de la rejilla: tabla año a año, el peor año, la contribución por año y por lado (largo o corto), riesgo fijo del 0,35 % frente a riesgo dinámico y el DSR v2.
- Escribe en `reports/research/ea_us100_ftmo1/robustness.md`. No cambia ningún parámetro.

## T12 · P4 · Riesgo abierto por símbolo y por clúster

Es el punto 2 del prompt anterior, ampliado con clústeres: `account_risk_caps` en `accounts.yaml` (símbolo 2 %, clúster 3 %, total 4 %), aplicado en PropGuard, ai_trader y el forward.

## T13 · P5 · Separar el replay del forward en el carril IA

- Verifica que `ai_replay` escriba en tablas o etiquetas distintas a las del scoreboard forward, y que `ai_distill` no use operaciones de replay como evidencia.
- Si se mezclan, añade una columna `source in {forward, replay}` y filtra por ella.
- **Test:** una operación de replay no altera el scoreboard.

## T14 · P6 · busy_timeout en SQLite

`db.connect` fija `PRAGMA busy_timeout=5000` en todas las conexiones. Test con dos escritores a la vez.

## T15 · P2 · N efectivo del DSR global por clúster de correlación de las pruebas

- **Problema:** `dsr_global` usa `count_tests` (hoy 1042) como si todas las pruebas fueran independientes; muchas son variantes correlacionadas de la misma familia/activo.
- **Diseño pendiente:** agrupar las pruebas por correlación de sus retornos o de sus Sharpes por periodo, calcular un N efectivo por clúster y reportarlo junto al N nominal. No cambiar el gate hasta que el operador lo apruebe con un pre-registro.
- **Aceptación:** informe con N nominal, N efectivo y pruebas por clúster; `dsr_global` sigue usando el N actual hasta aprobación explícita.
- **No implementar en Fase 1:** queda como tarea P2.

## Orden y dependencias

1. T01, T03 y T05 son independientes y van primero.
2. T02 depende de T01. T04 se puede hacer en paralelo.
3. T06, T07, T08 y T09 son independientes entre sí.
4. T10 y T11 dependen de T01.
5. T12 depende de T03. T13 y T14 son independientes.
