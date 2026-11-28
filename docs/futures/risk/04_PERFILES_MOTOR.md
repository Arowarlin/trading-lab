# Seis perfiles de riesgo con el motor real (FUT-A + ORPAE), 3 programas 50K

**Fecha:** 2026-11-28 · **Autor:** Claude Code · **Estado:** SIMULADO e HIPOTÉTICO. Ninguna estrategia
está validada; las ventajas son escenarios, no mediciones.
**Diferencia con `01` y `03`:** aquellos usaban simuladores de investigación (`risk_sim.py`,
`programs_compare.py`). Este estudio usa el **motor de producción** (`src/tradinglab/prop_economics/`), con
las reglas completas de cada YAML:
- consistencia de la evaluación;
- trailing EOD o intradía con bloqueo absoluto y bloqueo al pedir payout;
- colchón de MFF;
- escalado de Lucid (20/30/40 micros);
- máximo de 5 payouts de Lucid antes de pasar a Live;
- topes de contratos;
- tarifas y plazos de cobro.

## 1. Método

- **Código:** `sim/engine_profiles.py`.
- **Simulación:**
  - 4.000 caminos por celda, semilla 13, presupuesto de 1.500 USD;
  - horizontes de 182, 365 y 730 días naturales (≈ 6, 12 y 24 meses, calendario CME);
  - inicio el 2027-01-04;
  - números aleatorios comunes entre perfiles.
- **Estrategia hipotética:**
  - 1 operación MNQ al día, stop de 25 puntos y objetivo de 1,5 R;
  - ganadoras con excursión adversa U(0,1)·riesgo; perdedoras con excursión favorable U(0,1)·riesgo
    (afecta al trailing intradía de MFF).
- **Ventaja bruta en R:** 0, +0,08, +0,13 y +0,20.
- **Coste por contrato, ida y vuelta** (comisión verificada + 1 tick por lado): Topstep 2,22 USD,
  MFF 2,90 y Lucid 2,00.
- **Perfiles** (riesgo por operación, con el máximo de pérdida de 2.000 USD):

| Perfil | Filosofía | Política |
|---|---|---|
| A | Conservador | riesgo fijo de 250 USD (12,5 % del MLL) |
| B | Moderado | 500 USD (25 %) |
| C | Agresivo | 750 USD (37,5 %) |
| D | Muy agresivo | 1.000 USD (50 %) |
| E | Extremo experimental | 1.500 USD (75 %) |
| F | Adaptativo | min(1.000, 0,3·colchón), mínimo 1 micro; antimartingala por construcción |

- **Supuestos explícitos:**
  - Topstep: plazo de cobro de 3 días (Sin datos en el YAML).
  - MFF: sin tope por payout y fracción del 100 % por encima del colchón (Sin datos: la fuente no
    publica tope).
  - Lucid: tarifa de evaluación de 125 USD (Sin datos: web 403).
  - Contratos por perfil: suelo(riesgo / (50 + coste)), por ejemplo 9 MNQ para B en Topstep. Después
    se aplican los topes del programa.
- **Regla de elección** (`01 §5`, sin cambios): máximo EV a 12 meses con mediana > 0, ruina del
  presupuesto a 24 meses ≤ 10 % y P(neto > 0) ≥ 60 %. Si ningún perfil cumple: no comprar.

## 2. Resultados (`sim/engine_profiles.json`)

- USD netos (cobrado − tarifas) con un presupuesto de 1.500.
- «Ruina» = el presupuesto no alcanza para otra evaluación.
- «Capital P95» = salida de caja máxima en el percentil 95.

**Control de calidad:**
- Una primera ejecución usaba pools sintéticos sorteados libremente. Con 1.000 días, la ventaja
  realizada salió unos +0,05 R por encima de la nominal (el caso sin ventaja tenía +0,008 R).
- Se corrigió el generador para que use la proporción **exacta** de ganadoras (commit `bd59114`, con
  test). Estas tablas son las de la ejecución corregida y la primera se descarta.

