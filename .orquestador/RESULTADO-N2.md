# RESULTADO · N2 — plantillas H4/D1

Fecha: 2026-11-22. Repo `E:\trading-lab`, rama `feature/prop-fund-multifirm`.
No se registró, aprobó, ejecutó, confirmó ni supersedió ninguna campaña; no se
leyó OOS-1/OOS-2; no se hizo push; no se tocaron tareas programadas, umbrales,
el carril del EA, `us100-trend-d1` ni el worktree `tl2-f12`. Los únicos
backtests ejecutados son los de `feasibility --spec`: operaciones y coste, sin
PnL, expectativa ni equity.

## 1. Plantillas implementadas

| Plantilla | Familia | TF válidos | Simetría | Params (grid) | n_total |
|---|---|---|---|---:|---:|
| `ts_momentum_d1` | momentum de serie temporal | D1 | `symmetric: true` | 3 (3×3×3) | 27 |
| `donchian_vol_h4` | ruptura Donchian + volatilidad | H4 | `symmetric: true` | 3 (3×3×3) | 27 |
| `d1_extension_reversion` | reversión tras extensión | D1 | `symmetric: false` (long-only) | 3 (3×3×3) | 27 |

Cada YAML declara `timeframes`, `valid_timeframes`, `symmetric`, hipótesis,
invalidación, `parameter_space`, grid por defecto y estrategia completa.
Sesión `00:00–23:59` con `flat_at: 23:59` (no hay cierre intradía); el motor
solo marca `flat` en una barra exactamente a las 23:59, que no existe en H4/D1.

**Bloques DSL nuevos: ninguno.** Las tres se componen con bloques ya existentes
(`sma`, `cross_up/down`, `donchian_high/low`, `vol_high`, `zscore`, `rsi`,
`atr`, `trailing`, `time_exit_minutes`). Por eso no hay paridad nueva de
bloques; sí se añadió paridad de las **salidas completas** de cada plantilla
(Python vs numba) y un test de sesgo de anticipación por plantilla.

### Desviación de diseño en A

La propuesta de C1 decía “sin salida por tiempo” para `ts_momentum_d1`. La
feasibility usa `max_bars = max(2 velas de sesión, time_exit_bars)`; en D1 son
2 días y una tendencia mantiene 20–30 días, así que **las 27 combinaciones
fallaban por “tiempo medio > 2 velas”**. No se tocó el umbral: se añadió a la
plantilla una salida máxima de **60 días** (`time_exit_minutes: 86400`), que
sigue dejando correr la tendencia y desbloquea el gate. Es la única diferencia
funcional respecto al papel de C1.

### Corrección necesaria en el modo rejilla

`grid.grid_strategies` espejaba siempre `long_entry` ignorando `symmetric`.
En una plantilla long-only eso duplicaba los nodos (20 > `max_nodes` 12) y
convertía la hipótesis en simétrica. Ahora solo espeja si la plantilla declara
`symmetric: true`; en caso contrario conserva `short_entry` (null). Test:
`test_grid_long_only_conserva_short_null`.

## 2. Especificaciones y preflight

Seis specs en `.orquestador/specs/n2-*.yaml`, todas con `data_source:
dukascopy`, `cost_mode: best` y cuentas CFD-001/CFD-006, IS dentro de
`usable_from`, OOS-1/OOS-2 solo declarados (no leídos).

| Spec | Símbolo | TF | IS | Preflight |
|---|---|---|---|---:|
| `n2-ts-xauusd-d1` | XAUUSD | D1 | 2005-01-01 → 2024-06-30 | 27/27 |
| `n2-ts-usdjpy-d1` | USDJPY | D1 | 2004-01-01 → 2024-06-30 | 27/27 |
| `n2-donchian-xauusd-h4` | XAUUSD | H4 | 2005-01-01 → 2024-06-30 | 27/27 |
| `n2-donchian-usdjpy-h4` | USDJPY | H4 | 2004-01-01 → 2024-06-30 | 27/27 |
| `n2-d1reversion-xauusd` | XAUUSD | D1 | 2005-01-01 → 2024-06-30 | 27/27 |
| `n2-d1reversion-eurusd` | EURUSD | D1 | 2004-01-01 → 2024-06-30 | 27/27 |

## 3. Feasibility en seco (operaciones y coste, sin PnL)

