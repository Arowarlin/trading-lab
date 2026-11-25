# EA us100-ftmo1 · prueba fuera de instrumento (US500 y US30)

Generado: 2026-11-24 · **no se toca el EA, ni parámetros, ni setfiles.**
Motor: `ea_us100_engine.py` v3.2. Setfile:
`integrations/mt5/us100_ftmo1/US100_FTMO_v3_challenge.set`.
Ventana: desde el inicio de cada caché hasta 2026-11-24 21:45 NY.
MT5 FTMO demo login 1515349730 (attach-only, solo lectura).

## 1 · Datos y escalado

| Símbolo | Filas M5 | Inicio | Fin | Fuente |
|---|---:|---|---|---|
| US100.cash | 368.802 | 2017-12-28 18:00 | 2026-11-24 21:40 | caché E1 |
| US500.cash | 368.761 | 2017-12-28 17:00 | 2026-11-24 21:45 | `copy_rates_range` MT5 |
| US30.cash | 538.260 | 2019-02-08 07:25 | 2026-11-24 21:45 | `copy_rates_range` MT5 |

Escalado decidido antes de ver resultados:
`k = mediana(ATR14 M5 del símbolo) / mediana(ATR14 M5 de US100)` en el
periodo común, con el ATR14 del motor (media de los 14 primeros TR y
suavizado de Wilder).

| Símbolo | Barras comunes | ATR14 mediano | ATR14 US100 | k |
|---|---:|---:|---:|---:|
| US500 | 357.622 | 2,9525 | 14,4107 | **0,204886** |
| US30 | 357.374 | 20,3461 | 14,3961 | **1,413300** |

Parámetros en puntos escalados por k (el resto no se toca: ATR, %, horas, R,
`rr`, sesión, festivos):

| Parámetro del setfile | Motor | US100 (k=1) | US500 (k=0,2049) | US30 (k=1,4133) |
|---|---|---:|---:|---:|
| `InpMinSlPts` | `min_sl` | 2,0000 | 0,4098 | 2,8266 |
| `InpMaxSpreadPts` | `max_spread` | 3,0000 | 0,6147 | 4,2399 |
| `InpBEOffPts` | `be_off` | 0,5000 | 0,1024 | 0,7067 |