### Topstep 50K


**Ventaja sin ventaja bruta (0 R)** · elegido con la regla de risk/01 §5: **ninguno → no comprar**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | −327 | −601 (±7) | −686 | −835 / 19 | 0,05 | 0,32 | −1.150 | 9,9 % | 1.519 |
| B_moderado_500 | −22 | 104 (±29) | −501 | −1.471 / 3.803 | 0,36 | 0,78 | 295 | 41,3 % | 1.491 |
| C_agresivo_750 | 397 | 958 (±56) | −657 | −1.480 / 8.083 | 0,44 | 0,66 | 1.630 | 54,6 % | 1.484 |
| D_muy_agresivo_1000 | 628 | 1.279 (±75) | −1.382 | −1.482 / 11.049 | 0,37 | 0,52 | 2.120 | 64,5 % | 1.482 |
| E_extremo_1500 | 125 | 590 (±86) | −1.474 | −1.480 / 12.111 | 0,19 | 0,34 | 973 | 83,1 % | 1.492 |
| F_adaptativo_colchon | −207 | −387 (±14) | −686 | −884 / 1.243 | 0,16 | 0,36 | −715 | 14,5 % | 1.521 |

**Ventaja débil (+0,08 R bruta)** · elegido con la regla de risk/01 §5: **ninguno → no comprar**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | −217 | −327 (±13) | −616 | −835 / 1.245 | 0,17 | 0,65 | −558 | 3,9 % | 1.472 |
| B_moderado_500 | 590 | 1.497 (±46) | 617 | −1.371 / 7.419 | 0,61 | 0,93 | 3.083 | 16,4 % | 1.478 |
| C_agresivo_750 | 1.743 | 3.776 (±91) | 2.201 | −1.480 / 15.241 | 0,66 | 0,80 | 7.181 | 30,6 % | 1.480 |
| D_muy_agresivo_1000 | 2.360 | 4.886 (±128) | 1.724 | −1.480 / 21.255 | 0,56 | 0,66 | 9.312 | 42,4 % | 1.482 |
| E_extremo_1500 | 1.844 | 4.158 (±159) | −1.429 | −1.480 / 28.534 | 0,35 | 0,47 | 7.956 | 66,2 % | 1.480 |
| F_adaptativo_colchon | 42 | 192 (±27) | −522 | −835 / 3.390 | 0,33 | 0,56 | 458 | 4,5 % | 1.474 |

**Ventaja moderada (+0,13 R bruta)** · elegido con la regla de risk/01 §5: **B_moderado_500**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | −91 | 11 (±18) | −465 | −786 / 2.387 | 0,31 | 0,81 | 169 | 1,7 % | 1.410 |
| B_moderado_500 | 1.218 | 2.895 (±61) | 1.761 | −1.173 / 10.689 | 0,76 | 0,97 | 6.023 | 7,4 % | 1.454 |
| C_agresivo_750 | 2.954 | 6.642 (±118) | 5.010 | −1.478 / 21.177 | 0,79 | 0,87 | 13.180 | 18,6 % | 1.480 |
| D_muy_agresivo_1000 | 3.858 | 8.622 (±165) | 6.044 | −1.480 / 29.334 | 0,68 | 0,74 | 17.500 | 30,8 % | 1.480 |
| E_extremo_1500 | 3.464 | 8.095 (±211) | −1.378 | −1.480 / 36.961 | 0,45 | 0,55 | 17.007 | 54,6 % | 1.480 |
| F_adaptativo_colchon | 323 | 842 (±43) | −115 | −786 / 5.276 | 0,47 | 0,70 | 1.907 | 1,1 % | 1.421 |