| Spec | Factibles | % | Ops IS mediana [rango] | cost_R mediana [rango] | Cuentas viables |
|---|---:|---:|---|---|---|
| `n2-donchian-xauusd-h4` | 27/27 | 100,0 | 391 [262–637] | 0,0309 [0,0245–0,0401] | CFD-001 y CFD-006 |
| `n2-donchian-usdjpy-h4` | 27/27 | 100,0 | 330 [216–568] | 0,0185 [0,0145–0,0240] | CFD-001 y CFD-006 |
| `n2-d1reversion-eurusd` | 15/27 | 55,6 | 48 [32–92] | 0,0508 [0,0355–0,0612] | CFD-001 y CFD-006 |
| `n2-d1reversion-xauusd` | 18/27 | 66,7 | 45 [24–105] | 0,0141 [0,0112–0,0182] | CFD-001 y CFD-006 |
| `n2-ts-usdjpy-d1` | 27/27 | 100,0 | 31 [24–44] | 0,0120 [0,0085–0,0168] | CFD-001 y CFD-006 |
| `n2-ts-xauusd-d1` | 18/27 | 66,7 | 26,5 [22–36] | 0,0118 [0,0100–0,0152] | CFD-001 y CFD-006 |

Los seis pasan el gate ≥50 %. Las celdas no factibles son por muestra, no por
coste: `trades IS < 15`, `pliegue < 3` o `tiempo medio > 60 velas` (A antes del
time exit). Detalle de las **162 combinaciones** (parámetros, ops IS, pliegues,
`cost_R`, factible y motivo) en `.orquestador/feas-n2.json` y en formato
Markdown en `.orquestador/feas-n2-tablas.md`. Extracto de la recomendada
(`n2-donchian-xauusd-h4`):

| # | channel_n | vol_pct | stop_mult | Ops IS | Pliegues | cost_R | Factible |
|---:|---:|---:|---:|---:|---|---:|---|
| 1 | 20 | 0,6 | 1,5 | 637 | 167/142/165 | 0,0395 | sí |
| 2 | 20 | 0,6 | 2,0 | 573 | 153/130/141 | 0,0309 | sí |
| 3 | 20 | 0,6 | 2,5 | 523 | 140/115/134 | 0,0258 | sí |
| 4 | 20 | 0,7 | 1,5 | 521 | 133/123/133 | 0,0392 | sí |
| 5 | 20 | 0,7 | 2,0 | 472 | 123/113/114 | 0,0309 | sí |
| 6 | 20 | 0,7 | 2,5 | 441 | 117/103/108 | 0,0256 | sí |
| 7 | 20 | 0,8 | 1,5 | 402 | 101/91/104 | 0,0374 | sí |
| 8 | 20 | 0,8 | 2,0 | 369 | 94/85/92 | 0,0299 | sí |
| 9 | 20 | 0,8 | 2,5 | 350 | 87/83/89 | 0,0247 | sí |
| 10 | 40 | 0,6 | 1,5 | 504 | 133/112/129 | 0,0401 | sí |
| 11 | 40 | 0,6 | 2,0 | 462 | 122/106/112 | 0,0322 | sí |
| 12 | 40 | 0,6 | 2,5 | 433 | 115/99/107 | 0,0262 | sí |
| 13 | 40 | 0,7 | 1,5 | 409 | 104/91/108 | 0,0398 | sí |
| 14 | 40 | 0,7 | 2,0 | 380 | 98/87/94 | 0,0316 | sí |
| 15 | 40 | 0,7 | 2,5 | 361 | 93/82/91 | 0,0257 | sí |
| 16 | 40 | 0,8 | 1,5 | 317 | 77/71/89 | 0,0377 | sí |
| 17 | 40 | 0,8 | 2,0 | 298 | 72/69/81 | 0,0305 | sí |
| 18 | 40 | 0,8 | 2,5 | 287 | 66/68/79 | 0,0247 | sí |
| 19 | 55 | 0,6 | 1,5 | 456 | 123/102/113 | 0,0401 | sí |
| 20 | 55 | 0,6 | 2,0 | 417 | 114/97/96 | 0,0320 | sí |
| 21 | 55 | 0,6 | 2,5 | 391 | 107/91/93 | 0,0259 | sí |
| 22 | 55 | 0,7 | 1,5 | 374 | 96/84/97 | 0,0398 | sí |
| 23 | 55 | 0,7 | 2,0 | 348 | 92/81/83 | 0,0311 | sí |
| 24 | 55 | 0,7 | 2,5 | 330 | 87/76/81 | 0,0254 | sí |
| 25 | 55 | 0,8 | 1,5 | 289 | 75/62/77 | 0,0377 | sí |
| 26 | 55 | 0,8 | 2,0 | 273 | 72/60/70 | 0,0303 | sí |
| 27 | 55 | 0,8 | 2,5 | 262 | 66/59/68 | 0,0245 | sí |

(Las 27 filas de B XAUUSD y las de las otras cinco specs están en el fichero
citado; aquí va el extracto de la que se recomienda en N3.)

