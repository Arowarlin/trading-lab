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

### Interpretación de la calibración R1

La calibración de R1 (3 finalistas de ruido de 7b + 2 finalistas reales) muestra que **los 3 finalistas de
ruido pasan** noise, delay y execution (ratios 0,77–1,06). Por tanto:

- El Perturbation Lab detecta **fragilidad de ejecución/tiempo** (caso 258: delay +1 = 0,33), **no suerte**.
- La **suerte** solo la detectan **OOS-2 + DSR de confirmación + `test_vs_random_oos2`**.
- La prueba de ruido completa **no debe exigir** que el Perturbation Lab rechace a los finalistas de ruido.
  El criterio es que **ninguno se confirme** (nivel 4).

| Estrategia | Base | Noise mediana / p10 / ratio | Delay +1 | Delay +2 | Exec mediana / p10 / ratio |
|---|---:|---|---:|---:|---|
| 7b 1 año `7f0bf5962f` | 0,0617 | 0,0582 / 0,0208 / 0,944 | 0,0572 / 0,928 | 0,0319 / 0,517 | 0,0548 / 0,0329 / 0,888 |
| 7b 0,9 años `cf187a0037` | 0,2239 | 0,1915 / 0,1536 / 0,855 | 0,2382 / 1,064 | 0,1739 / 0,776 | 0,2157 / 0,1877 / 0,963 |
| 7b 0,9 años `45bb817291` | 0,1122 | 0,0862 / 0,0557 / 0,769 | 0,1018 / 0,907 | 0,0800 / 0,713 | 0,1046 / 0,0842 / 0,933 |
| Real 94 `64af2965` | 0,0376 | 0,0353 / 0,0250 / 0,941 | 0,0190 / 0,507 | 0,0179 / 0,476 | 0,0335 / 0,0238 / 0,891 |
| Real 258 `07093bb0` | 0,0188 | 0,0221 / 0,0149 / 1,172 | 0,0061 / **0,327** | 0,0030 / 0,160 | 0,0155 / 0,0083 / 0,825 |
| EA `us100-ftmo1` | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos |

El EA como control queda **Sin datos** en R1: el parquet diario no tiene OHLC ni operaciones; requiere un
adaptador del motor del EA, fuera de R1.

## Lo que más mejora la calidad del edge encontrado

1. Arreglar el gate de regímenes (sin él, el nivel 4 nunca es alcanzable: el laboratorio no podría
   reconocer un edge real aunque lo encontrara).
2. Pruebas de perturbación antes de gastar OOS-2.
3. Más datos (otros CFD, futuros) para buscar donde el coste relativo es menor.
4. Familias con causa de mercado en vez de más indicadores.
