# RESULTADO · COLA-merges — R7 Portfolio Lab y R7b deriva demo

Fecha: 2026-11-23. Sin push, sin borrar worktrees/ramas, sin campañas, sin OOS,
sin tocar tareas programadas, protegidos ni carril del EA.

## 1. Merge R7 · Portfolio Lab

- `git merge --no-ff refs/heads/tl2-r7` · commit **`99b4725`** ·
  tag **`tl2-merge-r7`**.
- Conflicto solo en `PLAN.md` (dos filas nuevas en el mismo punto); resuelto
  conservando **F10a** y **R7**. `cli.py`, `README.md` y `.gitignore` se
  auto-fusionaron conservando todo.
- Incluye `portfolio_lab.py`, `lab portfolio analyze` y
  `tests/test_portfolio_lab.py`.

## 2. Merge R7b · deriva demo

- La corrección de `count_tests` ya estaba en `tl2-r7b`:
  commit `476ef41` · `tl2: R7b - count_tests usa discovery de E`.
- `git merge --no-ff refs/heads/tl2-r7b` · commit **`40bec96`** ·
  tag **`tl2-merge-r7b`**.
- Tag `tl2-r7b` movido a `476ef41` para que incluya la corrección.
- Sin conflictos; se conservaron los comandos de `cli.py`.
- `count_tests` usa `E:\trading-lab\data\discovery.db` (o
  `TRADINGLAB_DISCOVERY_DB`); si falta, `FileNotFoundError`, nunca 0 silencioso.
  Los tests que usaban una discovery temporal inexistente se ajustaron para
  inicializarla (draft/noise/onboarding) y el test de ausencia espera error.

## 3. Comprobaciones

- `tests/test_portfolio_lab.py` + `tests/test_drift_lanes.py`: **24 passed**
  (15 de portfolio + 9 de drift; el resto de la suite cubre los nuevos).
- Tests EA: **53 passed**.
- `pytest -q`: **1745 passed, 1 skipped**.
- `ruff check src/tradinglab tests docs`: limpio.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1730**.
- `lab portfolio analyze --strategies syn-0,syn-90 --account CFD-001 --json`:
  exit 0; 6 series sintéticas, 252 días, matriz de correlación y MC de cartera.
- `lab drift report`: exit 0; `carriles=5 · medidos=3 · registro=1 ·
  sin datos=1 · demo=54 · coinciden=6 · pérdidas=5 · extra=2`.

## 4. `lab doctor` y frescura

`lab doctor` devuelve **0/17 fallan** y **6 avisos** ahora mismo (no 7 FAIL):

| Serie | Última vela | Última descarga | Estado |
|---|---|---|---|
| EURUSD H1 | 2026-11-23 08:00Z | 2026-11-23 08:05Z | aviso (~8,4 h) |
| EURUSD H4 | 2026-11-23 06:00Z | 2026-11-23 08:05Z | aviso (~8,4 h) |
| GBPUSD H1 | 2026-11-23 08:00Z | 2026-11-23 08:05Z | aviso (~8,4 h) |
| GBPUSD H4 | 2026-11-23 06:00Z | 2026-11-23 08:05Z | aviso (~8,4 h) |
| USDJPY H1 | 2026-11-23 08:00Z | 2026-11-23 08:05Z | aviso (~8,4 h) |
| USDJPY H4 | 2026-11-23 06:00Z | 2026-11-23 08:05Z | aviso (~8,4 h) |

El resto (US100 M1/M5/M15/H1/H4, XAUUSD M1/M5/H1/H4, EURUSD M15, USDJPY M15)
está `ok`. Las series FX H1/H4 llevan sin refrescarse desde las 08:05Z; el
doctor las marca aviso, no fallo.

**¿Lo explica la corrección de frescura de COLA-carriles?** No. Esa corrección
hace que el **forward** use la edad de `last_bar_utc` (`use_bar_age=True`) y
separe `mt5:<login>`; el doctor sigue usando la edad de la descarga. Los datos
se refrescaron a las 16:17–16:27Z durante esta sesión, por lo que el 7/17 FAIL
del enunciado no se reproduce ahora. No se descargó ni se tocó ningún dato.

## 5. Worktrees/ramas que el operador puede retirar

Ya fusionados y limpios; **no se ejecutó ningún comando de borrado**.

```powershell
# R7 y R7b (los de esta cola)
git worktree remove C:/Users/PC/.local/share/opencode/worktree/tl2-r7
git worktree remove C:/Users/PC/.local/share/opencode/worktree/tl2-r7b
git branch -d tl2-r7 tl2-r7b

# Ya fusionados antes; opcionales
git worktree remove C:/Users/PC/.local/share/opencode/worktree/tl2-f10a
git worktree remove C:/Users/PC/.local/share/opencode/worktree/tl2-f12
git branch -d tl2-f10a tl2-f12-export
```

No retirar los worktrees de `feature/tl2-r2h` ni `feature/tl2-integration` sin
revisar su estado. El worktree temporal
`C:/Users/PC/AppData/Local/Temp/opencode/worktree-a8743f9` figura `prunable`;
el operador puede limpiarlo con `git worktree prune` si lo decide.

## 6. Commits/tags

```text
40bec96 merge: R7b deriva demo          (tl2-merge-r7b)
99b4725 merge: R7 Portfolio Lab         (tl2-merge-r7)
c8df27d tl2: carriles - max-trades, frescura, horario us100 (autorizado 2026-11-23)
476ef41 tl2: R7b - count_tests usa discovery de E   (tl2-r7b)
fff0502 tl2: R7 - Portfolio Lab                     (tl2-r7)
```

`git status --short`: solo `?? tl2-edge-map.patch`.

PARA.
