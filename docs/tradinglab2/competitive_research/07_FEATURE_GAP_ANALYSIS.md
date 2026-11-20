# 07 · Brechas y oportunidades

Principio rector: **buscamos edge, no estrategias sobreoptimizadas**. Una función solo entra si (a) ayuda a
refutar estrategias falsas, (b) amplía el espacio de búsqueda con hipótesis que tienen causa de mercado,
o (c) ahorra tiempo sin abrir una vía de fuga. Nada puede leer OOS-2 fuera de `confirm`.

## Matriz de brechas

| Funcionalidad externa | Origen | Estado TL | Diferencia técnica | Prioridad |
|---|---|---|---|---|
| Gate de regímenes con años disponibles | (bug propio) | 2 · con bug | `REQUIRED_REGIMES=(2018,2020,2022)` fijo en `walkforward.py` | **P0** |
| Simetría long/short | Práctica común | 4 | Cortos absurdos | **P0** |
| Reintento de hijos inválidos/duplicados | Adaptrade (calidad por generación) | 4 | 45 % del presupuesto perdido | **P0** |
| Noise Test (OHLC perturbados) | Build Alpha / EA Studio | 4 | Solo MC de orden de operaciones | **P1** |
| Entradas/salidas retrasadas | Build Alpha | 4 | — | **P1** |
| MC de ejecución (skip, spread y slippage aleatorios) | EA Studio | 4 | — | **P1** |
| Datos M5 de los demás CFD | — | 2 | Solo US100/US500 | **P1** |
| Colecciones, etiquetas, familias, clones entre campañas | FSB Pro / EA Studio | 3 | Solo por campaña | **P1** |
| Perfil de criterios de aceptación con nombre y hash | FSB Pro / EA Studio | 2 | Umbrales repartidos | P1 |
| Consola: evolución, databank, detalle, presupuesto | Todas | 4 | Sin rutas | P1 (Fase 8) |
| Multi-mercado "pasa en k de n" pre-registrado | EA Studio / Build Alpha | 2 | `transfer` informativo | P2 |
| Bloqueo de partes de plantilla | Adaptrade | 4 | — | P2 |
| Nuevas familias con causa (sweeps, rangos de sesión, calendario, eventos) | — | 2 | Faltan bloques | P2 |
| Prueba de significancia del proceso (Reality Check / SPA) | Adaptrade (concepto) | 3 | DSR con N efectivo | P2 (investigar) |
| Cartera y correlación de estrategias de discovery | Build Alpha | 3 | `portfolio.py` legado | P2 (Fase 11) |
| Contraste del simulador de challenge con uno externo abierto | (LuxAlgo prop-firm-sim, open source) | 3 | Nuestro MC no validado externamente | P2 |
| Exportación MQL5 con paridad de señales | EA Studio / todas | 4 | — | P2 (Fase 12) |
| Agentes IA que proponen AST | — | 4 | — | P2 (Fase 9) |
| Editor visual | Todas | 4 | — | P3 |
| MCP de solo lectura sobre el databank | Build Alpha (no verificado) | 4 | — | P3 |
| Futuros (Databento) | — | 4 | Sin datos | P2 |
| Red neuronal como condición | Adaptrade | — | — | **DESCARTAR** |
| Reconstruir/resetear guiado por OOS | Adaptrade (opción), práctica de usuarios | — | — | **DESCARTAR** |
| Criterios de aceptación copiados de una estrategia que gustó | EA Studio (guía) | — | — | **DESCARTAR** |
| Randomized OOS para seleccionar | Build Alpha | — | Consumiría el OOS | **DESCARTAR** (solo dentro de IS) |
| Equity curve trading | Build Alpha | — | Lógica adaptativa en vivo | **DESCARTAR** por ahora |
| Optimizer que cambia parámetros sin campaña nueva | FSB Pro / EA Studio | — | — | **DESCARTAR** |

## Análisis de las pruebas de robustez nuevas

Todas son **pruebas de falsificación relativas a la propia estrategia**: comparan la estrategia con versiones
perturbadas de sí misma. No eligen entre candidatas, **no son hipótesis nuevas y no suman al DSR**.
Se ejecutan sobre IS+OOS-1 (nunca OOS-2).

| Prueba | Hipótesis que contrasta | Cálculo | Sesgos / cuándo engaña | Anti-leakage |
|---|---|---|---|---|
| Noise Test | El edge no depende de los valores exactos de cada vela | 500–1.000 copias de los OHLC con ruido proporcional al ATR local (manteniendo O≤H, L≤O/C, coherencia), re-ejecutar; mediana y p10 de expectativa vs base | Ruido demasiado grande destruye cualquier señal; calibrar con estrategias de control (ruido sintético) | Semilla fija; solo IS+OOS-1 |
| Entradas retrasadas (+1, +2 barras) | El edge no depende de la vela exacta de entrada | Mismas señales desplazadas; salidas iguales | En M5 un retraso de 1 vela ya es severo en rupturas: interpretar como degradación relativa | — |
| Salidas retrasadas (+1, +2) | Ídem salida | — | — | — |
| MC de ejecución | Resiste fallos reales | Saltar 5–10 % de operaciones al azar; spread por operación muestreado del histograma horario medido; slippage aleatorio | Requiere distribución real de spread (la tenemos por hora) | — |
| "k de n" mercados | Hay causa común | Mercados relacionados declarados antes (US100→US500, NQ; XAU→GC) | Mercados muy correlacionados no son independientes | Lista fija en la campaña; informe, no selección |

Umbral propuesto (por defecto, en `engine.yaml`, **fijado antes de ver resultados**): mediana de expectativa
perturbada ≥ 50 % de la base y > 0. Pasa a ser requisito del **nivel 3** (falsificación barata antes de
gastar la lectura OOS-2).

## Lo que más mejora la calidad del edge encontrado

1. Arreglar el gate de regímenes (sin él, el nivel 4 nunca es alcanzable: el laboratorio no podría
   reconocer un edge real aunque lo encontrara).
2. Pruebas de perturbación antes de gastar OOS-2.
3. Más datos (otros CFD, futuros) para buscar donde el coste relativo es menor.
4. Familias con causa de mercado en vez de más indicadores.
