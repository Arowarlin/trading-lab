# COLA-merges · unir R7 y R7b a la rama principal
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN + AGENTS.md. Repo E:\trading-lab, rama feature/prop-fund-multifirm.
Se ejecuta DESPUÉS de COLA-carriles (misma sesión o nueva, nunca a la vez que otra sesión en E:).
PROHIBIDO: campañas, OOS, push, tareas programadas, borrar (ni worktrees ni ramas), umbrales, protegidos, carril del EA, operar, activar bots.

## Tareas
1. Merge --no-ff de `tl2-r7` (tag tl2-r7, commit fff0502): Portfolio Lab. Conflictos previsibles en cli.py, README.md, PLAN.md, .gitignore: conserva todo.
2. Merge --no-ff de `tl2-r7b` (tag tl2-r7b + la corrección de count_tests que COLA-carriles debía hacer en esa rama; si no está, hazla aquí con test: sin DB de discovery → error claro, nunca 0 silencioso).
3. En E:: tests de portfolio_lab y drift (15 + 9 + los nuevos), tests del EA (deben pasar aquí), ruff, pytest -q (una vez), propfund verify (4 OK), count_tests 1730, `lab portfolio analyze --strategies syn-0,syn-90 --account CFD-001 --json` y `lab drift report` funcionan desde E:.
4. `lab doctor`: lista qué 7/17 series están desactualizadas (Frescura FAIL) y si la corrección de frescura de COLA-carriles lo explica; no descargues ni toques datos.
5. Commits "merge: R7 Portfolio Lab" y "merge: R7b deriva demo"; tags tl2-merge-r7 y tl2-merge-r7b. RESULTADO-merges.md con la lista de worktrees/ramas que el operador puede retirar (comandos exactos `git worktree remove ...`, sin ejecutarlos). PARA.
