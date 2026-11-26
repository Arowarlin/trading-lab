# BASELINE_REPORT · Programa ENG-1 (Fase 0)

**Fecha:** 2026-11-26 · **Autor:** Claude Code (coordinador), sesión en la nube.
**Alcance:** qué versión se audita y qué está activo. Solo lectura: no se modificó ningún fichero de
`src/`, `tests/`, `scripts/`, `config/` ni datos.

## 1. Versión auditada

| Elemento | Valor | Cómo se obtuvo |
|---|---|---|
| SHA | `adc0eec01ce8243cad1de0fe43f29194588e623c` (`wf-tf: W2 - EDGE-1`, 2026-11-26 10:28 -04:00) | `git rev-parse HEAD` |
| `master` local y `origin/master` | El mismo SHA | `git rev-parse master origin/master` |
| Rama de trabajo | `claude/upbeat-pasteur-nz8e0u` (sin cambios sobre `master` al empezar) | `git status -sb` |
| Worktrees | Solo el principal | `git worktree list` |
| Tags | **No hay tags en este clon.** `edge1`, `robust-1`, `robust-pre`, `motor-flat-pre`, etc. existen solo en el equipo del operador | `git tag` vacío |
| `discovery.__version__` | `0.1.0` | `src/tradinglab/discovery/__init__.py:13` |

## 2. Entorno de esta auditoría (contenedor Linux, **no** el equipo del operador)

| Elemento | Valor |
|---|---|
| Python | 3.13.18 |
| NumPy / Pandas / Numba | 2.5.4 / 3.1.1 / 0.68.1 |
| Instalación | `uv sync --frozen --extra dev` + `uv pip install "numba>=0.60"` |
| CPU / RAM | 4 núcleos / 15 GB |
| Datos de mercado | **Sin datos.** `data/` ocupa 220 KB (solo `calendar/` y `tl3/`). Los históricos, `discovery.db` y `lab.db` están en `E:\trading-lab` del operador |
| MT5, keyring, Telegram | No disponibles aquí |

Consecuencia: aquí solo se puede auditar código, ejecutar pruebas sintéticas y la parte de la suite
que no depende de datos locales. **Ningún resultado de este programa sale de datos reales.**

## 3. Campañas y colas activas (según el repositorio, 2026-11-26 10:28)

| Cola | Estado | Efecto sobre ENG-1 |
|---|---|---|
| **EDGE-2 Y2** | **En marcha** en el equipo del operador: 4/18 campañas `done` (`TL3_REPORTS/edge2_progreso.md`, commit `554497c`). Plan Y1 `6ffd14ae…d360d`, 18 campañas, `n_total` 7.920 | **Motor congelado:** `fastbt.py`, `costs.py`, `_session_mask`, métricas, `robustness.py`, `engine.yaml`. EDGE-2 lanza `lab discovery run` en procesos nuevos, así que cualquier cambio en `src/` alteraría las campañas que faltan |
| **WF-TF** | W2 hecho (`adc0eec`); W3 espera a `edge2_finalistas.md` | No tocar `walkforward.py`, `robustness.py`, `scripts/wf_tf_*` |
| **MOTOR-FLAT** | Preparada; arranca tras los tags `edge1` + `edge2` y sin `lab discovery run` vivo | El arreglo de `flat_at` ya tiene dueño: ENG-1 no lo duplica |
| **TL3-E** | Solo E0 hecho | Sin solape |
| Forward NQF | Desde el 2026-11-30 (tag `nqedge-forward-start`) | Protegido; no se mira rendimiento antes de las fechas de control |

**Procesos locales:** no se pueden ver desde la nube. Antes de integrar cualquier cosa en el equipo
del operador hay que comprobar `Get-CimInstance Win32_Process` (sin `lab discovery run` ni `pytest`
vivos) y los locks de `.orquestador`.

## 4. Tests y CI

| Comprobación | Resultado |
|---|---|
| `ruff check src tests scripts` (aquí) | **All checks passed** |
| `pytest` en el equipo del operador (ROBUST-1, 2026-11-26) | 2073 passed + 1 skipped (34:40), según `ESTADO.md` §9 (resultado reportado, no reproducido aquí) |
| CI GitHub, run 120 (`adc0eec`) | **failure:** 43 failed, 2025 passed, 10 skipped, 17:10 |
| CI runs 116-119 | failure (118 y 117 por `ruff`: `F401` en `scripts/edge1_x0_synthetic.py`, ya corregido en HEAD) |
| CI runs 113-115 | cancelled (concurrencia `cancel-in-progress` por pushes seguidos) |
| `pytest` en este contenedor | ver §6 (en curso al escribir) |

**Causa de los 43 fallos de CI (verificada en el log del run 120):** tests que leen recursos del
equipo del operador y no llevan marcador: `C:/Users/PC/AppData/Roaming/MetaQuotes/...` (`test_ea_registry`,
`test_guardian`), `data/cache/ea/US100_CASH_M5_NY.parquet` (`test_tl3_data`, `test_ea_nq_script`),
`data/discovery.db` (`test_portfolio_lab`, `test_wf_tf_eval`), y otros que devuelven `None` sin datos
(`test_research`, `test_optimize`). **No es una regresión del motor:** es falta de aislamiento de los
tests. Tarea ENG-F2.

## 5. Hallazgos de la Fase 0

| ID | Severidad | Hallazgo |
|---|---|---|
| F0-01 | MEDIUM | `pyproject.toml` declara la extra `discovery = ["numba>=0.60"]` pero `uv.lock` no la incluye: `uv sync --frozen --extra discovery` falla con *Extra `discovery` is not defined*. Numba **no está fijado**: el backend Numba de cada máquina puede tener una versión distinta, y no se puede reproducir |
| F0-02 | MEDIUM | `discovery.__version__` sigue en `0.1.0` y se guarda como `engine_version` en cada campaña (`campaigns.py:458`), aunque ROBUST-1 cambió el retester y el PBO. El campo no distingue versiones del motor; la trazabilidad depende de SHA y tags que no están en el remoto |
| F0-03 | MEDIUM | CI en rojo desde el run 116: 43 tests dependen de ficheros locales del operador (§4) |
| F0-04 | LOW | Los tags de control (`edge1`, `robust-1`, …) no están en `origin`: la condición de arranque de EDGE-2 Y2, WF-TF y MOTOR-FLAT no se puede verificar fuera del equipo del operador |

## 6. Suite local en este contenedor
Pendiente de que termine; se completa en `TASK_STATUS.md` (ENG-F1).