**Ventaja sólida (+0,20 R bruta)** · elegido con la regla de risk/01 §5: **C_agresivo_750**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | 221 | 765 (±29) | 97 | −737 / 4.453 | 0,53 | 0,95 | 1.794 | 0,4 % | 1.238 |
| B_moderado_500 | 2.445 | 5.769 (±85) | 4.551 | −517 / 16.216 | 0,90 | 0,99 | 12.158 | 1,6 % | 1.184 |
| C_agresivo_750 | 5.252 | 12.272 (±158) | 10.820 | −1.431 / 31.856 | 0,90 | 0,94 | 25.894 | 8,3 % | 1.476 |
| D_muy_agresivo_1000 | 6.682 | 16.202 (±216) | 14.962 | −1.480 / 40.681 | 0,81 | 0,84 | 35.940 | 18,4 % | 1.480 |
| E_extremo_1500 | 6.202 | 15.330 (±272) | 10.334 | −1.480 / 42.904 | 0,59 | 0,64 | 35.414 | 41,0 % | 1.480 |
| F_adaptativo_colchon | 1.050 | 2.658 (±77) | 1.287 | −737 / 9.741 | 0,70 | 0,85 | 6.069 | 0,3 % | 1.180 |

### MFF Rapid 50K


**Ventaja sin ventaja bruta (0 R)** · elegido con la regla de risk/01 §5: **ninguno → no comprar**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | −612 | −988 (±9) | −1.045 | −1.463 / −355 | 0,04 | 0,05 | −1.275 | 77,5 % | 1.463 |
| B_moderado_500 | −1.037 | −1.171 (±19) | −1.463 | −1.463 / 529 | 0,06 | 0,21 | −1.321 | 96,2 % | 1.463 |
| C_agresivo_750 | −1.057 | −1.210 (±20) | −1.463 | −1.463 / −251 | 0,05 | 0,24 | −1.356 | 98,2 % | 1.464 |
| D_muy_agresivo_1000 | −1.140 | −1.287 (±19) | −1.463 | −1.463 / −1.312 | 0,03 | 0,20 | −1.389 | 99,1 % | 1.463 |
| E_extremo_1500 | −1.134 | −1.275 (±23) | −1.463 | −1.463 / −1.319 | 0,02 | 0,21 | −1.408 | 99,4 % | 1.463 |
| F_adaptativo_colchon | −507 | −850 (±16) | −1.045 | −1.463 / 876 | 0,08 | 0,12 | −1.125 | 77,8 % | 1.463 |

**Ventaja débil (+0,08 R bruta)** · elegido con la regla de risk/01 §5: **ninguno → no comprar**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | −416 | −367 (±20) | −836 | −1.254 / 2.289 | 0,19 | 0,22 | −124 | 32,8 % | 1.463 |
| B_moderado_500 | −368 | −317 (±40) | −1.463 | −1.463 / 5.379 | 0,21 | 0,40 | −381 | 80,5 % | 1.463 |
| C_agresivo_750 | −354 | −409 (±46) | −1.463 | −1.463 / 6.121 | 0,15 | 0,37 | −522 | 88,5 % | 1.464 |
| D_muy_agresivo_1000 | −609 | −750 (±41) | −1.463 | −1.463 / 4.398 | 0,09 | 0,31 | −941 | 94,2 % | 1.463 |
| E_extremo_1500 | −626 | −782 (±47) | −1.463 | −1.463 / 3.653 | 0,07 | 0,29 | −970 | 96,1 % | 1.463 |
| F_adaptativo_colchon | −189 | −157 (±28) | −836 | −1.254 / 3.623 | 0,21 | 0,25 | −10 | 34,9 % | 1.463 |

