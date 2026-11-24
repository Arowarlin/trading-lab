# PARALELO · R7b · deriva demo vs backtest de los carriles que YA operan (solo lectura)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN (docs/tradinglab2/10) + AGENTS.md.
Otras sesiones trabajan en E:\trading-lab (C2-informe) y en otros worktrees. TÚ NO TRABAJAS EN E:\trading-lab.

## 0. Worktree
```powershell
cd E:\trading-lab
git worktree add -b tl2-r7b C:\Users\PC\.local\share\opencode\worktree\tl2-r7b HEAD
cd C:\Users\PC\.local\share\opencode\worktree\tl2-r7b
```
Usa E:\trading-lab\.venv con `$env:PYTHONPATH="$PWD\src"`. Para LEER datos reales usa una COPIA de E:\trading-lab\data\lab.db hecha con sqlite3 backup dentro del worktree; NUNCA escribas en E:\trading-lab\data. RESULTADO en E:\trading-lab\.orquestador\RESULTADO-R7b.md.
Si un test falla solo por CRLF, es entorno del worktree: lístalo, no lo arregles.

## Prohibido
Operar, enviar/modificar/cerrar órdenes, activar/desactivar bots, tocar MT5 salvo lectura attach-only (verificar login antes y después; si no está abierto, "Sin datos"), modificar archivos protegidos o del carril del EA/forward/ai_trader (solo leer), campañas, OOS de discovery, push, tareas programadas, borrar, umbrales.

## Objetivo
Medir cuánto se separa la ejecución demo real de lo que el backtest dice para los mismos días, en los carriles que ya están en marcha: EA us100-ftmo1, ftmo_forward (eurusd-london-pullback-forward, usdjpy-tokyo-breakout-forward), incubación us100-trend-d1 y ai_trader (este último solo como registro, no tiene backtest equivalente).

## Tareas
1. Inventario (solo lectura): qué operaciones demo hay registradas por carril (lab.db, logs, historial MT5 si attach-only es posible), desde cuándo, cuántas.
2. Módulo nuevo `src/tradinglab/drift.py` + `lab drift report [--lane X]`: para cada operación demo, la operación que el backtest del MISMO carril habría hecho ese día (misma regla congelada, mismos datos del bróker): señal sí/no, hora de entrada, precio de entrada/salida, slippage real vs asumido, spread pagado vs perfil, resultado en R demo vs backtest. Métricas: % de señales coincidentes, señales perdidas/extra, slippage medio y p95, diferencia de R por operación y acumulada.
3. Si hay pocas operaciones, dilo con números (no extrapoles). Umbrales de alerta SOLO como propuesta en el RESULTADO (no los configures).
4. Tests con datos sintéticos (operación demo vs backtest idénticos → deriva 0; slippage conocido → medido exacto; señal perdida → contada).
5. ruff, tests del módulo, pytest -q (una vez), propfund verify (4 OK). Commit en tl2-r7b "tl2: R7b - deriva demo vs backtest", tag tl2-r7b. NO push, NO merge.
6. RESULTADO-R7b.md con la tabla por carril y lo que significa para confiar (o no) en los costes asumidos del discovery. PARA.
