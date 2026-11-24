# RESULTADO · T1 — Preparación SSD (solo lectura)

Fecha: 2026-11-22. No se copió, movió ni borró nada. No se modificó ninguna tarea
programada.

## 1. Espacio libre

| Unidad | Libre | Usado |
|---|---:|---:|
| C: | 194,22 GB | 281,73 GB |
| E: | 684,47 GB | 247,04 GB |

## 2. Tamaño de E:\trading-lab por carpeta de primer nivel

| Carpeta | GB |
|---|---:|
| data | 1,239 |
| .venv (familia: .venv, .venv-vbt, .venv-r1, .venv-ta) | 1,654 |
| .git | 0,043 |
| resto (reports, logs, vendor, src, tests, docs, config, scripts, …) | 0,224 |
| **Total** | **3,160** |

Detalle de la familia `.venv`: `.venv` 0,572 GB; `.venv-vbt` 0,600 GB;
`.venv-r1` 0,287 GB; `.venv-ta` 0,196 GB. `data` incluye la caché de mercado.

## 3. Rutas absolutas a E: (config, src, scripts, *.yaml, *.ps1, *.toml, *.json)

53 coincidencias en 41 ficheros (excluidos `data` y `.git`):

```text
E:\trading-lab\config\telegram.example.yaml:9: working_dir: "E:\\trading-lab"
E:\trading-lab\config\telegram.yaml:4: working_dir: E:\trading-lab
E:\trading-lab\config\vector\vector.yaml:5: data_dir: E:/trading-lab/data/vector
E:\trading-lab\config\vector\vector.yaml:11: - E:/trading-lab/logs/ai_trader/**/*.log
E:\trading-lab\config\vector\vector.yaml:12: - E:/trading-lab/logs/intraday_forward/**/*.log
E:\trading-lab\config\vector\vector.yaml:13: - E:/trading-lab/logs/f13/**/*.log
E:\trading-lab\config\vector\vector.yaml:14: - E:/trading-lab/logs/drill/**/*.log
E:\trading-lab\config\vector\vector.yaml:15: - E:/trading-lab/logs/backup/**/*.log
E:\trading-lab\config\vector\vector.yaml:16: - E:/trading-lab/logs/heartbeat/**/*.log
E:\trading-lab\config\vector\vector.yaml:217: path: E:/trading-lab/logs/vector/all-%Y-%m-%d.jsonl
E:\trading-lab\config\vector\vector.yaml:227: path: E:/trading-lab/logs/vector/alerts.jsonl
E:\trading-lab\config\vector\vector.yaml:240: file: "E:/trading-lab/logs/ai_trader/2026-11-13_ny.log"
E:\trading-lab\config\vector\vector.yaml:356: file: "E:/trading-lab/logs/f13/f13_20261113.log"
E:\trading-lab\src\tradinglab\telegram.py:629: activar bots. El agente trabaja en E:\\trading-lab y responde con el resumen.
E:\trading-lab\src\tradinglab\telegram.py:638: "Trabaja en E:\\trading-lab. Sigue PLAN.md, README.md y AGENTS.md.\n"
E:\trading-lab\scripts\agents_daily.ps1:6: $root = "E:\trading-lab"
E:\trading-lab\scripts\await_model.ps1:9: $lab   = "E:\trading-lab\.venv\Scripts\lab.exe"
E:\trading-lab\scripts\backup.ps1:15: $root = "E:\trading-lab"
E:\trading-lab\scripts\backup.ps1:136: 1. Descomprimir en E:\trading-lab
E:\trading-lab\scripts\deep_compare_nightly.ps1:11: $root = "E:\trading-lab"
E:\trading-lab\scripts\drill_monthly.ps1:24: $root = "E:\trading-lab"
E:\trading-lab\scripts\guardian_enable_close.ps1:20: $root = "E:\trading-lab"
E:\trading-lab\scripts\heartbeat_pc.ps1:6: $root = "E:\trading-lab"
E:\trading-lab\scripts\intel_daily.ps1:12: $root = "E:\trading-lab"
E:\trading-lab\scripts\intraday_forward_execute.ps1:17: $root = "E:\trading-lab"
E:\trading-lab\scripts\intraday_forward_signal.ps1:16: $root = "E:\trading-lab"
E:\trading-lab\scripts\lab.ps1:3: & "E:\trading-lab\.venv\Scripts\lab.exe" @Args
E:\trading-lab\scripts\lessons_weekly.ps1:6: $root = "E:\trading-lab"
E:\trading-lab\scripts\llm_compare_daily.ps1:11: $root = "E:\trading-lab"
E:\trading-lab\scripts\lmstudio_start.ps1:11: $root = "E:\trading-lab"
E:\trading-lab\scripts\migrate_secrets.py:38: help="Ruta del .env (por defecto E:\\trading-lab\\.env)",
E:\trading-lab\scripts\premarket_daily.ps1:13: $root = "E:\trading-lab"
E:\trading-lab\scripts\reboot_after_download.ps1:4: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_ai_trader_tasks.ps1:9: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_cfd_tasks.ps1:23: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_deep_compare_task.ps1:6: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_drill_task.ps1:16: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_heartbeat_task.ps1:8: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_intraday_forward_task.ps1:8: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_llm_compare_task.ps1:5: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_premarket_task.ps1:5: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_resume_task.ps1:5: $root = "E:\trading-lab"
E:\trading-lab\scripts\register_telegram_task.ps1:5: $root = "E:\trading-lab"
E:\trading-lab\scripts\restore_test.ps1:7: [string]$Root = "E:\trading-lab",
E:\trading-lab\scripts\resume_after_reboot.ps1:6: $root = "E:\trading-lab"
E:\trading-lab\scripts\resume_terminal.ps1:8: Set-Location "E:\trading-lab"
E:\trading-lab\scripts\telegram_bridge.ps1:6: $root = "E:\trading-lab"
E:\trading-lab\scripts\trading_r1_premarket.ps1:14: $root = "E:\trading-lab"
E:\trading-lab\scripts\vector_cleanup.ps1:4: [string]$Root = "E:\trading-lab",
E:\trading-lab\scripts\vector_install.ps1:11: $root = "E:\trading-lab"
E:\trading-lab\scripts\vector_test.ps1:4: $root = "E:\trading-lab"
E:\trading-lab\scripts\web.ps1:10: Set-Location "E:\trading-lab"
E:\trading-lab\scripts\web_hidden.ps1:7: $root = "E:\trading-lab"
```

