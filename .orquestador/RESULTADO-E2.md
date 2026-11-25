# RESULTADO E2 · Prueba fuera de instrumento

- **Fecha:** 2026-11-24
- **Commit:** `tl2: E2 - prueba fuera de instrumento`
- **Tag:** `tl2-e2`
- **Informe:** `reports/ea/us100-ftmo1-fuera-de-instrumento.md`

## Datos

| Símbolo | Filas | Inicio | Fin |
|---|---:|---|---|
| US100.cash | 368.802 | 2017-12-28 18:00 | 2026-11-24 21:40 |
| US500.cash | 368.761 | 2017-12-28 17:00 | 2026-11-24 21:45 |
| US30.cash | 538.260 | 2019-02-08 07:25 | 2026-11-24 21:45 |

Descarga M5 con `copy_rates_range` del terminal FTMO demo, attach-only,
login 1515349730 verificado antes y después. Formato idéntico (OHLC,
`tickvol`, `spread`), barra en curso descartada.

Escalado por ATR14 M5 en el periodo común:

| Símbolo | k | `min_sl` | `max_spread` | `be_off` |
|---|---:|---:|---:|---:|
| US500 | 0,204886 | 0,4098 | 0,6147 | 0,1024 |
| US30 | 1,413300 | 2,8266 | 4,2399 | 0,7067 |

`slip = 0,5` no se escala (no está en el setfile). ATR, %, horas, R, `rr` y
sesión no se tocan.

## Resultado

| Métrica | US100 | US500 | US30 |
|---|---:|---:|---:|
| Operaciones | 479 | 435 | 775 |
| Expectativa | +0,3104 R | **−0,0229 R** | **+0,0692 R** |
| Desviación | 1,9173 | 1,8685 | 1,8734 |
| PF | 1,47 | 0,97 | 1,09 |
| DD | 24,8 R | 34,6 R | 37,3 R |
| IC95 bootstrap | [0,1511; 0,4722] | [−0,2003; 0,1552] | [−0,0584; 0,1965] |
| LCB95 | 0,1738 | **−0,1731** | **−0,0382** |
| `slip_eq` | 8,95 pts | 0,43 pts | 1,93 pts |

## Criterio prerregistrado

`expectativa ≥ 0,10 R` **y** `LCB95 > 0`, con `n ≥ 150`.

- **US500:** no cumple (exp −0,0229; LCB −0,1731).
- **US30:** no cumple (exp +0,0692 < 0,10; LCB −0,0382 < 0).

**Veredicto conjunto: "no transfiere"** (0 de 2). No se reinterpreta el
criterio.

## P(pasar) FTMO (fase 1, T41 §8)

| Símbolo | 0,35 % actual | Mejor con P(romper) ≤ 5 % |
|---|---|---|
| US100 | 35,9 % · 0,18 % · 42 d | 0,65 % → 71,7 % · 4,62 % · 28 d |
| US500 | 4,8 % · 6,28 % · 45 d | 0,30 % → 2,48 % · 2,82 % · 47 d |
| US30 | 10,4 % · 2,38 % · 44 d | 0,40 % → 15,18 % · 4,34 % · 42 d |

## Correlación diaria de R

| Par | Días | Pearson | Spearman |
|---|---:|---:|---:|
| US100 – US500 | 202 | 0,289 | 0,286 |
| US100 – US30 | 219 | 0,316 | 0,348 |
| US500 – US30 | 265 | 0,345 | 0,407 |

## Lectura

La lógica v3.2 **no transfiere** a US500 ni a US30 con el criterio
prerregistrado. US30 es el más cercano (775 ops, expectativa positiva), pero
no alcanza 0,10 R y su LCB95 es negativa. US500 es negativo incluso antes de
costes de slippage; con 0,5 puntos/lado su `slip_eq` es solo 0,43.

Esto reduce la probabilidad de que la ventaja de US100 sea un efecto amplio
de los índices estadounidenses, pero no la refuta: US100 sigue siendo el
único instrumento con evidencia fuerte (T41, INCIERTA por falta de forward).

## Cumplimiento

Sin campañas, OOS, `confirm` ni `record-informal`. MT5 solo lectura, sin
órdenes. EA/setfile/ai_trader/forward sin cambios. `count_tests` = 1894.
