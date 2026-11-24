# RESULTADO · C1-fix — grid del spec en run

Fecha: 2026-11-22. Sesión de diagnóstico y arreglo. No se aprobó, ejecutó ni
registró ninguna campaña real; no se leyó OOS-1/OOS-2; no se hizo push.

## 1. Diagnóstico (solo lectura)

Fila de `data/discovery.db::disc_campaigns` para `c1-asia-usdjpy-h1-long`:

- `instrument/timeframe`: USDJPY / H1; `template`: `asia_range_reversion`.
- `status`: **running**; `n_evaluated`: **0**; `n_total`: **27**.
- `approved_at`: `2026-11-23T02:07:18.646+00:00`; `approved_by`: `operator`.
- `config_json.grid` **SÍ está guardada**:
  - `regime_threshold`: `long_entry.args[1].params.threshold` → `[15, 20, 25]`.
  - `stop_mult`: `exit.stop.mult` → `[1.5, 2.0, 2.5]`.
  - `target_rr`: `exit.target.rr` → `[1.5, 2.0, 2.5]`.
- `config_hash`: `acebffb4cc28b07d…` (incluye la grid).
- `disc_strategies` 0, `disc_evaluations` 0, `disc_validations` 0,
  `disc_lineage` 0. No hay trials parciales.
- El fallo ocurrió después de marcar `running` y antes de evaluar:
  `engine.run_campaign → grid.grid_strategies(grid_spec=None) →
  load_grid(template) → GridError "la plantilla asia_range_reversion no declara
  grid"`.

La campaña aprobada cuenta 27 en el DSR: contador actual **1703**.

## 2. Opción aplicada

**Opción (a)**: la grid sí estaba guardada en la campaña. El run ahora la lee de
`campaign["config"]["grid"]` y la pasa a `grid.grid_strategies(..., grid_spec=...)`;
no se cambió `n_total` ni `config_hash`.

Cambios:

- `run_campaign` resuelve y valida la grid **antes** de marcar `running`:
  - campaña grid sin grid → `CampaignError: preflight: campaña grid sin grid
    resoluble en config.grid`;
  - grid inválida o tamaño distinto de `n_total` → error de preflight claro.
- `grid.grid_strategies`/`grid_size` aceptan `grid_spec` (override del spec).
- `campaigns.reopen_empty_running`: si una campaña quedó `running` con
  `n_evaluated=0` y 0 estrategias, vuelve a `registered` para poder reintentar.
  El CLI de `run` y `engine.run_campaign` lo aplican. `approved_at` no se toca.
- Un fallo antes de evaluar deja la campaña re-ejecutable y 0 trials (test).

## 3. Tests

- `test_register_approve_run_aplica_grid_del_spec`: register_from_spec →
  approve → run sobre DB temporal y frame sintético; **27 estrategias
  evaluadas**, `n_total=27`, `n_evaluated=27`, estado `done`; los DSL guardados
  contienen exactamente `{15,20,25}`, `{1.5,2.0,2.5}` y `{1.5,2.0,2.5}`.
  También ejecuta `lab discovery show <id> --db <temp>` con exit 0.
- `test_run_grid_sin_grid_falla_antes_de_evaluar`: campaña grid sin grid →
  error de preflight, estado `registered` y 0 estrategias.
- `test_reopen_running_vacio_vuelve_a_registered`: running vacío → registered.
- `lab discovery show 94`, `lab discovery edge-map --by cuenta --account
  CFD-001` y las consultas de estado/DSR del RESULTADO-C1-prep funcionan.
- `pytest -q`: **1616 passed, 1 skipped**.
- `ruff check src/tradinglab tests`: limpio.
- `lab propfund verify`: 4 OK.
- `count_tests`: **1703** (la aprobación del operador ya contó 27; no 1676).
- Commit `89f75fb` · `tl2: C1-fix - grid del spec en run`; tag `tl2-c1-fix`.

## 4. Comandos exactos para el operador

La campaña ya está registrada y aprobada. Solo falta el run; el arreglo reabre
automáticamente el estado `running` vacío.

```powershell
Set-Location E:\trading-lab

# 1) Ejecutar la campaña aprobada (sin approve de nuevo)
.\.venv\Scripts\lab.exe discovery run c1-asia-usdjpy-h1-long --approved-by-operator --workers 12

# 2) Ver estado de la campaña
.\.venv\Scripts\python.exe -c "from tradinglab.discovery import databank; import json; print(json.dumps(databank.get_campaign('c1-asia-usdjpy-h1-long'), indent=2, default=str))"

# 3) Ver estrategias: nivel, estado, veredicto, bruto/neto y motivo (solo IS)
.\.venv\Scripts\lab.exe discovery results c1-asia-usdjpy-h1-long
.\.venv\Scripts\lab.exe discovery edge-map --by cuenta --account CFD-001
.\.venv\Scripts\lab.exe discovery show <strategy_id>

# 4) Ver el contador DSR actual (sin confirm ni OOS-2)
.\.venv\Scripts\python.exe -c "from tradinglab.config import DEFAULT_DB; from tradinglab.learning import count_tests; print(count_tests(DEFAULT_DB))"
```

No ejecutar `lab discovery confirm`: leería OOS-2. `results`/`show`/`edge-map` son solo
lectura y no leen el holdout.

## 5. Cierre

`git status --short`:

```text
?? tl2-edge-map.patch
```

`git log --oneline -3`:

```text
89f75fb tl2: C1-fix - grid del spec en run
641124d tl2: C1-prep - registro desde spec
043e979 tl2: R2k - arreglos previos a campaña
```

- La grid de esta campaña estaba guardada; no hace falta `supersede`.
- `n_total`/`config_hash` no cambiaron.
- DSR actual 1703; el run no lo incrementa otra vez.
- No se ejecutó la campaña real en esta sesión.

PARA.
