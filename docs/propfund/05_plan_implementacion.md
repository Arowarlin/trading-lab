# 05 · Plan de implementación

Estado al cierre de esta sesión (2026-11-19, rama `feature/prop-fund-multifirm`).

| Fase | Contenido | Estado |
|---|---|---|
| 0 · Protección y auditoría | inventario, SHA-256, test de integridad, línea base de tests | ✅ hecho |
| 1 · Arquitectura multi-firma | modelos, registro, 10 firmas, matriz de automatización, cuentas, versionado de reglas | ✅ hecho |
| 2 · Motor CFD | universo + alias + subyacentes; motor de costes CFD con comisión FTMO verificada | 🟡 falta escribir spreads medidos por cuenta (`lab ticks broker-spread` → `config/propfund/costs.yaml`) |
| 3 · Motor Futures | especificaciones CME/COMEX, micro-equivalencias, motor de costes | 🟡 falta proveedor histórico intradía y rollover |
| 4 · Integraciones | MT5 worker por cuenta, ProjectX multi-account, Tradovate, Rithmic | ⬜ pendiente |
| 5 · Strategy Router | pipeline completo en dry-run, log de decisiones, `lab propfund route` | ✅ hecho (dry-run) |
| 6 · Riesgo multicuenta | cuenta + global por subyacente, hedging cruzado, concentración | ✅ hecho (con snapshots manuales; falta alimentarlo con MT5/ProjectX) |
| 7 · Dashboard | vista Prop Fund + tema visual Quantum para toda la consola | ✅ hecho |
| 8 · Validación integral | unitarios + hashes ✅; integración/concurrencia/fallos de conexión ⬜ con la Fase 4 |

## Archivos nuevos

`src/tradinglab/propfund/{__init__,models,registry,instruments,costs,risk,router,protected,console,cli}.py`,
`config/propfund/{firms,accounts,strategies,assignments,costs,risk}.yaml`,
`config/propfund/protected_manifest.json`, `tests/test_propfund.py`,
`docs/propfund/01..06`.

## Archivos modificados (aditivos)

| Archivo | Cambio |
|---|---|
| `src/tradinglab/cli.py` | registra `lab propfund` (3 líneas) |
| `src/tradinglab/web.py` | endpoint `GET /api/propfund` (4 líneas) |
| `src/tradinglab/webui/index.html` | vista Prop Fund, botón de navegación, capa CSS v4 "Quantum" |
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
