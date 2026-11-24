# Informe · `q2-fix-gbpusd-h1`

Fecha: 2026-11-24. Campaña `done`, 6 combinaciones, 0 finalistas.
IS 2010-01-01 → 2024-06-30 · H1 · GBPUSD · Dukascopy · coste `best` CFD-001/CFD-006.
Solo IS; OOS-1 no se abrió (no hubo candidatos) y OOS-2 sigue sellado.

## Veredicto

**Edge bruto que el coste elimina.** El bruto (0,007–0,015 R) es positivo pero
muy inferior al coste (0,028–0,044 R); la deriva pasa (100) y el neto sigue
negativo en las 6 combinaciones: no hay finalista.

## Bruto vs coste vs neto (R por operación)

| Rejilla (6 combinaciones) | Bruto | Coste CFD-001 | Coste CFD-006 | Neto |
|---|---:|---:|---:|---:|
| Mediana | 0,0128 | 0,0362 | 0,0315 | −0,0227 |
| Mejor combinación (hold 120 h, stop 3,0) | 0,0120 | 0,0362 | 0,0285 | −0,0177 |
| Peor combinación (hold 60 h, stop 2,5) | 0,0066 | 0,0417 | 0,0341 | −0,0291 |

- Operaciones IS: **3.763** por combinación.
- Percentil de deriva: **100,0** en las 6 combinaciones (mínimo 90).
- Pliegues positivos: **0/4** en las 6 combinaciones.
- El coste es 1,9–6,7× el bruto.

## Bruto por año (2010–2024)

Combinación de mejor neto (hold 120 h, stop 3,0). R bruto sumado por año de
entrada; la última columna es la mediana de las 6 combinaciones.

| Año | Ops | R bruto | Mediana 6 combos |
|---:|---:|---:|---:|
| 2010 | 261 | +1,29 | +1,22 |
| 2011 | 260 | +7,67 | +4,22 |
| 2012 | 260 | +3,89 | +3,64 |
| 2013 | 259 | +12,37 | +13,13 |
| 2014 | 259 | −10,58 | −10,03 |
| 2015 | 259 | +7,16 | +7,32 |
| 2016 | 260 | +12,17 | +13,28 |
| 2017 | 259 | −2,04 | −2,13 |
| 2018 | 259 | −3,60 | −5,34 |
| 2019 | 259 | +0,46 | −3,69 |
| 2020 | 260 | −4,23 | −4,38 |
| 2021 | 260 | +5,13 | +4,21 |
| 2022 | 260 | −7,87 | −8,30 |
| 2023 | 259 | +15,81 | +16,93 |
| 2024 | 129 | +8,61 | +9,28 |

El bruto positivo se concentra en 2013, 2016 y 2023; 2014 y 2022 son muy
negativos. No hay persistencia suficiente para pagar el coste.

## Por cuenta

| Cuenta | Firma | Coste mediano (R) | Neto aprox. (bruto − coste) |
|---|---|---:|---:|
| CFD-001 | FTMO | 0,0362 | −0,0242 |
| CFD-006 | FundingPips | 0,0285 | −0,0165 |

Neto oficial almacenado de la mejor combinación (cuenta seleccionada por
`best`): **−0,0177 R**. El neto por cuenta es aproximado porque el pipeline
guarda la mediana de coste, no la media por cuenta.

## Coste que haría falta para neto > 0

- Coste de equilibrio: **0,0120 R** (bruto de la mejor combinación).
- Equivale a **0,64 bps** o **0,90 pips** ida y vuelta (riesgo medio 0,52 % del precio).
- El pipeline cobra 0,028–0,044 R: el coste tendría que caer ~58–72 %.

> Nota de auditoría: la auditoría TL2 abierta el 2026-11-24 señala un posible
> doble spread en salidas que no son por objetivo. Si se confirma, el coste
> almacenado podría estar sobreestimado; estas cifras no se reescriben y la
> campaña conserva su veredicto.

## Decisión

Hipótesis 2 (fix de Londres) **probada** en GBPUSD H1: edge bruto que el coste
elimina. No se proponen variantes ni re-optimizaciones.
