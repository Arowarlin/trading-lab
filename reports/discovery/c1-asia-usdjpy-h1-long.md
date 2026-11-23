# C1 · asia_range_reversion USDJPY H1

Fecha: 2026-11-22. Campaña `c1-asia-usdjpy-h1-long`, `tl2-c1-fix` + run del operador. Este informe es **solo lectura**: únicamente IS y métricas ya calculadas por el pipeline. No se leyó OOS-1 (el pipeline no lo calculó: `OOS-1 medio None`) y **nunca** se leyó OOS-2. No se registró, aprobó, ejecutó ni confirmó nada.

## 1. Ficha de la campaña

- Plantilla: `asia_range_reversion` · USDJPY H1 · sesión Asia/Tokyo 18:00–03:00 · flat 02:45.
- IS: 2010-01-01 → 2024-06-30 (cobertura 99,91 %, `status: warn` por 4 huecos no programados).
- Rejilla: 3 × 3 × 3 = **27** combinaciones (threshold 15/20/25 · stop ATR 1,5/2,0/2,5 · target R:R 1,5/2,0/2,5).
- Resultado: **27/27 evaluadas**, **3 pruebas efectivas** (clusters por correlación), **8 en frontera**, **0 finalistas**, `OOS-1 medio None`.
- Estado: `done` · aprobada por `operator` el 2026-11-23T02:07:18.646+00:00 · `count_tests` = **1703** (la aprobación ya contó las 27; este informe no añade pruebas).
- `disc_validations`: 0. No hay PBO, WF ni OOS-1 que leer.

## 2. Veredicto

**Clasificación Edge Map: sin edge bruto.** No es un caso de "edge bruto que el coste elimina": el bruto ya es negativo en las 27 combinaciones antes de costes (mediana **−0,0533 R/op**, mejor **−0,0291 R/op**); el coste solo agranda la pérdida.

Una frase: **la hipótesis no tiene edge bruto en IS; no hay nada que rescatar con otra configuración de esta rejilla.**

## 3. Resultado por combinación (27)

Neto CF1/CF6 = expectancy en R aplicando el cost book de cada cuenta a las mismas operaciones IS (recalculado en lectura, sin OOS). `cost_R` = mediana del coste por operación que guarda el pipeline; no se usa para recomponer el neto. `Pliegues+` = pliegues con expectancy neta CF6 > 0. El `expectancy_r` de `discovery results` es el neto de la cuenta elegida por operación en modo `best`; en 3 de 27 combinaciones (446, 455, 459) elige CF1 en el 2–5 % de las operaciones y difiere del neto puro CF6 en menos de 0,0007 R. Aquí se muestran las cuentas puras.