Si el repo se mueve a C:, estas rutas deben actualizarse. Las más críticas son
`config/telegram.yaml`, `config/vector/vector.yaml`, `src/tradinglab/telegram.py`
y los `scripts/*.ps1` que fijan `$root = "E:\trading-lab"`.

## 4. Tarea programada TradingLab_sync_spreads_daily

Leída con `Get-ScheduledTask` (sin modificarla):

- Estado: `Ready`; habilitada: sí.
- Acción: `powershell.exe`
- Argumentos: `-NoProfile -ExecutionPolicy Bypass -File "E:\trading-lab\scripts\sync_spreads_daily.ps1"`
- WorkingDirectory: vacío.
- Disparador: diario, inicio `2026-11-21T18:30:00-04:00`.

La acción apunta a E:. Si se mueve el repo, la tarea quedaría rota hasta
actualizarla; **no se ha tocado**.

## 5. pytest-xdist

No instalado. `uv pip show pytest-xdist --python .\.venv\Scripts\python.exe`
responde `Package(s) not found`; `importlib.util.find_spec("xdist")` devuelve
`False`. El `.venv` no tiene `pip` (`No module named pip`), así que no se usó
`pip show` directamente. No se instaló nada.

## 6. Comando robocopy propuesto (NO ejecutado)

C: tiene 194 GB libres para 3,16 GB. Se propone copiar el repo sin las venv
(no portables) ni cachés, y recrear la venv en destino:

```powershell
robocopy "E:\trading-lab" "C:\trading-lab" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /MT:16 `
  /XD "E:\trading-lab\.venv" "E:\trading-lab\.venv-vbt" `
      "E:\trading-lab\.venv-r1" "E:\trading-lab\.venv-ta" `
      "E:\trading-lab\.ruff_cache" "E:\trading-lab\.pytest_cache" `
  /LOG:"C:\Users\PC\AppData\Local\Temp\opencode\robocopy-tradinglab.log" /TEE
```

Después habría que recrear la venv en `C:\trading-lab`, revisar las 53 rutas
absolutas y actualizar (fuera de esta tarea) la acción de la tarea programada.
No se ejecutó el comando.

## Cierre

- Solo lectura; sin copias, sin borrados, sin cambios en tareas.
- Sin commit (no cambió el repo).
- Siguiente: T2.
