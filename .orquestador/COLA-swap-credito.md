# COLA-swap-credito · no contar créditos de swap en discovery (decisión de diseño)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN + AGENTS.md. Misma sesión, DESPUÉS de cerrar COLA-RAPIDA. Repo E:\trading-lab.
PROHIBIDO: register/approve/run/confirm/supersede, OOS, calcular rendimiento de nada no aprobado, push, tareas programadas, borrar, umbrales, protegidos (si costs.py o swap.yaml fueran protegidos: PARA y pregunta), carril del EA, operar.

## Contexto (verificado por el operador en MT5 FTMO-Demo, 2026-11-23)
US100.cash: swap en puntos, long +1076.28, short -1677.49, contract size 1, triple viernes. US500.cash: long +32.83, short -198.56. Son los valores REALES del servidor, no un error de lectura: con US100 ~26.700 USD/lote eso es un crédito de ~10,8 USD/noche (~15 %/año) por estar largo.
Problema: el swap medido HOY se aplica a todo el histórico 2010-2024 (tipos de interés muy distintos) y, con cost_mode best, el crédito de FTMO convierte cualquier estrategia larga en índices en "ganadora" por financiación, no por mercado. Eso contamina la detección de ventaja.

## Tarea
1. En discovery (fitness, selección, control de deriva, feasibility/cost_R): el swap solo puede ser COSTE. Un swap positivo (crédito) cuenta como 0. Se mantiene el swap negativo. Implementa un flag de configuración `discovery.swap_credit: false` (por defecto false) en engine.yaml; documenta por qué.
2. La capa de empresa / onboarding / informes puede seguir MOSTRANDO el crédito real de cada cuenta como información aparte ("crédito de swap no contado en discovery: X R/noche"), sin usarlo para seleccionar.
3. Tests: estrategia larga US100 con perfil FTMO → swap aplicado 0 (no negativo, no positivo); perfil CFD-006 → coste negativo aplicado; corto US100 FTMO → coste aplicado.
4. Recalcula SOLO coste (feasibility, permitido) de r9-tom-us500-d1, r9-tom-us100-d1, q1-rebote-us500-d1, q1-rebote-us100-d1 y pega cost_R antes/después. Nada de rendimiento.
5. ruff, pytest -q (una vez), propfund verify (4 OK), count_tests (el que haya). Commit "tl2: swap - créditos no cuentan en discovery", tag tl2-swap-credito. RESULTADO-swap-credito.md y PARA.
