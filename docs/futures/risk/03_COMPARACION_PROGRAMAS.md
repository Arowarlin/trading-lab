# Comparación de programas 50K: Topstep, MFF Rapid y Lucid Flex (misma estrategia hipotética)

**Fecha:** 2026-11-28 · **Autor:** Claude Code · **Estado:** investigación reproducible. **Ninguna
ventaja está validada**: todas las cifras son condicionales a una ventaja hipotética.
**Pregunta:** con la **misma** estrategia, ¿en qué programa llega más dinero neto al operador, y con qué
mediana y qué colas?

## 1. Método

- **Simulador:** `sim/programs_compare.py` (investigación, no el motor FUT-A). 4.000 caminos por
  celda, semilla 11, presupuesto de tarifas de 1.500 USD y horizontes de 6, 12 y 24 meses de sesión.
- **Estrategia:**
  - 1 operación MNQ al día, stop de 25 puntos y objetivo de 1,5 R;
  - riesgo fijo de 250, 500 o 1.000 USD por operación (5, 10 o 20 MNQ);
  - excursión adversa de las ganadoras U(0,1)·riesgo, vigilada en tiempo real.
- **Ventaja:**
  - **bruta** en R, igual para los tres programas: 0; +0,08; +0,13; +0,20; +0,30;
  - cada programa descuenta **sus** comisiones verificadas más 1 tick de slippage por lado (MNQ, ida y
    vuelta): Topstep 1,22 + 1,00; MFF 1,90 + 1,00; Lucid 1,00 + 1,00 USD;
  - ventaja neta = bruta − coste/50 (Topstep −0,044 R, MFF −0,058 R, Lucid −0,040 R).
- **Reglas:** de los YAML (`docs/futures/04 §8` para Topstep; `research/programs/*.yaml` para MFF y
  Lucid). Lo que se modela:

| Regla | Topstep 50K | MFF Rapid 50K | Lucid Flex 50K |
|---|---|---|---|
| Evaluación | 3.000 · trailing EOD 2.000 (se bloquea en S) · consistencia 55 % · 2 días · 50 micros | 3.000 · trailing EOD 2.000 (bloqueo en S: **supuesto**) · 50 % · 2 días · 50 micros | 3.000 · trailing EOD 2.000 (bloqueo en S + 100) · 40 % · 40 micros |
| Tarifas | 49 USD cada 21 sesiones + 149 de activación | 209 de lista (125 con promoción, en la sensibilidad), pago único | **Sin datos**: barrido de 75, 125, 175 y 225, pago único |
| Financiada | trailing EOD 2.000, bloqueo en 0 y en el primer payout · 20 micros (**supuesto**) | **trailing intradía** 2.000 con P&L no realizado, bloqueo en +100 (discrepancia) · 50 micros | trailing EOD 2.000, bloqueo en +100 y al pedir payout · escalado 20/30/40 micros |
| Payout | 5 días ≥ 150 · 50 % del saldo, hasta 2.000 · mínimo 125 · 90 % · 30 USD de transferencia · 10 sesiones de retraso | colchón de 2.100 que no se retira · todo lo que exceda el colchón, sin tope publicado · mínimo 500 · 90 % · comisión 0 y 2 sesiones (**supuestos**) | 5 días ≥ 150 y ciclo neto > 0 · 50 % del beneficio, hasta 2.000 · mínimo 500 · 90 % · comisión 0 y 3 sesiones (**supuestos**) · **5 payouts y pasa a Live** |

- **Supuesto de modelo en MFF.** En el trailing intradía, las perdedoras alcanzan antes una excursión
  favorable U(0,1)·riesgo, que sube el umbral antes de tocar el stop. Su efecto se mide con
  `mfe_losers = 0` en §4.
- **Lucid Live.** La cuenta que llega a 5 payouts sale del modelo, porque las reglas de Live no están
  verificadas, y el proyecto compra otra evaluación si hay presupuesto. **Esto infravalora a Lucid:**
  lo que se ganaría en Live no se cuenta.
- **Control de reproducción.** Con el coste de `risk_sim.py` (2,5 USD) y las reglas de Topstep, este
  simulador da un EV a 12 meses de 3.182 USD frente a 3.149 de `risk_sim.py` (n = 1.000), dentro del
  error Monte Carlo. Las secuencias aleatorias difieren porque aquí se sortea además la excursión
  favorable.

