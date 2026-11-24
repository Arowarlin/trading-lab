# RESULTADO · C1-prep — primera campaña con historia larga

Fecha: 2026-11-22. Sesión de preparación. **No se registró** la campaña, no se
aprobó, no se ejecutó, no se leyó OOS-1/OOS-2 y no se hizo push. Solo se hizo el
`register --dry-run` para validar el comando.

## Decisión del operador

- Una sola campaña, modo **GRID** pequeño, historia larga (2010-2024). No GA.
- USDJPY H1, plantilla `asia_range_reversion`, fuente Dukascopy.
- Coste `best` entre CFD-001 (FTMO) y CFD-006 (FundingPips).

## 1. Spec

`.orquestador/specs/c1-asia-usdjpy-h1-long.yaml`

Hipótesis copiada literal antes de ver resultados:

> "El USDJPY concentra el flujo asiático. Los extremos del rango 18:00-03:00 NY
> actúan como zonas de liquidez y, cuando el precio los rebasa durante la sesión
> siguiente sin continuación, tiende a revertir hacia el interior del rango. Si
> es real, debe aparecer en varios regímenes (2010-2024), no solo en uno."

| Campo | Valor |
|---|---|
| campaign_id | `c1-asia-usdjpy-h1-long` |
| instrumento / TF | USDJPY / H1 |
| plantilla | `asia_range_reversion` |
| fuente | `dukascopy` |
| modo | `grid` (estructura bloqueada) |
| coste | `best` · CFD-001 y CFD-006 |
| IS | 2010-01-01 → 2024-06-30 |
| OOS-1 | 2024-07-01 → 2025-06-30 |
| OOS-2 | 2025-07-01 → última barra |
| n_total | **27** combinaciones exactas |

`usable_from` de `dukascopy:USDJPY:H1` = **2003-05-04**; 2010-01-01 ≥ 2003-05-04.

### Grid (3 dimensiones × 3 valores = 27)

| Dimensión | Path | Valores | Por qué |
|---|---|---|---|
| `regime_threshold` | `long_entry.args[1].params.threshold` | 15, 20, 25 | Exige un rango asiático más o menos lateral; 20 es el base de la plantilla. |
| `stop_mult` | `exit.stop.mult` | 1.5, 2.0, 2.5 | Stop en ATR(14): 2.0 es el base; 1.5/2.5 prueban si el ruido H1 pide más o menos margen. |
| `target_rr` | `exit.target.rr` | 1.5, 2.0, 2.5 | Objetivo en R: 1.5 es el base; 2.5 prueba si el retorno al rango da más recorrido. |

No se afinaron valores con resultados: son decisiones de mercado y el rango es
pequeño. El espejo corto se genera con `genetic.mirror_expr` al aplicar cada
combinación.

## 2. Preflight y feasibility en seco

```text
lab discovery preflight --spec .orquestador/specs/c1-asia-usdjpy-h1-long.yaml
```

- Generados 27 / válidos **27** / rechazados 0 / duplicadas 0.
- `Preflight OK: 27 válidos para población 27.`

```text
lab discovery feasibility --spec .orquestador/specs/c1-asia-usdjpy-h1-long.yaml
```

- Factibles **27/27 (100,0 %)** · gate ≥50 %: **PASA**.
- No hizo falta ajustar el grid; fue el primer intento.
- Feasibility midió 27 combinaciones en 11,8 s.

## 3. Estimación

- Operaciones IS por combinación: mín. 372, mediana **1.321**, máx. 2.375.
- Operaciones sumadas en los pliegues: mín. 301, mediana **1.058**, máx. 1.906.
- `cost_R` de operaciones: mín. 0,0411, mediana **0,0529**, máx. 0,0763.
- Tiempo medio en mercado: 143-231 min (mediana 185 min).
- Duración estimada del run: **< 5 min** con 12 workers (27 combinaciones sobre
  14,5 años de H1; feasibility, que además calcula pliegues, tardó 11,8 s).
- DSR antes: **1676**. Después de aprobar: 1676 + 27 = **1703**. Un borrador no
  cuenta; el `n_total` entra al aprobar.

## 4. Comandos exactos para el operador

Copiar en PowerShell, en este orden. El registro es un borrador; no cuenta hasta
aprobar.

```powershell
Set-Location E:\trading-lab

# 1) Registrar el borrador desde el spec (no aprueba)
.\.venv\Scripts\lab.exe discovery register --spec .orquestador\specs\c1-asia-usdjpy-h1-long.yaml

# 2) Aprobar explícitamente (aquí empieza a contar en el DSR)
.\.venv\Scripts\lab.exe discovery approve c1-asia-usdjpy-h1-long --approved-by-operator

# 3) Ejecutar la campaña
.\.venv\Scripts\lab.exe discovery run c1-asia-usdjpy-h1-long --approved-by-operator --workers 12

# 4) Ver estado de la campaña
.\.venv\Scripts\python.exe -c "from tradinglab.discovery import databank; import json; print(json.dumps(databank.get_campaign('c1-asia-usdjpy-h1-long'), indent=2, default=str))"

# 5) Ver estrategias: nivel, estado, veredicto, bruto/neto y motivo (solo IS)
.\.venv\Scripts\lab.exe discovery results c1-asia-usdjpy-h1-long
.\.venv\Scripts\lab.exe discovery edge-map --by cuenta --account CFD-001
.\.venv\Scripts\lab.exe discovery show <strategy_id>

# 6) Ver el contador DSR actual (sin confirm ni OOS-2)
.\.venv\Scripts\python.exe -c "from tradinglab.config import DEFAULT_DB; from tradinglab.learning import count_tests; print(count_tests(DEFAULT_DB))"
```

No ejecutar `lab discovery confirm`: leería OOS-2. `results`, `show` y `edge-map` son solo
lectura y no leen el holdout.

## 5. Cambios de código y checks

El registro desde spec no existía; se añadió:

- `campaigns.register_from_spec` y `lab discovery register --spec`.
- Override de grid en `grid.grid_strategies`/`grid_size` y en el spec
  (`grid.dimensions`); `n_total` sale de las combinaciones reales.
- `campaign_id` seguro (sin `:`), coste `best` con CFD-001/CFD-006.
- Tests: `test_register_from_spec_no_aprueba` (M5 sintético, 27 combos, borrador)
  y los tests de spec/preflight/feasibility.
- `pytest -q`: **1613 passed, 1 skipped**.
- `ruff check src/tradinglab tests`: limpio.
- `lab propfund verify`: 4 OK.
- `count_tests`: **1676**; `disc_campaigns`: 5 filas (no se registró nada).
- Commit `641124d` · `tl2: C1-prep - registro desde spec`; tag `tl2-c1-prep`.

`git status --short`: solo `?? tl2-edge-map.patch`.

## Aviso

- La campaña **no está registrada**; el operador debe ejecutar los comandos.
- El dry-run de registro mostró `n_total 27`, coste `best · CFD-001, CFD-006`,
  calidad `warn` e inicio útil 2003-05-04; no escribió campaña.
- No se leyó OOS-1/OOS-2 ni se hizo push.

PARA.
