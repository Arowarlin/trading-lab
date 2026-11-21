# Campaña disc-US100.CASH-M5-20261121180458-0e579341

**Nota: sin ventaja en IS.**

Campaña terminada, modo rejilla, plantilla `intraday_momentum_close_v2`, instrumento `US100.CASH`, M5, semilla 20261122, IS 2021-10-01 → 2024-06-30. Solo se ha leído IS; no se ha abierto OOS-1 ni OOS-2 y las reevaluaciones no han escrito en `disc_*` ni han cambiado niveles.

## 1. Frontera: 14 estrategias descartadas

Las 14 celdas factibles de rango 0 se descartaron por el mismo motivo: **IS completa ≤ 0** con el coste base CFD-001. Conteo: **14/14**.

| ID | u | fin | entrada | stop | `selection_reason` |
|---:|---:|---:|---:|---:|---|
| 408 | 0.0 % | 600 | 15:30 | 6×ATR | `descartado: IS completa -0.07364372487236105 <= 0` |
| 412 | 0.0 % | 630 | 15:30 | 6×ATR | `descartado: IS completa -0.06284082458856655 <= 0` |
| 414 | 0.1 % | 600 | 15:00 | 6×ATR | `descartado: IS completa -0.07654034176273933 <= 0` |
| 416 | 0.1 % | 600 | 15:30 | 6×ATR | `descartado: IS completa -0.07684650155467072 <= 0` |
| 418 | 0.1 % | 630 | 15:00 | 6×ATR | `descartado: IS completa -0.05281002998177227 <= 0` |
| 420 | 0.1 % | 630 | 15:30 | 6×ATR | `descartado: IS completa -0.06211363459660476 <= 0` |
| 424 | 0.2 % | 600 | 15:30 | 6×ATR | `descartado: IS completa -0.09159120482709594 <= 0` |
| 426 | 0.2 % | 630 | 15:00 | 6×ATR | `descartado: IS completa -0.04644294706115347 <= 0` |
| 428 | 0.2 % | 630 | 15:30 | 6×ATR | `descartado: IS completa -0.060375679644486153 <= 0` |
| 430 | 0.3 % | 600 | 15:00 | 6×ATR | `descartado: IS completa -0.07105834304774845 <= 0` |
| 432 | 0.3 % | 600 | 15:30 | 6×ATR | `descartado: IS completa -0.09156062911747868 <= 0` |
| 433 | 0.3 % | 630 | 15:00 | 4×ATR | `descartado: IS completa -0.0658894901415679 <= 0` |
| 434 | 0.3 % | 630 | 15:00 | 6×ATR | `descartado: IS completa -0.05047591656848625 <= 0` |
| 436 | 0.3 % | 630 | 15:30 | 6×ATR | `descartado: IS completa -0.05752762934722436 <= 0` |

Rango de la expectativa neta CFD-001 en la frontera: -0.0916 a -0.0464 R. No hubo finalistas.

## 2. Las 32 combinaciones en IS

Costes: **B** = 0 (bruto); **001** = CFD-001 FTMO (spread p75 1,945476 pts + slippage 1,0 + comisión 0); **006** = CFD-006 FundingPips (spread p75 2,097528 pts + comisión 0; slippage Sin datos → coste **cota inferior** y expectativa optimista). Pliegues + = pliegues con expectativa > 0 (de 4). La expectativa es la media de R por operación en toda la IS; los pliegues son los 4 pliegues walk-forward del motor.