## 4. Tests y comprobaciones

- `tests/test_discovery_templates_h4d1.py` (nuevo):
  - TF declarada, simetría, validación y `count_nodes <= 12`;
  - sesgo de anticipación: se alteran las barras futuras y las señales hasta el
    corte no cambian (las tres plantillas; con señales reales, no todo False);
  - rejilla 27/27 única, válida y con el lado correcto (A/B espejo, C null);
  - paridad de la salida completa Python vs numba (stop, target, trailing y
    salida temporal) para las tres plantillas.
- `tests/test_discovery_grid.py`: `test_grid_long_only_conserva_short_null`.
- `tests/test_discovery_timeframes.py`: las tres plantillas declaran H4/D1 y
  las cinco antiguas siguen sin admitirlos.
- `ruff check` limpio; `pytest -q` completo y `lab propfund verify` al cerrar
  (ver sección 5); `count_tests` **1703** (no se registró nada).

## 5. Cierre

- `pytest -q` completo: **1635 passed, 1 skipped** (1 warning preexistente:
  `psutil` no instalado; 1:13:49, dominado por `test_noise_five_campaigns`).
  La primera tanda se bloqueó por la suite F12 en paralelo; se relanzó sola.
- `ruff check src/tradinglab tests`: limpio.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1703** (sin registrar).
- Commit `c2cecea` · `tl2: N2 - plantillas H4/D1` · tag `tl2-n2`.
- Fixes posteriores: `e1d4f69` · recuento de 8 plantillas en test DSL;
  `a246eeb` · fecha de mercado (`market_today`) en tests de comparación, que
  fallaban al cruzar medianoche UTC con `date.today()`.


## Anexo ? detalle de las 162 combinaciones

### n2-d1reversion-eurusd.yaml
| # | Params | Ops IS | Pliegues | cost_R | Factible | Motivo |
|---:|---|---:|---|---:|---|---|
| 1 | z_n=10, z_entry=-1.5, stop_mult=1.5 | 92 | 26/17/21 | 0.0612 | si |  |
| 2 | z_n=10, z_entry=-1.5, stop_mult=2.0 | 89 | 25/16/21 | 0.0492 | si |  |
| 3 | z_n=10, z_entry=-1.5, stop_mult=2.5 | 85 | 25/16/20 | 0.0403 | si |  |
| 4 | z_n=10, z_entry=-2.0, stop_mult=1.5 | 36 | 14/7/7 | 0.0561 | si |  |
| 5 | z_n=10, z_entry=-2.0, stop_mult=2.0 | 36 | 14/7/7 | 0.0440 | si |  |
| 6 | z_n=10, z_entry=-2.0, stop_mult=2.5 | 36 | 14/7/7 | 0.0355 | si |  |
| 7 | z_n=10, z_entry=-2.5, stop_mult=1.5 | 2 | 1/1/0 | 0.0565 | NO | trades IS 2 < 15; pliegue 1 trades 1 < 3; pliegue 2 trades 1 < 3; pliegue 3 trades 0 < 3 |
| 8 | z_n=10, z_entry=-2.5, stop_mult=2.0 | 2 | 1/1/0 | 0.0424 | NO | trades IS 2 < 15; pliegue 1 trades 1 < 3; pliegue 2 trades 1 < 3; pliegue 3 trades 0 < 3 |
| 9 | z_n=10, z_entry=-2.5, stop_mult=2.5 | 2 | 1/1/0 | 0.0339 | NO | trades IS 2 < 15; pliegue 1 trades 1 < 3; pliegue 2 trades 1 < 3; pliegue 3 trades 0 < 3 |
| 10 | z_n=20, z_entry=-1.5, stop_mult=1.5 | 61 | 16/10/15 | 0.0610 | si |  |
| 11 | z_n=20, z_entry=-1.5, stop_mult=2.0 | 58 | 15/10/15 | 0.0517 | si |  |
| 12 | z_n=20, z_entry=-1.5, stop_mult=2.5 | 56 | 14/10/14 | 0.0427 | si |  |
| 13 | z_n=20, z_entry=-2.0, stop_mult=1.5 | 35 | 8/4/8 | 0.0610 | si |  |
| 14 | z_n=20, z_entry=-2.0, stop_mult=2.0 | 33 | 8/4/8 | 0.0529 | si |  |
| 15 | z_n=20, z_entry=-2.0, stop_mult=2.5 | 32 | 8/4/7 | 0.0414 | si |  |
| 16 | z_n=20, z_entry=-2.5, stop_mult=1.5 | 11 | 0/2/5 | 0.0705 | NO | trades IS 11 < 15; pliegue 1 trades 0 < 3; pliegue 2 trades 2 < 3 |
| 17 | z_n=20, z_entry=-2.5, stop_mult=2.0 | 11 | 0/2/5 | 0.0548 | NO | trades IS 11 < 15; pliegue 1 trades 0 < 3; pliegue 2 trades 2 < 3 |
| 18 | z_n=20, z_entry=-2.5, stop_mult=2.5 | 11 | 0/2/5 | 0.0475 | NO | trades IS 11 < 15; pliegue 1 trades 0 < 3; pliegue 2 trades 2 < 3 |
| 19 | z_n=30, z_entry=-1.5, stop_mult=1.5 | 50 | 13/7/10 | 0.0602 | si |  |
| 20 | z_n=30, z_entry=-1.5, stop_mult=2.0 | 48 | 13/7/10 | 0.0508 | si |  |
| 21 | z_n=30, z_entry=-1.5, stop_mult=2.5 | 47 | 12/7/10 | 0.0409 | si |  |
| 22 | z_n=30, z_entry=-2.0, stop_mult=1.5 | 30 | 8/2/7 | 0.0593 | NO | pliegue 2 trades 2 < 3 |
| 23 | z_n=30, z_entry=-2.0, stop_mult=2.0 | 27 | 7/2/7 | 0.0469 | NO | pliegue 2 trades 2 < 3 |
| 24 | z_n=30, z_entry=-2.0, stop_mult=2.5 | 27 | 7/2/7 | 0.0409 | NO | pliegue 2 trades 2 < 3 |
| 25 | z_n=30, z_entry=-2.5, stop_mult=1.5 | 11 | 2/1/4 | 0.0630 | NO | trades IS 11 < 15; pliegue 1 trades 2 < 3; pliegue 2 trades 1 < 3 |
| 26 | z_n=30, z_entry=-2.5, stop_mult=2.0 | 11 | 2/1/4 | 0.0548 | NO | trades IS 11 < 15; pliegue 1 trades 2 < 3; pliegue 2 trades 1 < 3 |
| 27 | z_n=30, z_entry=-2.5, stop_mult=2.5 | 11 | 2/1/4 | 0.0473 | NO | trades IS 11 < 15; pliegue 1 trades 2 < 3; pliegue 2 trades 1 < 3 |

