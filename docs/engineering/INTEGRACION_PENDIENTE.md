# INTEGRACION_PENDIENTE · Pasos del operador para llevar ENG-1 a `master`

La rama `claude/upbeat-pasteur-nz8e0u` contiene cambios de código además de documentos. Desde la nube
no se pueden tomar los locks ni ejecutar `lab`, así que estos pasos los hace el operador (u OpenCode
siguiendo este fichero) **cuando no haya ningún `lab discovery run` ni `pytest` en marcha**.

## 1. Qué cambia en código

| Commit | Ficheros | Efecto en producción | Tipo |
|---|---|---|---|
| F4 | `tests/conftest.py` | Ninguno (solo tests) | Tests |
| M1a | `tests/test_eng1_regressions.py` | Ninguno (3 `xfail` estrictos) | Tests |
| C-02 | `src/tradinglab/discovery/fetch_dukascopy.py`, `tests/test_dukascopy_resume_month_tail.py` | La próxima reanudación de Dukascopy **vuelve a bajar** el último mes de la caché si no llega a su último día laborable. No toca la caché que usa EDGE-2 hasta que alguien ejecute un fetch | Datos |
| **F5** | `src/tradinglab/config.py`, `telegram.py`, `task_health.py`, `tests/conftest.py`, `tests/test_eng1_default_db.py` | **Ninguno si `TRADINGLAB_DB` no está definida** (test de regresión `test_sin_variable_las_rutas_son_las_de_siempre`). `telegram_state.json` y `task_missed_seen.json` siguen en `data/` | Código compartido con producción |
| F3 | `uv.lock` | Añade `arch` 9.0.0 (+ formulaic, interface-meta, narwhals, patsy, statsmodels, wrapt) y `numba` 0.68.1 + `llvmlite` 0.50.0. **Ninguna versión existente cambia.** Generado con uv 0.13.7 (la de CI), `revision = 5` | Dependencias |

## 2. Pasos (en este orden)

```powershell
cd E:\trading-lab
git fetch origin claude/upbeat-pasteur-nz8e0u
```

```powershell
.\.venv\Scripts\lab.exe propfund baseline --reason "ENG-1 F5: DEFAULT_DB configurable para tests"
```

```powershell
git tag tl2-eng1-f5-pre master
```

Toma los locks `changelog-produccion` y `readme-plan` y luego:

```powershell
git merge --no-ff origin/claude/upbeat-pasteur-nz8e0u
```

```powershell
uv sync --frozen --extra dev --extra mt5 --extra discovery
```

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Resultado esperado de `pytest` en el equipo del operador: los mismos tests que antes, más 3 `xfailed`
y los tests nuevos en verde. **Puede que algún test que antes pasaba solo porque leía la `lab.db` real
ahora falle**: eso es justo la fuga que F5 destapa. Hay que anotarlo, no esconderlo.
Al final **no** debe salir la línea `AVISO: la suite modificó ficheros reales del laboratorio`.

## 3. Entrada para `docs/CHANGELOG-produccion.md` (copiar bajo el lock `changelog-produccion`)

```markdown
### 2026-11-26 · ENG-1 F5 · `DEFAULT_DB` configurable solo para la suite de tests
- **Qué:** `config.DEFAULT_DB` lee `TRADINGLAB_DB` si existe; `telegram.STATE_PATH` y
  `task_health.STATE_FILE` van junto a `DEFAULT_DB`. `tests/conftest.py` define la variable con una
  carpeta temporal y quita `.env`/keyring a los tests sin marcador de red/credenciales.
- **Por qué:** cada `pytest` escribía alertas falsas (una crítica), `data_freshness`,
  `learning_holdout` y `telegram_state.json` en `data/` real, y podía enviar alertas reales por
  ntfy/Telegram (docs/engineering/AUDIT_FINDINGS.md, F0-08).
- **Sin cambio en producción:** sin la variable las rutas son idénticas
  (`tests/test_eng1_default_db.py::test_sin_variable_las_rutas_son_las_de_siempre`).
- **Baseline:** `lab propfund baseline --reason "ENG-1 F5 …"` antes del merge.
- **Vuelta atrás:** tag `tl2-eng1-f5-pre`.
```

## 4. Limpieza opcional (decide el operador; nada se borra sin su orden)

La suite ya escribió filas de test en la `lab.db` real en ejecuciones anteriores. L1a
(`OPENCODE_PROMPTS.md`) las lista sin tocarlas. Si se quieren quitar, hace falta una orden explícita y
un backup previo (`docs/backups.md`).