| # | u | fin | entrada | stop | Ops IS | Pliegues + B/001/006 | Bruto R | Neto 001 R | Neto 006 R (cota inf.) | Coste 001 R | Coste 006 R (cota inf.) |
|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | 0.0 % | 600 | 15:00 | 4×ATR | 679 | 1/0/0 de 4 | -0.0290 | -0.1116 | -0.0878 | 0.0826 | 0.0588 |
| 2 | 0.0 % | 600 | 15:00 | 6×ATR | 678 | 1/0/0 de 4 | -0.0237 | -0.0788 | -0.0629 | 0.0551 | 0.0392 |
| 3 | 0.0 % | 600 | 15:30 | 4×ATR | 673 | 0/0/0 de 4 | -0.0231 | -0.1047 | -0.0812 | 0.0816 | 0.0581 |
| 4 | 0.0 % | 600 | 15:30 | 6×ATR | 673 | 0/0/0 de 4 | -0.0192 | -0.0736 | -0.0580 | 0.0544 | 0.0388 |
| 5 | 0.0 % | 630 | 15:00 | 4×ATR | 678 | 3/0/1 de 4 | 0.0109 | -0.0717 | -0.0479 | 0.0826 | 0.0588 |
| 6 | 0.0 % | 630 | 15:00 | 6×ATR | 678 | 3/0/0 de 4 | 0.0010 | -0.0540 | -0.0382 | 0.0551 | 0.0392 |
| 7 | 0.0 % | 630 | 15:30 | 4×ATR | 673 | 2/0/0 de 4 | -0.0089 | -0.0905 | -0.0670 | 0.0816 | 0.0581 |
| 8 | 0.0 % | 630 | 15:30 | 6×ATR | 673 | 2/0/0 de 4 | -0.0085 | -0.0628 | -0.0472 | 0.0544 | 0.0387 |
| 9 | 0.1 % | 600 | 15:00 | 4×ATR | 576 | 1/0/0 de 4 | -0.0249 | -0.1068 | -0.0832 | 0.0819 | 0.0583 |
| 10 | 0.1 % | 600 | 15:00 | 6×ATR | 575 | 1/0/0 de 4 | -0.0219 | -0.0765 | -0.0608 | 0.0546 | 0.0389 |
| 11 | 0.1 % | 600 | 15:30 | 4×ATR | 570 | 1/0/0 de 4 | -0.0279 | -0.1085 | -0.0853 | 0.0806 | 0.0574 |
| 12 | 0.1 % | 600 | 15:30 | 6×ATR | 570 | 1/0/0 de 4 | -0.0231 | -0.0768 | -0.0614 | 0.0537 | 0.0383 |
| 13 | 0.1 % | 630 | 15:00 | 4×ATR | 572 | 3/0/1 de 4 | 0.0110 | -0.0704 | -0.0470 | 0.0814 | 0.0580 |
| 14 | 0.1 % | 630 | 15:00 | 6×ATR | 572 | 3/0/0 de 4 | 0.0015 | -0.0528 | -0.0372 | 0.0543 | 0.0387 |
| 15 | 0.1 % | 630 | 15:30 | 4×ATR | 569 | 2/0/0 de 4 | -0.0119 | -0.0920 | -0.0689 | 0.0801 | 0.0571 |
| 16 | 0.1 % | 630 | 15:30 | 6×ATR | 568 | 2/0/0 de 4 | -0.0087 | -0.0621 | -0.0467 | 0.0534 | 0.0380 |
| 17 | 0.2 % | 600 | 15:00 | 4×ATR | 454 | 1/0/0 de 4 | -0.0314 | -0.1113 | -0.0883 | 0.0800 | 0.0570 |
| 18 | 0.2 % | 600 | 15:00 | 6×ATR | 453 | 1/0/0 de 4 | -0.0296 | -0.0829 | -0.0676 | 0.0533 | 0.0380 |
| 19 | 0.2 % | 600 | 15:30 | 4×ATR | 448 | 1/0/0 de 4 | -0.0508 | -0.1294 | -0.1068 | 0.0785 | 0.0559 |
| 20 | 0.2 % | 600 | 15:30 | 6×ATR | 448 | 1/0/0 de 4 | -0.0392 | -0.0916 | -0.0765 | 0.0524 | 0.0373 |
| 21 | 0.2 % | 630 | 15:00 | 4×ATR | 493 | 3/0/1 de 4 | 0.0188 | -0.0615 | -0.0384 | 0.0803 | 0.0572 |
| 22 | 0.2 % | 630 | 15:00 | 6×ATR | 493 | 3/0/1 de 4 | 0.0071 | -0.0464 | -0.0310 | 0.0535 | 0.0381 |
| 23 | 0.2 % | 630 | 15:30 | 4×ATR | 489 | 2/0/0 de 4 | -0.0060 | -0.0851 | -0.0623 | 0.0790 | 0.0563 |
| 24 | 0.2 % | 630 | 15:30 | 6×ATR | 489 | 2/0/0 de 4 | -0.0077 | -0.0604 | -0.0452 | 0.0527 | 0.0375 |
| 25 | 0.3 % | 600 | 15:00 | 4×ATR | 350 | 1/0/0 de 4 | -0.0207 | -0.0977 | -0.0756 | 0.0770 | 0.0549 |
| 26 | 0.3 % | 600 | 15:00 | 6×ATR | 349 | 1/0/0 de 4 | -0.0197 | -0.0711 | -0.0563 | 0.0514 | 0.0366 |
| 27 | 0.3 % | 600 | 15:30 | 4×ATR | 344 | 1/0/0 de 4 | -0.0530 | -0.1287 | -0.1069 | 0.0757 | 0.0539 |
| 28 | 0.3 % | 600 | 15:30 | 6×ATR | 344 | 1/0/0 de 4 | -0.0411 | -0.0916 | -0.0770 | 0.0504 | 0.0359 |
| 29 | 0.3 % | 630 | 15:00 | 4×ATR | 420 | 3/1/1 de 4 | 0.0128 | -0.0659 | -0.0432 | 0.0786 | 0.0560 |
| 30 | 0.3 % | 630 | 15:00 | 6×ATR | 420 | 3/0/1 de 4 | 0.0020 | -0.0505 | -0.0354 | 0.0524 | 0.0373 |
| 31 | 0.3 % | 630 | 15:30 | 4×ATR | 416 | 2/0/1 de 4 | -0.0020 | -0.0792 | -0.0570 | 0.0772 | 0.0550 |
| 32 | 0.3 % | 630 | 15:30 | 6×ATR | 416 | 2/0/1 de 4 | -0.0061 | -0.0575 | -0.0427 | 0.0515 | 0.0366 |

