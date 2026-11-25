# RESULTADO P4 · Specs v2 para la Fase 4 (borradores)

- **Fecha:** 2026-11-24
- **Commit:** `tl2: P4 - specs v2 de la fase 4`
- **Tag:** `tl2-p4`
- **Alcance:** solo `preflight` y `feasibility`. No se registró, aprobó ni
  ejecutó ninguna campaña; no se leyó OOS-1 ni OOS-2; no se calculó
  expectativa, PF, percentil ni ningún rendimiento.

## Specs escritas

| Spec | Familia | Símbolos | Rejilla | Meseta | Primaria (literatura) |
|---|---|---|---:|---:|---|
| `v2-fix-londres-eurgbp-h1.yaml` | `fx_fix` | EURUSD, GBPUSD | 9 | 9 | fix 15:00-15:59, largo, salida 1 h, stop 2,5 ATR |
| `v2-tom-indices-d1.yaml` | `calendario` | US500, US100 | 9 | 9 | N=1 (último día hábil), M=3 |
| `v2-tsmom-cesta-d1.yaml` | `momentum` | XAUUSD, US500, US100, EURUSD, GBPUSD, USDJPY | 9 | 9 | fast=50 / slow=200 (proxy de 12m/1m) |
| `v2-rebote-indices-d1.yaml` | `reversion` | US500, US100 | 9 | 9 | extensión z=-2σ con n=10, stop 1,5 ATR |

Todas llevan `protocol_version: 2`, `cost_model_version: 2`,
`spread_model: historical_scaled`, `holdout_start: 2025-07-01`, `primary:`,
`plateau_grid:` de 9 puntos, `plausible_edge_r` y `family:`.

Notas de ejecución:

- La ventana del fix (15:00-15:59 Londres, largo) sale de la plantilla
  `fix_reversal`; los campos `side`, `fix_start` y `fix_end` de la spec la
  documentan, pero `basket.load` no los reaplica. La feasibility confirma que
  la ventana y el lado son los de la plantilla.
- La meseta del fix incluye `stop_mult=2.0` (fuera del `parameter_space`
  original) para medir robustez; la primaria sigue en 2.5, que es la que
  recomiendan la literatura y el coste.
- La cesta de momentum son los 6 símbolos de Q3, no una cesta nueva; el
  instrumento base del DSL es XAUUSD y la familia los sustituye en cada pierna.

### Primarias y literatura

- **fx_fix:** Evans (2018) y Krohn, Mueller & Whelan (2024) documentan la
  reversión tras el fix de las 16:00 de Londres. La salida a 1 h es la más
  corta de las tres probadas por la plantilla y la que menos expone el efecto
  a noticias posteriores. `plausible_edge_r = 0,05` porque el propio
  `HIPOTESIS-4-10.md` cifra el coste del fix en 0,05-0,09 R.
- **calendario:** Ariel (1987), Lakonishok & Smidt (1988) y McConnell & Xu
  (2008): entrar el último día hábil (N=1) y salir el día 3 del mes siguiente
  (M=3).
- **momentum:** Moskowitz/Ooi/Pedersen (2012) y Hurst/Ooi/Pedersen (2017)
  usan 12 meses / 1 mes. La plantilla D1 no tiene ventanas de 12 meses ni de
  1 mes: el proxy declarado es fast_n=50 y slow_n=200 (≈2,5 y 10 meses de
  velas D1). No se puede afirmar que sea el 12m/1m exacto; queda explicado.
- **reversion:** Connors/Alvarez (RSI-2, 2008), Jegadeesh (1990) y
  De Bondt/Thaler (1985): extensión de 2σ y stop 1,5 ATR. La ventana n=10 es
  la más corta de la rejilla y la más cercana a RSI-2.
- **δ:** 0,05 R en `fx_fix` y 0,10 R en las tres familias D1 (el mismo
  `cost_r_max` del motor, efecto mínimo que compensa el coste).

### Símbolos descartados

- **GER40:** no hay datos en la caché local (`usable_from` Sin datos).
- **US30:** hay datos D1 (`usable_from 2015-01-01`), pero
  `broker_spreads[broker:CFD-006]` no tiene filas para `DJI30`; sin costes no
  entra. Se probó y `feasibility` falló con `Sin datos`, así que la familia de
  calendario se queda en US500 + US100, como permite la cola.

## Preflight

