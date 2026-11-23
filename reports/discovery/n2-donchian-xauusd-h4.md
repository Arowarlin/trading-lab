# N2 · donchian_vol_h4 XAUUSD H4

Fecha: 2026-11-23. Campaña `n2-donchian-xauusd-h4`. Diagnóstico **solo lectura** sobre IS y sobre el OOS-1 que el pipeline ya leyó (9 candidatos); OOS-2 **nunca** se leyó. No se re-ejecutó la campaña ni se cambió la lógica de selección. `count_tests` = **1730**.

## 1. Ficha

- `donchian_vol_h4` · XAUUSD H4 · Dukascopy · IS 2005-01-01 → 2024-06-30 (99,89 %) · OOS-1 2024-07-01 → 2025-06-30 (100 %).
- 27/27 evaluadas · `n_effective` 6 · 12 en frontera · 9 candidatas · 1 finalista · OOS-1 medio 0.3942.
- La rejilla completa tiene **23/27** con bruto IS > 0 y **16/27** con neto IS > 0. El resumen del operador decía 20/27 brutos; el conteo directo de `gross_expectancy_r` da 23/27. La diferencia no cambia ninguna conclusión.
- `Params` y `Veredicto` de `discovery results` corregidos: los parámetros salen del `grid` guardado en la campaña (`channel_n`, `vol_pct`, `stop_mult`); el veredicto muestra el guardado o, si no existe, la selección (`FINALISTA`, `DESCARTADO`, `NO FINALISTA`).

## 2. Veredicto en una frase

**No hay ventaja de tendencia: lo que queda es deriva del oro capturada por el lado largo y una selección defectuosa que conservó la segunda combinación más débil por IS porque ordenó por OOS-1.**

## 3. Selección: correlación y regla

Candidatas = `rank 0` con IS completa > 0 y pliegues positivos ≥ 2/3 (`engine.py:401-416`): **9**. A las 9 se les leyó OOS-1 y se les aplicó `_select_finalists` (`engine.py:448-497`):

1. Descarta OOS-1 ≤ 0 o PF ≤ 1,1 (`engine.py:465-473`).
2. Ordena por `score = OOS-1 expectancy − 0,001 × complejidad` (`engine.py:475-479`).
3. Acepta en ese orden si `|corr(returns OOS-1)| < 0,7` con **todas** las ya aceptadas; si no, descarta (`engine.py:486-493`).

La correlación se calcula sobre la serie **diaria de OOS-1**, no sobre IS. El que queda primero es el de mayor OOS-1, no el de mejor IS.

| ID | channel_n | vol_pct | stop_mult | IS neto | OOS-1 neto | OOS-1 PF | Ops OOS-1 | Score OOS-1 | corr con 478 | corr máx. con otro | Decisión |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 478 | 40 | 0.7 | 2.5 | 0.0138 | 0.3942 | 2.120 | 16 | 0.374215 | 1.000000 | 1.000000 (466) | **FINALISTA** |
| 467 | 20 | 0.7 | 1.5 | 0.0740 | 0.3434 | 1.696 | 25 | 0.323447 | 0.702384 | 1.000000 (470) | descartada: corr ≥ 0,7 |
| 475 | 40 | 0.6 | 2.5 | 0.0141 | 0.3113 | 1.796 | 17 | 0.291303 | 1.000000 | 1.000000 (472) | descartada: corr ≥ 0,7 |
| 471 | 20 | 0.8 | 2 | 0.0475 | 0.2782 | 1.576 | 19 | 0.258175 | 0.967224 | 0.971506 (466) | descartada: corr ≥ 0,7 |
| 472 | 20 | 0.8 | 2.5 | 0.0600 | 0.2663 | 1.714 | 18 | 0.246338 | 1.000000 | 1.000000 (466) | descartada: corr ≥ 0,7 |
| 466 | 20 | 0.6 | 2.5 | 0.0843 | 0.2266 | 1.676 | 22 | 0.206630 | 1.000000 | 1.000000 (472) | descartada: corr ≥ 0,7 |
| 470 | 20 | 0.8 | 1.5 | 0.1109 | 0.1760 | 1.314 | 22 | 0.156027 | 0.717135 | 1.000000 (464) | descartada: corr ≥ 0,7 |
| 464 | 20 | 0.6 | 1.5 | 0.0956 | 0.1540 | 1.271 | 29 | 0.134039 | 0.702384 | 1.000000 (470) | descartada: corr ≥ 0,7 |
| 484 | 55 | 0.6 | 2.5 | 0.0055 | 0.0844 | 1.172 | 17 | 0.064436 | 0.998888 | 0.998967 (475) | descartada: corr ≥ 0,7 |

