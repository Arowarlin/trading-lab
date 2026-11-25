# TL3-D · D2 Línea base sin ventaja (sintética)

Retornos diarios sintéticos con ventaja bruta exactamente 0:
p = 1/(1+b), +b R con p y −1 R en el resto; 20.000 días de pool,
5.000 caminos, 180 días por fase, semilla 42.

| Programa | b | Riesgo | P(fase 1) | P(fase 2) | P(financiada) | P(romper) | P(diario) | P(total) | Días |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FTMO 2-Step | 1 | 0.25% | 0.42% | 0.04% | 0.04% | 0.58% | 0.00% | 0.58% | 270.0 |
| FTMO 2-Step | 1 | 0.50% | 11.84% | 4.94% | 4.94% | 20.04% | 0.00% | 20.04% | 192.0 |
| FTMO 2-Step | 1 | 1.00% | 39.14% | 23.50% | 23.50% | 63.02% | 0.00% | 63.02% | 104.0 |
| FTMO 2-Step | 2 | 0.25% | 4.84% | 1.28% | 1.28% | 3.78% | 0.00% | 3.78% | 240.5 |
| FTMO 2-Step | 2 | 0.50% | 30.34% | 17.44% | 17.44% | 36.68% | 0.00% | 36.68% | 150.0 |
| FTMO 2-Step | 2 | 1.00% | 47.14% | 30.18% | 30.18% | 67.88% | 0.00% | 67.88% | 62.0 |
| FTMO 2-Step | 3 | 0.25% | 11.18% | 4.32% | 4.32% | 9.16% | 0.00% | 9.16% | 203.0 |
| FTMO 2-Step | 3 | 0.50% | 37.88% | 22.90% | 22.90% | 51.08% | 0.00% | 51.08% | 123.0 |
| FTMO 2-Step | 3 | 1.00% | 47.54% | 28.84% | 28.84% | 71.00% | 0.00% | 71.00% | 43.0 |
| FTMO 1-Step | 1 | 0.25% | 0.42% | — | 0.42% | 0.58% | 0.00% | 0.58% | 161.0 |
| FTMO 1-Step | 1 | 0.50% | 11.84% | — | 11.84% | 18.00% | 0.00% | 18.00% | 118.0 |
| FTMO 1-Step | 1 | 1.00% | 39.14% | — | 39.14% | 48.34% | 0.00% | 48.34% | 62.0 |
| FTMO 1-Step | 2 | 0.25% | 4.84% | — | 4.84% | 3.54% | 0.00% | 3.54% | 138.0 |
| FTMO 1-Step | 2 | 0.50% | 30.34% | — | 30.34% | 28.92% | 0.00% | 28.92% | 90.0 |
| FTMO 1-Step | 2 | 1.00% | 47.14% | — | 47.14% | 50.98% | 0.00% | 50.98% | 35.0 |
| FTMO 1-Step | 3 | 0.25% | 11.18% | — | 11.18% | 8.02% | 0.00% | 8.02% | 125.0 |
| FTMO 1-Step | 3 | 0.50% | 37.88% | — | 37.88% | 38.44% | 0.00% | 38.44% | 75.0 |
| FTMO 1-Step | 3 | 1.00% | 47.54% | — | 47.54% | 52.30% | 0.00% | 52.30% | 24.0 |
| FundingPips 2-Step | 1 | 0.25% | 1.96% | 0.24% | 0.24% | 18.36% | 18.36% | 0.58% | 253.0 |
| FundingPips 2-Step | 1 | 0.50% | 19.86% | 7.40% | 7.40% | 61.28% | 61.28% | 21.66% | 173.5 |
| FundingPips 2-Step | 1 | 1.00% | 36.30% | 17.30% | 17.30% | 82.08% | 82.08% | 63.08% | 66.0 |
| FundingPips 2-Step | 2 | 0.25% | 10.70% | 2.94% | 2.94% | 32.86% | 32.86% | 4.10% | 226.0 |
| FundingPips 2-Step | 2 | 0.50% | 34.10% | 15.86% | 15.86% | 75.46% | 75.46% | 38.84% | 113.0 |
| FundingPips 2-Step | 2 | 1.00% | 37.66% | 18.00% | 18.00% | 82.00% | 82.00% | 65.34% | 34.0 |
| FundingPips 2-Step | 3 | 0.25% | 19.10% | 7.18% | 7.18% | 46.82% | 46.82% | 9.76% | 186.0 |
| FundingPips 2-Step | 3 | 0.50% | 35.88% | 16.74% | 16.74% | 80.88% | 80.88% | 52.54% | 80.0 |
| FundingPips 2-Step | 3 | 1.00% | 37.02% | 17.32% | 17.32% | 82.68% | 82.68% | 67.68% | 24.0 |

**EV: Sin datos.** `firms.yaml` no trae tarifa y reparto verificados; no se modela pago.
Neto: **Sin datos** (no hay coste por operación en R sin suponer).

Lectura: una estrategia real aporta sobre las reglas solo si su P(financiada)
o EV supera esta línea base con la misma regla de riesgo.
El simulador con datos diarios subestima el riesgo intradía.

Aviso (2026-11-25, TL2-DIARIO): las 9 filas de FundingPips de esta tabla se calcularon con el simulador anterior (`max(initial, day_start)`); la tabla antes/despues esta en `TL3_REPORTS/tl2_diario_inventario.md` §9.

## Aviso · FundingPips (D3b)

**Cifras de FundingPips no fiables: las 9 filas de D2 se calcularon con el error del simulador protegido `max(initial, day_start)`, ya corregido en TL2-DIARIO `020b41b`; ver COLA-TL3-D D3b y `TL3_REPORTS/tl2_diario_inventario.md §9`.**

El código anterior usaba `np.maximum(initial, day_start) - eff_daily`, es decir, el balance **inicial**. La regla de `firms.yaml` es el mayor de balance o equidad **al inicio del día**. Así, quedar 5 % por debajo del balance inicial contaba como rotura diaria aunque la pérdida del día fuera menor. La versión actual usa `day_start - eff_daily` y no se toca `prop/`.

Comprobación con los mismos 5.000 caminos y semilla 42 de D2, replicando el consumo del generador en ambas versiones:

| b | Riesgo | Caminos afectados (antes) | Rotura diaria (antes) | Caminos afectados (actual) | Rotura diaria (actual) |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.25% | 918 | 918 | 0 | 0 |
| 1 | 0.50% | 3095 | 3095 | 0 | 0 |
| 1 | 1.00% | 4655 | 4655 | 0 | 0 |
| 2 | 0.25% | 1644 | 1644 | 0 | 0 |
| 2 | 0.50% | 3981 | 3981 | 0 | 0 |
| 2 | 1.00% | 4802 | 4802 | 0 | 0 |
| 3 | 0.25% | 2347 | 2347 | 0 | 0 |
| 3 | 0.50% | 4371 | 4371 | 0 | 0 |
| 3 | 1.00% | 4859 | 4859 | 0 | 0 |

Agregado: **30672 de 45000** caminos (68.2 %) rompen el diario en la versión anterior en un día cuya pérdida es menor que el 5 % del balance de ese día y sin romper el límite total. En la versión actual: **0 de 45000**.

**Confirma el error de la versión anterior del simulador** para FundingPips; la versión corregida no lo reproduce.
No se modifica `prop/` (Prop Fund protegido) y D2 no se reejecuta en D3b: su tabla queda como valores anteriores, marcados como no fiables.