| Spec | Población | Válidos | Rechazados | Duplicados |
|---|---:|---:|---:|---:|
| fix-londres | 9 | 9 | 0 | 0 |
| tom-indices | 9 | 9 | 0 | 0 |
| tsmom-cesta | 9 | 9 | 0 | 0 |
| rebote-indices | 9 | 9 | 0 | 0 |

## Feasibility

| Spec | Factibles | % | `cost_r` mediano | `cost_r` p90 | `cost_r` máximo |
|---|---:|---:|---:|---:|---:|
| fix-londres | 9/9 | 100,0 % | 0,0316 | 0,0525 | 0,1690 |
| tom-indices | 9/9 | 100,0 % | 0,0275 | 0,0538 | 0,0943 |
| tsmom-cesta | 8/9 | 88,9 % | 0,0526 | 0,3210 | 1,1297 |
| rebote-indices | 7/9 | 77,8 % | 0,0503 | 0,1029 | 0,1328 |

`cost_r` es la mediana por operación de la primaria, en R, con el libro de
costes v2 (`historical_scaled`); el p90 y el máximo se calculan sobre las
mismas operaciones. `cost_r_max = 0,10`.

- **fix-londres:** el libro `best` reparte entre CFD-001 y CFD-006; medianas
  por cuenta 0,0367 y 0,0286. El p90 (0,0525) queda por debajo del límite,
  pero el máximo (0,1690) lo supera en la cola.
- **tom-indices:** todo bajo 0,10, incluso el máximo.
- **tsmom-cesta:** la mediana pasa, pero el p90 (0,3210) y el máximo (1,1297)
  están muy por encima de 0,10. La regla actual solo mira la mediana; la cola
  es un riesgo real de la familia de 6 símbolos.
- **rebote-indices:** mediana 0,0503; el p90 (0,1029) roza el límite y el
  máximo (0,1328) lo supera.

## Potencia (holdout v2)

Definición v2 (T22): **desarrollo** = todo lo anterior a `holdout_start`;
**holdout** = desde `holdout_start` (2025-07-01) hasta hoy (2026-11-24),
1,40 años. Las operaciones se escalan por duración desde las de IS de la
primaria; son estimaciones, no conteos observados en OOS.

| Spec | Ops desarrollo | Ops holdout | MDE holdout | δ | `potencia_ok` |
|---|---:|---:|---:|---:|---|
| fix-londres | 8.047 | 727 | 0,0923 | 0,05 | **No** |
| tom-indices | 157 | 29 | 0,4624 | 0,10 | **No** |
| tsmom-cesta | 44 | 8 | 0,8803 | 0,10 | **No** |
| rebote-indices | 35 | 6 | 1,0165 | 0,10 | **No** |

Ninguna spec tiene potencia para detectar su δ en el holdout v2: el holdout
sellado es corto (1,4 años) y las familias D1 generan pocas operaciones.
Con la definición antigua de holdout (OOS-1 + OOS-2, 2,4 años) los MDE serían
0,0706 / 0,3521 / 0,6655 / 0,7508; el veredicto sigue siendo **No** en las
cuatro. No se ha leído OOS-1 ni OOS-2 para obtener estos números.

**Lectura para el operador:** `fix-londres` es la única que se acerca
(MDE 0,092 frente a δ 0,05; haría falta un δ de 0,10 o un holdout ≈3,4 veces
mayor, unos 4,8 años, para bajar el MDE a 0,05). Las tres D1 necesitan muchos
más años de holdout o un δ mayor; con 6-29 operaciones esperadas, cualquier
resultado del holdout será ruido.

## Ajuste mínimo de código

`basket._check_frames` no exponía `trades_is` en el agregado, y
`campaigns.approve(verify=True)` lo necesita para la puerta de potencia de
una cesta. Se añade la mediana de `trades_is` de las filas (misma convención
que `feasibility.check` para individuos). Test existente ampliado en
`tests/test_discovery_basket_run.py`.

## Tests

- `ruff check` sobre `basket.py` y `test_discovery_basket_run.py`: limpio.
- `pytest tests/test_discovery_basket_run.py`: **10 passed** (2:26).

## Rollback

Borrar los cuatro YAML de `.orquestador/specs/` y revertir el campo
`trades_is` del agregado de `_check_frames`. No hay campañas registradas ni
datos que recalcular.
