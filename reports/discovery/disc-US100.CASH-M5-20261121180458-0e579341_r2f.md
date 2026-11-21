# R2f · Comparación de coste · campaña intraday momentum v2

**Nota: sin ventaja en IS.** Campaña archivada/terminada
`disc-US100.CASH-M5-20261121180458-0e579341` (modo grid, 32 combinaciones,
IS 2021-10-01 → 2024-06-30). Comparación informativa: no se ha escrito en
`disc_*`, no se han registrado trials y no se ha leído OOS-1/OOS-2.

- **Anterior:** CFD-001 con spread p75 global 1,945476 pts + slippage 1,0 pt
  (el coste con el que se ejecutó la campaña).
- **Nuevo:** `worst` entre CFD-001 y CFD-006, spread p75 por **hora local NY**
  desde `broker_spreads` + slippage asumido 1,0 pt (US100), comisión 0.
- El coste nuevo es más bajo en la ventana 15:00-16:00 NY porque el p75
  horario (≈1,42 pts en CFD-001 y ≈1,00 en CFD-006) es menor que el p75
  global que usaba el backtest anterior.

## Mejor y peor celda

| Celda | u | Fin | Entrada | Stop | Ops | Bruto R | Neto anterior | Coste anterior | Neto nuevo (worst) | Coste nuevo | Δ neto | Coste 001 | Coste 006 | Peor cuenta | Pliegues + nuevos |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| Mejor | 0,2 % | 10:30 | 15:00 | 6×ATR | 493 | +0,0071 | **−0,0464** | 0,0523 | **−0,0251** | 0,0309 | **+0,0213** | 0,0309 | 0,0271 | CFD-001 (100 %) | 1/4 |
| Peor | 0,2 % | 10:00 | 15:30 | 4×ATR | 448 | −0,0508 | **−0,1294** | 0,0769 | **−0,0979** | 0,0455 | **+0,0315** | 0,0455 | 0,0396 | CFD-001 (100 %) | 0/4 |

El coste nuevo mejora la neta entre 0,021 y 0,031 R, pero **las dos celdas
siguen negativas**. La mejor sigue siendo la misma celda (u=0,2 %, 10:30,
15:00, 6×ATR) y la peor la misma (u=0,2 %, 10:00, 15:30, 4×ATR). El bruto de
la mejor es +0,0071 R; el de la peor, −0,0508 R: no hay una ventaja bruta
agregada que el coste pueda conservar.

## Spread medido por cuenta y hora

Ventana de la estrategia: 15:00-16:00 NY = 20:00-21:00 UTC en noviembre (EST).
Puntos al cierre del 2026-11-19 20:00 UTC (26.513,83).

| Cuenta | Hora local NY | Días medidos | Ventana de la fila | p75 bps | p75 pts | Horas sin medición |
|---|---:|---:|---|---:|---:|---|
| CFD-001 | 15:00 | **7 días** | 2026-11-12 20:01:12 → 2026-11-19 20:01:11 | 0,5358 | 1,42 | 17:00 (usa el máximo) |
| CFD-006 | 15:00 | **1 día** | 2026-11-19 20:00:00 → 2026-11-19 20:59:59 | 0,3770 | 1,00 | 17:00 (usa el máximo) |

- CFD-001: 7 días de medición; 18.000 ticks en la hora 20 UTC.
- CFD-006: 1 día de medición; 3.600 ticks en la hora 20 UTC. Muestra corta:
  el p75 de CFD-006 es menos fiable que el de CFD-001.
- La hora local 17:00 no tiene medición en ninguna de las dos cuentas; el
  modelo usa el máximo de las horas medidas de esa cuenta.

## Lectura

1. El coste nuevo por hora local es **más barato** que el p75 global anterior
   en la ventana 15:00-16:00 NY; aun así, la mejor celda queda en −0,0251 R
   y la peor en −0,0979 R.
2. CFD-001 es la peor cuenta en las dos celdas (100 % de las operaciones),
   por el slippage asumido de 1,0 pt; CFD-006 ahorra ≈0,004-0,006 R/op.
3. **Sin ventaja en IS**: el bruto positivo de la mejor celda es demasiado
   pequeño (+0,0071 R) y el resto de la rejilla es negativo; el coste no es
   la única causa, pero tampoco hay margen para pagarlo.