### Agregado por umbral × stop

| u | stop | Bruto medio | Neto 001 medio | Neto 006 medio (cota inf.) | Coste 001 | Coste 006 (cota inf.) | Pliegues + B/001/006 (media) | Ops medias | Mejor celda 001 | Peor celda 001 |
|---|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| 0.0 % | 4×ATR | -0.0125 | -0.0946 | -0.0710 | 0.0821 | 0.0585 | 1.50/0.00/0.25 de 4 | 676 | 630/15:00 (-0.0717) | 600/15:00 (-0.1116) |
| 0.0 % | 6×ATR | -0.0126 | -0.0673 | -0.0516 | 0.0547 | 0.0390 | 1.50/0.00/0.00 de 4 | 676 | 630/15:00 (-0.0540) | 600/15:00 (-0.0788) |
| 0.1 % | 4×ATR | -0.0134 | -0.0944 | -0.0711 | 0.0810 | 0.0577 | 1.75/0.00/0.25 de 4 | 572 | 630/15:00 (-0.0704) | 600/15:30 (-0.1085) |
| 0.1 % | 6×ATR | -0.0131 | -0.0671 | -0.0515 | 0.0540 | 0.0385 | 1.75/0.00/0.00 de 4 | 571 | 630/15:00 (-0.0528) | 600/15:30 (-0.0768) |
| 0.2 % | 4×ATR | -0.0174 | -0.0968 | -0.0739 | 0.0795 | 0.0566 | 1.75/0.00/0.25 de 4 | 471 | 630/15:00 (-0.0615) | 600/15:30 (-0.1294) |
| 0.2 % | 6×ATR | -0.0174 | -0.0703 | -0.0551 | 0.0530 | 0.0377 | 1.75/0.00/0.25 de 4 | 471 | 630/15:00 (-0.0464) | 600/15:30 (-0.0916) |
| 0.3 % | 4×ATR | -0.0158 | -0.0929 | -0.0707 | 0.0771 | 0.0549 | 1.75/0.25/0.50 de 4 | 382 | 630/15:00 (-0.0659) | 600/15:30 (-0.1287) |
| 0.3 % | 6×ATR | -0.0162 | -0.0677 | -0.0529 | 0.0514 | 0.0366 | 1.75/0.00/0.50 de 4 | 382 | 630/15:00 (-0.0505) | 600/15:30 (-0.0916) |