**Ventaja moderada (+0,13 R bruta)** · elegido con la regla de risk/01 §5: **ninguno → no comprar**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | −236 | 354 (±30) | −627 | −1.254 / 4.521 | 0,36 | 0,41 | 1.688 | 12,0 % | 1.463 |
| B_moderado_500 | 323 | 903 (±59) | −1.397 | −1.463 / 8.988 | 0,38 | 0,55 | 1.530 | 62,8 % | 1.463 |
| C_agresivo_750 | 383 | 735 (±71) | −1.463 | −1.463 / 11.211 | 0,26 | 0,46 | 1.223 | 76,8 % | 1.463 |
| D_muy_agresivo_1000 | −35 | −8 (±63) | −1.463 | −1.463 / 9.294 | 0,16 | 0,39 | 48 | 87,0 % | 1.463 |
| E_extremo_1500 | −11 | −31 (±74) | −1.463 | −1.463 / 10.616 | 0,12 | 0,34 | −61 | 91,3 % | 1.463 |
| F_adaptativo_colchon | 160 | 643 (±42) | −627 | −1.045 / 6.163 | 0,35 | 0,38 | 1.620 | 12,9 % | 1.463 |

**Ventaja sólida (+0,20 R bruta)** · elegido con la regla de risk/01 §5: **F_adaptativo_colchon**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | 207 | 2.095 (±45) | 1.444 | −836 / 7.859 | 0,67 | 0,70 | 6.225 | 1,5 % | 1.254 |
| B_moderado_500 | 1.792 | 3.808 (±90) | 2.434 | −1.463 / 14.989 | 0,62 | 0,72 | 7.133 | 36,3 % | 1.463 |
| C_agresivo_750 | 2.014 | 3.638 (±115) | −1.365 | −1.463 / 18.669 | 0,44 | 0,60 | 6.423 | 56,7 % | 1.463 |
| D_muy_agresivo_1000 | 1.301 | 2.152 (±108) | −1.463 | −1.463 / 17.091 | 0,30 | 0,49 | 3.546 | 72,2 % | 1.463 |
| E_extremo_1500 | 1.317 | 2.054 (±124) | −1.463 | −1.463 / 20.861 | 0,22 | 0,41 | 3.286 | 80,0 % | 1.463 |
| F_adaptativo_colchon | 1.030 | 2.753 (±68) | 1.193 | −836 / 11.668 | 0,61 | 0,63 | 6.190 | 1,3 % | 1.254 |

### Lucid Flex 50K (tarifa 125, supuesta)


**Ventaja sin ventaja bruta (0 R)** · elegido con la regla de risk/01 §5: **ninguno → no comprar**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | −285 | −404 (±9) | −500 | −875 / 653 | 0,14 | 0,24 | −648 | 3,6 % | 1.500 |
| B_moderado_500 | −363 | −383 (±28) | −1.279 | −1.500 / 3.451 | 0,27 | 0,64 | −452 | 67,3 % | 1.500 |
| C_agresivo_750 | −215 | −166 (±43) | −1.485 | −1.500 / 5.980 | 0,24 | 0,50 | −191 | 78,8 % | 1.500 |
| D_muy_agresivo_1000 | −378 | −414 (±43) | −1.500 | −1.500 / 6.163 | 0,17 | 0,36 | −547 | 86,9 % | 1.500 |
| E_extremo_1500 | −996 | −1.137 (±27) | −1.500 | −1.500 / 577 | 0,05 | 0,19 | −1.332 | 97,4 % | 1.500 |
| F_adaptativo_colchon | −169 | −235 (±14) | −625 | −875 / 1.632 | 0,23 | 0,29 | −349 | 4,0 % | 1.500 |

**Ventaja débil (+0,08 R bruta)** · elegido con la regla de risk/01 §5: **ninguno → no comprar**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | −71 | 116 (±14) | −150 | −750 / 1.999 | 0,41 | 0,55 | 459 | 0,1 % | 1.125 |
| B_moderado_500 | 420 | 1.180 (±43) | 404 | −1.500 / 6.647 | 0,56 | 0,86 | 2.341 | 29,5 % | 1.500 |
| C_agresivo_750 | 1.087 | 2.120 (±73) | −95 | −1.500 / 11.429 | 0,49 | 0,68 | 3.732 | 50,4 % | 1.500 |
| D_muy_agresivo_1000 | 870 | 1.574 (±78) | −1.477 | −1.500 / 12.216 | 0,36 | 0,51 | 2.695 | 65,7 % | 1.500 |
| E_extremo_1500 | −263 | −271 (±54) | −1.500 | −1.500 / 7.975 | 0,15 | 0,29 | −351 | 88,6 % | 1.500 |
| F_adaptativo_colchon | 160 | 466 (±24) | −236 | −750 / 3.591 | 0,46 | 0,51 | 1.038 | 0,1 % | 1.125 |

