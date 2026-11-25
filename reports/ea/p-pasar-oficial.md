# EA us100-ftmo1 · P(pasar) con las reglas oficiales (N1)

Generado: 2026-11-24 · solo lectura, sin tocar el EA.

## Reglas cargadas

`config/propfund/firms.yaml`, `rules_version: 2026-11-24.1`. Fuentes
oficiales consultadas el 2026-11-24 (`source.kind: official`), con
`effective_from: 2026-11-24` en cada regla.

| Programa | Fase | Objetivo | Diario | Máximo | Días mínimos | Periodo |
|---|---|---:|---:|---:|---:|---|
| FTMO 2-Step | evaluation | 10 % | 5 % | 10 % estático | 4 | ilimitado |
| FTMO 2-Step | verification | 5 % | 5 % | 10 % estático | 4 | ilimitado |
| FTMO 1-Step | evaluation | 10 % | 3 % | 10 % estático | 0 | ilimitado |
| FundingPips 2-Step | evaluation | 8 % | 5 % | 10 % estático | 3 | ilimitado |
| FundingPips 2-Step | verification | 5 % | 5 % | 10 % estático | 3 | ilimitado |

Fuentes: `https://ftmo.com/en/2-step-challenge/`,
`https://ftmo.com/en/blog/how-ftmo-works/`,
`https://ftmo.com/en/blog/drawdowns/`,
`https://ftmo.com/en/maximum-daily-loss/`,
`https://promo.ftmo.com/m26b-practice-trading-without-risk/`.
FundingPips conserva los valores del registro; su fuente es el panel/ayuda
oficial ya cargado, sin URL nueva inventada.

## Simulador

- Dos fases para el 2-Step: la verificación **empieza con el balance
  inicial** (100k), no con el saldo final del reto.
- Días mínimos por fase; un objetivo alcanzado antes del día 4 (FTMO) o del
  día 3 (FundingPips) no cuenta.
- Periodo ilimitado con tope técnico de **180 días hábiles por fase**; quien
  no llega queda como **sin terminar**.
- FundingPips: base diaria `max(balance, equity)` en el reinicio.
- 5.000 caminos, bootstrap de los R diarios, bloque 5, semilla 42.
- Serie: 478 operaciones de T41 (US100). Escenarios de ventaja: backtest
  (+0,3104 R), mitad (+0,1552 R), LCB95 (+0,1682 R).
- Riesgo por operación: 0,25 % a 1,00 % en pasos de 0,05 %.

## P(pasar) por programa y escenario

"Mejor" = riesgo que maximiza P(pasar) con P(romper) ≤ 5 %. Si ninguno del
barrido cumple, se indica **ninguno**.

| Escenario | Programa | Mejor riesgo | P(pasar) | P(romper) | P(sin terminar) | Días | P(pasar) 0,35 % |
|---|---|---:|---:|---:|---:|---:|---:|
| Backtest | FTMO 2-Step | 0,25 % | 99,86 % | 0,14 % | 0,00 % | 37 | 99,00 % |
| Backtest | FTMO 1-Step | 0,25 % | 99,94 % | 0,06 % | 0,00 % | 23 | 99,50 % |
| Backtest | FundingPips 2-Step | 0,25 % | 95,66 % | 4,34 % | 0,00 % | 32 | 87,52 % |
| Mitad | FTMO 2-Step | **ninguno** | — | — | — | — | 85,86 % (rompe 14,10 %) |
| Mitad | FTMO 1-Step | 0,25 % | 96,18 % | 3,14 % | 0,68 % | 39 | 92,20 % (rompe 7,76 %) |
| Mitad | FundingPips 2-Step | **ninguno** | — | — | — | — | 57,70 % (rompe 42,30 %) |
| LCB95 | FTMO 2-Step | 0,25 % | 95,02 % | 4,50 % | 0,48 % | 61 | 88,42 % (rompe 11,54 %) |
| LCB95 | FTMO 1-Step | 0,25 % | 97,14 % | 2,40 % | 0,46 % | 37 | 93,66 % (rompe 6,30 %) |
| LCB95 | FundingPips 2-Step | **ninguno** | — | — | — | — | 61,22 % (rompe 38,78 %) |

## Lectura

- El **tope de 180 días por fase** cambia el resultado respecto a T41 §8
  (60 días, una fase): con la ventaja del backtest, la P(pasar) del 2-Step se
  acerca a 100 % y el riesgo óptimo pasa a ser el mínimo del barrido, porque
  lo que limita no es llegar al objetivo sino **no romper** en el camino.
- Con la ventaja contraída a la mitad o al LCB95, el 2-Step de FTMO y el de
  FundingPips **no tienen ningún riesgo del barrido con P(romper) ≤ 5 %**;
  el 1-Step sí (0,25 %), porque su límite diario es del 3 % y el objetivo es
  de una sola fase.
- Al 0,35 % actual, la P(pasar) es alta en el backtest (99 % en FTMO 2-Step),
  pero el riesgo de romper crece rápido: 1,0 % en el backtest, 11,5 % con el
  LCB95 y 14,1 % con la mitad.
- FundingPips es el más frágil: su base diaria `max(balance, equity)` y sus
  360 días potenciales (2 × 180) elevan la P(romper) al 12,5 % ya con la
  ventaja del backtest al 0,35 %.
- Estas cifras son **optimistas** por construcción: asumen que la ventaja del
  backtest persiste y que los R diarios son intercambiables. No son una
  predicción; son una cota superior del simulador.

## Cumplimiento

Solo lectura sobre el EA. No se cambió el motor ni el setfile. Sin campañas,
OOS, `confirm` ni `record-informal`. `count_tests` = 1894.
