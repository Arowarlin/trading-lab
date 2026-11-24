# RESULTADO · R9c — swap de financiación en el coste

Fecha: 2026-11-23. Sesión única en `E:\trading-lab`, HEAD `dd2f1f8` + R9c.
Sin registrar/aprobar/ejecutar campañas, sin OOS, sin push, sin tareas
programadas, sin borrar, sin operar y sin tocar el carril del EA.

## 1. Diagnóstico

Antes de R9c el swap **no se cobraba** en el backtest del Discovery:

- `src/tradinglab/propfund/costs.py:338-397` (`estimate_cfd`) sí acepta
  `nights` y cobra swap, pero solo cuando el llamador lo pide
  (`:374 if nights:`). El router de propfund lo llama con `nights=0`.
- `src/tradinglab/discovery/fastbt.py:221` (`CfdProfileCosts.panel`) solo
  construía bps de entrada/salida; el núcleo calculaba `r_cost` con esos bps,
  sin noches.
- `src/tradinglab/discovery/costs.py:377` (`CostBook.apply`) reasignaba
  entrada/salida por cuenta, también sin swap.

Por tanto, las posiciones que cruzaban el rollover tenían el coste
subestimado. R9c lo corrige en el motor, en `CostBook` y en el control de
deriva.

## 2. Medición MT5 (attach-only)

Login verificado antes y después:

| Cuenta | Login antes | Login después | Servidor |
|---|---:|---:|---|
| CFD-001 | 1515349730 | 1515349730 | FTMO-Demo |
| CFD-006 | 40000459328 | 40000459328 | FundingPips-Trial |

Medición: `symbol_info` de MT5, 2026-11-23T22:57:47Z, sin órdenes. El rollover
es 00:00 del servidor = **17:00 America/New_York**; MT5 no expone la hora, se
usa el corte de sesión NY. Los valores crudos y la fuente quedan en
`config/propfund/swap.yaml`, que `load_profile` fusiona en el perfil.

| Cuenta | Símbolo MT5 | swap_long | swap_short | swap_mode | triple (servidor) | point |
|---|---|---:|---:|---|---|---:|
| CFD-001 | US100.cash | 1076.28 | -1677.49 | 1 points | viernes | 0.01 |
| CFD-001 | US500.cash | 32.83 | -198.56 | 1 points | viernes | 0.01 |
| CFD-001 | US30.cash | -391.97 | -760.67 | 1 points | viernes | 0.01 |
| CFD-001 | XAUUSD | -54.46 | -15.0 | 1 points | miércoles | 0.01 |
| CFD-001 | EURUSD | -8.44 | 0.19 | 1 points | miércoles | 0.00001 |
| CFD-001 | GBPUSD | -4.47 | -5.88 | 1 points | miércoles | 0.00001 |
| CFD-001 | USDJPY | 1.78 | -17.83 | 1 points | miércoles | 0.001 |
| CFD-006 | NDX100 | -7.33 | -1.33 | 5 interest_current | viernes | 0.01 |
| CFD-006 | SPX500 | -7.33 | -1.33 | 5 interest_current | viernes | 0.01 |
| CFD-006 | DJI30 | -7.33 | -1.33 | 5 interest_current | viernes | 0.01 |
| CFD-006 | XAUUSD | -67.986 | 25.026 | 1 points | miércoles | 0.01 |
| CFD-006 | EURUSD | -8.191 | 3.857 | 1 points | miércoles | 0.00001 |
| CFD-006 | GBPUSD | -2.872 | -1.38 | 1 points | miércoles | 0.00001 |
| CFD-006 | USDJPY | 4.542 | -18.868 | 1 points | miércoles | 0.001 |

`swap_mode=1` se convierte con `point`; `swap_mode=5` usa interés anual sobre
el precio de entrada y convención 360 días. El modo queda guardado para no
inventar una conversión distinta.

## 3. Cobro en el backtest

