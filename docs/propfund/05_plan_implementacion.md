# 05 · Plan de implementación

Estado al cierre de esta sesión (2026-11-19, rama `feature/prop-fund-multifirm`).

| Fase | Contenido | Estado |
|---|---|---|
| 0 · Protección y auditoría | inventario, SHA-256, test de integridad, línea base de tests | ✅ hecho |
| 1 · Arquitectura multi-firma | modelos, registro, 10 firmas, matriz de automatización, cuentas, versionado de reglas | ✅ hecho |
| 2 · Motor CFD | universo + alias + subyacentes; motor de costes CFD con comisión FTMO verificada | 🟡 spreads por cuenta: `lab propfund sync-spreads` listo y probado en dry-run con datos reales; falta ejecutar `--write` |
| 3 · Motor Futures | especificaciones CME/COMEX, micro-equivalencias, motor de costes | 🟡 falta proveedor histórico intradía y rollover |
| 4 · Integraciones | MT5 worker por cuenta, ProjectX multi-account, Tradovate, Rithmic | 🟡 lectura MT5 adjunta al terminal abierto (Tarea D); falta worker aislado y ProjectX |
| 5 · Strategy Router | pipeline completo en dry-run, log de decisiones, `lab propfund route` | ✅ hecho (dry-run) |
| 6 · Riesgo multicuenta | cuenta + global por subyacente, hedging cruzado, concentración | ✅ hecho; snapshots MT5 de solo lectura para `CFD-001` (Tarea D); faltan ProjectX y más cuentas |
| 7 · Dashboard | vista Prop Fund + tema visual Quantum para toda la consola | ✅ hecho |
| 8 · Validación integral | unitarios + hashes ✅; integración/concurrencia/fallos de conexión ⬜ con la Fase 4 |

## Archivos nuevos

`src/tradinglab/propfund/{__init__,models,registry,instruments,costs,risk,router,protected,console,cli,measure,snapshots}.py`,
`config/propfund/{firms,accounts,strategies,assignments,costs,risk}.yaml`,
`config/propfund/protected_manifest.json`, `tests/test_propfund.py`,
`tests/test_propfund_spreads.py`, `tests/test_propfund_snapshots.py`, `docs/propfund/01..06`.

## Tarea A · spreads medidos (2026-11-19)

`measure.py::sync_spreads(account_id)` lee `broker_spreads` (`source="broker"`) y
escribe por cuenta CFD:

* `spread_price` = mediana de las `median_bps` horarias.
* `spread_p75_price` = percentil 75 de los `p75_bps` horarios (conservador).
* Conversión bps → precio con el último cierre **completado** de
  `data/cache/mt5/<bróker>_<TF>.parquet`; sin red.
* `source` indica la procedencia de la medición y del slippage; `measured_at`
  es el fin de la ventana medida. Sin datos → `null` + `needs_verification`.

Símbolos de `CFD-001`: US100, XAUUSD, EURUSD, USDJPY (medidos; la medición
de USDJPY es del 2026-11-09, 240 h de antigüedad al ejecutar el dry-run) y
GBPUSD (`Sin datos`: no hay filas en `broker_spreads`). El slippage se lee de
`config/ai_trader.yaml` sin modificarlo. Pendiente: revisar el dry-run y
ejecutar `--write`.

## Tarea D · snapshots y exposición (2026-11-19)

`snapshots.py` construye `AccountSnapshot` y `PositionView` desde MT5 **sin
worker nuevo y sin credenciales**:

* Solo se adjunta al terminal ya abierto: comprueba `terminal64.exe` con
  `tasklist` antes de llamar a `MetaTrader5.initialize()` y no le pasa
  `login`/`password`/`server` (el terminal es compartido con el EA, `ai_trader`
  y el forward). Si MT5 no está abierto → `Sin datos: MT5 no está abierto` sin
  arrancar nada. Nunca llama a `mt5.shutdown()`.
* Fail-closed: exige cuenta DEMO y que `login`/`server` coincidan con
  `MT5_LOGIN`/`MT5_SERVER`. Si faltan o no coinciden → `Sin datos`.
* Posiciones en solo lectura por `magic`: EA `93010001/93020001`, `ai_trader`
  `20261191-93`, forward `20261151-53`; un magic desconocido se muestra como
  `desconocido:<magic>`. Nada se modifica ni se cierra.
* `AccountSnapshot`: balance/equity de `account_info`, inicio de día y pico con
  `PropGuard.state_from_equity`, `trades_today` desde cierres de `history_deals`
  y riesgo abierto sumando la distancia al SL (el que no se puede medir queda
  `None` y se avisa).
* `exposure` en `GET /api/propfund` y `lab propfund exposure [--json]`:
  nocional neto/bruto por subyacente, posiciones y avisos. Caché de **60 s**;
  cualquier fallo se devuelve como `Sin datos` sin romper el endpoint.

Hoy solo `CFD-001` (espejo de `ftmo_demo`, `DEMO`) entra en la lectura;
`CFD-002` está `DISCONNECTED` y las plantillas nunca se leen. ProjectX y el
worker aislado por cuenta siguen pendientes.

## Archivos modificados (aditivos)

| Archivo | Cambio |
|---|---|
| `src/tradinglab/cli.py` | registra `lab propfund` (3 líneas) |
| `src/tradinglab/web.py` | endpoint `GET /api/propfund` (4 líneas; ahora incluye `exposure` en solo lectura) |
| `src/tradinglab/propfund/console.py` | bloque `exposure` opcional en el payload |
| `src/tradinglab/propfund/cli.py` | comando `lab propfund exposure [--json]` |
| `src/tradinglab/webui/index.html` | vista Prop Fund, botón de navegación, capa CSS v4 "Quantum" y panel de exposición |
| `docs/ui_inventory.json`, `tests/test_console_shell.py` | nueva vista en el inventario |
| `README.md`, `PLAN.md` | documentación |

## Criterios de aceptación pendientes

* Spreads p50/p75 por hora escritos para cada cuenta CFD con `source` y `measured_at`.
* Proveedor intradía de futuros con barras reales y contratos continuos ajustados.
* Worker MT5 aislado por cuenta con verificación de login/servidor antes de cada orden.
* Reconciliación por cuenta Prop Fund.
* Reglas numéricas verificadas en contrato para cada programa antes de quitar `template`.

## Rollback

Todo el trabajo es aditivo. Revertir = `git revert` del commit o borrar la rama.
Ningún componente protegido cambió (`lab propfund verify`).
