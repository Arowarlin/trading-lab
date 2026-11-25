# EA us100-ftmo1 · validación v2 (solo lectura)

Generado: 2026-11-24 · **no se toca el EA, ni parámetros, ni setfiles.**
Motor: `ea_us100_engine.py` v3.2 (BID/ASK con spread por barra).
Setfile: `integrations/mt5/us100_ftmo1/US100_FTMO_v3_challenge.set`.
Caché: `data/cache/ea/US100_CASH_M5_NY.parquet` (2017-12-28 → 2026-11-23 09:15).

## 1 · Fuentes

| Fuente | Estado |
|---|---|
| Motor `ea_us100_engine.py` v3.2 | OK, solo lectura |
| Setfile v3.2 (`InpRiskPct=0.35`, `InpDynRisk=true`) | OK |
| Informe `reports/audit/ea_us100_m5_only.md` | OK |
| Backtest: caché M5 + motor | OK, 478 operaciones |
| Forward: MT5 FTMO demo, login 1515349730 | OK, 1 operación desde 2026-11-23 |
| `lab.db` / `ea_forward` | OK, forward 1 operación, expectancy 0,5583 R |

## 2 · Backtest (2017-12-28 → 2026-11-23)

| Métrica | Valor |
|---|---:|
| Operaciones | 478 |
| Win rate | 34,1 % |
| PF | 1,47 |
| Expectativa | **+0,3104 R** |
| Desviación | 1,9193 R |
| Total | +148,4 R |
| DD máximo | 24,8 R |
| IC95 bootstrap (bloque 1 semana ≈ 2 ops) | [0,1415; 0,4856] |
| **LCB95** | **0,1682 R** |

### Por año

| Año | Ops | Exp R | Total R | DD R |
|---|---:|---:|---:|---:|
| 2021 (desde sep) | 34 | +0,1348 | +4,58 | 7,17 |
| 2022 | 84 | +0,6753 | +56,72 | 6,99 |
| 2023 | 94 | +0,0367 | +3,45 | 16,53 |
| 2024 | 96 | +0,2943 | +28,26 | 10,76 |
| 2025 | 86 | +0,2729 | +23,47 | 14,06 |
| 2026 | 84 | +0,3794 | +31,87 | 9,05 |

El año 2023 es el más flojo (+0,037 R) y el 2022 el mejor (+0,675 R): la
ventaja depende del régimen.

## 3 · Sensibilidad al slippage

| Slippage (puntos/lado) | Expectativa R | PF | Total R | Ops |
|---:|---:|---:|---:|---:|
| 0,0 | +0,3396 | 1,52 | +162,7 | 479 |
| 0,5 (actual) | +0,3104 | 1,47 | +148,4 | 478 |
| 1,0 | +0,2995 | 1,45 | +142,9 | 477 |
| 2,0 | +0,2517 | 1,37 | +119,0 | 473 |
| 3,0 | +0,2277 | 1,33 | +107,5 | 472 |
| 5,0 | +0,1515 | — | +71,3 | 471 |
| 8,0 | +0,0291 | — | +13,7 | 470 |
| 12,0 | −0,0952 | — | −44,6 | 468 |

**`slip_eq` ≈ 8,9 puntos por lado** (interpolación entre 8 y 12). El EA
soportaría mucha más fricción que la modelada (0,5 puntos), pero el dato real
del bróker no está medido para este EA.

## 4 · Corrección por variantes (DSR)

8 variantes (RR 3,0/3,5 × gap 0,5/0,7 × consec 1/2), SR por periodo de cada
una, DSR sobre los retornos diarios del setfile actual:

| N trials | DSR | SR0 periodo |
|---:|---:|---:|
| 8 | **0,99936** | 0,02506 |
| 20 | 0,99883 | 0,03265 |
| 50 | 0,99809 | 0,03910 |

Con N=50 sigue por encima de 0,99: la corrección por variantes no tumba la
señal del backtest.