| ID | Thr | Stop | RR | Ops | Bruto R | Neto CF1 | Neto CF6 | cost_R CF1 | cost_R CF6 | PF bruto | PF CF1 | PF CF6 | Pliegues+ | Rank | Control exacto de salida |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 437 | 15 | 1.5 | 1.5 | 393 | -0.0965 | -0.1904 | -0.1745 | 0.0823 | 0.0685 | 0.779 | 0.619 | 0.643 | 1/4 | 3 | rank 3 > 0 (dominada) |
| 438 | 15 | 1.5 | 2 | 391 | -0.0925 | -0.1899 | -0.1735 | 0.0893 | 0.0745 | 0.789 | 0.623 | 0.647 | 1/4 | 2 | rank 2 > 0 (dominada) |
| 439 | 15 | 1.5 | 2.5 | 391 | -0.0773 | -0.1758 | -0.1592 | 0.0911 | 0.0763 | 0.824 | 0.652 | 0.677 | 1/4 | 2 | rank 2 > 0 (dominada) |
| 440 | 15 | 2 | 1.5 | 383 | -0.1203 | -0.1925 | -0.1804 | 0.0664 | 0.0553 | 0.680 | 0.544 | 0.564 | 0/4 | 1 | rank 1 > 0 (dominada) |
| 441 | 15 | 2 | 2 | 383 | -0.1032 | -0.1763 | -0.1640 | 0.0677 | 0.0566 | 0.726 | 0.584 | 0.605 | 1/4 | 1 | rank 1 > 0 (dominada) |
| 442 | 15 | 2 | 2.5 | 382 | -0.0848 | -0.1584 | -0.1461 | 0.0686 | 0.0575 | 0.775 | 0.626 | 0.648 | 1/4 | 1 | rank 1 > 0 (dominada) |
| 443 | 15 | 2.5 | 1.5 | 375 | -0.1021 | -0.1604 | -0.1507 | 0.0537 | 0.0456 | 0.682 | 0.552 | 0.571 | 1/4 | 0 | IS completa -0.15066045383991786 ≤ 0 |
| 444 | 15 | 2.5 | 2 | 374 | -0.0804 | -0.1392 | -0.1294 | 0.0544 | 0.0461 | 0.750 | 0.611 | 0.632 | 1/4 | 0 | IS completa -0.12937978810289721 ≤ 0 |
| 445 | 15 | 2.5 | 2.5 | 372 | -0.0597 | -0.1188 | -0.1089 | 0.0548 | 0.0462 | 0.812 | 0.665 | 0.687 | 1/4 | 0 | IS completa -0.10892386778043585 ≤ 0 |
| 446 | 20 | 1.5 | 1.5 | 1361 | -0.0661 | -0.1541 | -0.1391 | 0.0795 | 0.0655 | 0.845 | 0.682 | 0.707 | 0/4 | 2 | rank 2 > 0 (dominada) |
| 447 | 20 | 1.5 | 2 | 1355 | -0.0543 | -0.1458 | -0.1305 | 0.0828 | 0.0680 | 0.875 | 0.703 | 0.728 | 0/4 | 2 | rank 2 > 0 (dominada) |
| 448 | 20 | 1.5 | 2.5 | 1353 | -0.0419 | -0.1350 | -0.1194 | 0.0853 | 0.0702 | 0.904 | 0.726 | 0.752 | 0/4 | 2 | rank 2 > 0 (dominada) |
| 449 | 20 | 2 | 1.5 | 1325 | -0.0547 | -0.1229 | -0.1116 | 0.0620 | 0.0509 | 0.845 | 0.688 | 0.712 | 0/4 | 1 | rank 1 > 0 (dominada) |
| 450 | 20 | 2 | 2 | 1321 | -0.0453 | -0.1151 | -0.1036 | 0.0645 | 0.0529 | 0.872 | 0.709 | 0.734 | 0/4 | 1 | rank 1 > 0 (dominada) |
| 451 | 20 | 2 | 2.5 | 1320 | -0.0411 | -0.1117 | -0.1001 | 0.0653 | 0.0541 | 0.885 | 0.719 | 0.743 | 0/4 | 1 | rank 1 > 0 (dominada) |
| 452 | 20 | 2.5 | 1.5 | 1302 | -0.0393 | -0.0947 | -0.0857 | 0.0503 | 0.0420 | 0.866 | 0.709 | 0.732 | 0/4 | 0 | IS completa -0.08567423730598252 ≤ 0 |
| 453 | 20 | 2.5 | 2 | 1299 | -0.0346 | -0.0910 | -0.0818 | 0.0520 | 0.0433 | 0.882 | 0.722 | 0.746 | 0/4 | 0 | IS completa -0.0817629991650932 ≤ 0 |
| 454 | 20 | 2.5 | 2.5 | 1299 | -0.0327 | -0.0894 | -0.0801 | 0.0523 | 0.0435 | 0.890 | 0.729 | 0.753 | 0/4 | 0 | IS completa -0.08013999301994494 ≤ 0 |
| 455 | 25 | 1.5 | 1.5 | 2375 | -0.0615 | -0.1473 | -0.1328 | 0.0776 | 0.0645 | 0.857 | 0.696 | 0.720 | 0/4 | 2 | rank 2 > 0 (dominada) |
| 456 | 25 | 1.5 | 2 | 2366 | -0.0511 | -0.1404 | -0.1255 | 0.0807 | 0.0667 | 0.882 | 0.713 | 0.739 | 0/4 | 3 | rank 3 > 0 (dominada) |
| 457 | 25 | 1.5 | 2.5 | 2365 | -0.0411 | -0.1321 | -0.1170 | 0.0828 | 0.0683 | 0.905 | 0.731 | 0.757 | 0/4 | 3 | rank 3 > 0 (dominada) |
| 458 | 25 | 2 | 1.5 | 2307 | -0.0533 | -0.1197 | -0.1089 | 0.0604 | 0.0499 | 0.848 | 0.693 | 0.716 | 0/4 | 1 | rank 1 > 0 (dominada) |
| 459 | 25 | 2 | 2 | 2306 | -0.0421 | -0.1099 | -0.0989 | 0.0622 | 0.0513 | 0.880 | 0.718 | 0.742 | 0/4 | 1 | rank 1 > 0 (dominada) |
| 460 | 25 | 2 | 2.5 | 2304 | -0.0378 | -0.1065 | -0.0953 | 0.0631 | 0.0524 | 0.893 | 0.728 | 0.752 | 0/4 | 2 | rank 2 > 0 (dominada) |
| 461 | 25 | 2.5 | 1.5 | 2278 | -0.0400 | -0.0941 | -0.0854 | 0.0494 | 0.0411 | 0.862 | 0.706 | 0.729 | 0/4 | 1 | rank 1 > 0 (dominada) |
| 462 | 25 | 2.5 | 2 | 2276 | -0.0331 | -0.0881 | -0.0792 | 0.0502 | 0.0419 | 0.886 | 0.726 | 0.749 | 0/4 | 0 | IS completa -0.07919897556108874 ≤ 0 |
| 463 | 25 | 2.5 | 2.5 | 2274 | -0.0291 | -0.0844 | -0.0755 | 0.0506 | 0.0422 | 0.900 | 0.738 | 0.762 | 0/4 | 0 | IS completa -0.07546851553502852 ≤ 0 |