**Grupo único G1:** las 9 candidatas están conectadas a 478 con |corr| ≥ 0,702; por eso solo queda una. 464 y 467 están en **0,7024**, justo por encima del umbral 0,7: el grupo es sensible a la serie OOS-1. 466, 472 y 475 dan 1,000; 484, 0,9989; 471, 0,9672; 470, 0,7171.

**S1 confirmada en términos de IS:** 478 tiene IS neto 0.0138 y es la **segunda más débil** de las 9 (solo 484, 0.0055, es peor). La mejor, 470, tiene 0.1109 y fue descartada; 475, la mediana de la rejilla, 0.0141, también. El filtro no conserva la mejor métrica IS: conserva la mejor OOS-1 y luego exige decorrelación.

**Caveat de selección:** como OOS-1 se usa para elegir, el 0,394 de 478 es el máximo de 9 lecturas de OOS-1, no una estimación limpia. El OOS-1 de 478 está sesgado al alza por construcción; no es un holdout virgen.

## 4. Largo vs corto

Neto = cuenta elegida por operación en modo `best`; bruto = sin costes. Todos los valores son R por operación.

| ID | ch | vol | stop | Ops L | Bruto L | Neto L | Ops S | Bruto S | Neto S | Neto total |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 464 | 20 | 0.6 | 1.5 | 316 | 0.2887 | 0.2457 | 321 | -0.0111 | -0.0522 | 0.0956 |
| 465 | 20 | 0.6 | 2 | 283 | 0.2193 | 0.1851 | 290 | -0.0104 | -0.0425 | 0.0697 |
| 466 | 20 | 0.6 | 2.5 | 254 | 0.2277 | 0.1989 | 269 | 0.0029 | -0.0239 | 0.0843 |
| 467 | 20 | 0.7 | 1.5 | 247 | 0.2465 | 0.2038 | 274 | -0.0022 | -0.0429 | 0.0740 |
| 468 | 20 | 0.7 | 2 | 222 | 0.1586 | 0.1245 | 250 | -0.0172 | -0.0492 | 0.0325 |
| 469 | 20 | 0.7 | 2.5 | 208 | 0.1567 | 0.1283 | 233 | 0.0020 | -0.0250 | 0.0473 |
| 470 | 20 | 0.8 | 1.5 | 181 | 0.3126 | 0.2716 | 221 | 0.0188 | -0.0208 | 0.1109 |
| 471 | 20 | 0.8 | 2 | 165 | 0.1927 | 0.1600 | 204 | -0.0123 | -0.0434 | 0.0475 |
| 472 | 20 | 0.8 | 2.5 | 159 | 0.1682 | 0.1402 | 191 | 0.0196 | -0.0067 | 0.0600 |
| 473 | 40 | 0.6 | 1.5 | 258 | 0.3248 | 0.2816 | 246 | -0.1874 | -0.2301 | 0.0319 |
| 474 | 40 | 0.6 | 2 | 233 | 0.1984 | 0.1633 | 229 | -0.1882 | -0.2217 | -0.0275 |
| 475 | 40 | 0.6 | 2.5 | 214 | 0.2064 | 0.1772 | 219 | -0.1184 | -0.1452 | 0.0141 |
| 476 | 40 | 0.7 | 1.5 | 203 | 0.3181 | 0.2753 | 206 | -0.1762 | -0.2177 | 0.0270 |
| 477 | 40 | 0.7 | 2 | 186 | 0.1993 | 0.1647 | 194 | -0.1746 | -0.2073 | -0.0252 |
| 478 | 40 | 0.7 | 2.5 | 175 | 0.1916 | 0.1631 | 186 | -0.1000 | -0.1266 | 0.0138 |
| 479 | 40 | 0.8 | 1.5 | 154 | 0.3170 | 0.2756 | 163 | -0.1818 | -0.2218 | 0.0198 |
| 480 | 40 | 0.8 | 2 | 142 | 0.1897 | 0.1564 | 156 | -0.1859 | -0.2176 | -0.0394 |
| 481 | 40 | 0.8 | 2.5 | 136 | 0.1728 | 0.1447 | 151 | -0.1354 | -0.1611 | -0.0162 |
| 482 | 55 | 0.6 | 1.5 | 239 | 0.3506 | 0.3073 | 217 | -0.2491 | -0.2923 | 0.0220 |
| 483 | 55 | 0.6 | 2 | 215 | 0.2148 | 0.1795 | 202 | -0.2176 | -0.2513 | -0.0294 |
| 484 | 55 | 0.6 | 2.5 | 199 | 0.2178 | 0.1885 | 192 | -0.1572 | -0.1843 | 0.0055 |
| 485 | 55 | 0.7 | 1.5 | 189 | 0.3364 | 0.2936 | 185 | -0.2702 | -0.3125 | -0.0062 |
| 486 | 55 | 0.7 | 2 | 173 | 0.2083 | 0.1737 | 175 | -0.2363 | -0.2693 | -0.0491 |
| 487 | 55 | 0.7 | 2.5 | 163 | 0.1997 | 0.1711 | 167 | -0.1562 | -0.1828 | -0.0080 |
| 488 | 55 | 0.8 | 1.5 | 145 | 0.3574 | 0.3165 | 144 | -0.2910 | -0.3316 | -0.0064 |
| 489 | 55 | 0.8 | 2 | 134 | 0.2088 | 0.1758 | 139 | -0.2917 | -0.3236 | -0.0785 |
| 490 | 55 | 0.8 | 2.5 | 128 | 0.1985 | 0.1705 | 134 | -0.2114 | -0.2372 | -0.0380 |
| **Total** | | | | **5321** | **0.2395** | **0.2040** | **5558** | **-0.1159** | **-0.1497** | **0.0233** |