`slip = 0,5` no está en el setfile y se mantiene igual en los tres símbolos
(0,5 puntos por lado, el supuesto de T41). El spread es el de cada barra de
MT5. Comisión de índices: 0 según `costs.yaml` (FTMO, "Zero Commissions on
Indices", 2025-08-04).

## 2 · Resultados por símbolo

| Métrica | US100 | US500 | US30 |
|---|---:|---:|---:|
| Operaciones | 479 | 435 | 775 |
| Win rate | 34,2 % | 24,8 % | 25,7 % |
| PF | 1,47 | 0,97 | 1,09 |
| Expectativa | **+0,3104 R** | **−0,0229 R** | **+0,0692 R** |
| Desviación | 1,9173 | 1,8685 | 1,8734 |
| Total | +148,7 R | −9,9 R | +53,7 R |
| DD máximo | 24,8 R | 34,6 R | 37,3 R |
| IC95 bootstrap (semanal) | [0,1511; 0,4722] | [−0,2003; 0,1552] | [−0,0584; 0,1965] |
| **LCB95** | **0,1738** | **−0,1731** | **−0,0382** |
| Semanas bootstrap | 238 | 227 | 366 |
| `slip_eq` (puntos/lado) | 8,95 | 0,43 | 1,93 |

Bootstrap estacionario por bloques de 1 semana, 10.000 remuestreos, semilla
42; LCB95 = media − 1,645 × sd bootstrap.

### US500 · por año

| Año | Ops | Exp R | Total R | DD R | PF |
|---|---:|---:|---:|---:|---:|
| 2021 (desde sep) | 35 | −0,1351 | −4,73 | 14,88 | 0,84 |
| 2022 | 88 | +0,0379 | +3,33 | 20,79 | 1,05 |
| 2023 | 90 | +0,0431 | +3,88 | 18,78 | 1,05 |
| 2024 | 79 | −0,1071 | −8,46 | 23,79 | 0,87 |
| 2025 | 53 | −0,2193 | −11,62 | 20,45 | 0,74 |
| 2026 | 90 | +0,0850 | +7,65 | 21,48 | 1,11 |

### US30 · por año

| Año | Ops | Exp R | Total R | DD R | PF |
|---|---:|---:|---:|---:|---:|
| 2019 (desde feb) | 73 | +0,3094 | +22,59 | 8,51 | 1,46 |
| 2020 | 95 | +0,0248 | +2,36 | 17,89 | 1,03 |
| 2021 | 103 | −0,0350 | −3,61 | 26,16 | 0,95 |
| 2022 | 103 | +0,0471 | +4,85 | 13,24 | 1,06 |
| 2023 | 91 | +0,0639 | +5,82 | 14,60 | 1,09 |
| 2024 | 110 | +0,1070 | +11,77 | 16,85 | 1,14 |
| 2025 | 105 | +0,0581 | +6,10 | 12,88 | 1,08 |
| 2026 | 95 | +0,0399 | +3,79 | 14,31 | 1,05 |

### US100 · por año (referencia, caché actualizada)

| Año | Ops | Exp R | Total R | DD R | PF |
|---|---:|---:|---:|---:|---:|
| 2021 (desde sep) | 34 | +0,1348 | +4,58 | 7,17 | 1,18 |
| 2022 | 84 | +0,6753 | +56,72 | 6,99 | 2,16 |
| 2023 | 94 | +0,0367 | +3,45 | 16,53 | 1,05 |
| 2024 | 96 | +0,2943 | +28,26 | 10,76 | 1,43 |
| 2025 | 86 | +0,2729 | +23,47 | 14,06 | 1,41 |
| 2026 | 85 | +0,3785 | +32,17 | 9,05 | 1,61 |

## 3 · Sensibilidad al slippage

Puntos por lado; `slip_eq` es el cruce de expectativa 0.

| Slip | US100 exp (n) | US500 exp (n) | US30 exp (n) |
|---:|---:|---:|---:|
| 0,0 | +0,3396 (480) | +0,1318 (437) | +0,0803 (776) |
| 0,5 (actual) | +0,3104 (479) | −0,0229 (435) | +0,0692 (775) |
| 1,0 | +0,2995 (478) | −0,1292 (434) | +0,0423 (774) |
| 2,0 | +0,2518 (474) | −0,3437 (432) | −0,0032 (772) |
| 3,0 | +0,2279 (473) | −0,4869 (432) | −0,0422 (769) |
| 5,0 | +0,1517 (472) | −0,7326 (431) | −0,1202 (763) |
| 8,0 | +0,0295 (471) | −0,9390 (430) | −0,2019 (761) |
| 12,0 | −0,0945 (469) | −1,1094 (430) | −0,3001 (760) |

El mismo slippage absoluto de 0,5 puntos pesa mucho más en US500 (riesgo
medio menor en puntos) que en US100: US500 pasa de +0,1318 R bruto a
−0,0229 R; su `slip_eq` es 0,43 puntos/lado. US30 aguanta hasta 1,93
puntos/lado. US100 aguanta hasta 8,95.

## 4 · P(pasar) FTMO (fase 1 del challenge, T41 §8)

`prop.simulator.monte_carlo`, 5.000 caminos, 60 días, bootstrap de los R
diarios, reglas `ftmo` challenge 100k del `prop.yaml` (objetivo 10 %, diario
5 %, máximo 10 % estático, colchón 10 %). Riesgo por operación de 0,25 % a
1,00 % en pasos de 0,05 %.

| Símbolo | Riesgo actual 0,35 % | Mejor riesgo (P(romper) ≤ 5 %) |
|---|---|---|
| US100 | P(pasar) 35,9 % · P(romper) 0,18 % · 42 días | **0,65 %** → 71,7 % · 4,62 % · 28 días |
| US500 | P(pasar) 4,8 % · P(romper) 6,28 % · 45 días | **0,30 %** → 2,48 % · 2,82 % · 47 días |
| US30 | P(pasar) 10,4 % · P(romper) 2,38 % · 44 días | **0,40 %** → 15,18 % · 4,34 % · 42 días |

En US500 el 0,35 % ya supera el 5 % de ruptura; el óptimo baja a 0,30 % y
solo da 2,5 % de P(pasar). En US30 el óptimo es 0,40 % y 15,2 %.

## 5 · Criterio prerregistrado y veredicto

Criterio por instrumento: **expectativa ≥ 0,10 R y LCB95 > 0**, con al menos
150 operaciones.

| Instrumento | Ops | Exp ≥ 0,10 | LCB95 > 0 | ¿Cumple? |
|---|---:|---|---|---|
| US500 | 435 | No (−0,0229) | No (−0,1731) | **No** |
| US30 | 775 | No (+0,0692) | No (−0,0382) | **No** |

**Veredicto conjunto: "no transfiere".** Ninguno de los dos instrumentos
cumple el criterio. US30 es el más cercano (positivo, 775 ops), pero su
expectativa queda por debajo de 0,10 R y su LCB95 es negativa. No se
reinterpreta el criterio después de ver el resultado.

## 6 · Correlación diaria de R

Pearson sobre días con operación en ambos símbolos:

| Par | Días comunes | Pearson | Spearman |
|---|---:|---:|---:|
| US100 – US500 | 202 | 0,289 | 0,286 |
| US100 – US30 | 219 | 0,316 | 0,348 |
| US500 – US30 | 265 | 0,345 | 0,407 |

Las correlaciones son bajas-moderadas (0,29-0,41). No hay base para una
cartera de los tres con estos datos: US500 y US30 no pasan el criterio.

## 7 · Cumplimiento

- Sin campañas, OOS, `confirm` ni `record-informal`.
- MT5 attach-only: `copy_rates_range` y `history_deals`; login
  1515349730 verificado antes y después; ninguna orden.
- EA, setfile, ai_trader y carriles forward sin cambios.
- `count_tests` = 1894, sin cambios.
