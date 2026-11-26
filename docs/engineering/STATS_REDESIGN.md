# STATS_REDESIGN · Propuesta ENG-S1 (diseño; no aplicado)

**Estado:** propuesta. Cambiar las puertas o su metodología requiere la aprobación del operador y un
prerregistro, y se aplica **después** del tag `edge2`. Ningún umbral baja. El objetivo es que cada
puerta mida lo que dice medir: menos falsos positivos **y** más potencia frente a ventajas reales.

## 1. Qué falla hoy y qué se propone

| Puerta | Fallo (AUDIT_FINDINGS) | Propuesta | Coste |
|---|---|---|---|
| WF (puerta 2) | D-01: corre sobre el IS que ya usó el GA para elegir | **WF anidado:** en cada pliegue se re-elige el mejor de una muestra fija de la población usando solo el tramo de entrenamiento, y se mide en el de prueba. Si es caro: WF solo sobre OOS-1 (fuera de la selección), declarado | Guardar la serie diaria de una muestra de la población (no solo del frontier) |
| PBO (puerta 2) | D-02: se calcula sobre el frontier y depende de su composición | CSCV sobre una **muestra aleatoria fija** (p. ej. 200, semilla = campaña) de las estrategias **evaluadas** por el GA, con la serie de días hábiles con ceros (R2) | Lo mismo que arriba |
| Potencia | D-06: suma OOS-1 + OOS-2 aunque `confirm` solo usa OOS-2 | Potencia con las operaciones esperadas **solo en OOS-2** | Ninguno |
| Selección de finalistas | E-02: sin n mínimo en OOS-1 (finalistas con 1 operación) | n mínimo en OOS-1 derivado de la potencia (no un número arbitrario) | Ninguno |
| `mc_trades` | D-05: equivale a "expectativa > 0" | Se elimina como puerta (queda como informe) o se sustituye por un bootstrap por bloques de la serie diaria | Ninguno |
| SPA (`family`) | D-04: Reality Check sin studentizar, bloque ≈ 1, alineado por posición | SPA de Hansen studentizado (`arch.bootstrap.SPA`, ya en dependencias, falta en el lock: F0-05), series alineadas por fecha y bloque por autocorrelación | `uv lock` (ENG-F3) |
| Sharpe | D-07: solo días con operación | Serie de días hábiles con ceros en todas las métricas | Cambia las cifras históricas: versión nueva de métricas (`metric_version`) |
| DSR de `confirm` | D-03: con k = 1 no deflacta; V[SR] de ≤ 5 finalistas; N por campaña | V[SR] de la muestra de la población; N = `count_tests` global; y **Holm** (o Romano-Wolf) sobre **todas** las lecturas del mismo tramo OOS-2 | Registro de lecturas del OOS-2 (ya existe `disc_holdout_reads`) |
| GA | E-01: `mutate_session` fijo a 09:30-15:00 | Límites de mutación = límites de la sesión de la plantilla | Ninguno |

## 2. Cómo se comprueba que el rediseño es mejor (antes de aplicarlo)

Un banco sintético (`docs/engineering/tools/`, sin datos ni contador). Se basa en las simulaciones
`s2`, `s5` y `s8` de D:

1. **Nulo:** 500 estrategias de ruido por campaña, GA simulado con selección top-k, 1.000 réplicas.
   Se mide la tasa de "pasa las 4 puertas" (falsos positivos), hoy y con el rediseño.
2. **Alternativa:** lo mismo con 5 estrategias con ventaja real de 0,1, 0,2 y 0,3 R. Se mide la
   potencia.
3. **Criterio de aceptación (prerregistrado):** falsos positivos por campaña ≤ 5 % y potencia mayor
   que la actual para 0,2 R. Si el rediseño no mejora las dos cosas, no se aplica.

## 3. Qué pasa con los resultados guardados
- Nada se borra. Las métricas nuevas van en columnas o JSON nuevos (`metric_version` v3).
- EDGE-1 y EDGE-2 se pueden **recalcular** con el rediseño sin sumar al contador, como hizo
  ROBUST-1, porque solo cambia cómo se juzga lo ya evaluado. Excepción: el WF anidado y el PBO sobre
  la población necesitan las series de la muestra, que hoy no se guardan; para eso habría que
  re-evaluar la muestra (**no** suma: son las mismas estrategias ya contadas). Hay que confirmarlo
  con el operador.

## 4. Resultados del banco sintético S2 (2026-11-26)

`docs/engineering/tools/s2_gate_bench.py`, 200 campañas por escenario, semilla 2026. JSON en
`docs/engineering/BENCH/`. Probabilidad de que **al menos un finalista pase todas las puertas** (con
ventaja: y que sea uno de los que la tienen de verdad; en todas las filas coincide).

| Escenario | p = 0,10 (~25 ops/año) actual | propuesta | propuesta m=100 | p = 0,40 (~100 ops/año) actual | propuesta | propuesta m=100 |
|---|---:|---:|---:|---:|---:|---:|
| Ruido (falsos positivos) | 0,0 % | 0,5 % | 0,0 % | 0,0 % | 0,0 % | 0,0 % |
| Ventaja neta 0,1 R | 0,0 % | 0,5 %* | 0,0 % | 1,5 % | 4,5 % | 1,0 % |
| Ventaja neta 0,2 R | 0,5 % | 11,0 % | 5,0 % | 18,0 % | 55,5 % | 55,5 % |
| Ventaja neta 0,3 R | 6,5 % | 48,5 % | 39,0 % | 63,0 % | 92,0 % | 92,0 % |

\* El 0,5 % de 0,1 R es un falso positivo (pasa una estrategia sin ventaja).

**Lectura:**
1. **Las puertas actuales casi nunca dejan pasar una ventaja real** con la frecuencia de EDGE-1:
   6,5 % con 0,3 R, 0,5 % con 0,2 R. El cuello de botella es el WF 60/20, con unas 2 operaciones por
   ventana de prueba. Esto explica "0 robustas" sin necesidad de que no haya ventaja.
2. **La propuesta multiplica la potencia por 3 a 20 sin subir los falsos positivos** (≤ 0,5 %).
3. **La frecuencia pesa más que cualquier puerta.** Con 4 veces más operaciones, 0,2 R pasa del
   11 % al 55 %.
4. **Una ventaja de 0,1 R no se puede confirmar en una sola campaña** con 3 años de OOS-2, a ninguna de
   las dos frecuencias. Hacen falta cestas (varios activos con la misma regla) o más tiempo de forward.
5. **Corrección de la propuesta original:** el DSR con N = 440 en el OOS-2 deflactaba de más (potencia
   ~0 incluso con 0,3 R). Los finalistas se eligen antes de ver el OOS-2: se corrige por cuántos se leen
   ahí (Bonferroni/Holm, `m`), no por la población.

**Supuestos y límites del banco** (no medidos con datos reales):
- Estrategias independientes, sin correlación entre ellas.
- R normal con σ = 1 y coste de 0,05 R por operación.
- "GA" modelado como top-40 por IS.
- No incluye las puertas 1 y 3 ni el baseline aleatorio de `confirm`.
- Ventanas WF de la propuesta: 504/126 con p = 0,10 y 252/63 con p = 0,40.
