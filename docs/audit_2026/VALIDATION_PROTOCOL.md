# VALIDATION_PROTOCOL — Código, estrategias, brokers y resultados

## A. Ciclo de vida de una estrategia (no se puede saltar ninguna etapa)

| Etapa | Entra si | Sale (rechazo) si |
|---|---|---|
| RESEARCH | Hipótesis escrita con su fundamento | — |
| CANDIDATE | Pre-registro con hash: universo, reglas, N de variantes, métricas, umbrales y fecha de corte | Cambiar los criterios después de ver los datos invalida la candidata |
| VALIDATION | Costes completos (spread por hora, comisión, slippage y swap). Si falta el modelo de costes, queda **provisional** | DSR v2 < 0,90; PBO > 0,30; walk-forward fallido; menos de 100 operaciones (intradía) o menos de 30 rebalanceos (diario); un único año explica más del 50 % del PnL |
| APPROVED FOR PAPER | Holdout sellado leído **una sola vez** con Sharpe > 0 y expectativa > 0 | Holdout negativo: va al cementerio |
| PAPER INCUBATION | Forward pre-registrado con hash; la cuenta es dedicada si se trata de un candidato a fondeo | Expectativa forward < 0 tras la muestra mínima; un breach |
| FORWARD VALIDATED | Pasa los criterios del forward (por ejemplo, el EA: 40 operaciones, PF ≥ 1,15, +0,10R) | — |
| HUMAN REVIEW | Informe completo y revisión adversarial | El operador decide |
| LIVE | **Desactivado.** Fuera del alcance de cualquier tarea automática | — |

### Umbrales por frecuencia

| Frecuencia | Muestra mínima | Sharpe (en backtest) | PF |
|---|---|---|---|
| Intradía (más de 200 operaciones al año) | 300 operaciones y 2 años | > 1,0 neto | > 1,2 |
| Swing (20-100 operaciones al año) | 100 operaciones | > 0,7 | > 1,3 |
| Diario de cartera | 10 años | > 0,5 | — |

## B. Validación de código (cada tarea de opencode)

1. `uv run ruff check .`
2. `uv run pytest -q`: 0 fallos, y el número de tests no puede bajar.
3. `uv run lab doctor`: sin errores nuevos.
4. `uv run lab f13 config-check`: el hash de F13 no cambia salvo que la tarea lo diga expresamente.
5. Ningún diff toca `.env`, `data/` ni las tareas programadas.
6. Las funciones estadísticas se prueban contra valores publicados (por ejemplo, el ejemplo del DSR con resultado 0,9004).

## C. Validación del bróker

- Reconciliar a diario las posiciones del bróker con el diario del lab.
- Slippage medido (`slippage_probe`) frente al slippage supuesto en el backtest. Si el medido supera 1,5 veces el supuesto, la estrategia vuelve a VALIDATION.
- Coincidencia de entradas forward con el motor de réplica: al menos el 90 %.

## D. Integridad de resultados

- Toda métrica guardada lleva la versión de la función que la calculó (`metric_version`). Con eso, un error como el del DSR se arregla sin borrar la historia.
- Un experimento contaminado se marca `contaminated = 1` y queda excluido de la evidencia confirmatoria, pero se conserva.