**Ventaja moderada (+0,13 R bruta)** · elegido con la regla de risk/01 §5: **F_adaptativo_colchon**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | 131 | 588 (±18) | 206 | −625 / 2.948 | 0,63 | 0,74 | 1.488 | 0,0 % | 750 |
| B_moderado_500 | 1.093 | 2.587 (±53) | 1.794 | −1.500 / 9.020 | 0,75 | 0,93 | 5.285 | 12,9 % | 1.500 |
| C_agresivo_750 | 2.197 | 4.405 (±90) | 3.503 | −1.500 / 15.127 | 0,66 | 0,78 | 8.272 | 32,2 % | 1.500 |
| D_muy_agresivo_1000 | 1.975 | 3.678 (±100) | 310 | −1.500 / 16.145 | 0,51 | 0,61 | 6.675 | 50,0 % | 1.500 |
| E_extremo_1500 | 437 | 848 (±78) | −1.500 | −1.500 / 13.000 | 0,24 | 0,37 | 1.381 | 79,0 % | 1.500 |
| F_adaptativo_colchon | 476 | 1.115 (±31) | 417 | −625 / 5.052 | 0,62 | 0,65 | 2.383 | 0,0 % | 875 |

**Ventaja sólida (+0,20 R bruta)** · elegido con la regla de risk/01 §5: **B_moderado_500**

| Perfil | EV 6 m | EV 12 m (±EE) | Mediana 12 m | P5 / P95 12 m | P(neto>0) | P(≥1 payout) | EV 24 m | Ruina 24 m | Capital P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A_conservador_250 | 518 | 1.485 (±23) | 1.160 | −375 / 4.127 | 0,86 | 0,92 | 3.353 | 0,0 % | 500 |
| B_moderado_500 | 2.299 | 5.214 (±66) | 4.853 | −643 / 12.880 | 0,91 | 0,98 | 10.833 | 2,9 % | 1.375 |
| C_agresivo_750 | 4.131 | 8.602 (±110) | 8.531 | −1.500 / 20.401 | 0,84 | 0,89 | 17.123 | 14,9 % | 1.500 |
| D_muy_agresivo_1000 | 4.080 | 8.013 (±130) | 8.093 | −1.500 / 22.036 | 0,69 | 0,75 | 15.503 | 30,9 % | 1.500 |
| E_extremo_1500 | 1.998 | 3.586 (±117) | −1.500 | −1.500 / 19.065 | 0,40 | 0,50 | 6.511 | 61,1 % | 1.500 |
| F_adaptativo_colchon | 1.181 | 2.601 (±44) | 2.052 | −500 / 8.002 | 0,81 | 0,82 | 5.342 | 0,0 % | 625 |

### Resumen de la elección

| Programa | Ventaja | Perfil elegido | EV 12 m | Mediana 12 m | Ruina 24 m |
|---|---|---|---:|---:|---:|
| Topstep 50K | sin ventaja bruta (0 R) | ninguno → no comprar | — | — | — |
| Topstep 50K | débil (+0,08 R bruta) | ninguno → no comprar | — | — | — |
| Topstep 50K | moderada (+0,13 R bruta) | B_moderado_500 | 2.895 | 1.761 | 7,4 % |
| Topstep 50K | sólida (+0,20 R bruta) | C_agresivo_750 | 12.272 | 10.820 | 8,3 % |
| MFF Rapid 50K | sin ventaja bruta (0 R) | ninguno → no comprar | — | — | — |
| MFF Rapid 50K | débil (+0,08 R bruta) | ninguno → no comprar | — | — | — |
| MFF Rapid 50K | moderada (+0,13 R bruta) | ninguno → no comprar | — | — | — |
| MFF Rapid 50K | sólida (+0,20 R bruta) | F_adaptativo_colchon | 2.753 | 1.193 | 1,3 % |
| Lucid Flex 50K (tarifa 125, supuesta) | sin ventaja bruta (0 R) | ninguno → no comprar | — | — | — |
| Lucid Flex 50K (tarifa 125, supuesta) | débil (+0,08 R bruta) | ninguno → no comprar | — | — | — |
| Lucid Flex 50K (tarifa 125, supuesta) | moderada (+0,13 R bruta) | F_adaptativo_colchon | 1.115 | 417 | 0,0 % |
| Lucid Flex 50K (tarifa 125, supuesta) | sólida (+0,20 R bruta) | B_moderado_500 | 5.214 | 4.853 | 2,9 % |