## 2. Resultados (`sim/programs_compare.json`, 4.000 caminos por celda)

- USD netos recibidos menos tarifas, con un presupuesto de 1.500.
- Lucid, con la tarifa supuesta de 125 USD.
- «Ruina» = el presupuesto no alcanza para otra evaluación.
- «Cuentas» = evaluaciones compradas.

#### Sin ventaja bruta (0 R)

| Programa | Riesgo | μ neta (R) | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto > 0) 12 m | P(≥ 1 payout) 12 m | EV 24 m | Mediana 24 m | Ruina 24 m | Cuentas 24 m |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Topstep | 250 | −0,044 | −332 | −578 (±9) | −735 | −933 / 480 | 0,10 | 0,46 | −1.056 | −1.388 | 31,2 % | 12,9 |
| Topstep | 500 | −0,044 | −29 | 221 (±32) | −439 | −1.525 / 4.292 | 0,40 | 0,81 | 576 | −681 | 43,1 % | 32,0 |
| Topstep | 1.000 | −0,044 | 444 | 1.010 (±70) | −1.476 | −1.625 / 10.792 | 0,36 | 0,55 | 1.802 | −1.476 | 68,4 % | 47,8 |
| MFF Rapid | 250 | −0,058 | −767 | −1.143 (±12) | −1.463 | −1.463 / 135 | 0,06 | 0,10 | −1.274 | −1.463 | 88,9 % | 7,5 |
| MFF Rapid | 500 | −0,058 | −1.004 | −1.136 (±20) | −1.463 | −1.463 / 1.001 | 0,07 | 0,23 | −1.292 | −1.463 | 95,6 % | 10,1 |
| MFF Rapid | 1.000 | −0,058 | −1.106 | −1.250 (±21) | −1.463 | −1.463 / −1.306 | 0,03 | 0,28 | −1.362 | −1.463 | 98,8 % | 13,2 |
| Lucid Flex (125) | 250 | −0,040 | −335 | −493 (±12) | −750 | −1.250 / 975 | 0,16 | 0,38 | −728 | −1.083 | 27,9 % | 12,2 |
| Lucid Flex (125) | 500 | −0,040 | −361 | −332 (±31) | −1.402 | −1.500 / 3.876 | 0,27 | 0,63 | −370 | −1.434 | 71,0 % | 22,5 |
| Lucid Flex (125) | 1.000 | −0,040 | −497 | −537 (±42) | −1.500 | −1.500 / 5.664 | 0,14 | 0,33 | −632 | −1.500 | 89,2 % | 26,4 |

#### Ventaja bruta débil (+0,08 R)

| Programa | Riesgo | μ neta (R) | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto > 0) 12 m | P(≥ 1 payout) 12 m | EV 24 m | Mediana 24 m | Ruina 24 m | Cuentas 24 m |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Topstep | 250 | +0,036 | −185 | −216 (±16) | −616 | −933 / 1.881 | 0,23 | 0,75 | −249 | −797 | 11,6 % | 11,2 |
| Topstep | 500 | +0,036 | 668 | 1.822 (±51) | 942 | −1.478 / 8.204 | 0,64 | 0,92 | 3.860 | 2.928 | 18,5 % | 31,2 |
| Topstep | 1.000 | +0,036 | 2.062 | 4.515 (±118) | 1.367 | −1.584 / 20.595 | 0,57 | 0,69 | 8.999 | 3.673 | 44,8 % | 50,2 |
| MFF Rapid | 250 | +0,022 | −456 | −376 (±26) | −1.045 | −1.463 / 3.187 | 0,23 | 0,33 | −75 | −1.463 | 55,0 % | 7,8 |
| MFF Rapid | 500 | +0,022 | −329 | −299 (±41) | −1.463 | −1.463 / 5.313 | 0,21 | 0,41 | −298 | −1.463 | 81,3 % | 13,8 |
| MFF Rapid | 1.000 | +0,022 | −451 | −533 (±50) | −1.463 | −1.463 / 5.976 | 0,11 | 0,38 | −673 | −1.463 | 92,6 % | 20,9 |
| Lucid Flex (125) | 250 | +0,040 | −45 | 187 (±18) | −155 | −1.000 / 2.654 | 0,41 | 0,68 | 658 | 249 | 3,6 % | 10,9 |
| Lucid Flex (125) | 500 | +0,040 | 504 | 1.324 (±48) | 420 | −1.500 / 7.268 | 0,55 | 0,83 | 2.552 | 1.254 | 36,5 % | 27,1 |
| Lucid Flex (125) | 1.000 | +0,040 | 711 | 1.375 (±78) | −1.500 | −1.500 / 12.328 | 0,33 | 0,49 | 2.354 | −1.500 | 69,7 % | 36,9 |