### n2-d1reversion-xauusd.yaml
| # | Params | Ops IS | Pliegues | cost_R | Factible | Motivo |
|---:|---|---:|---|---:|---|---|
| 1 | z_n=10, z_entry=-1.5, stop_mult=1.5 | 105 | 26/22/28 | 0.0176 | si |  |
| 2 | z_n=10, z_entry=-1.5, stop_mult=2.0 | 100 | 25/20/27 | 0.0141 | si |  |
| 3 | z_n=10, z_entry=-1.5, stop_mult=2.5 | 99 | 25/19/27 | 0.0122 | si |  |
| 4 | z_n=10, z_entry=-2.0, stop_mult=1.5 | 41 | 13/7/9 | 0.0148 | si |  |
| 5 | z_n=10, z_entry=-2.0, stop_mult=2.0 | 39 | 13/7/8 | 0.0135 | si |  |
| 6 | z_n=10, z_entry=-2.0, stop_mult=2.5 | 39 | 13/7/8 | 0.0112 | si |  |
| 7 | z_n=10, z_entry=-2.5, stop_mult=1.5 | 3 | 1/1/1 | 0.0192 | NO | trades IS 3 < 15; pliegue 1 trades 1 < 3; pliegue 2 trades 1 < 3; pliegue 3 trades 1 < 3 |
| 8 | z_n=10, z_entry=-2.5, stop_mult=2.0 | 3 | 1/1/1 | 0.0144 | NO | trades IS 3 < 15; pliegue 1 trades 1 < 3; pliegue 2 trades 1 < 3; pliegue 3 trades 1 < 3 |
| 9 | z_n=10, z_entry=-2.5, stop_mult=2.5 | 3 | 1/1/1 | 0.0115 | NO | trades IS 3 < 15; pliegue 1 trades 1 < 3; pliegue 2 trades 1 < 3; pliegue 3 trades 1 < 3 |
| 10 | z_n=20, z_entry=-1.5, stop_mult=1.5 | 67 | 20/12/19 | 0.0176 | si |  |
| 11 | z_n=20, z_entry=-1.5, stop_mult=2.0 | 64 | 19/12/17 | 0.0145 | si |  |
| 12 | z_n=20, z_entry=-1.5, stop_mult=2.5 | 63 | 18/12/17 | 0.0129 | si |  |
| 13 | z_n=20, z_entry=-2.0, stop_mult=1.5 | 34 | 12/4/11 | 0.0167 | si |  |
| 14 | z_n=20, z_entry=-2.0, stop_mult=2.0 | 32 | 11/4/10 | 0.0159 | si |  |
| 15 | z_n=20, z_entry=-2.0, stop_mult=2.5 | 31 | 10/4/10 | 0.0133 | si |  |
| 16 | z_n=20, z_entry=-2.5, stop_mult=1.5 | 10 | 4/1/3 | 0.0138 | NO | trades IS 10 < 15; pliegue 2 trades 1 < 3 |
| 17 | z_n=20, z_entry=-2.5, stop_mult=2.0 | 10 | 4/1/3 | 0.0136 | NO | trades IS 10 < 15; pliegue 2 trades 1 < 3 |
| 18 | z_n=20, z_entry=-2.5, stop_mult=2.5 | 10 | 4/1/3 | 0.0109 | NO | trades IS 10 < 15; pliegue 2 trades 1 < 3 |
| 19 | z_n=30, z_entry=-1.5, stop_mult=1.5 | 52 | 17/10/12 | 0.0173 | si |  |
| 20 | z_n=30, z_entry=-1.5, stop_mult=2.0 | 50 | 16/10/11 | 0.0141 | si |  |
| 21 | z_n=30, z_entry=-1.5, stop_mult=2.5 | 49 | 15/10/11 | 0.0137 | si |  |
| 22 | z_n=30, z_entry=-2.0, stop_mult=1.5 | 26 | 11/3/8 | 0.0182 | si |  |
| 23 | z_n=30, z_entry=-2.0, stop_mult=2.0 | 24 | 10/3/7 | 0.0140 | si |  |
| 24 | z_n=30, z_entry=-2.0, stop_mult=2.5 | 24 | 10/3/7 | 0.0120 | si |  |
| 25 | z_n=30, z_entry=-2.5, stop_mult=1.5 | 11 | 4/1/4 | 0.0146 | NO | trades IS 11 < 15; pliegue 2 trades 1 < 3 |
| 26 | z_n=30, z_entry=-2.5, stop_mult=2.0 | 11 | 4/1/4 | 0.0129 | NO | trades IS 11 < 15; pliegue 2 trades 1 < 3 |
| 27 | z_n=30, z_entry=-2.5, stop_mult=2.5 | 11 | 4/1/4 | 0.0103 | NO | trades IS 11 < 15; pliegue 2 trades 1 < 3 |

