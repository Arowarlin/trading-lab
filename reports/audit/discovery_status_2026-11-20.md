# Auditoría · estado de campaña Discovery

**Fecha:** 2026-11-20
**Campaña:** `disc-US100.CASH-M5-20261120211100-092a76d2`
**`config_hash`:** `092a76d2fd33a1477fce834bd2006c1568a485faafc62d34e9e313a944f1fab7`
**`n_total`:** 440

## Cambio manual de estado (declarado)

| Campo | Valor |
|---|---|
| Fecha y hora local | 2026-11-20 17:23:39 (21:23:39 UTC) |
| Estado anterior | `running` |
| Estado nuevo | `registered` |
| Motivo | El motor dejó la campaña en `running` al abortar la inicialización con "población inicial vacía". Se restauró para desbloquear el reintento tras corregir el código, sin tocar la configuración. |
| Método | `UPDATE disc_campaigns SET status='registered' WHERE id=? AND status='running'` sobre `data/discovery.db` |
| Comprobaciones previas | 0 estrategias, 0 evaluaciones, 0 jobs de la campaña |
| Campos intactos | `config_json`, `config_hash`, `n_total`, `approved_at`, `dataset_hash` |

Este cambio se hizo **antes** de que el operador lanzara el run real. A partir de
ahora no se edita la base de datos a mano sin avisar al operador. El motor ya
restaura `registered` por sí mismo cuando falla antes de evaluar y guarda el
motivo en `disc_campaigns.last_error`.

## Run real posterior

| Campo | Valor |
|---|---|
| Lanzado por el operador | 2026-11-20 17:26:30 local |
| Comando | `lab discovery run disc-US100.CASH-M5-20261120211100-092a76d2 --approved-by-operator --workers 12` |
| Estado final | `done` |
| Evaluados | 260 |
| `n_effective` | 29 |
| Finalistas | 2 |
| Estrategias / evaluaciones en DB | 260 / 290 |
| `approved_at` | 2026-11-20T21:14:41.920+00:00 (sin cambios) |

**Decisión del operador (2026-11-20):** la campaña se archiva como resultado
válido **sin ventaja**. No se ejecuta `confirm`; OOS-2 sigue sin leerse
(0 evaluaciones OOS-2, 0 lecturas de holdout). `count_tests` se mantiene en 1500.

## Migración aditiva

Al ejecutar `lab discovery preflight` se añadió automáticamente la columna
`disc_campaigns.last_error` (migración del código, `TEXT`, por defecto `NULL`).
No se modificó ningún dato de la campaña. `preflight` no ejecuta backtests, no
lee OOS y no escribe estrategias.
