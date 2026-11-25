# TL3 · T7 EA v3.2 fuera de periodo US100 Dukascopy

Datos: Dukascopy US100 M1 → M5 con `prepare_nq`; ventana de entradas 2012-01-03 → 2021-08-31.
k = ATR14 M5 Dukascopy / US100.cash 2022: 1.0358 → aplicado 1.000000.
Costes: spread por franja 5 min (perfil 2021-2026, anacrónico declarado), slippage 0,5 pt/lado, comisión 0.
Sesiones válidas por cobertura: 2363; festivos/cierres excluidos: 86.
Filtro de noticias no modelado (igual que el backtest).

## Resultado

| Métrica | Valor |
|---|---:|
| Operaciones | 374 |
| Win rate | 27.0 % |
| Expectativa | -0.0296 R |
| Desviación | 1.7324 |
| PF | 0.9603 |
| DD | 37.1212 R |
| LCB95 semanal | -0.1753 R |
| **Veredicto** | **no confirma** |

## Por año

| Año | Ops | Exp R | Total R | DD R |
|---|---:|---:|---:|---:|
| 2013 | 16 | -0.8799 | -14.0776 | 15.3465 |
| 2014 | 50 | -0.1572 | -7.8595 | 15.2353 |
| 2015 | 11 | 0.0112 | 0.1227 | 5.2072 |
| 2018 | 60 | -0.0178 | -1.0685 | 12.2933 |
| 2019 | 88 | 0.0665 | 5.8511 | 16.8957 |
| 2020 | 81 | 0.0321 | 2.6019 | 11.7161 |
| 2021 | 68 | 0.0492 | 3.3434 | 21.4224 |

## Largo/corto

| Lado | Ops | Exp R |
|---|---:|---:|
| long | 259 | 0.0143 |
| short | 115 | -0.1286 |

## Slippage

| Slip pt/lado | Ops | Exp R | PF |
|---:|---:|---:|---:|
| 0 | 376 | 0.0310 | 1.0433 |
| 0.5 | 374 | -0.0296 | 0.9603 |
| 1 | 374 | -0.0992 | 0.8724 |
| 2 | 371 | -0.1817 | 0.7787 |
| 3 | 369 | -0.2684 | 0.6900 |

`slip_eq` ≈ **0.26 puntos/lado**.

Solo una ejecución del criterio. La tabla por año es descriptiva.

## Correcci?n TL3-C

La regla del script usaba 371 velas de sesi?n (?99 %) y no comprobaba la sesi?n anterior; el prerregistro exige **?357 (95 %) en la sesi?n y en la anterior** y **?744 nocturnas**.

| A?o | D?as NYSE | V?lidos script (371 + noche) | V?lidos prerregistro | Mediana velas nocturnas |
|---|---:|---:|---:|---:|
| 2012 | 235 | 0 | 0 | 0.0 |
| 2013 | 186 | 67 | 73 | 891.0 |
| 2014 | 248 | 136 | 176 | 885.5 |
| 2015 | 250 | 37 | 37 | 450.0 |
| 2016 | 251 | 0 | 0 | 450.0 |
| 2017 | 249 | 0 | 0 | 442.0 |
| 2018 | 248 | 176 | 178 | 927.0 |
| 2019 | 249 | 248 | 249 | 930.0 |
| 2020 | 251 | 246 | 247 | 930.0 |
| 2021 | 167 | 167 | 167 | 930.0 |

**Sesiones v?lidas en la ventana: 1077 de 2334 con la regla del script; 1127 con el prerregistro** (el 2363 anterior contaba 2011-2026). La muestra efectiva es **2013-2014 y 2018-2021**; 2012, 2016 y 2017 no tienen sesiones v?lidas y 2015 solo 37.

Cota: para que el veredicto pasara de ?no confirma? a ?confirma? har?an falta ~2,8 R de media en cada una de las ~51 operaciones a?adidas; el veredicto **no cambia**. No se reejecuta el motor ni se toca el registro.