### n2-donchian-usdjpy-h4.yaml
| # | Params | Ops IS | Pliegues | cost_R | Factible | Motivo |
|---:|---|---:|---|---:|---|---|
| 1 | channel_n=20, vol_pct=0.6, stop_mult=1.5 | 568 | 139/137/149 | 0.0240 | si |  |
| 2 | channel_n=20, vol_pct=0.6, stop_mult=2.0 | 521 | 133/124/132 | 0.0192 | si |  |
| 3 | channel_n=20, vol_pct=0.6, stop_mult=2.5 | 486 | 122/119/122 | 0.0157 | si |  |
| 4 | channel_n=20, vol_pct=0.7, stop_mult=1.5 | 461 | 107/111/123 | 0.0232 | si |  |
| 5 | channel_n=20, vol_pct=0.7, stop_mult=2.0 | 424 | 104/102/109 | 0.0187 | si |  |
| 6 | channel_n=20, vol_pct=0.7, stop_mult=2.5 | 401 | 99/101/101 | 0.0153 | si |  |
| 7 | channel_n=20, vol_pct=0.8, stop_mult=1.5 | 350 | 82/87/96 | 0.0228 | si |  |
| 8 | channel_n=20, vol_pct=0.8, stop_mult=2.0 | 330 | 80/82/87 | 0.0185 | si |  |
| 9 | channel_n=20, vol_pct=0.8, stop_mult=2.5 | 314 | 76/81/81 | 0.0150 | si |  |
| 10 | channel_n=40, vol_pct=0.6, stop_mult=1.5 | 404 | 99/105/101 | 0.0236 | si |  |
| 11 | channel_n=40, vol_pct=0.6, stop_mult=2.0 | 369 | 92/94/90 | 0.0186 | si |  |
| 12 | channel_n=40, vol_pct=0.6, stop_mult=2.5 | 346 | 87/90/82 | 0.0155 | si |  |
| 13 | channel_n=40, vol_pct=0.7, stop_mult=1.5 | 339 | 81/90/83 | 0.0229 | si |  |
| 14 | channel_n=40, vol_pct=0.7, stop_mult=2.0 | 311 | 78/81/73 | 0.0185 | si |  |
| 15 | channel_n=40, vol_pct=0.7, stop_mult=2.5 | 296 | 76/79/68 | 0.0151 | si |  |
| 16 | channel_n=40, vol_pct=0.8, stop_mult=1.5 | 265 | 60/73/67 | 0.0221 | si |  |
| 17 | channel_n=40, vol_pct=0.8, stop_mult=2.0 | 248 | 58/68/60 | 0.0183 | si |  |
| 18 | channel_n=40, vol_pct=0.8, stop_mult=2.5 | 235 | 55/67/56 | 0.0148 | si |  |
| 19 | channel_n=55, vol_pct=0.6, stop_mult=1.5 | 361 | 91/90/90 | 0.0236 | si |  |
| 20 | channel_n=55, vol_pct=0.6, stop_mult=2.0 | 334 | 84/82/81 | 0.0185 | si |  |
| 21 | channel_n=55, vol_pct=0.6, stop_mult=2.5 | 315 | 80/79/74 | 0.0152 | si |  |
| 22 | channel_n=55, vol_pct=0.7, stop_mult=1.5 | 307 | 77/80/74 | 0.0226 | si |  |
| 23 | channel_n=55, vol_pct=0.7, stop_mult=2.0 | 285 | 74/72/66 | 0.0183 | si |  |
| 24 | channel_n=55, vol_pct=0.7, stop_mult=2.5 | 274 | 72/72/62 | 0.0148 | si |  |
| 25 | channel_n=55, vol_pct=0.8, stop_mult=1.5 | 242 | 57/66/61 | 0.0218 | si |  |
| 26 | channel_n=55, vol_pct=0.8, stop_mult=2.0 | 228 | 55/62/55 | 0.0179 | si |  |
| 27 | channel_n=55, vol_pct=0.8, stop_mult=2.5 | 216 | 52/61/51 | 0.0145 | si |  |