- **27/27** combinaciones tienen neto largo > 0; **0/27** tienen neto corto > 0. El lado corto pierde en todas.
- Agregado IS: largo **+0.2395 bruto / +0.2040 neto**; corto **-0.1159 bruto / -0.1497 neto**. La ventaja es solo de las compras; el corto es lastre.

### 478 en IS y OOS-1

| Tramo | Ops | Ops L | Bruto L | Neto L | Ops S | Bruto S | Neto S | Bruto total | Neto total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| IS | 361 | 175 | 0.1916 | 0.1631 | 186 | -0.1000 | -0.1266 | 0.0414 | 0.0138 |
| OOS-1 | 16 | 9 | 0.6342 | 0.6177 | 7 | 0.1207 | 0.1069 | 0.4095 | 0.3942 |

478 gana en IS porque el largo (+0,163 neto) supera al corto (−0,127). En OOS-1 ambos lados son positivos, pero 9 operaciones largas (+0,618) frente a 7 cortas (+0,107): el resultado es casi todo largo.

## 5. Deriva del oro

Benchmark: entradas aleatorias **solo largas** en el mismo tramo, con el mismo stop ATR(14) × 2,5 y un horizonte calibrado para igualar el tiempo medio en mercado de 478 (21,64 barras H4 en IS; 20,62 en OOS-1). 1.000 simulaciones, semilla fija 20261123, sin costes. `N` = número de operaciones de 478 en cada tramo.

| Tramo | N ops/sim | Horizonte | Held medio | Estrategia bruto | Azar medio | p5–p95 azar | Percentil estrategia |
|---|---:|---:|---:|---:|---:|---:|---:|
| IS | 361 | 32 | 21.73 | 0.0414 | 0.1490 | 0.0266 … 0.2762 | 7.9 |
| OOS-1 | 16 | 29 | 20.41 | 0.4095 | 0.3079 | -0.2583 … 0.8719 | 61.5 |

En IS la estrategia (0,0414 bruto) está en el **percentil 7,9** del azar largo: peor que comprar aleatoriamente con el mismo tiempo y stop. En OOS-1 (0,4095) está en el **percentil 61,5**: dentro de la distribución del azar, con un intervalo que cruza cero. El benchmark largo con N = número de operaciones largas da percentil 17,5 en IS y 56,3 en OOS-1; el tramo largo de 478 no supera claramente al azar.

### Bruto por año 2005–2024

Mejor por neto IS: **470** (0.1109). Mediana: **475** (0.0141). Finalista: **478** (0.0138). Bruto R/op; 2024 es parcial.