- `CostProfile` amplía `swap_long`, `swap_short`, `swap_mode`,
  `swap_rollover3days`, `swap_rollover_hour`, `swap_rollover_tz`, `point`,
  `swap_source`, `swap_measured_at`.
- `SwapSpec` y `rollover_units` en `propfund/costs.py`: cuentan los cierres
  diarios 17:00 NY estrictamente posteriores a la entrada y hasta la salida;
  lunes a viernes; el día triple del servidor se aplica al cierre NY anterior.
- `fastbt.run` ajusta cada `Trade` con `swap_r` (positivo = crédito, negativo =
  coste): `r_cost -= swap_r`, `r_net += swap_r`; `Trade.swap_r` queda expuesto.
- `CostBook.apply` lo aplica **por cuenta** antes de elegir best/worst/target,
  igual que el resto de costes; `cost_by_account` y `cost_R` lo incluyen.
- El control de deriva (`drift.outcome_tables`) cobra el swap de la cuenta
  representativa en las entradas aleatorias.
- `estimate_cfd` usa el nuevo `SwapSpec` cuando recibe `nights`; conserva el
  fallback `swap_*_per_lot` para perfiles antiguos.

Tests (`tests/test_discovery_swap.py`, 6 passed): 0/1/3 noches, día triple,
largo vs corto, swap positivo, `fastbt` y `CostBook` best/worst.

## 4. Peso del swap en R (ATR D1 últimos 12 meses)

`cost_r_for` da precio y ATR D1; el swap se expresa en R por noche con el
`SwapSpec` medido. No es rendimiento: es coste. Negativo = coste; positivo =
crédito.

| Cuenta | Símbolo | Lado | R/noche | 3 noches | 5 noches |
|---|---|---|---:|---:|---:|
| CFD-001 | US100 | largo | +0.021303 | +0.063910 | +0.106517 |
| CFD-001 | US100 | corto | -0.033203 | -0.099610 | -0.166017 |
| CFD-001 | US500 | largo | +0.003993 | +0.011980 | +0.019967 |
| CFD-001 | US500 | corto | -0.024153 | -0.072459 | -0.120765 |
| CFD-001 | US30 | largo | -0.006546 | -0.019639 | -0.032731 |
| CFD-001 | US30 | corto | -0.012704 | -0.038111 | -0.063519 |
| CFD-001 | XAUUSD | largo | -0.005347 | -0.016041 | -0.026736 |
| CFD-001 | XAUUSD | corto | -0.001473 | -0.004418 | -0.007364 |
| CFD-001 | EURUSD | largo | -0.013968 | -0.041903 | -0.069839 |
| CFD-001 | EURUSD | corto | +0.000314 | +0.000943 | +0.001572 |
| CFD-001 | GBPUSD | largo | -0.005747 | -0.017240 | -0.028734 |
| CFD-001 | GBPUSD | corto | -0.007560 | -0.022679 | -0.037798 |
| CFD-001 | USDJPY | largo | +0.001745 | +0.005234 | +0.008723 |
| CFD-001 | USDJPY | corto | -0.017475 | -0.052425 | -0.087374 |
| CFD-006 | US100 | largo | -0.011321 | -0.033962 | -0.056604 |
| CFD-006 | US100 | corto | -0.002054 | -0.006162 | -0.010271 |
| CFD-006 | US500 | largo | -0.018257 | -0.054772 | -0.091286 |
| CFD-006 | US500 | corto | -0.003313 | -0.009938 | -0.016564 |
| CFD-006 | US30 | largo | -0.017061 | -0.051183 | -0.085305 |
| CFD-006 | US30 | corto | -0.003096 | -0.009287 | -0.015478 |
| CFD-006 | XAUUSD | largo | -0.006675 | -0.020025 | -0.033376 |
| CFD-006 | XAUUSD | corto | +0.002457 | +0.007371 | +0.012286 |
| CFD-006 | EURUSD | largo | -0.013556 | -0.040667 | -0.067778 |
| CFD-006 | EURUSD | corto | +0.006383 | +0.019149 | +0.031916 |
| CFD-006 | GBPUSD | largo | -0.003692 | -0.011077 | -0.018462 |
| CFD-006 | GBPUSD | corto | -0.001774 | -0.005323 | -0.008871 |
| CFD-006 | USDJPY | largo | +0.004452 | +0.013355 | +0.022258 |
| CFD-006 | USDJPY | corto | -0.018492 | -0.055477 | -0.092461 |