### n2-donchian-xauusd-h4.yaml
| # | Params | Ops IS | Pliegues | cost_R | Factible | Motivo |
|---:|---|---:|---|---:|---|---|
| 1 | channel_n=20, vol_pct=0.6, stop_mult=1.5 | 637 | 167/142/165 | 0.0395 | si |  |
| 2 | channel_n=20, vol_pct=0.6, stop_mult=2.0 | 573 | 153/130/141 | 0.0309 | si |  |
| 3 | channel_n=20, vol_pct=0.6, stop_mult=2.5 | 523 | 140/115/134 | 0.0258 | si |  |
| 4 | channel_n=20, vol_pct=0.7, stop_mult=1.5 | 521 | 133/123/133 | 0.0392 | si |  |
| 5 | channel_n=20, vol_pct=0.7, stop_mult=2.0 | 472 | 123/113/114 | 0.0309 | si |  |
| 6 | channel_n=20, vol_pct=0.7, stop_mult=2.5 | 441 | 117/103/108 | 0.0256 | si |  |
| 7 | channel_n=20, vol_pct=0.8, stop_mult=1.5 | 402 | 101/91/104 | 0.0374 | si |  |
| 8 | channel_n=20, vol_pct=0.8, stop_mult=2.0 | 369 | 94/85/92 | 0.0299 | si |  |
| 9 | channel_n=20, vol_pct=0.8, stop_mult=2.5 | 350 | 87/83/89 | 0.0247 | si |  |
| 10 | channel_n=40, vol_pct=0.6, stop_mult=1.5 | 504 | 133/112/129 | 0.0401 | si |  |
| 11 | channel_n=40, vol_pct=0.6, stop_mult=2.0 | 462 | 122/106/112 | 0.0322 | si |  |
| 12 | channel_n=40, vol_pct=0.6, stop_mult=2.5 | 433 | 115/99/107 | 0.0262 | si |  |
| 13 | channel_n=40, vol_pct=0.7, stop_mult=1.5 | 409 | 104/91/108 | 0.0398 | si |  |
| 14 | channel_n=40, vol_pct=0.7, stop_mult=2.0 | 380 | 98/87/94 | 0.0316 | si |  |
| 15 | channel_n=40, vol_pct=0.7, stop_mult=2.5 | 361 | 93/82/91 | 0.0257 | si |  |
| 16 | channel_n=40, vol_pct=0.8, stop_mult=1.5 | 317 | 77/71/89 | 0.0377 | si |  |
| 17 | channel_n=40, vol_pct=0.8, stop_mult=2.0 | 298 | 72/69/81 | 0.0305 | si |  |
| 18 | channel_n=40, vol_pct=0.8, stop_mult=2.5 | 287 | 66/68/79 | 0.0247 | si |  |
| 19 | channel_n=55, vol_pct=0.6, stop_mult=1.5 | 456 | 123/102/113 | 0.0401 | si |  |
| 20 | channel_n=55, vol_pct=0.6, stop_mult=2.0 | 417 | 114/97/96 | 0.0320 | si |  |
| 21 | channel_n=55, vol_pct=0.6, stop_mult=2.5 | 391 | 107/91/93 | 0.0259 | si |  |
| 22 | channel_n=55, vol_pct=0.7, stop_mult=1.5 | 374 | 96/84/97 | 0.0398 | si |  |
| 23 | channel_n=55, vol_pct=0.7, stop_mult=2.0 | 348 | 92/81/83 | 0.0311 | si |  |
| 24 | channel_n=55, vol_pct=0.7, stop_mult=2.5 | 330 | 87/76/81 | 0.0254 | si |  |
| 25 | channel_n=55, vol_pct=0.8, stop_mult=1.5 | 289 | 75/62/77 | 0.0377 | si |  |
| 26 | channel_n=55, vol_pct=0.8, stop_mult=2.0 | 273 | 72/60/70 | 0.0303 | si |  |
| 27 | channel_n=55, vol_pct=0.8, stop_mult=2.5 | 262 | 66/59/68 | 0.0245 | si |  |

