# Propuesta prerregistrada · ventanas de walk-forward por TF

**Estado:** propuesta para una cola futura. **No aplicada en ROBUST-1.**
**Requiere aprobación humana explícita** antes de tocar `engine.yaml` o el
código del walk-forward. No cambia ninguna puerta: `wf_min_efficiency` sigue
siendo 0,3 y el WF sigue sin pasar si no se alcanza.

## Motivo

Con la matriz ya diaria y ordenada (R2), los 22 finalistas de EDGE-1 muestran
estas operaciones cerradas por ventana de prueba de **20 días hábiles**
(ventanas actuales `train=60` / `test=20`):

| TF | Operaciones por ventana (mediana observada) | Campañas |
|---|---|---:|
| H4 | 0, 2, 3 | 5 |
| H1 | 0, 9 | 4 |
| M30 | 0, 4 | 2 |

Catorce de los 22 finalistas caen en campañas con mediana < 2 y quedan
etiquetados como **“WF no informativo (baja frecuencia)”**. La etiqueta no
aprueba nada: solo explica por qué la eficiencia 0,000 no es una medida útil.

## Ventanas propuestas (preregistro)

| TF | `train` (días hábiles) | `test` (días hábiles) | Pliegues aproximados en 2012-2019 |
|---|---:|---:|---:|
| M5 | 60 | 20 | ~95 |
| M15 | 60 | 20 | ~95 |
| M30 | 120 | 40 | ~46 |
| H1 | 180 | 60 | ~29 |
| H4 | 360 | 120 | ~13 |
| D1 | 504 | 126 | ~11 |

* Se mantiene la proporción train:test = 3:1 y el mínimo de 3 pliegues.
* El objetivo es que la mediana de operaciones por ventana de prueba sea ≥ 10
  antes de volver a mirar la eficiencia; no se usa para relajar la puerta.
* Si un TF no reúne 3 pliegues con su histórico usable, el WF debe seguir
  devolviendo **Sin datos**, nunca un aprobado.
* Esta tabla queda congelada como propuesta. Aplicarla exige una cola nueva,
  un test de conformidad y aprobación del operador; ROBUST-1 no la aplica.
