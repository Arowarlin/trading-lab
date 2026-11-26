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