**Mejor celda global (neto CFD-001):** u=0.2 %, fin=630, entrada=15:00, stop=6×ATR: bruto 0.0071 R, coste 001 0.0535 R, neto 001 -0.0464 R, neto 006 -0.0310 R, 493 ops y 3/4 pliegues positivos brutos.

**Peor celda global (neto CFD-001):** u=0.2 %, fin=600, entrada=15:30, stop=4×ATR: bruto -0.0508 R, coste 001 0.0785 R, neto 001 -0.1294 R, neto 006 -0.1068 R, 448 ops.

Totales de pliegues positivos: **54/128 (42,2 %) brutos**, **1/128 (0,8 %) con CFD-001**, **8/128 (6,3 %) con CFD-006 (cota inferior)**.

## 3. Coste medio por operación frente al bruto

Medias no ponderadas de las 32 celdas; entre paréntesis, media ponderada por operaciones.

| Cuenta | Coste medio R/op | Bruto medio R/op | Neto medio R/op | Coste / |bruto| |
|---|---:|---:|---:|---:|
| CFD-001 FTMO | 0.0666 (0.0669) | -0.0148 (-0.0139) | -0.0814 (-0.0809) | 4.5× |
| CFD-006 FundingPips (cota inferior) | 0.0474 (0.0477) | -0.0148 (-0.0139) | -0.0622 (-0.0616) | 3.2× |

El bruto agregado es negativo (−0,0148 R/op), así que no hay una ventaja positiva que comer: el coste profundiza la pérdida. En las 8 celdas con bruto positivo (todas fin 10:30 y entrada 15:00, +0,001 a +0,019 R), el coste 001 (0,052–0,083 R; **4,3–52,9×** la ventaja bruta) y el 006 (0,037–0,059 R; **3,0–37,7×**) se comen la ventaja y dejan la neta negativa.

## 4. Spread p75 en la ventana 15:00–16:00 NY

Noviembre de 2026: NY en EST (UTC−5); 15:00–16:00 NY = **20:00–21:00 UTC**. La fila de las 20:00 UTC es la ventana de la estrategia; la de las 21:00 UTC es 16:00–17:00 NY, fuera de la sesión.

| Hora NY | Hora UTC | CFD-001 p75 bps | CFD-001 p75 pts* | CFD-006 p75 bps | CFD-006 p75 pts* |
|---|---:|---:|---:|---:|---:|
| 14:00–15:00 | 19:00 | 0.5396 | 1.43 | 0.3753 | 0.99 |
| 15:00–16:00 | 20:00 | 0.5358 | 1.42 | 0.3770 | 1.00 |
| 16:00–17:00 | 21:00 | 0.7846 | 2.08 | 0.3789 | 1.00 |

*Puntos al último cierre del 2026-11-19 20:00 UTC (26.513,83). Días de medición: **CFD-001 = 7 días** (2026-11-12 20:01:12 → 2026-11-19 20:01:11, 18.000 ticks en la hora 20 UTC); **CFD-006 = 1 día** (2026-11-19 16:51:22 → 2026-11-20 16:51:20, 3.600 ticks en la hora 20 UTC). La muestra de CFD-006 es corta.

El backtest usa el p75 global de los p75 horarios: 1,945476 pts (CFD-001) y 2,097528 pts (CFD-006), más conservador que el p75 de la ventana 15:00–16:00 (≈1,42 y ≈1,00 pts). Aun con ese sesgo conservador, el bruto no alcanza.

## 5. Conclusión (3 líneas)

1. **No hay ventaja bruta agregada en IS**: la expectativa bruta media es −0,0148 R/op; solo 8 de 32 celdas (fin 10:30, entrada 15:00) tienen un bruto positivo pequeño, +0,001 a +0,019 R.
2. **El coste elimina esa ventaja**: CFD-001 cuesta 0,0666 R/op y CFD-006 0,0474 R/op (cota inferior); las 32 celdas quedan negativas y solo 1 de 128 pliegues es positivo con CFD-001 (8/128 con CFD-006).
3. **Entre firmas no cambia la conclusión**: CFD-006 es ≈29 % más barata y mejora la neta ≈0,019 R, pero la mejor celda pasa de −0,0464 R (CFD-001) a −0,0310 R (CFD-006): sigue sin ventaja en IS.

**Nota: sin ventaja en IS.**