#### Ventaja bruta moderada (+0,13 R)

| Programa | Riesgo | μ neta (R) | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto > 0) 12 m | P(≥ 1 payout) 12 m | EV 24 m | Mediana 24 m | Ruina 24 m | Cuentas 24 m |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Topstep | 250 | +0,086 | −28 | 198 (±23) | −350 | −886 / 3.101 | 0,37 | 0,88 | 652 | 6 | 5,0 % | 10,5 |
| Topstep | 500 | +0,086 | 1.338 | 3.372 (±67) | 2.335 | −1.341 / 11.773 | 0,78 | 0,97 | 7.203 | 6.109 | 9,0 % | 29,6 |
| Topstep | 1.000 | +0,086 | 3.517 | 8.091 (±150) | 6.141 | −1.580 / 26.632 | 0,70 | 0,77 | 17.397 | 15.208 | 31,4 % | 44,5 |
| MFF Rapid | 250 | +0,072 | −135 | 561 (±38) | −579 | −1.463 / 5.636 | 0,41 | 0,52 | 1.937 | 730 | 27,8 % | 7,4 |
| MFF Rapid | 500 | +0,072 | 416 | 981 (±62) | −1.394 | −1.463 / 9.660 | 0,38 | 0,55 | 1.761 | −1.429 | 63,5 % | 16,8 |
| MFF Rapid | 1.000 | +0,072 | 256 | 473 (±76) | −1.463 | −1.463 / 11.461 | 0,19 | 0,45 | 717 | −1.463 | 84,4 % | 27,8 |
| Lucid Flex (125) | 250 | +0,090 | 235 | 814 (±23) | 417 | −750 / 3.656 | 0,63 | 0,83 | 1.990 | 1.642 | 0,5 % | 10,0 |
| Lucid Flex (125) | 500 | +0,090 | 1.236 | 2.900 (±59) | 2.151 | −1.500 / 9.855 | 0,73 | 0,91 | 5.804 | 5.372 | 18,5 % | 28,1 |
| Lucid Flex (125) | 1.000 | +0,090 | 1.893 | 3.602 (±104) | −1.400 | −1.500 / 16.766 | 0,47 | 0,59 | 6.518 | −1.412 | 53,4 % | 42,7 |

#### Ventaja bruta sólida (+0,20 R)

| Programa | Riesgo | μ neta (R) | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto > 0) 12 m | P(≥ 1 payout) 12 m | EV 24 m | Mediana 24 m | Ruina 24 m | Cuentas 24 m |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Topstep | 250 | +0,156 | 320 | 1.107 (±34) | 357 | −832 / 5.417 | 0,59 | 0,97 | 2.713 | 1.995 | 1,3 % | 9,7 |
| Topstep | 500 | +0,156 | 2.603 | 6.471 (±92) | 5.289 | −445 / 17.482 | 0,91 | 0,99 | 14.053 | 12.867 | 2,6 % | 26,1 |
| Topstep | 1.000 | +0,156 | 5.924 | 14.742 (±186) | 14.707 | −1.576 / 34.353 | 0,82 | 0,85 | 33.504 | 37.237 | 18,9 % | 29,8 |
| MFF Rapid | 250 | +0,142 | 531 | 2.660 (±56) | 1.869 | −1.254 / 9.488 | 0,70 | 0,76 | 6.962 | 6.324 | 6,2 % | 6,0 |
| MFF Rapid | 500 | +0,142 | 1.820 | 3.873 (±93) | 2.362 | −1.463 / 15.241 | 0,61 | 0,72 | 7.497 | 5.964 | 37,9 % | 19,6 |
| MFF Rapid | 1.000 | +0,142 | 1.659 | 2.906 (±125) | −1.436 | −1.463 / 20.434 | 0,31 | 0,55 | 4.932 | −1.451 | 70,4 % | 36,7 |
| Lucid Flex (125) | 250 | +0,160 | 718 | 1.919 (±30) | 1.530 | −375 / 5.401 | 0,85 | 0,96 | 4.320 | 4.055 | 0,0 % | 9,3 |
| Lucid Flex (125) | 500 | +0,160 | 2.534 | 5.749 (±73) | 5.407 | −935 / 13.788 | 0,90 | 0,97 | 11.964 | 11.828 | 5,0 % | 27,0 |
| Lucid Flex (125) | 1.000 | +0,160 | 3.832 | 7.715 (±134) | 7.588 | −1.500 / 22.200 | 0,65 | 0,71 | 14.913 | 16.057 | 35,1 % | 46,0 |

