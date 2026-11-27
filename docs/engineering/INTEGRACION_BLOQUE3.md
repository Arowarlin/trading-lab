# INTEGRACION_BLOQUE3 · Pasos para llevar a `master` el tercer bloque de ENG-1

**Contenido del bloque** (rama `claude/upbeat-pasteur-nz8e0u`):

| Hallazgo | Qué cambia | ¿Producción? |
|---|---|---|
| F0-09 | Hash del forward del EA independiente de los finales de línea; el hash antiguo se acepta como alias del mismo contenido | **Sí** (`ea_forward.py`, grupo protegido `ea_us100_ftmo1`) |
| Puertas v3 + `min_trades_oos1: 30` | **Activadas** en `config/discovery/engine.yaml` (volver a `gates_version: 2` restaura las anteriores) | No (Discovery) |
| C-07 | Año Nuevo en sábado no cierra el 31-dic en los calendarios de investigación. `nyse_calendar.py` (EA) **no** se toca | No |
| C-01 | `data-check` ve los huecos largos entre semana en M1-M30 | No |
| E-01 | El GA explora el horario fuera de 09:30-15:00 (NY idéntico) | No |
| E-03 | `edge_map`: nuevo estado "edge neto sin robustez" | No |
| F0-06 | El error de arranque del worker llega con su motivo | No |
| D-04 | SPA de Hansen studentizado con bloque automático y fechas | No |
| D-05 | Con v3: Monte Carlo y bootstrap por bloques con sentido | No |
| A-01 | `weekday_mode` opcional (apagado) | No |
| F0-10 | Duración de vela correcta con pandas 3 | No |

Suite completa en Linux antes de integrar: 1 fallo esperado (`test_componentes_protegidos_intactos`,
porque `ea_forward.py` cambia hasta que se rehace el baseline en el paso 6).

## Pasos (PowerShell, en orden; sin campañas ni `pytest` en marcha)

1. Comprobar que no hay nada en marcha (no debe salir nada):

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "discovery run|pytest" } | Select-Object ProcessId
```

2. Baseline **antes** y tag de vuelta atrás:

```powershell
cd E:\trading-lab
.\.venv\Scripts\lab.exe propfund baseline --reason "ENG-1 F0-09: antes del cambio del hash del forward"
git tag tl2-eng1-f009-pre master
```

3. Traer e integrar la rama (si sale CONFLICT, parar y avisar):

```powershell
git fetch origin claude/upbeat-pasteur-nz8e0u
git merge --no-ff origin/claude/upbeat-pasteur-nz8e0u -m "merge: ENG-1 bloque 3 (F0-09, v3 activa, C-01, C-07, E-01, E-03, F0-06, D-04, D-05, A-01, F0-10)"
```

4. Comprobar que el forward del EA sigue funcionando con el hash guardado (no cambia nada en `lab.db`):

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_eng1_ea_hash.py tests\test_ea_forward.py
```

5. Entrada del CHANGELOG (toma el lock `changelog-produccion`):

```powershell
.\.venv\Scripts\python.exe docs\engineering\tools\eng_changelog.py F0-09
```

6. Baseline **después** (el manifiesto registra el nuevo `ea_forward.py`) y verificación:

```powershell
.\.venv\Scripts\lab.exe propfund baseline --reason "ENG-1 F0-09: hash normalizado a LF con alias del anterior"
.\.venv\Scripts\lab.exe propfund verify
```

7. Suite completa (unos 35 min):

```powershell
.\.venv\Scripts\python.exe -m pytest -q *> E:\pytest-bloque3.log
Get-Content E:\pytest-bloque3.log -Tail 15
```

8. Guardar y subir (solo esos dos ficheros además del merge):

```powershell
git add config\propfund\protected_manifest.json docs\CHANGELOG-produccion.md
git commit -m "eng1: baseline F0-09 y CHANGELOG"
git push origin master --tags
```

## Después: prompts L5 y L6 (OpenCode, DeepSeek V4.1 Flash)

Están en `docs\engineering\OPENCODE_PROMPTS.md`:
- **L5:** qué noche cobra el triple swap tu bróker, con tus deals reales. Es lo que falta para decidir
  B-04.
- **L6:** descargar el ASK de USDJPY 2003-2022 para C1. Tarda; no toca el OOS-2.

Subir sus informes:

```powershell
git add docs\engineering\WORKER_REPORTS\B04-swap.md docs\engineering\WORKER_REPORTS\L6-ask.md
git commit -m "eng1: informes L5 y L6"
git push origin master
```
