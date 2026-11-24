# Cambios en producción

Registro obligatorio de los cambios en componentes de producción: EA
`us100-ftmo1`, carril forward FTMO, riesgo FTMO, `ai_trader`, Prop Fund y
`ea_lab`. Cada entrada indica la autorización del operador, qué cambió y cómo se
comprueba. El baseline de hashes vive en
`config/propfund/protected_manifest.json` y se consulta con
`lab propfund verify`; se reescribe con `lab propfund baseline --reason "..."`.

## 2026-11-24 · Retirada de la protección de componentes

- **Autorización del operador (literal):** "EL PASO YA NO ESTA PROTEGIDO
  QUITALE LA PROTECCION".
- **Qué cambia:** el manifiesto deja de bloquear. `lab propfund verify` informa
  de los archivos cambiados y sale con código 0; `lab propfund baseline
  --reason "..."` reescribe el baseline y añade una entrada a `authorizations`
  con fecha, motivo y lista de cambios. El concepto `protected` de una
  estrategia pasa a `external_engine` (la ejecuta su propio motor); el YAML
  antiguo con `protected: true` sigue cargando como alias de lectura.
- **Qué no cambia:** el router sigue rechazando enviar órdenes a estrategias de
  motor externo. Solo demo/paper; ninguna orden real.
- **Rollback:** tag `tl2-t00-pre`.

## 2026-11-24 · Modelo de ejecución BID/ASK v2 en Discovery

- **Qué cambia:** `CostPanel` lleva `spread_bps`, `slip_bps` y `comm_bps` por
  barra. Las campañas nuevas registran `cost_model_version: 2`: un solo spread
  por operación, stop de corto disparado por el ASK (`max(stop, open_ask)`) y
  desglose por operación (`spread_r`, `slip_r`, `comm_r`). Las campañas
  existentes se cargan como versión 1 y se reproducen igual.
- **Alcance:** `discovery/fastbt.py`, `discovery/costs.py`, `discovery/drift.py`,
  `discovery/jobs.py`, `discovery/fitness.py`, `discovery/robustness.py`,
  `discovery/levels.py`, `discovery/feasibility.py`, `discovery/specs.py`,
  `discovery/basket.py` y `discovery/campaigns.py`. No se toca
  `ea_us100_engine.py` (es la referencia).
- **Verificación:** `tests/test_discovery_execution_v2.py` (17 pruebas con
  resultados a mano), paridad v1 en las fixtures existentes, paridad de
  convención con `ea_us100_engine` y tabla de coste antes/después en
  `docs/tradinglab2/06_TRADINGLAB_DATA_AND_COST_AUDIT.md`.
- **Rollback:** tag `tl2-t10-pre` o `cost_model_version: 1` en la campaña.