#### Ventaja bruta elevada (+0,30 R)

| Programa | Riesgo | μ neta (R) | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto > 0) 12 m | P(≥ 1 payout) 12 m | EV 24 m | Mediana 24 m | Ruina 24 m | Cuentas 24 m |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Topstep | 250 | +0,256 | 1.251 | 3.574 (±56) | 2.775 | −562 / 10.615 | 0,86 | 1,00 | 8.158 | 7.323 | 0,0 % | 8,9 |
| Topstep | 500 | +0,256 | 5.400 | 13.500 (±136) | 12.264 | 1.787 / 29.781 | 0,99 | 1,00 | 29.773 | 28.252 | 0,2 % | 19,5 |
| Topstep | 1.000 | +0,256 | 10.179 | 25.856 (±194) | 28.350 | −1.480 / 41.941 | 0,93 | 0,94 | 58.943 | 64.754 | 8,0 % | 13,3 |
| MFF Rapid | 250 | +0,242 | 2.161 | 7.347 (±75) | 7.159 | −219 / 15.518 | 0,94 | 0,96 | 17.721 | 17.405 | 0,2 % | 4,0 |
| MFF Rapid | 500 | +0,242 | 4.924 | 10.856 (±134) | 10.425 | −1.463 / 25.401 | 0,86 | 0,90 | 22.266 | 22.819 | 12,6 % | 19,8 |
| MFF Rapid | 1.000 | +0,242 | 5.156 | 9.815 (±207) | 5.227 | −1.463 / 34.299 | 0,54 | 0,68 | 18.445 | 13.414 | 46,2 % | 50,5 |
| Lucid Flex (125) | 250 | +0,260 | 1.689 | 4.106 (±38) | 3.975 | 549 / 8.360 | 0,98 | 1,00 | 8.880 | 8.727 | 0,0 % | 8,9 |
| Lucid Flex (125) | 500 | +0,260 | 4.968 | 11.035 (±88) | 10.778 | 2.076 / 20.748 | 0,99 | 1,00 | 23.014 | 22.832 | 0,4 % | 23,4 |
| Lucid Flex (125) | 1.000 | +0,260 | 7.464 | 15.605 (±153) | 16.925 | −1.500 / 29.638 | 0,85 | 0,86 | 31.635 | 35.304 | 15,2 % | 44,9 |

## 3. Lucid: precio de equilibrio

El precio de LucidFlex 50K es **Sin datos** (la web dio 403). Barrido de la tarifa de evaluación:

#### Lucid Flex: EV / mediana a 12 m según la tarifa de evaluación (USD)