- Bruto: 27/27 negativos; mediana -0.0533 R/op, mejor -0.0291 R/op (ID 463: thr 25, stop 2.5, RR 2.5).
- Neto CF1: 27/27 negativos; rango -0.1925 … -0.0844 R/op. Neto CF6: 27/27 negativos; rango -0.1804 … -0.0755 R/op.
- `cost_R` mediano: CF1 0.0494–0.0911, CF6 0.0411–0.0763 R por operación. El coste es del mismo orden que el bruto (o mayor): no hay margen.
- Pliegues positivos: **8/108** en total; ninguna combinación pasa de **1/4**. Los pliegues son netos de la cuenta seleccionada (CF6). Edge Map cuenta **0** estrategias con ≥3/4 pliegues positivos (`positive_folds_count`), que es el criterio de robustez, no el recuento bruto de pliegues.
- Frontera: **8** combinaciones con `rank = 0` (443, 444, 445, 452, 453, 454, 462, 463); las otras **19** están dominadas (`rank > 0`). El control de finalista es `IS completa > 0`; el de frontera, `rank = 0`. Ninguna de las 8 de frontera supera 0, así que el filtro deja 0 finalistas.

## 4. Resultado por pliegue

Expectancy neta CF6 por pliegue (4 pliegues del pipeline). Valores en R/op.

| ID | Pliegue 1 | Pliegue 2 | Pliegue 3 | Pliegue 4 | Positivos |
|---:|---:|---:|---:|---:|---:|
| 437 | -0.213 | -0.149 | 0.122 | -0.383 | 1/4 |
| 438 | -0.193 | -0.110 | 0.048 | -0.377 | 1/4 |
| 439 | -0.182 | -0.070 | 0.074 | -0.399 | 1/4 |
| 440 | -0.191 | -0.141 | -0.006 | -0.319 | 0/4 |
| 441 | -0.181 | -0.099 | 0.023 | -0.334 | 1/4 |
| 442 | -0.168 | -0.067 | 0.055 | -0.341 | 1/4 |
| 443 | -0.154 | -0.110 | 0.013 | -0.297 | 1/4 |
| 444 | -0.132 | -0.075 | 0.047 | -0.302 | 1/4 |
| 445 | -0.116 | -0.037 | 0.093 | -0.302 | 1/4 |
| 446 | -0.159 | -0.156 | -0.096 | -0.189 | 0/4 |
| 447 | -0.133 | -0.141 | -0.135 | -0.190 | 0/4 |
| 448 | -0.112 | -0.128 | -0.119 | -0.208 | 0/4 |
| 449 | -0.114 | -0.110 | -0.128 | -0.166 | 0/4 |
| 450 | -0.096 | -0.102 | -0.109 | -0.189 | 0/4 |
| 451 | -0.107 | -0.097 | -0.097 | -0.192 | 0/4 |
| 452 | -0.067 | -0.086 | -0.121 | -0.145 | 0/4 |
| 453 | -0.073 | -0.086 | -0.106 | -0.148 | 0/4 |
| 454 | -0.062 | -0.072 | -0.100 | -0.175 | 0/4 |
| 455 | -0.113 | -0.111 | -0.132 | -0.186 | 0/4 |
| 456 | -0.101 | -0.102 | -0.147 | -0.184 | 0/4 |
| 457 | -0.083 | -0.088 | -0.135 | -0.189 | 0/4 |
| 458 | -0.102 | -0.078 | -0.127 | -0.148 | 0/4 |
| 459 | -0.090 | -0.067 | -0.108 | -0.147 | 0/4 |
| 460 | -0.097 | -0.059 | -0.093 | -0.152 | 0/4 |
| 461 | -0.062 | -0.056 | -0.110 | -0.124 | 0/4 |
| 462 | -0.066 | -0.051 | -0.093 | -0.122 | 0/4 |
| 463 | -0.055 | -0.042 | -0.085 | -0.135 | 0/4 |

