---
name: backtest-leakage-audit
description: "Auditar un motor o una estrategia de backtest de futuros en busca de lookahead, fugas, same-bar, fills irreales, errores de zona horaria/sesión y de rollover. Usar al revisar código del motor o una entrega de OpenCode que toque simulación."
---

# backtest-leakage-audit

## Propósito
Que ningún resultado salga de un motor con sesgos conocidos sin declararlos.

## Cuándo usarla
Revisión de `fastbt`, del futuro simulador de eventos, de una plantilla nueva o de una entrega de OpenCode.

## Entradas
Rutas del código y la spec de la estrategia.

## Procedimiento
Recorrer la tabla de `docs/futures/00_AUDITORIA_REPO.md §3.1` y marcar cada fila para el cambio:
1. Entrada con datos de la vela de la señal o posteriores.
2. Indicadores/ATR calculados con la vela actual.
3. SL/TP en la misma vela: ¿quién gana?
4. Huecos: ¿al peor precio?
5. Límites: ¿se llenan al tocar? En futuros exigir trade-through ≥ 1 tick o cola (FUT-04).
6. Contratos enteros y redondeo (FUT-05).
7. Sesión CME, festivos (FUT-08) y cambio de horario.
8. Rolls: ¿retornos que cruzan el cambio de contrato?
9. Costes: falta un componente → `MissingCostData`, nunca 0.

## Validación
Por cada sesgo, un test sintético rojo antes del arreglo y verde después.

## Salidas
Informe con fichero:línea, sesgo y si favorece o perjudica.

## Falla si
No se puede reproducir el sesgo con un caso sintético: se marca Hipotético.

## Restricciones
Solo lectura y datos sintéticos; nunca P&L con datos reales.