| Año | 470 ops | 470 bruto | 475 ops | 475 bruto | 478 ops | 478 bruto |
|---:|---:|---:|---:|---:|---:|---:|
| 2005 | 24 | 0.6192 | 23 | 0.2951 | 21 | 0.0563 |
| 2006 | 16 | -0.1642 | 21 | -0.1143 | 17 | 0.0156 |
| 2007 | 23 | 0.0764 | 25 | -0.1283 | 19 | -0.1524 |
| 2008 | 24 | 0.1427 | 24 | 0.3140 | 20 | 0.3493 |
| 2009 | 24 | 0.0673 | 25 | -0.0996 | 22 | -0.1375 |
| 2010 | 20 | 0.3487 | 27 | -0.1141 | 22 | -0.1225 |
| 2011 | 24 | 0.3761 | 28 | 0.1774 | 21 | 0.2047 |
| 2012 | 19 | 0.3254 | 18 | 0.1364 | 13 | 0.3993 |
| 2013 | 21 | -0.1404 | 18 | 0.0925 | 17 | -0.1517 |
| 2014 | 16 | 0.1055 | 24 | -0.0562 | 21 | 0.0787 |
| 2015 | 21 | 0.0097 | 22 | -0.0870 | 22 | -0.1954 |
| 2016 | 17 | 0.0448 | 17 | 0.1386 | 12 | -0.0199 |
| 2017 | 19 | 0.5775 | 18 | 0.0004 | 14 | 0.0046 |
| 2018 | 18 | -0.3385 | 17 | -0.0244 | 15 | -0.1299 |
| 2019 | 15 | -0.2595 | 24 | 0.0113 | 19 | 0.1147 |
| 2020 | 19 | 0.1695 | 21 | -0.1990 | 14 | -0.3463 |
| 2021 | 22 | -0.1818 | 21 | 0.0989 | 19 | 0.2101 |
| 2022 | 24 | -0.0000 | 26 | 0.0828 | 24 | -0.0228 |
| 2023 | 25 | 0.6242 | 25 | 0.1561 | 20 | 0.4545 |
| 2024 | 11 | 0.3636 | 9 | 0.3453 | 9 | 0.3453 |

470 tiene años muy fuertes (2005, 2017, 2023) y años negativos (2018, 2019, 2021); 478 alterna positivos y negativos sin un patrón estable. No hay una tendencia consistente que separe la estrategia del oro.

## 6. 478 en OOS-1

- 16 operaciones (9 largas, 7 cortas), neto **0,3942 R/op**, PF **2,120**, bruto 0,4095 R/op.
- Bootstrap de las 16 operaciones (10.000 remuestreos, semilla 20261123): neto 95 % **[-0,1814, 0,9878]**, P(media ≤ 0) = **9,4 %**; bruto 95 % [-0,1661, 0,9985]. El intervalo es muy ancho y cruza cero.
- El benchmark aleatorio largo de OOS-1 da 0,3079 R/op (p5–p95 [-0,2583, 0,8719]); 0,3942 está en el percentil 61,5. **El resultado cabe dentro de lo que produce la deriva del oro con entradas aleatorias.**

## 7. Perturbation Lab (R1) sobre 478

Ejecutado con `lab discovery perturb 478`: solo IS+OOS-1, sin OOS-2 y sin coste DSR. La base es el neto combinado IS+OOS-1 con el perfil de coste de CFD-001 (una cuenta), no el modo `best` de la campaña.

| Prueba | Base | Resultado | P10 | Pasa |
|---|---:|---:|---:|---|
| Ruido OHLC (500) | -0.001586 | -0.014395 | -0.044028 | no |
| Retraso entrada +1 | -0.001586 | -0.012922 | — | no |
| Retraso entrada +2 | -0.001586 | -0.036185 | — | no |
| MC de ejecución (1.000) | -0.001586 | -0.003941 | -0.021522 | no |
| Retraso salida +1 | -0.001586 | 0.014999 | — | — |
| Retraso salida +2 | -0.001586 | 0.011638 | — | — |

La base combinada es **−0,0016 R/op**: con CFD-001, 478 no gana ni en IS+OOS-1. El ruido y el retraso de entrada degradan a −0,013/−0,036; la ejecución deja mediana −0,0039 (39 % de paths positivos). Las tres pruebas quedan `passed = false`. El nivel queda en 2 y el veredicto guardado es `SIN VEREDICTO` porque no hay PBO/WF/OOS-2; no se puede etiquetar ROBUSTA/FRÁGIL sin esas pruebas, pero la falsificación falla.

## 8. Conclusión

**¿Ventaja de tendencia, deriva del oro o selección defectuosa?** Deriva del oro **y** selección defectuosa: el lado largo es el único que gana, su bruto OOS-1 es indistinguible de entradas largas aleatorias y en IS está por debajo de ellas; además, el filtro de correlación conservó la segunda combinación más débil por IS porque ordenó por OOS-1. No hay evidencia de una ventaja de tendencia específica de la estrategia.

No se cambia la lógica de selección ni se re-ejecuta la campaña: la decisión es del operador.

## 9. Reproducibilidad

```powershell
Set-Location E:\trading-lab
.\.venv\Scripts\lab.exe discovery results n2-donchian-xauusd-h4
.\.venv\Scripts\lab.exe discovery perturb 478
.\.venv\Scripts\python.exe -c "from tradinglab.config import DEFAULT_DB; from tradinglab.learning import count_tests; print(count_tests(DEFAULT_DB))"
```

`results` es solo lectura. `perturb` usa IS+OOS-1 y escribe validaciones; no lee OOS-2 ni suma al DSR. No ejecutar `discovery confirm`.