| Ventaja bruta | Riesgo | Tarifa 75 | Tarifa 125 | Tarifa 175 | Tarifa 225 | Tarifa de equilibrio del EV |
|---|---:|---|---|---|---|---:|
| 0 R | 250 | −147 / −450 | −493 / −750 | −803 / −1.050 | −992 / −1.350 | < 75 |
| 0 R | 500 | 498 / −169 | −332 / −1.402 | −770 / −1.400 | −1.003 / −1.350 | ≈ 105 |
| 0 R | 1.000 | 639 / −1.500 | −537 / −1.500 | −1.002 / −1.400 | −1.154 / −1.350 | ≈ 102 |
| +0,08 R | 250 | 479 / 120 | 187 / −155 | −100 / −425 | −355 / −675 | ≈ 158 |
| +0,08 R | 500 | 2.254 / 1.511 | 1.324 / 420 | 509 / −1.154 | −72 / −1.328 | ≈ 219 |
| +0,08 R | 1.000 | 3.526 / 1.788 | 1.375 / −1.500 | 144 / −1.400 | −450 / −1.350 | ≈ 187 |
| +0,13 R | 250 | 1.083 / 682 | 814 / 417 | 546 / 152 | 290 / −108 | > 225 |
| +0,13 R | 500 | 3.785 / 3.086 | 2.900 / 2.151 | 1.941 / 729 | 1.133 / −987 | > 225 |
| +0,13 R | 1.000 | 6.276 / 5.913 | 3.602 / −1.400 | 1.730 / −1.400 | 620 / −1.350 | > 225 |
| +0,20 R | 250 | 2.167 / 1.767 | 1.919 / 1.530 | 1.671 / 1.283 | 1.424 / 1.034 | > 225 |
| +0,20 R | 500 | 6.524 / 6.135 | 5.749 / 5.407 | 4.767 / 4.374 | 3.777 / 3.031 | > 225 |
| +0,20 R | 1.000 | 10.834 / 11.388 | 7.715 / 7.588 | 5.090 / −1.350 | 3.204 / −1.350 | > 225 |
| +0,30 R | 250 | 4.344 / 4.220 | 4.106 / 3.975 | 3.868 / 3.731 | 3.630 / 3.496 | > 225 |
| +0,30 R | 500 | 11.651 / 11.397 | 11.035 / 10.778 | 10.279 / 10.148 | 9.344 / 9.408 | > 225 |
| +0,30 R | 1.000 | 18.390 / 19.038 | 15.605 / 16.925 | 12.288 / 14.200 | 9.643 / 9.495 | > 225 |

**Lectura:**
- **Con ventaja moderada o mayor,** Lucid tiene EV positivo con cualquier tarifa hasta 225 USD.
- **Con ventaja débil (+0,08 R bruta),** la tarifa de equilibrio está entre unos 160 y 220 USD.
- **Frente a Topstep (riesgo de 500, +0,13 R),** Lucid solo le iguala si cuesta **unos 98 USD o menos**.
  Interpolación entre 75 (3.785) y 125 (2.900) frente a los 3.372 de Topstep.
- **Sin ventaja bruta y con tarifa de 75,** el EV es positivo y la mediana negativa: la convexidad de
  las reglas otra vez, no una ventaja.

## 4. Sensibilidad de MFF (`sim/programs_compare_mff_sens.json`)

EV y mediana a 12 meses y ruina a 24 meses, en USD. Error estándar del EV: entre 12 y 95.

| Variante | Ventaja bruta | Riesgo | EV 12 m | Mediana 12 m | P(neto > 0) | Ruina 24 m |
|---|---:|---:|---:|---:|---:|---:|
| Base (209 de lista; MFE U(0,1)) | +0,13 R | 250 | 561 | −579 | 0,41 | 27,8 % |
| Base | +0,13 R | 500 | 981 | −1.394 | 0,38 | 63,5 % |
| Base | +0,20 R | 500 | 3.873 | 2.362 | 0,61 | 37,9 % |
| `mfe_losers = 0` | +0,13 R | 500 | 1.390 | −1.306 | 0,43 | 57,2 % |
| Promoción a 125 | +0,13 R | 250 | 936 | −220 | 0,47 | 2,7 % |
| Promoción a 125 | +0,13 R | 500 | **2.385** | **1.302** | 0,60 | 35,1 % |
| Promoción a 125 | +0,20 R | 500 | 5.601 | 4.734 | 0,81 | 14,9 % |
| Promoción a 125 + `mfe_losers = 0` | +0,13 R | 500 | 2.851 | 1.898 | 0,65 | 29,2 % |
| Base, sin ventaja bruta | 0 | 500 | −1.137 | −1.463 | 0,07 | 95,6 % |

**Lectura:**
- **En MFF Rapid, el precio de la evaluación domina.** Con el mismo presupuesto, 209 frente a 125 USD
  cambia el número de intentos y hace pasar el EV de 981 a 2.385 (riesgo 500, +0,13 R).
- **El supuesto de la excursión favorable** en el trailing intradía mueve el EV entre un 18 % y un
  42 % en las celdas con ventaja.
- **Sin ventaja bruta, MFF pierde casi todo el presupuesto:** ruina del 96 % a 24 meses con 500 USD
  de riesgo.