### n2-ts-usdjpy-d1.yaml
| # | Params | Ops IS | Pliegues | cost_R | Factible | Motivo |
|---:|---|---:|---|---:|---|---|
| 1 | fast_n=20, slow_n=150, stop_mult=2.5 | 44 | 13/13/8 | 0.0139 | si |  |
| 2 | fast_n=20, slow_n=150, stop_mult=3.0 | 44 | 13/13/8 | 0.0115 | si |  |
| 3 | fast_n=20, slow_n=150, stop_mult=3.5 | 43 | 13/13/8 | 0.0099 | si |  |
| 4 | fast_n=20, slow_n=200, stop_mult=2.5 | 44 | 12/13/8 | 0.0118 | si |  |
| 5 | fast_n=20, slow_n=200, stop_mult=3.0 | 43 | 11/13/8 | 0.0099 | si |  |
| 6 | fast_n=20, slow_n=200, stop_mult=3.5 | 43 | 11/13/8 | 0.0085 | si |  |
| 7 | fast_n=20, slow_n=250, stop_mult=2.5 | 31 | 5/11/7 | 0.0132 | si |  |
| 8 | fast_n=20, slow_n=250, stop_mult=3.0 | 31 | 5/11/7 | 0.0110 | si |  |
| 9 | fast_n=20, slow_n=250, stop_mult=3.5 | 30 | 5/11/7 | 0.0098 | si |  |
| 10 | fast_n=50, slow_n=150, stop_mult=2.5 | 34 | 9/9/7 | 0.0153 | si |  |
| 11 | fast_n=50, slow_n=150, stop_mult=3.0 | 33 | 9/9/7 | 0.0121 | si |  |
| 12 | fast_n=50, slow_n=150, stop_mult=3.5 | 33 | 9/9/7 | 0.0104 | si |  |
| 13 | fast_n=50, slow_n=200, stop_mult=2.5 | 30 | 7/11/5 | 0.0151 | si |  |
| 14 | fast_n=50, slow_n=200, stop_mult=3.0 | 30 | 7/11/5 | 0.0127 | si |  |
| 15 | fast_n=50, slow_n=200, stop_mult=3.5 | 30 | 7/11/5 | 0.0109 | si |  |
| 16 | fast_n=50, slow_n=250, stop_mult=2.5 | 27 | 5/10/5 | 0.0159 | si |  |
| 17 | fast_n=50, slow_n=250, stop_mult=3.0 | 27 | 5/10/5 | 0.0133 | si |  |
| 18 | fast_n=50, slow_n=250, stop_mult=3.5 | 27 | 5/10/5 | 0.0114 | si |  |
| 19 | fast_n=100, slow_n=150, stop_mult=2.5 | 39 | 11/11/9 | 0.0152 | si |  |
| 20 | fast_n=100, slow_n=150, stop_mult=3.0 | 38 | 11/11/8 | 0.0123 | si |  |
| 21 | fast_n=100, slow_n=150, stop_mult=3.5 | 38 | 11/11/8 | 0.0105 | si |  |
| 22 | fast_n=100, slow_n=200, stop_mult=2.5 | 28 | 7/9/5 | 0.0168 | si |  |
| 23 | fast_n=100, slow_n=200, stop_mult=3.0 | 28 | 7/9/5 | 0.0140 | si |  |
| 24 | fast_n=100, slow_n=200, stop_mult=3.5 | 28 | 7/9/5 | 0.0120 | si |  |
| 25 | fast_n=100, slow_n=250, stop_mult=2.5 | 24 | 6/7/5 | 0.0122 | si |  |
| 26 | fast_n=100, slow_n=250, stop_mult=3.0 | 24 | 6/7/5 | 0.0114 | si |  |
| 27 | fast_n=100, slow_n=250, stop_mult=3.5 | 24 | 6/7/5 | 0.0097 | si |  |

