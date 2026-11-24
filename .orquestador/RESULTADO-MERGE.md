# RESULTADO · MERGE-1 — principal + integración

Fecha: 2026-11-22. Sin campañas, sin OOS, sin push, sin borrar worktree ni ramas.

## Hecho

- Merge de `feature/prop-fund-multifirm` sobre `feature/tl2-integration`.
- Fast-forward de `E:\trading-lab` a `feature/tl2-integration`.
- Verificación completa en E: propfund, pytest, ruff, count_tests, edge-map, data-check y consola.
- Tag `tl2-merge-1`.

## 1. Comprobación previa

- `E:\trading-lab`: solo `?? tl2-edge-map.patch`.
- Worktree `tl2-integration`: limpio, HEAD `7d1d46c`.
- Base común: `8c7ad56`.

## 2. Merge en el worktree

Comando:

```text
git merge --no-ff --no-commit feature/prop-fund-multifirm
```

**No hubo conflictos textuales.** Archivos modificados por el merge:

| Archivo | Resolución |
|---|---|
| `.gitignore` | Ambas ramas añadían `.orquestador/`. Se dejó **una sola** línea, en el bloque final con comentario. |
| `PLAN.md` | Auto-merge. Se conservaron **todas** las filas: R2g, R2g-fix, R2i, R2h, R3 y Fase 8. |
| `src/tradinglab/discovery/data_quality.py` | Auto-merge. Se conservaron densidad de meses, `_calendar_gap` y `D1 = 72`. |
| `tests/test_discovery_data_quality.py` | Auto-merge. Tests de densidad + calendario. |

### Incidencia de fin de línea en el worktree

La primera pasada de `pytest -q` dio **5 fallos** en hashes de EA (`test_ea_forward`,
`test_ea_lab_candidate`, `test_ea_lab_session_equivalence`). Eran diferencias CRLF/LF
entre el worktree y E:. Para probar, se copiaron temporalmente:

- los **57 archivos** de `config/propfund/protected_manifest.json` desde E:;
- `src/tradinglab/nyse_calendar.py`;
- `src/tradinglab/ea_lab/session_engine.py`.

Con esas copias: **1581 passed, 1 skipped**. Después se restauraron todos con
`git checkout -- .` antes del commit; el worktree quedó limpio y el merge no incluye
ninguna copia.

Commit del merge:

```text
1a5049d merge: principal (R2g + R2g-fix) en integración
```

## 3. Fast-forward a la principal

```text
cd E:\trading-lab
git merge --ff-only feature/tl2-integration
Updating cb5417d..1a5049d
Fast-forward
```

## 4. Verificación en E:\trading-lab

| Comprobación | Resultado |
|---|---|
| `lab propfund verify` | **OK** en ai_trader (17), ea_us100_ftmo1 (18), ftmo_forward (8), ftmo_risk (14) |
| `pytest -q` | **1581 passed, 1 skipped** (901,77 s; 1 warning psutil) |
| `ruff check src/tradinglab/discovery tests` | **limpio** |
| `count_tests` | **1676** |
| `lab discovery edge-map --by cuenta` | 3 combos, 4 firmas; export a `reports/discovery/edge_map.{md,json}`; CFD-002 sin conectar |
| `lab discovery data-check US100 --source dukascopy --all-tf` | M1–M30 WARN, H1/H4 FAIL, **D1 WARN (8 huecos)** |

### D1 de US100: WARN, no OK

`data-check` completo da **WARN** (no OK) por 8 huecos de **2013–2020**:

```text
2013-10-11, 2016-03-24, 2016-12-23, 2016-12-30,
2017-04-13, 2018-03-29, 2019-04-18, 2020-04-09
```

Son festivos NYSE (Good Friday, Navidad/Año Nuevo observados) **fuera de la
cobertura 2021–2027** de `nyse_calendar`. No se extiende el calendario porque
SIGUIENTE lo deja para la fase siguiente. En la ventana real de campaña
**2021-09 → 2026-11-20, D1 de US100 es OK con 0 huecos**.

H1/H4 de índices siguen FAIL por el truncamiento de Dukascopy los viernes antes
de las 17:00 NY, también pendiente de la fase de calendarios por instrumento.

## 5. Consola

- `Get-NetTCPConnection -LocalPort 8421`: **libre**; no hubo que usar otro puerto.
- `lab web --port 8421 --no-open --no-external` desde E:.
- `/api/health`: **200**.
- `/api/discovery/summary`: **200** (18.567 bytes).
- `/api/discovery/edge-map`: **200** (8.012 bytes; la primera petición tardó más de
  lo normal porque calcula el mapa, pero respondió).
- `/`: **200** y contiene `Discovery Lab`.
- Servidor detenido; solo se pararon los procesos arrancados por esta sesión.
  Puerto 8421 libre después.

## 6. Git

`git status --short`:

```text
?? tl2-edge-map.patch
```

`git log --oneline -5`:

```text
1a5049d merge: principal (R2g + R2g-fix) en integración
cb5417d tl2: R2g - huecos de fin de semana por calendario
1886c20 orquestador: protocolo de relevo por archivos
f9666ef tl2: R2g - revertir umbral D1
e85b75f tl2: R2g - cierre e historia completa
```

Tags:

```text
tl2-merge-1 -> 1a5049d
tl2-r2g-fix -> cb5417d
tl2-r2g     -> f9666ef (no se ha movido)
```

## 7. Comandos para el operador

Push de la rama principal y de los tags de esta fase:

```powershell
cd E:\trading-lab
git push origin feature/prop-fund-multifirm
git push origin tl2-r2g-fix
git push origin tl2-merge-1
```

No empujar `tl2-r2g`: en GitHub apunta a otro commit.

Retirar el worktree cuando el operador lo decida:

```powershell
cd E:\trading-lab
git worktree remove C:\Users\PC\.local\share\opencode\worktree\tl2-integration
```

El worktree está limpio; si Git pidiera `--force`, revisar antes que no haya
cambios locales.

## Aviso

- D1 de US100 en historia completa queda WARN, no OK, por los 8 festivos NYSE
  2013–2020 fuera de cobertura. La ventana 2021-09→2026-11 sí es OK.
- H1/H4 de índices siguen FAIL por el cierre real de Dukascopy a las 16:15 NY,
  pendiente de la fase de calendarios por instrumento.
- No se ejecutaron campañas ni se leyó OOS-1/OOS-2. No se hizo push. No se borró
  el worktree ni ninguna rama.

## Siguiente

PARA. El operador decide push y retirada del worktree.
