# Informe · `q2-fix-eurusd-h1`

Fecha: 2026-11-24. Campaña `done`, 6 combinaciones, 0 finalistas.
IS 2010-01-01 → 2024-06-30 · H1 · EURUSD · Dukascopy · coste `best` CFD-001/CFD-006.
Solo IS; OOS-1 no se abrió (no hubo candidatos) y OOS-2 sigue sellado.

## Veredicto

**Edge bruto que el coste elimina.** Hay un bruto pequeño y real (0,012–0,029 R
por operación) pero el coste (0,033–0,039 R) lo supera; el control de deriva sí
pasa (100), y aun así no queda ninguna combinación con neto positivo.

## Bruto vs coste vs neto (R por operación)

| Rejilla (6 combinaciones) | Bruto | Coste CFD-001 | Coste CFD-006 | Neto |
|---|---:|---:|---:|---:|
| Mediana | 0,0234 | 0,0359 | 0,0359 | −0,0133 |
| Mejor combinación (hold 180 h, stop 3,0) | 0,0234 | 0,0327 | 0,0346 | −0,0112 |
| Peor combinación (hold 60 h, stop 2,5) | 0,0151 | 0,0392 | 0,0392 | −0,0265 |

- Operaciones IS: **3.764** por combinación.
- Percentil de deriva: **100,0** en las 6 combinaciones (mínimo 90).
- Pliegues positivos: **0/4** en cinco combinaciones; **1/4** en la mejor.
- El bruto es positivo, pero el coste es 1,1–3,2× el bruto.

## Bruto por año (2010–2024)

Combinación de mejor neto (hold 180 h, stop 3,0). R bruto sumado por año de
entrada; la última columna es la mediana de las 6 combinaciones.

| Año | Ops | R bruto | Mediana 6 combos |
|---:|---:|---:|---:|
| 2010 | 261 | +4,82 | +4,86 |
| 2011 | 260 | +1,08 | +6,47 |
| 2012 | 261 | +11,18 | +13,32 |
| 2013 | 259 | +11,65 | +14,71 |
| 2014 | 259 | −8,27 | −5,88 |
| 2015 | 259 | +10,11 | +7,83 |
| 2016 | 260 | +16,73 | +16,79 |
| 2017 | 259 | +9,25 | +2,40 |
| 2018 | 259 | +0,16 | +2,82 |
| 2019 | 259 | +2,13 | +2,98 |
| 2020 | 260 | +1,45 | +0,74 |
| 2021 | 260 | +3,57 | +2,28 |
| 2022 | 260 | −5,68 | −7,69 |
| 2023 | 259 | +13,25 | +12,25 |
| 2024 | 129 | +8,45 | +7,38 |

El bruto aparece en muchos años, pero 2014 y 2022 son negativos y el coste se
come el resto. No es un edge que sobreviva al coste actual.

## Por cuenta

| Cuenta | Firma | Coste mediano (R) | Neto aprox. (bruto − coste) |
|---|---|---:|---:|
| CFD-001 | FTMO | 0,0327 | −0,0093 |
| CFD-006 | FundingPips | 0,0346 | −0,0112 |

Neto oficial almacenado de la mejor combinación (cuenta seleccionada por
`best`): **−0,0112 R**. El neto por cuenta es aproximado porque el pipeline
guarda la mediana de coste, no la media por cuenta.

## Coste que haría falta para neto > 0

- Coste de equilibrio: **0,0234 R** (bruto de la mejor combinación).
- Equivale a **1,04 bps** o **1,24 pips** ida y vuelta (riesgo medio 0,49 % del precio).
- El pipeline cobra 0,033–0,039 R: el coste tendría que caer ~30–40 %.

> Nota de auditoría: la auditoría TL2 abierta el 2026-11-24 señala un posible
> doble spread en salidas que no son por objetivo. Si se confirma, el coste
> almacenado podría estar sobreestimado; estas cifras no se reescriben y la
> campaña conserva su veredicto.

## Decisión

Hipótesis 2 (fix de Londres) **probada** en EURUSD H1: edge bruto que el coste
elimina. No se proponen variantes ni re-optimizaciones.
