# RESULTADO N1 · Reglas oficiales y P(pasar) real

- **Fecha:** 2026-11-24
- **Rama:** `tl2-n1` (desde `feature/prop-fund-multifirm`)
- **Tag previo:** `tl2-n1-pre`

## Reglas

`config/propfund/firms.yaml`, `rules_version 2026-11-24.1`:

- FTMO 2-Step: objetivo 10 % / 5 %, diario 5 %, máximo 10 % estático,
  4 días mínimos, periodo ilimitado (`max_days: null`), base diaria `balance`.
- FTMO 1-Step: objetivo 10 %, diario **3 %**, máximo 10 %, sin días mínimos,
  periodo ilimitado.
- Fuentes oficiales con `consulted_at: 2026-11-24` y
  `source.kind: official`; `effective_from: 2026-11-24` en cada regla.
- FundingPips 2-Step: valores ya cargados (8 % / 5 %, diario 5 %, máximo
  10 % estático, 3 días mínimos), sin URL oficial inventada.
- Se añadió `effective_from` al modelo `FirmRule` (el modelo no lo admitía).

## Simulador

- `prop.simulator.monte_carlo_program`: dos fases, la verificación empieza
  con el balance inicial, días mínimos, tope técnico de 180 días hábiles por
  fase y `P(sin terminar)`.
- `monte_carlo` aplica días mínimos y `max_days`.
- FundingPips: base diaria `max(balance, equity)` en el reinicio.
- `discovery.robustness._challenge` usa el programa de dos fases para
  2-Step y 180 días.

## Tests (`tests/test_prop_n1.py`, 4)

1. FundingPips: equidad por debajo del balance en el reinicio y caída
   posterior → rompe con `max(balance, equity)`, no con `equity`.
2. Verificación del 2-Step: empieza en 100k, no en los 110k del final del
   reto; no pasa si el retorno de verificación es 0.
3. Días mínimos: un objetivo alcanzado antes del día 4 no cuenta; la mediana
   de días es ≥ 4.
4. 1-Step: −3,1 % diario rompe el 3 %; el 2-Step con 5 % no rompe.

`pytest` dirigido: **68 passed** (prop, propfund y N1). `ruff`: limpio.

## P(pasar) oficial (US100)

Serie de 478 operaciones de T41; 5.000 caminos, 180 días por fase, bloque 5.
Detalle en `reports/ea/p-pasar-oficial.md`.

| Escenario | Programa | Mejor riesgo | P(pasar) | P(romper) | P(sin terminar) | Días | P(pasar) 0,35 % |
|---|---|---:|---:|---:|---:|---:|---:|
| Backtest | FTMO 2-Step | 0,25 % | 99,86 % | 0,14 % | 0,00 % | 37 | 99,00 % |
| Backtest | FTMO 1-Step | 0,25 % | 99,94 % | 0,06 % | 0,00 % | 23 | 99,50 % |
| Backtest | FundingPips | 0,25 % | 95,66 % | 4,34 % | 0,00 % | 32 | 87,52 % |
| Mitad | FTMO 2-Step | ninguno | — | — | — | — | 85,86 % (rompe 14,10 %) |
| Mitad | FTMO 1-Step | 0,25 % | 96,18 % | 3,14 % | 0,68 % | 39 | 92,20 % (rompe 7,76 %) |
| Mitad | FundingPips | ninguno | — | — | — | — | 57,70 % (rompe 42,30 %) |
| LCB95 | FTMO 2-Step | 0,25 % | 95,02 % | 4,50 % | 0,48 % | 61 | 88,42 % (rompe 11,54 %) |
| LCB95 | FTMO 1-Step | 0,25 % | 97,14 % | 2,40 % | 0,46 % | 37 | 93,66 % (rompe 6,30 %) |
| LCB95 | FundingPips | ninguno | — | — | — | — | 61,22 % (rompe 38,78 %) |

El tope de 180 días por fase cambia el óptimo respecto a T41 (60 días, una
fase): con la ventaja del backtest, lo que limita es no romper, no llegar al
objetivo. Con la ventaja contraída, el 2-Step no tiene ningún riesgo del
barrido con P(romper) ≤ 5 %; el 1-Step sí (0,25 %).

## Baseline de producción

`lab propfund baseline --reason "N1: simulador de dos fases, dias minimos y
cache sin barra en curso; motor y setfile del EA intactos"`. El manifiesto
incluye `ea_us100.py`, `prop/rules.py` y `prop/simulator.py`; el motor
`ea_us100_engine.py` y el setfile no se tocaron.

## Cierre

- `pytest -q`: **1961 passed, 1 skipped** (31:04). Aviso único:
  `psutil no está instalado: la cola corre sin prioridad below normal`.
- `ruff check`: limpio.
- Merge `--ff-only` a `feature/prop-fund-multifirm`, tag `tl2-n1`.
- `count_tests` = 1894.
- `git status` conserva solo los cambios externos
  (`reports/discovery/edge_map.md` y `tl2-edge-map.patch`).