## 3. Lectura

1. **Sin ventaja, ningún perfil se compra** en ningún programa. Los perfiles agresivos tienen EV positivo
   (convexidad: la pérdida queda limitada a la tarifa), pero la mediana es negativa y la ruina alta.
   - En Topstep con D (1.000 USD): EV a 12 m de 1.279 y mediana de −1.382, con ruina a 24 m del 64,5 %.
   - Es lotería, no ventaja.
2. **Con ventaja débil (+0,08 R bruta, unos +0,04 R neta) tampoco cumple nadie.** El mejor caso, Topstep
   B, tiene mediana positiva (617), pero ruina del 16,4 % (> 10 %). Coincide con la escalera de `01 §5`:
   «no comprar todavía».
3. **Con ventaja moderada (+0,13 R bruta):**
   - **Topstep B (500 USD):** EV a 12 m de 2.895, mediana de 1.761, P(neto > 0) de 0,76 y ruina del
     7,4 %.
   - **Lucid:** solo cumple el **adaptativo F** (EV 1.115, ruina 0 %).
   - **MFF:** no cumple ninguno. Lo penalizan el colchón de 2.100, el trailing intradía y la tarifa de
     209.
4. **Con ventaja sólida (+0,20 R bruta):**
   - **Topstep C (750 USD):** EV de 12.272, mediana de 10.820 y ruina del 8,3 %.
   - **Lucid B (500):** EV de 5.214 y ruina del 2,9 %.
   - **MFF F (adaptativo):** EV de 2.753.
5. **El perfil E (extremo, 1.500 USD) no se elige nunca.** La mediana se hunde y la ruina va del 41 al
   83 %: ser más agresivo que el 37,5 % del MLL no mejora el resultado típico en ninguna fila.
6. **El adaptativo F** tiene la ruina más baja de todos. Sale elegido justo donde los fijos no cumplen
   la restricción de ruina o de mediana (Lucid moderada, MFF sólida). Es el perfil para empezar cuando la
   ventaja es real pero pequeña.

**Salvedades que cambian números:**
- **Topstep XFA:** su plan de escalado es **Sin datos**, así que el motor no limita los contratos en la
  financiada. Si el escalado real arranca con pocos contratos, los perfiles C y D rinden menos. El
  control de ejecución (R02) ya bloquea esas órdenes por «reglas desconocidas» hasta verificar la tabla.
- **Lucid:** está infravalorado (Live no se modela) y depende de su precio (Sin datos).
- **Ventajas hipotéticas:** la decisión real usa la **cota inferior** de la ventaja medida en forward
  (`lab propecon allocate`).

**Conclusión operativa (sin cambios):**
- Sin ventaja validada, no se compran evaluaciones.
- Con la cota inferior en torno a +0,13 R bruta: Topstep con 500 USD por operación, y Lucid con el
  perfil adaptativo como segunda firma.
- Con ≥ +0,20 R: subir a 750 USD en Topstep solo cuando se conozca su escalado.

## 4. Reproducir

```bash
python -I docs/futures/risk/sim/engine_profiles.py --paths 4000 --out docs/futures/risk/sim/engine_profiles.json
```
