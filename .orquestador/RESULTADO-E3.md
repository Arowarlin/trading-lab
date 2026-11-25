# RESULTADO E3 · P(pasar) con la ventaja contraída

- **Fecha:** 2026-11-24
- **Commit:** `tl2: E3 - P(pasar) con ventaja contraida`
- **Tag:** `tl2-e3`
- **Informe:** `reports/ea/us100-ftmo1-reto-contraido.md`

## Método

Serie de 478 operaciones de T41; a cada una se le resta una constante `c`
para fijar la expectativa:

| Escenario | Objetivo | `c` |
|---|---:|---:|
| Backtest | 0,3104 R | 0,0000 |
| Mitad | 0,1552 R | 0,1552 |
| LCB95 | 0,1682 R | 0,1422 |

Riesgo 0,35-0,80 % en pasos de 0,05 %, 5.000 caminos, 60 días, reglas FTMO
challenge 100k.

## Resumen

| Escenario | Mejor riesgo con P(romper) ≤ 5 % | P(pasar) al 0,35 % |
|---|---|---|
| Backtest | **0,70 %** → 73,62 % · 4,94 % · 27 d | 35,62 % · 0,12 % · 42 d |
| Mitad | **0,45 %** → 30,06 % · 3,58 % · 38 d | 17,48 % · 0,94 % · 43 d |
| LCB95 | **0,45 %** → 31,70 % · 3,32 % · 38 d | 18,70 % · 0,80 % · 43 d |

Celdas: P(pasar) · P(romper) · días medianos.

## Lectura

La ventaja contraída reduce la P(pasar) óptima de ~74 % a ~30-32 % y baja el
riesgo óptimo de 0,70 % a 0,45 %. Al 0,35 % actual, la P(pasar) cae de 35,6 %
a 17,5-18,7 %. La diferencia con la tabla de T41 es de muestreo del simulador
(5.000 caminos, semilla 42); la conclusión cualitativa no cambia.

## Cumplimiento

Solo lectura. Sin campañas, OOS, `confirm` ni `record-informal`; sin órdenes;
EA/setfile sin cambios. `count_tests` = 1894.
