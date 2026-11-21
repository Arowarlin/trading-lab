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

## Migración 2026-11-19 · solo CFD/futuros

Decisión del operador: TradingLab queda enfocado solo en cuentas de fondeo CFD
(US100, US500, GER40, XAUUSD, EURUSD, GBPUSD, USDJPY) y futuros (NQ, MNQ, GC,
MGC cuando haya datos). Se retira el carril de acciones/ETF.

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Inventario A/R/C sin cambios | hecho |
| 1 | Informe final F13 (`reports/f13/final_2026-11.md`); tarea deshabilitada | hecho |
| 2 | Archivado con `git mv` a `legacy/`; CLI y paneles retirados; tests de F13/acciones archivados | hecho |
| 3 | Briefing pre-Londres/pre-NY con MT5 en solo lectura (`propfund/market.py`), agentes e intel CFD, mercado y overnight | hecho |
| 4 | `accounts.yaml` sin `paper_main`/`alpaca_paper`; `bots.yaml` vacío; `f13.yaml` y `equities_lane.yaml` en `legacy/config/`; `f13_hash` fuera del manifiesto y re-freeze aprobado | hecho |
| 5 | `scripts/register_cfd_tasks.ps1` generado, sin ejecutar | hecho |
| 5b | Consola CFD/futuros completa y barrido sin QQQ/SPY/ETF/Alpaca/F13 fuera de `legacy/` | hecho |
| 5c | Sustituida por **TradingLab 2.0** (`docs/tradinglab2/`, parche aparte) | sustituida |
| 6 | README, PLAN y este documento | hecho |

El manifiesto protegido queda con 4 grupos (`ai_trader`, `ea_us100_ftmo1`,
`ftmo_forward`, `ftmo_risk`); `f13_hash` se retiró y el re-freeze se
ejecutó con `lab propfund freeze --approved-by-operator`.

## Tarea E · Onboarding de cuentas (R2i, 2026-11-21)

`lab propfund onboard ACCOUNT_ID` escribe `reports/propfund/<cuenta>_onboarding.md`
(solo lectura, sin campañas, sin OOS y sin `count_tests`):

* **Reglas** del programa con URL y fecha; lo no encontrado queda `Sin datos` y
  `unverified`. Incluye EAs, noticias, fin de semana, overnight, días mínimos,
  límites de pérdida, apalancamiento, límite de tiempo y máximos.
* **Costes**: símbolos del bróker leídos con `symbols_get` (sin adivinar),
  `sync-spreads` en dry-run, spread p75 por hora local NY, comisión citada y
  `assumed_slippage` de `engine.yaml`. MT5 solo adjunto: sin login ni shutdown y
  con login/servidor comprobados contra la cuenta.
* **Mapa de viabilidad** de las plantillas existentes por instrumento × sesión ×
  TF con el coste de ESTA cuenta (`cost_mode target`): solo operaciones IS y
  `cost_R`, sin PnL.
* **Restricciones** de la firma en `config/propfund/firms.yaml`
  (`firm_constraints`): noticias, fin de semana, overnight, máx. operaciones/día
  y máx. lotes. `propfund/constraints.py::check_strategy` marca
  `incompatible con <firma>` y comparten la regla el onboarding, el mapa y la
  matriz.
* **Matriz** de estrategias nivel ≥ 3: DSL congelado, solo IS, sin reoptimizar;
  expectativa neta, `cost_R`, P(pasar), P(romper), compatibilidad y si la firma
  permite automatizarla. Si el dataset sellado ya no coincide, el recálculo se
  marca como indicativo. Si no hay estrategias nivel ≥ 3, se dice.
* **Resumen**: instrumentos donde esta cuenta es más barata que las demás y
  combinaciones candidatas (sugerencia; la campaña la decide y aprueba el
  operador).

Datos verificados de FundingPips el 2026-11-21 (Free Trial y 2 Step Standard):
14 días naturales por fase, MT5/servidor `FundingPips-Trial`, Standard 5 %/10 %
y Pro 3 %/6 %, noticias permitidas en evaluación, overnight/weekend permitidos
en evaluación, 20 lotes por operación y máximo de operaciones/día `Sin datos`.
Informe de referencia: `reports/propfund/CFD-006_onboarding.md` (ignorado por
git, se regenera con el comando).