## 5 · Congelación de v3.2 y holdout natural

- Fecha de adopción: **2026-11-16** (`docs/ea_us100_ftmo1.md`; commit del
  setfile `bdc9aca`, 2026-11-15). El forward arrancó el 2026-11-16.
- Operaciones del backtest posteriores a la congelación: **2** (2026-11-18 y
  2026-11-19), ambas stop, **−1,0039 R de media**, t no informativo (n=2).
- Holdout demasiado corto para decidir; se reporta como evidencia negativa
  débil, no como refutación.

## 6 · Paridad forward

Forward demo desde 2026-11-23 (MT5, solo lectura):

| # | Lado | Entrada | Salida | Puntos | R (ea_forward) |
|---:|---|---:|---:|---:|---:|
| 1 | corto | 26.185,73 | 26.110,28 | +75,45 | +0,5583 |

El motor no tiene barras posteriores al 2026-11-23 09:15, así que **no hay
operación equivalente que comparar**. El forward es de 2026-11-24 17:20 UTC
(12:20 NY) a 22:45 UTC. Paridad: **Sin datos** (1 operación, menos de 5).

## 7 · Plan SPRT

σ = 1,9193 R; frecuencia real = 478 / 237 semanas = **2,02 ops/semana**.

| δ | E[N] | Semanas | E[N \| μ=0] | Semanas (H0) |
|---:|---:|---:|---:|---:|
| 0,1552 (0,5× backtest) | 583 | **289** | 410 | 203 |
| 0,1682 (LCB95) | 496 | **246** | 349 | 173 |

Con la frecuencia actual, confirmar la mitad de la ventaja del backtest
llevaría **casi 5 años** de forward; con el LCB, **4,7 años**. El EA no se
puede validar en demo en un plazo razonable con 2 ops/semana.

## 8 · P(pasar el reto FTMO)

Reglas `firms.yaml` FTMO 2-step challenge 100k: objetivo 10 %, diario 5 %,
máximo 10 % estático, colchón 10 %. Simulador `prop.simulator.monte_carlo`,
60 días, 2.000–5.000 caminos, bootstrap de los R diarios del backtest.

| Riesgo/op | P(pasar) | P(romper) | Días medianos |
|---:|---:|---:|---:|
| 0,35 % (actual) | 38,5 % | 0,1 % | 43 |
| 0,50 % | 60,2 % | 2,0 % | 34 |
| 0,60 % | 67,3 % | 3,3 % | 30 |
| **0,65 %** | **71,7 %** | **4,6 %** | **28** |
| 0,70 % | 73,9 % | 5,4 % | 26 |

Riesgo que maximiza P(pasar) con P(romper) ≤ 5 %: **≈0,65 % por operación**,
no el 0,35 % actual. Duplica la P(pasar) estimada (38,5 % → 71,7 %) sin pasar
del 5 % de ruptura. Es una decisión del operador; no se cambia nada aquí.

## 9 · Veredicto

**INCIERTA.**

- LCB95 > 0 (0,168 R) y DSR(N=8) = 0,999 ≥ 0,95: el backtest es sólido.
- Pero el holdout natural es de **2 operaciones negativas** y el forward de
  **1 operación**; no hay evidencia fuera de muestra suficiente.
- No se cumple el criterio completo de "ventaja probable" (holdout > 0).
- Tampoco es "no demostrada": el backtest y el DSR son fuertes y el EA soporta
  slippage hasta ~9 puntos/lado.

**Siguiente paso recomendado:** no tocar el EA; dejar correr el forward y
revisar cuando haya ≥30 operaciones, o usar el SPRT con δ = LCB95 (246
semanas estimadas, inviable a la frecuencia actual). La vía práctica es
aumentar la frecuencia o la familia de instrumentos, no relajar el criterio.

---

Solo lectura: no se envió ninguna orden, no se modificó el EA, el setfile ni
`lab.db`. `count_tests` sin cambios.