### n2-ts-xauusd-d1.yaml
| # | Params | Ops IS | Pliegues | cost_R | Factible | Motivo |
|---:|---|---:|---|---:|---|---|
| 1 | fast_n=20, slow_n=150, stop_mult=2.5 | 36 | 7/11/11 | 0.0152 | si |  |
| 2 | fast_n=20, slow_n=150, stop_mult=3.0 | 36 | 7/11/11 | 0.0127 | si |  |
| 3 | fast_n=20, slow_n=150, stop_mult=3.5 | 35 | 7/10/11 | 0.0108 | si |  |
| 4 | fast_n=20, slow_n=200, stop_mult=2.5 | 28 | 7/9/9 | 0.0141 | si |  |
| 5 | fast_n=20, slow_n=200, stop_mult=3.0 | 27 | 7/9/8 | 0.0118 | si |  |
| 6 | fast_n=20, slow_n=200, stop_mult=3.5 | 27 | 7/9/8 | 0.0101 | si |  |
| 7 | fast_n=20, slow_n=250, stop_mult=2.5 | 26 | 6/9/8 | 0.0148 | si |  |
| 8 | fast_n=20, slow_n=250, stop_mult=3.0 | 26 | 6/9/8 | 0.0123 | si |  |
| 9 | fast_n=20, slow_n=250, stop_mult=3.5 | 26 | 6/9/8 | 0.0106 | si |  |
| 10 | fast_n=50, slow_n=150, stop_mult=2.5 | 27 | 5/9/8 | 0.0143 | si |  |
| 11 | fast_n=50, slow_n=150, stop_mult=3.0 | 27 | 5/9/8 | 0.0119 | si |  |
| 12 | fast_n=50, slow_n=150, stop_mult=3.5 | 27 | 5/9/8 | 0.0102 | si |  |
| 13 | fast_n=50, slow_n=200, stop_mult=2.5 | 23 | 6/6/8 | 0.0140 | si |  |
| 14 | fast_n=50, slow_n=200, stop_mult=3.0 | 23 | 6/6/8 | 0.0117 | si |  |
| 15 | fast_n=50, slow_n=200, stop_mult=3.5 | 23 | 6/6/8 | 0.0101 | si |  |
| 16 | fast_n=50, slow_n=250, stop_mult=2.5 | 16 | 6/7/2 | 0.0164 | NO | pliegue 3 trades 2 < 3 |
| 17 | fast_n=50, slow_n=250, stop_mult=3.0 | 16 | 6/7/2 | 0.0136 | NO | pliegue 3 trades 2 < 3 |
| 18 | fast_n=50, slow_n=250, stop_mult=3.5 | 16 | 6/7/2 | 0.0117 | NO | pliegue 3 trades 2 < 3 |
| 19 | fast_n=100, slow_n=150, stop_mult=2.5 | 22 | 5/6/8 | 0.0140 | si |  |
| 20 | fast_n=100, slow_n=150, stop_mult=3.0 | 22 | 5/6/8 | 0.0117 | si |  |
| 21 | fast_n=100, slow_n=150, stop_mult=3.5 | 22 | 5/6/8 | 0.0100 | si |  |
| 22 | fast_n=100, slow_n=200, stop_mult=2.5 | 18 | 4/2/9 | 0.0145 | NO | pliegue 2 trades 2 < 3 |
| 23 | fast_n=100, slow_n=200, stop_mult=3.0 | 18 | 4/2/9 | 0.0121 | NO | pliegue 2 trades 2 < 3 |
| 24 | fast_n=100, slow_n=200, stop_mult=3.5 | 18 | 4/2/9 | 0.0104 | NO | pliegue 2 trades 2 < 3 |
| 25 | fast_n=100, slow_n=250, stop_mult=2.5 | 14 | 4/6/3 | 0.0169 | NO | trades IS 14 < 15 |
| 26 | fast_n=100, slow_n=250, stop_mult=3.0 | 14 | 4/6/3 | 0.0141 | NO | trades IS 14 < 15 |
| 27 | fast_n=100, slow_n=250, stop_mult=3.5 | 14 | 4/6/3 | 0.0120 | NO | trades IS 14 < 15 |