Lectura: el US100 largo de FTMO tiene swap **positivo** (+0.0213 R/noche);
por eso su cost_R puede quedar por debajo de cero. No es un error: es un
crédito de financiación. El US500 largo de CFD-006 es el más caro de los
índices (−0.0183 R/noche).

## 5. Campañas ya ejecutadas con posiciones nocturnas

No se recalcularon ni cambiaron de estado. Revisadas las 8 campañas de
`discovery.db`:

- **n2-donchian-xauusd-h4**: cruza rollover. 10.879 operaciones, media 17,21
  barras H4 = 2,87 noches; 48,5 % largos. Mejor swap por lado (CFD-001 largo /
  CFD-006 corto): −0,001326 R/noche ⇒ **≈ −0,0038 R/op** no cobrados;
  ≈ **−41 R** en total (estimación).
- **n2-donchian-usdjpy-h4**: cruza rollover. 9.230 operaciones, media 15,34
  barras H4 = 2,56 noches; 42,2 % largos. Mejor swap por lado (CFD-006 largo /
  CFD-001 corto): −0,008224 R/noche ⇒ **≈ −0,0210 R/op**; ≈ **−194 R** en total
  (estimación).
- Las otras 6 (c1-asia-usdjpy-h1-long, campañas M5 US100) son intradía o
  terminan antes del corte 17:00 NY; no cruzan rollover.

Las estimaciones usan la media de barras y la proporción de lados guardadas /
del informe; no se reejecutó ningún backtest.

## 6. Preflight y feasibility con swap

Preflight: 9/9 válidos, 0 rechazados en `r9-tom-us500-d1` y
`r9-tom-us100-d1`.

Feasibility (solo coste, permitido), cost_R de las 9 combinaciones:

| Spec | Antes (R9) | Ahora (R9c) | Factibles |
|---|---|---|---|
| US500 Dukascopy | 0.0149–0.0174 | **0.0316, 0.0389, 0.0446, 0.0384, 0.0466, 0.0576, 0.0482, 0.0557, 0.0638** | 9/9 |
| US100 Dukascopy | 0.0085–0.0093 | **−0.0587, −0.1209, −0.1405, −0.0997, −0.1550, −0.2147, −0.1608, −0.2042, −0.2626** | 9/9 |

El US100 negativo es el crédito de swap largo de FTMO; el US500 sube porque
CFD-006 cobra interés negativo. Ambas pasan el gate de coste 0,10 (una cuenta
negativa no es un fallo de coste).

## 7. Verificación

- `ruff check src/tradinglab tests docs`: limpio.
- `pytest -q`: **1779 passed, 1 skipped**.
- `lab propfund verify`: **4 OK** (no se re-selló ningún protegido).
- `count_tests`: **1775**.
- `preflight`/`feasibility` de ambas specs: OK.
- Sin push, sin campañas, sin OOS, sin órdenes.

## Commits y tag

```text
5e0130b  tl2: R9c - swap en el coste  (tl2-r9c)
```

## Avisos

- La hora de rollover no la expone MT5; se usa 00:00 servidor = 17:00 NY y
  queda documentado en `swap.yaml`.
- `swap_mode=5` usa interés anual / 360; es la convención del modelo, no una
  liquidación real del bróker.
- Las estimaciones de la tarea 5 son eso, estimaciones; no se recalculó ni se
  reclasificó ninguna campaña.

PARA.
