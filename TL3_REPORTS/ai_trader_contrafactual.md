# TL3 · Contrafactual de `ai_trader` (T5)

Solo lectura sobre una copia de `lab.db` (`mode=ro`). No se tocó
`ai_trader.py`, su configuración ni sus tareas.

## Muestra

48 operaciones cerradas con `result_r` y `shadow_r` (gemela), frente a las 42
de T42. Periodo: 2026-11-13 → 2026-11-25.

| Métrica | IA | Gemela | Diferencia |
|---|---:|---:|---:|
| R medio | +0,0479 | −0,1196 | **+0,1675** |
| sd diferencia | — | — | 1,3379 |
| IC95 bootstrap (10.000, semilla 7) | — | — | **[−0,2090; +0,5411]** |

## Desglose

| Corte | n | Δ R (IA − gemela) |
|---|---:|---:|
| Compra | 13 | −0,4454 |
| Venta | 35 | +0,3952 |
| XAUUSD | 19 | +0,1647 |
| US100.cash | 26 | +0,2331 |
| GBPUSD | 2 | −0,2544 |
| USDJPY | 1 | −0,6384 |

## Benchmarks

- **Regla de tendencia** (lado = signo del cierre 15:55 − apertura 09:30 de la
  sesión anterior): **Sin datos**. Requiere M1 del bróker y una simulación
  intradía que no se ejecutó en este bloque.
- **Siempre tomar el lado del setup**: **Sin datos**. El setup no define un
  lado independiente en todas las operaciones.
- La comparación disponible es solo IA frente a la gemela aleatoria.

## Veredicto

**Sin datos.** La IA no se distingue de su gemela: Δ +0,1675 R con IC95 que
incluye 0 y n=48. No se cumple la regla de `TL3_AI_TRADER_AUDIT.md §5`
(Δ frente a la regla de tendencia ≥ 0,1 R con IC95 > 0), que además no se
pudo calcular. No se cambia nada en `ai_trader`.

## Cumplimiento

Sin órdenes, sin campañas, sin OOS, sin `record-informal`. `count_tests`
sin cambios.
