# Informe · `q1-rebote-us500-d1`

Fecha: 2026-11-24. Campaña `done`, 27 combinaciones, 0 finalistas.
IS 2018-01-01 → 2024-06-30 · D1 · US500 · Dukascopy · coste `best` CFD-006.
Solo IS; OOS-1 no se abrió (no hubo candidatos) y OOS-2 sigue sellado.

## Veredicto

**Sin edge bruto.** La mediana de la rejilla pierde antes de costes (−0,054 R);
solo 3 combinaciones quedan positivas y las tres tienen 9–16 operaciones y un
percentil de deriva de 61–68, por debajo de 90: muestra insuficiente.

## Bruto vs coste vs neto (R por operación)

| Rejilla (27 combinaciones) | Bruto | Coste | Neto | Ops | Deriva | Pliegues |
|---|---:|---:|---:|---:|---:|---:|
| Mediana | −0,0539 | 0,0515 | −0,1257 | 16 | 33,3 | 1/3 |
| Mejor neto (`z_n=30`, `z_entry=−1,5`, stop 2,5) | 0,0767 | 0,0414 | 0,0291 | 15 | 68,2 | 2/3 |
| Peor neto (`z_n=30`, `z_entry=−2,5`, stop 2,5) | −0,6312 | 0,0344 | −0,6687 | 3 | 3,1 | 1/3 |

- Operaciones IS: **2–38** por combinación (mediana 16); el mínimo del gate es 15.
- Percentil de deriva: **0,8–68,2**; ninguna combinación alcanza 90.
- Pliegues positivos: **0/3 a 2/3**; ninguna combinación pasa el mínimo de 3/3.
- Las tres combinaciones con neto positivo (ids 568, 574 y 577) tienen 9–16
  operaciones y deriva < 70; no son evidencia, son muestra corta.

## OOS-1

No se abrió: ninguna combinación llegó a candidata (deriva < 90 y/o IS no
positiva). No hay OOS-1 que analizar.

## Decisión

Hipótesis 4 (rebote tras ventas fuertes) **probada** en US500 D1: sin edge
bruto en la rejilla. No se proponen variantes ni re-optimizaciones.
