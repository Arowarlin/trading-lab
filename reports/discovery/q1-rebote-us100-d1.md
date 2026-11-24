# Informe · `q1-rebote-us100-d1`

Fecha: 2026-11-24. Campaña `done`, 27 combinaciones, 0 finalistas.
IS 2014-01-01 → 2024-06-30 · D1 · US100 · Dukascopy · coste `best` CFD-001/CFD-006.
Solo IS y el OOS-1 que el pipeline ya leyó; OOS-2 sigue sellado.

## Veredicto

**Muestra insuficiente.** El IS es positivo en 25/27 combinaciones y 10 pasan la
deriva ≥ 90, pero los 3 candidatos que llegaron a OOS-1 abrieron **0
operaciones**; sin operaciones no hay confirmación y no queda ningún finalista.

## Bruto vs coste vs neto (R por operación)

| Rejilla (27 combinaciones) | Bruto | Coste | Neto | Ops | Deriva | Pliegues |
|---|---:|---:|---:|---:|---:|---:|
| Mediana | 0,1504 | 0,0103 | 0,1361 | 27 | 68,2 | 1/3 |
| Mejor neto (`z_n=30`, `z_entry=−2,5`, stop 2,0) | 0,8087 | 0,0085 | 0,7970 | 6 | 98,7 | 3/3 |
| Peor neto (`z_n=10`, `z_entry=−2,5`, stop 1,5) | 0,0000 | 0,0302 | −0,0302 | 2 | 42,8 | 1/3 |

- Operaciones IS: **2–75** por combinación (mediana 27); el mínimo del gate es 15.
- Percentil de deriva: **26,0–99,9**; 10 combinaciones pasan 90.
- Pliegues positivos: **0/3 a 3/3**; varias combinaciones pasan 3/3.
- El mejor neto (0,797 R) sale de solo 6 operaciones y queda fuera del frente
  (rank 5): no se usa como evidencia.

## Candidatos y OOS-1

Los 3 candidatos con deriva ≥ 90 y 3/3 pliegues:

| ID | Parámetros | Ops IS | Neto IS | Deriva | OOS-1 ops | OOS-1 neto |
|---:|---|---:|---:|---:|---:|---:|
| 593 | `z_n=20`, `z_entry=−2,0`, stop 1,5 | 31 | 0,4503 | 98,5 | 0 | Sin datos |
| 595 | `z_n=20`, `z_entry=−2,0`, stop 2,5 | 29 | 0,3768 | 99,9 | 0 | Sin datos |
| 604 | `z_n=30`, `z_entry=−2,0`, stop 2,5 | 22 | 0,2429 | 92,2 | 0 | Sin datos |

Los tres se descartaron por «OOS-1 expectativa None»: el tramo OOS-1 no generó
ninguna operación. No es un fallo del motor; es muestra insuficiente.

## Decisión

Hipótesis 4 (rebote tras ventas fuertes) **probada** en US100 D1: señal
prometedora en IS, sin confirmación por falta de operaciones en OOS-1. No se
proponen variantes ni re-optimizaciones.
