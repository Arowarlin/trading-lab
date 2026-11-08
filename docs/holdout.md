# Holdout de una sola lectura

El tramo sellado se evalúa **una vez por configuración**. La configuración se
identifica con `sha256(symbol + strategy + params)`; no se usa para elegir
parámetros ni para calcular el mejor trial.

## Contrato

- Primera lectura: se ejecuta el evaluador, se guarda el resultado en
  `holdout_evaluations` y se registra una lectura en `holdout_reads`.
- Segunda lectura con el mismo hash: **no recalcula**; devuelve el resultado
  guardado, incrementa `reads` y registra otra lectura con `cached=1`.
- Cada lectura (calculada o cacheada) suma una prueba extra al contador que usa
  el DSR (`count_tests` = lecciones + trials Optuna + lecturas de holdout).
- Si el evaluador falla o no hay datos, no se guarda como evaluación válida y
  se puede reintentar.
- `lab optimize` recalcula el DSR después de la lectura para incluir ese trial.
- El desarrollo termina antes del holdout (`dev_end < sealed_start`); el test
  comprueba que todos los `optimization_trials` tienen `period_end` anterior.

## Visibilidad

```powershell
lab lessons holdout
lab lessons weekly          # incluye una línea con lecturas/configuraciones
lab research                # estatua/estadística de holdout en Research
```

El payload de research incluye `holdout.reads`, `holdout.configs`, última
lectura y configuraciones más leídas. No se muestran parámetros secretos; los
params son los del modelo/estrategia.

## Datos

- `holdout_evaluations`: hash, símbolo, estrategia, params, resultado JSON,
  primera/última lectura y contador.
- `holdout_reads`: una fila por lectura, con `cached` 0/1 y fecha.
- `count_tests` incluye `holdout_reads` además de lecciones y trials Optuna.

## Evidencia

`pytest tests/test_learning.py tests/test_optimize.py tests/test_web.py -q` →
29 passed; suite completa 402 passed; `ruff` limpio; `lab doctor` OK.
