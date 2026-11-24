# PARALELO · F12a · exportador MQL5 determinista (solo código, en worktree)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN (docs/tradinglab2/10) + AGENTS.md.
OTRA sesión está trabajando en E:\trading-lab (C1-prep). TÚ NO TRABAJAS EN E:\trading-lab.

## 0. Worktree (obligatorio, antes de nada)
```powershell
cd E:\trading-lab
git worktree add -b tl2-f12-export C:\Users\PC\.local\share\opencode\worktree\tl2-f12 043e979
cd C:\Users\PC\.local\share\opencode\worktree\tl2-f12
```
Trabaja SOLO dentro de ese worktree. Usa el Python de E:\trading-lab\.venv (no crees venv). Para que importe el código del worktree, ejecuta siempre con `$env:PYTHONPATH="$PWD\src"`.
NO toques E:\trading-lab ni .orquestador\SIGUIENTE.md. NO hagas merge a la rama principal.

## Prohibido
Campañas (ni borrador), approve/run/confirm/supersede, OOS, push, tareas programadas, borrar, umbrales, archivos protegidos (propfund verify). NO escribas en carpetas de MT5, NO compiles en el terminal, NO adjuntes nada a MT5, NO abras MT5.
Tests: solo los del módulo nuevo durante el trabajo. Suite completa una sola vez al final (la otra sesión también usa el disco).

## Objetivo
Convertir una estrategia del DSL de discovery (genoma + plantilla + parámetros) en un EA MQL5 (.mq5) de forma DETERMINISTA, para cuando haya una estrategia confirmada. Hoy no hay ninguna: se construye y se prueba con estrategias sintéticas.

## Tareas
1. Módulo nuevo `src/tradinglab/discovery/export_mql5.py` + comando `lab discovery export-mql5 --strategy-id ID | --spec FICHERO --out reports/export/`.
2. Determinismo: misma entrada → bytes idénticos (sin fechas, sin rutas absolutas, orden estable). Cabecera con: hash del genoma, versión de plantilla, versión del exportador, símbolo/TF, cuenta y firma objetivo. Manifest JSON al lado con sha256 del .mq5.
3. Cobertura: cada bloque del DSL (blocks.py) tiene traducción MQL5 o el exportador FALLA con error claro "bloque X no exportable". Nunca exportar aproximaciones en silencio. Tabla bloque → soportado sí/no en el RESULTADO.
4. Reglas: sesión y huso NY como en el backtest (DST incluido), una posición a la vez, stop y objetivo como en fastbt, magic number derivado del hash, riesgo por operación y límites de pérdida diaria/total como PARÁMETROS de entrada (leídos del perfil de la firma, no hardcodeados). NO reutilices ni modifiques código de ftmo_risk ni del EA us100-ftmo1.
5. Paridad lógica: para 3 estrategias sintéticas, genera además una traza de señales en Python (barra, dirección, entrada, stop, objetivo) y deja el .mq5 preparado para emitir la misma traza en el Tester (Print en CSV). Documenta cómo compararlas cuando el operador quiera; no ejecutes el Tester.
6. Tests: determinismo (2 exportaciones → mismo sha256), bloque no soportado → error, golden file de 1 estrategia sintética, magic estable.
7. ruff, pytest -q (una vez), lab propfund verify (4 OK), count_tests 1676 — todo en el worktree. Commit en la rama tl2-f12-export "tl2: F12a - exportador MQL5 determinista", tag tl2-f12a. NO push, NO merge.
8. Escribe E:\trading-lab\.orquestador\RESULTADO-F12a.md (es el único archivo que puedes escribir fuera del worktree) y PARA.
