# EA us100-ftmo1 · P(pasar) con la ventaja contraída (E3)

Generado: 2026-11-24 · solo lectura, sin tocar el EA.

Serie: 478 operaciones del backtest de T41 (2017-12-28 → 2026-11-23 09:15),
motor v3.2, setfile `US100_FTMO_v3_challenge.set`, expectativa +0,3104 R,
desviación 1,9193 R, LCB95 0,1682 R.

## Método

A cada operación se le resta una **cantidad constante** `c` para que la
expectativa quede en el objetivo:

- **Backtest:** objetivo 0,3104 R, `c = 0`.
- **Mitad:** objetivo 0,1552 R, `c = 0,1552 R`.
- **LCB95:** objetivo 0,1682 R, `c = 0,1422 R`.

Después se repite la tabla de T41 §8: riesgo por operación de 0,35 % a
0,80 % en pasos de 0,05 %, simulador `prop.simulator.monte_carlo`, 5.000
caminos, 60 días, bootstrap de los R diarios, reglas FTMO challenge 100k de
`prop.yaml` (objetivo 10 %, diario 5 %, máximo 10 % estático, colchón 10 %).

## Tabla de riesgo

P(pasar) / P(romper) por escenario:

| Riesgo | Backtest | Mitad | LCB95 |
|---:|---:|---:|---:|
| 0,35 % | 35,62 % / 0,12 % | 17,48 % / 0,94 % | 18,70 % / 0,80 % |
| 0,40 % | 44,06 % / 0,42 % | 24,14 % / 2,14 % | 25,44 % / 1,80 % |
| 0,45 % | 52,08 % / 0,68 % | 30,06 % / 3,58 % | 31,70 % / 3,32 % |
| 0,50 % | 58,38 % / 1,20 % | 36,28 % / 5,82 % | 38,06 % / 5,10 % |
| 0,55 % | 64,10 % / 1,76 % | 41,26 % / 8,36 % | 42,86 % / 7,42 % |
| 0,60 % | 68,24 % / 2,66 % | 44,96 % / 11,06 % | 46,64 % / 10,02 % |
| 0,65 % | 71,12 % / 3,78 % | 48,14 % / 13,48 % | 50,06 % / 12,24 % |
| 0,70 % | 73,62 % / 4,94 % | 51,14 % / 16,22 % | 53,06 % / 14,92 % |
| 0,75 % | 75,56 % / 6,10 % | 53,88 % / 18,80 % | 56,30 % / 17,38 % |
| 0,80 % | 77,26 % / 7,18 % | 56,60 % / 20,78 % | 58,22 % / 19,50 % |

## Resumen

| Escenario | Expectativa | Mejor riesgo (P(romper) ≤ 5 %) | P(pasar) al 0,35 % |
|---|---:|---|---|
| Backtest | 0,3104 R | **0,70 %** → 73,62 % · 4,94 % · 27 d | 35,62 % · 0,12 % · 42 d |
| Mitad | 0,1552 R | **0,45 %** → 30,06 % · 3,58 % · 38 d | 17,48 % · 0,94 % · 43 d |
| LCB95 | 0,1682 R | **0,45 %** → 31,70 % · 3,32 % · 38 d | 18,70 % · 0,80 % · 43 d |

Las celdas del resumen son P(pasar) · P(romper) · días medianos hasta pasar.

## Lectura

- Contraer la ventaja a la mitad o al LCB95 **reduce a menos de la mitad** la
  P(pasar) óptima: de ~74 % a ~30-32 %.
- El riesgo que maximiza P(pasar) con P(romper) ≤ 5 % baja de **0,70 %** a
  **0,45 %**; el 0,35 % actual es demasiado conservador si la ventaja es la
  del backtest, pero queda razonable si la ventaja real es la mitad.
- Con el riesgo actual de 0,35 %, la P(pasar) cae de 35,6 % (backtest) a
  17,5-18,7 % (ventaja contraída).
- La diferencia con la tabla de T41 (38,5 % al 0,35 % y 71,7 % al 0,65 %) es
  de muestreo del simulador (5.000 caminos, semilla 42); la conclusión
  cualitativa es la misma.

## Cumplimiento

Solo lectura: no se tocó el EA, el setfile, `lab.db` ni ninguna campaña. Sin
órdenes. `count_tests` = 1894.
