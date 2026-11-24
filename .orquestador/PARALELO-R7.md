# PARALELO · R7 · Portfolio Lab (infraestructura con datos sintéticos y carriles existentes)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN (docs/tradinglab2/10) + AGENTS.md.
Otras sesiones trabajan en E:\trading-lab (C2-informe) y en otros worktrees. TÚ NO TRABAJAS EN E:\trading-lab.

## 0. Worktree
```powershell
cd E:\trading-lab
git worktree add -b tl2-r7 C:\Users\PC\.local\share\opencode\worktree\tl2-r7 HEAD
cd C:\Users\PC\.local\share\opencode\worktree\tl2-r7
```
Usa E:\trading-lab\.venv con `$env:PYTHONPATH="$PWD\src"`. Datos reales solo desde COPIAS (sqlite3 backup) dentro del worktree. RESULTADO en E:\trading-lab\.orquestador\RESULTADO-R7.md.
Si un test falla solo por CRLF, es entorno del worktree: lístalo, no lo arregles.

## Prohibido
Campañas, approve/run/confirm/supersede, leer OOS-2 de discovery, push, tareas programadas, borrar, umbrales, MODIFICAR archivos protegidos (prop/overlay, simulator, guard: se pueden LLAMAR, no cambiar), carril del EA, operar.

## Objetivo
Cuando haya 2+ estrategias confirmadas, saber si juntas mejoran la probabilidad de pasar el reto de cada empresa sin romper sus reglas.

## Tareas
1. Módulo `src/tradinglab/portfolio_lab.py` + `lab portfolio analyze --strategies A,B,... --account CFD-001`:
   - Entradas: series de operaciones (R y fecha/hora) de estrategias de discovery (solo IS/OOS-1 ya leídos, nunca OOS-2), de carriles forward (backtest congelado) o sintéticas.
   - Correlación de retornos diarios y de pérdidas simultáneas; solape temporal de posiciones; exposición por símbolo.
   - Reparto de riesgo por estrategia (igual, inverso a volatilidad, y con tope por regla de firma como "riesgo por idea" de FundingPips) — máx. 3 métodos, sin optimizar pesos sobre los datos.
   - Por cuenta (CFD-001, CFD-006): MC prop con las reglas de la firma (llamando al simulador existente), P(pasar fase 1), P(romper diario), P(romper máximo), días medianos a objetivo; individual vs cartera.
2. Prueba con: 3 estrategias sintéticas (correlación conocida 0, 0.5, 0.9) y con los backtests congelados de los 2 forward de FTMO + us100-trend-d1 (lectura). Muestra si la cartera mejora o empeora frente a cada una sola.
3. Tests: correlación conocida medida bien; con correlación 0.9 la cartera NO debe reducir el riesgo; reglas de firma respetadas.
4. ruff, tests del módulo, pytest -q (una vez), propfund verify (4 OK). Commit en tl2-r7 "tl2: R7 - Portfolio Lab", tag tl2-r7. NO push, NO merge.
5. RESULTADO-R7.md y PARA.
