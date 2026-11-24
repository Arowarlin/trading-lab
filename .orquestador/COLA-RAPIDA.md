# COLA-RAPIDA · preparar las hipótesis 2, 3 y 4 del PLAN-BUSQUEDA seguidas (tras R9c)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN (docs/tradinglab2/10) + AGENTS.md. Misma sesión que R9c, DESPUÉS de cerrar R9c (si R9c falló, NO empieces). Repo E:\trading-lab.
Ejecuta Q1 → Q2 → Q3 seguidas. Antes de pasar a la siguiente: tests del módulo + su sección en RESULTADO-cola-rapida.md + commit/tag. Si algo falla o exige decisión: escríbelo y PARA TODO.
PROHIBIDO: register/approve/run/confirm/supersede (los hace el operador), OOS, calcular rendimiento de NADA no aprobado (el guard de R9b; no lo desactives fuera de tests sintéticos), push, tareas programadas, borrar, umbrales, protegidos, carril del EA, operar, descargar. Solo preflight/feasibility (operaciones, pliegues, coste incl. swap). pytest -q completo SOLO una vez al final de toda la cola.
Lee .orquestador/PLAN-BUSQUEDA.md y .orquestador/HIPOTESIS-4-10.md (secciones fix de Londres y reversión tras caídas) antes de empezar.

## Q1 · Hipótesis 4: rebote tras ventas fuertes (sin código nuevo)
- Specs `.orquestador/specs/q1-rebote-us500-d1.yaml` y `q1-rebote-us100-d1.yaml` con `d1_extension_reversion` SOLO lado largo tras caída (si la plantilla no permite fijar el lado sin tocar código, PARA esta tarea y dilo). Hipótesis literal (Boyarchenko, Larsen & Whelan 2023: reversión asimétrica tras ventas fuertes), máx. 27 combinaciones en total por spec, valores razonados en el YAML, IS desde usable_from D1 hasta 2024-06-30, Dukascopy.
- preflight/feasibility en seco; pega operaciones IS y cost_R (con swap). Commit "tl2: Q1 - specs rebote", tag tl2-q1.

## Q2 · Hipótesis 2: reversión alrededor de los fix de divisas
- Plantilla `fix_reversal` (H1) con hipótesis literal y cita (Krohn, Mueller & Whelan, Journal of Finance 2024): el dólar se aprecia antes de los fix y revierte después. Regla: entrar CONTRA el dólar al cierre de la barra del fix y salir tras M horas. Fix de Tokio 09:55 JST (= 00:55 UTC, Japón sin DST) para USDJPY; fix de Londres 16:00 hora de Londres (DST de Londres, distinto del de NY) para EURUSD y GBPUSD. symmetric: false (dirección fija por hipótesis). Parámetros máx. 2: M ∈ {1,2,3} horas, stop ∈ {2.5, 3.0} ×ATR (≥ 2,5 por coste según HIPOTESIS-4-10). Tests: horas exactas del fix en invierno/verano en ambas zonas, semanas de desfase DST Londres/NY, sin anticipación.
- Specs q2-fix-usdjpy-h1.yaml, q2-fix-eurusd-h1.yaml, q2-fix-gbpusd-h1.yaml (Dukascopy, IS dentro de usable_from H1 hasta 2024-06-30). preflight/feasibility. Commit "tl2: Q2 - plantilla fix_reversal", tag tl2-q2.

## Q3 · Hipótesis 3: momentum de serie temporal en cesta (excepción mínima)
- Implementa lo mínimo de .orquestador/PROPUESTA-multisimbolo.md: una campaña con varios símbolos y UNA hipótesis; n_total = combinaciones (no × símbolos); R agregado por fecha; coste y swap por símbolo y cuenta; control de deriva por cesta (entradas aleatorias con la misma mezcla de lados por símbolo); pliegues globales. Tests sintéticos (cesta de 2-3 símbolos con ventaja conocida y sin ventaja).
- Spec q3-tsmom-cesta-d1.yaml con ts_momentum_d1 en XAUUSD, US500, US100, EURUSD, GBPUSD, USDJPY (Dukascopy; IS común dentro de usable_from de todos hasta 2024-06-30), máx. 18 combinaciones, hipótesis literal (Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi & Pedersen 2017). preflight/feasibility. Commit "tl2: Q3 - campañas multi-símbolo", tag tl2-q3.

## Cierre
ruff, pytest -q (una vez), propfund verify (4 OK), count_tests (el que haya). En RESULTADO-cola-rapida.md: tabla de TODAS las specs listas (id, n_total, operaciones IS, cost_R) y el bloque PowerShell con register/approve/run/results de cada una para el operador, en este orden: q1 (2), q2 (3), q3 (1). PARA.
