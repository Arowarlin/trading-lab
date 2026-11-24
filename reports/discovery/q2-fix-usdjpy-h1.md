# Informe · `q2-fix-usdjpy-h1`

Fecha: 2026-11-24. Campaña `done`, 6 combinaciones, 0 finalistas.
IS 2010-01-01 → 2024-06-30 · H1 · USDJPY · Dukascopy · coste `best` CFD-001/CFD-006.
Solo IS; OOS-1 no se abrió (no hubo candidatos) y OOS-2 sigue sellado.

## Veredicto

**Edge bruto que el coste elimina.** El bruto es indistinguible de cero
(mediana −0,0018 R; máximo +0,0060 R) y el coste de 0,041–0,060 R lo borra:
ninguna combinación queda con neto positivo ni pasa el control de deriva.

## Bruto vs coste vs neto (R por operación)

| Rejilla (6 combinaciones) | Bruto | Coste CFD-001 | Coste CFD-006 | Neto |
|---|---:|---:|---:|---:|
| Mediana | −0,0018 | 0,0498 | 0,0410 | −0,0476 |
| Mejor combinación (hold 180 h, stop 3,0) | 0,0052 | 0,0481 | 0,0410 | −0,0396 |
| Peor combinación (hold 60 h, stop 2,5) | −0,0016 | 0,0597 | 0,0492 | −0,0557 |

- Operaciones IS: **3.771** por combinación.
- Percentil de deriva: **19,3–47,2** (mínimo exigido 90); ninguna pasa.
- Pliegues positivos: **0/4** en las 6 combinaciones.
- Concentración máxima 0,0061; no es un problema de una sola operación.

## Bruto por año (2010–2024)

Combinación de mejor neto (hold 180 h, stop 3,0). R bruto sumado por año de
entrada; la última columna es la mediana de las 6 combinaciones.

| Año | Ops | R bruto | Mediana 6 combos |
|---:|---:|---:|---:|
| 2010 | 260 | −19,70 | −18,05 |
| 2011 | 260 | −11,47 | −16,22 |
| 2012 | 261 | +0,08 | +0,80 |
| 2013 | 260 | +5,00 | −0,04 |
| 2014 | 260 | +8,26 | +7,71 |
| 2015 | 260 | +23,73 | +17,81 |
| 2016 | 260 | +1,36 | +1,09 |
| 2017 | 260 | +8,57 | +9,91 |
| 2018 | 260 | −11,66 | −15,80 |
| 2019 | 260 | +4,86 | +4,71 |
| 2020 | 261 | −3,28 | −4,85 |
| 2021 | 260 | +8,59 | +7,52 |
| 2022 | 260 | +1,53 | −3,30 |
| 2023 | 260 | +1,59 | +0,99 |
| 2024 | 129 | +3,87 | +7,26 |

El bruto no es estable: años de −19,7 R y +23,7 R. No hay un régimen
persistente que el coste pueda dejar pasar.

## Por cuenta

| Cuenta | Firma | Coste mediano (R) | Neto aprox. (bruto − coste) |
|---|---|---:|---:|
| CFD-001 | FTMO | 0,0481 | −0,0429 |
| CFD-006 | FundingPips | 0,0410 | −0,0358 |

Neto oficial almacenado de la mejor combinación (cuenta seleccionada por
`best`): **−0,0396 R**. El neto por cuenta es aproximado porque el pipeline
guarda la mediana de coste, no la media por cuenta.

## Coste que haría falta para neto > 0

- Coste de equilibrio: **0,0052 R** (bruto de la mejor combinación).
- Equivale a **0,23 bps** o **0,25 pips** ida y vuelta (riesgo medio 0,40 % del precio).
- El pipeline cobra 0,041–0,048 R: el coste tendría que caer ~8×.

> Nota de auditoría: la auditoría TL2 abierta el 2026-11-24 señala un posible
> doble spread en salidas que no son por objetivo. Estas cifras son las
> **almacenadas por la campaña**; no se reescriben ni se re-optimiza la spec.

## Decisión

Hipótesis 2 (fix de Tokio) **probada** en USDJPY H1: sin edge neto. No se
proponen variantes ni re-optimizaciones.