## 5. Lectura y recomendación condicional

**Regla de decisión** (`01 §5`, sin cambios): maximizar el EV a 12 meses **sujeto a** mediana a
12 m > 0, ruina a 24 m ≤ 10 % y P(neto > 0) ≥ 0,60, con la **cota inferior** de la ventaja medida.

| Ventaja bruta (cota inferior) | Celdas que cumplen | Elegida | EV / mediana 12 m | Ruina 24 m |
|---|---|---|---:|---:|
| 0 | ninguna (todas las medianas < 0) | **no comprar** | — | — |
| +0,08 R | ninguna: Topstep 500 tiene una ruina del 18,5 % y Lucid 250 una mediana < 0 | **no comprar todavía** (con tolerancia del 20 %: Topstep 500, EV 1.822) | — | — |
| +0,13 R | Topstep 500; Lucid 250 | **Topstep 50K, 500 USD** | 3.372 / 2.335 | 9,0 % |
| +0,20 R | Topstep 500; Lucid 500 y 250; MFF 250 | **Topstep 50K, 500 USD** (Lucid 500 casi igual: 5.749 / 5.407 con 5,0 %) | 6.471 / 5.289 | 2,6 % |
| +0,30 R | Topstep 1.000 y 500; Lucid 500 y 250; MFF 250 | **Topstep 50K, 1.000 USD** (si el escalado del XFA permite 20 micros) | 25.856 / 28.350 | 8,0 % |

**Por qué gana Topstep en este modelo:**
- el intento más barato (49 USD cada 21 sesiones);
- un objetivo y unos payouts que se alcanzan con 500 USD de riesgo.

**Lo que este modelo no incluye y le resta:**
- la **API de ProjectX** si se automatiza: 14,50 USD/mes con el código `topstep`, unos 174 USD a
  12 meses. No cambia el orden con +0,13 R (3.198 frente a 2.900 de Lucid a 125);
- **NT8 no está soportado** en Topstep: hace falta el adaptador de ProjectX (FUT-J3) o el ticket
  semimanual.

**MFF Rapid** sale el último con ventaja débil o moderada:
- el pago único de 209 USD da menos intentos con el mismo presupuesto;
- el trailing **intradía** con P&L no realizado;
- el colchón de 2.100 que no se retira;
- con la promoción a 125 y una ventaja ≥ +0,20 R, es competitivo (§4).

**Lucid Flex:**
- tiene las comisiones más bajas y la ruina más baja con 250 USD de riesgo;
- su valor depende del **precio, que es Sin datos**: con ≤ ~98 USD iguala o supera a Topstep en la
  celda de referencia;
- además está **infravalorado**: las cuentas que llegan a 5 payouts pasan a Live, que no se modela.

**Recomendación (condicional, nada se compra sin ventaja validada):**
1. **Hoy:** no comprar evaluaciones. Ninguna estrategia está validada y, sin ventaja, todas las
   medianas son negativas.
2. **Con ventaja validada de unos +0,13 R bruta en forward** (≈ +0,08 R neta): Topstep 50K con
   500 USD de riesgo como programa principal.
   - Si el precio de Lucid se confirma barato, Lucid Flex con 250 USD como segunda firma: ruina
     del 0,5 %, otra regla y otro riesgo de firma.
3. **Con ≥ +0,20 R:** Topstep 500 y Lucid 500 en paralelo, y MFF Rapid solo con promoción.
4. **Pendiente de datos que cambia la decisión:**
   - el precio de Lucid (operador, con navegador);
   - el escalado real del XFA de Topstep;
   - las reglas de Lucid Live;
   - el coste y el plazo reales de los cobros de MFF (Rise) y Lucid.

**Limitaciones:**
- una cuenta a la vez por camino: la cartera multicuenta está en `01 §4`;
- operaciones independientes: el clustering está en `01` (regímenes);
- payouts siempre aprobados;
- los supuestos marcados en §1.

**Confianza:**
- **alta** en el orden relativo con ventaja moderada (diferencias de muchos errores estándar);
- **baja** en los niveles absolutos, que dependen de la ventaja hipotética.

## 6. Reproducir

```bash
python -I docs/futures/risk/sim/programs_compare.py --paths 4000 --out docs/futures/risk/sim/programs_compare.json
```
