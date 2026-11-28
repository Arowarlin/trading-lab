# FUT-V0 · Verificación en Windows

**Ejecutado:** 2026-11-28 en `E:\tl-fut-s`, rama `claude/vibrant-mayer-r46s0o`.
Hubo dos ejecuciones en paralelo sobre el mismo worktree (Claude local y OpenCode/DeepSeek); se conservan
ambas para que el operador vea la diferencia.

## Hecho

### 1. Primera ejecución (Claude local)

- `uv sync --frozen --extra dev --extra discovery`: Checked 93 packages.
- `ruff check .`: All checks passed!
- `pytest -q -m "not network and not mt5 and not lmstudio and not alpaca and not credentials"`:
  `3 failed, 2467 passed, 17 skipped, 3 deselected, 1 warning in 2058.22s (0:34:18)`
- `lab doctor` (FAIL/WARN): Frescura FAIL (17/17, EURUSD H1 sin datos en el worktree); WARN: Telegram remoto,
  Carpeta logs, TradingAgents, Trading-R1, Deep LLM, MetaTrader 5, Riesgo abierto, Reglas fondeo.
- `lab propecon programs --today 2026-12-01`: 5 programas, ninguno caducado.
- `lab propecon ranking`: MFF Rapid 3.55, Tradeify 3.45, TradeDay 3.00, Topstep 2.85, Alpha 2.80
  (Lucid 4.11 y Bulenox 3.06 provisionales).
- Fallos: `test_claude_hooks.py::test_runner_end_to_end`,
  `test_console_shell.py::test_barra_lateral_con_secciones_y_todas_las_vistas`,
  `test_console_shell.py::test_inventario_ui_base_sigue_completo`.

### 2. Segunda ejecución (OpenCode, DeepSeek V4.1 Flash) y corrección

- `uv sync --frozen --extra dev --extra discovery`: CPython 3.12.16, 93 paquetes, venv en `E:\tl-fut-s\.venv`.
- `ruff check .`: All checks passed!
- `pytest` inicial: `3 failed, 2466 passed, 18 skipped, 3 deselected, 1 warning in 2062.09s (0:34:22)`
  (los mismos 3 fallos; un test pasó a skip respecto a la primera ejecución).
- `lab doctor` y `propecon`: mismas filas y cifras que la primera ejecución.
- Diagnóstico y corrección:
  1. `test_runner_end_to_end`: el `bash` del PATH es el de **WSL** (`C:\Windows\system32\bash.exe`), que no
     acepta `E:\...`. El runner es para Windows/Git Bash. El test ahora usa Git Bash y `RUNNER.as_posix()`;
     si no hay Git Bash, se salta (el bash de WSL no sirve).
  2. `test_barra_lateral_con_secciones_y_todas_las_vistas` y `test_inventario_ui_base_sigue_completo`:
     la vista `futecon` existía en `index.html` pero no en el set esperado ni en `docs/ui_inventory.json`.
     Añadidos: vista, pestaña `◆ Economía futuros`, `view-futecon`, ids `fe-real/fe-nominal/fe-sim/
     fe-ranking/fe-alerts` y `/api/futures/economics`.
- Pruebas afectadas tras el arreglo: `73 passed, 1 skipped` (`tests/test_claude_hooks.py` y
  `tests/test_console_shell.py`).
- **Suite completa final:**

```text
2470 passed, 17 skipped, 3 deselected, 1 warning in 1886.78s (0:31:26)
```

- `ruff check .` final: `All checks passed!`

## Ficheros

- `tests/test_claude_hooks.py` (Git Bash en el test del hook).
- `tests/test_console_shell.py` (`futecon` en el set esperado).
- `docs/ui_inventory.json` (vista, pestaña, ids y endpoint de `futecon`).
- `docs/futures/WORKER_REPORTS/FUT-V0.md` (este informe).

## Aviso

- **Sesión concurrente en el mismo worktree.** Mientras corría la segunda ejecución, una sesión Claude Code
  (`claude.exe` PID 28540) mantuvo su propio pytest (`-p no:cacheprovider`, PID 7644) y ejecutó S2, S3 y la
  copia de S4. Su commit es `022b6fb`. No se pisaron ficheros: S2/S3/S4-copia quedaron en su commit y los
  arreglos de S1 en el commit posterior. El informe original de esa sesión se conserva íntegro arriba.
- El **FAIL de Frescura es esperado**: el venv y el `data/` son locales del worktree (`E:\tl-fut-s\data`);
  los datos reales están en `E:\trading-lab\data` y no se copiaron.
- S2/S3 verificados: 34 filas de coste (0 errores «Sin datos», total USD 14.065,31) y 9 parquet con los
  9 SHA-256 coincidentes. S3 se ejecutó con un envoltorio `runpy` porque `--data-dir` fuera de `ROOT`
  falla en `relative_to`; el resultado es correcto pero es una desviación del comando del prompt.
- S4: copia del `.cs` verificada (SHA-256 idéntico) y parada esperando compilación/activación en NT8.
  Hoy es sábado y el mercado está cerrado; sin ticks no habrá ack (CME reabre domingo 18:00 ET o Playback).
- Sin descargas de pago, sin campañas, sin live y sin `git push`.

## Siguiente

- **S1 en verde.** S2/S3 hechos y verificados. S4 queda en la parada obligatoria: compilar
  `TradingLabBridge` en NT8, activarlo en Sim101 con `BridgeDir = E:\tl-fut-s\data\futures\nt8_bridge`
  y responder «OK NT8».