## 5. Expectativa bruta por año (2010–2024)

Mejor combinación por neto: **463** (thr 25, stop 2,5, RR 2,5). Mediana por neto: **457** (thr 25, stop 1.5, RR 2.5). Bruto, sin costes, sobre las mismas operaciones IS. 2024 es parcial (enero–junio).

| Año | 463 ops | 463 bruto R/op | 457 ops | 457 bruto R/op |
|---:|---:|---:|---:|---:|
| 2010 | 143 | 0.0820 | 149 | 0.1545 |
| 2011 | 170 | -0.0357 | 178 | -0.0543 |
| 2012 | 154 | -0.0471 | 158 | -0.0734 |
| 2013 | 161 | -0.0131 | 167 | -0.0470 |
| 2014 | 155 | -0.0555 | 159 | -0.0388 |
| 2015 | 154 | -0.0143 | 166 | -0.0273 |
| 2016 | 146 | -0.0184 | 152 | -0.0419 |
| 2017 | 140 | 0.0557 | 142 | 0.0568 |
| 2018 | 172 | -0.0524 | 172 | -0.0801 |
| 2019 | 148 | 0.0581 | 155 | 0.0431 |
| 2020 | 159 | -0.0380 | 163 | -0.0291 |
| 2021 | 154 | -0.0828 | 163 | -0.1198 |
| 2022 | 161 | -0.1649 | 171 | -0.1902 |
| 2023 | 173 | -0.0239 | 181 | -0.0694 |
| 2024 | 84 | -0.0815 | 89 | -0.0633 |

**¿Algún régimen funciona?** No de forma sostenida: solo 2010, 2017 y 2019 son positivos, y 2010 es el arranque de la muestra. 2022 es el peor (−0,165 / −0,190 R/op). No hay un régimen anual estable que justifique re-optimizar por año; solo se documenta.

## 6. Hipótesis marcada como probada

`edge_map._tested_keys` añadía solo la clave `(plantilla, instrumento, TF, fuente)`; la campaña se probó con `dukascopy` y `suggest` la volvía a proponer para `broker`. Ahora, si una campaña tiene `n_evaluated > 0`, se añade además la clave comodín `(plantilla, instrumento, TF, "*")`.

Comprobado en lectura: `edge_map.suggest('CFD-001', allow_dukascopy=True)` devuelve 14 filas y **ya no incluye** `asia_range_reversion` / USDJPY / H1. Test: `tests/test_discovery_edge_map_tested.py::test_tested_keys_marca_hipotesis_probada_sin_fuente`.

## 7. Reproducibilidad

```powershell
Set-Location E:\trading-lab
.\.venv\Scripts\lab.exe discovery results c1-asia-usdjpy-h1-long
.\.venv\Scripts\lab.exe discovery edge-map --by hipotesis
.\.venv\Scripts\python.exe -c "from tradinglab.config import DEFAULT_DB; from tradinglab.learning import count_tests; print(count_tests(DEFAULT_DB))"
```

`discovery results` y `edge-map` son solo lectura. No ejecutar `discovery confirm`: leería OOS-2.
