# RESULTADO · COLA-NOCHE

Fecha: 2026-11-23 (la cola cruzó medianoche UTC). Repo `E:\trading-lab`,
rama `feature/prop-fund-multifirm`. No se registró, aprobó, ejecutó, confirmó
ni supersedió ninguna campaña; no se leyó OOS-1/OOS-2; no se hizo push; no se
tocaron tareas programadas, umbrales, el carril del EA, `us100-trend-d1` ni el
worktree `tl2-f12`.

## N1 · FundingPips CFD-006 = 2-Step Standard

Hecho:

- `config/propfund/accounts.yaml`: CFD-006 pasa a 5 % diario (5.000), 10 %
  máximo estático (10.000), objetivo 8 % P1 (8.000), 3 días mínimos y base
  `higher_of_balance_or_equity`.
- `config/propfund/firms.yaml`: programa `fundingpips_2step` renombrado
  “2-Step Standard” con 13 reglas (8/5 %, 5 %, 10 % estático, base, reset,
  3 días, comisión 5 USD/lote ida y vuelta en forex/metales, 0 en
  índices/energía, 3 %/2 % por idea en fondeada). El programa Trial recibe
  base, reset y comisión.
- `config/propfund/costs.yaml`: `commission_side` de CFD-006 pasa a
  `round_turn`; la comisión ya no se duplica (5 USD/lote, no 10).
- `AccountLimits.daily_loss_base` y aviso en `_rules_from_account`: overlay y
  MC prop (protegidos) solo modelan equidad; la diferencia con “mayor de
  balance o equidad” queda declarada, no oculta.
- Onboarding-mtf CFD-006 recalculado: bajan cost_R en XAU/FX (EURUSD H4
  0,0973 → 0,0751; GBPUSD H4 0,0851 → 0,0681); **ninguna celda cambia de
  viable**. Detalle en `RESULTADO-N1.md` y los JSON `onboarding-mtf-CFD-006-*`.

Commit `236f0b1` · tag `tl2-n1`.

## N2 · Plantillas H4/D1

Hecho:

- Tres plantillas nuevas en `config/discovery/templates/`:
  `ts_momentum_d1` (D1, simétrica), `donchian_vol_h4` (H4, simétrica) y
  `d1_extension_reversion` (D1, long-only). `valid_timeframes` solo H4/D1,
  3 parámetros, grid 27.
- `grid.grid_strategies` respeta `symmetric`: una plantilla long-only conserva
  `short_entry: null` (antes lo espejaba y duplicaba nodos).
- Tests nuevos: validación, lookahead por plantilla, rejilla 27 única y
  paridad Python/numba de las salidas completas (stop, target, trailing y
  salida temporal).
- Seis specs `n2-*` en `.orquestador/specs/`: preflight **27/27** en las seis;
  feasibility en seco **15/27 a 27/27**, gate ≥50 % superado en todas. Sin
  registrar campañas, sin OOS, sin PnL.
- A (tendencia D1) necesitó una salida máxima de 60 días para pasar el gate de
  tiempo medio; no se cambió ningún umbral.

Commits `c2cecea` + fixes `e1d4f69` (recuento de 8 plantillas en el test DSL) y
`a246eeb` (fecha de mercado en tests de comparación). Tag `tl2-n2`.

## N3 · Propuestas para la mañana

`.orquestador/PROPUESTAS-manana.md` (solo papel):

- Tabla de las seis specs ordenadas por operaciones IS y coste, con n_total 27,
  cuentas viables CFD-001/CFD-006 y DSR 1703 → 1730 por spec (1865 las seis).
- Recomendación: **`n2-donchian-xauusd-h4`** (27/27 factible, 391 ops IS
  medianas, cost_R mediano 0,0309, sin solape con la incubación
  `us100-trend-d1`), sin mirar rendimiento.
- Comandos exactos `register` / `approve` / `run` / `results`.

## Comprobaciones

- `pytest -q`: **1635 passed, 1 skipped** (1 warning preexistente: `psutil`
  no instalado). 1:13:49, dominado por `test_noise_five_campaigns`.
- `ruff check src/tradinglab tests`: limpio.
- `lab propfund verify`: **4 OK** (ai_trader, ea_us100_ftmo1, ftmo_forward,
  ftmo_risk).
- `count_tests`: **1703** (sin registrar; `lab lessons holdout`).
- `git status --short`: solo `?? tl2-edge-map.patch` (archivo previo, sin
  tocar). `PLAN.md` actualizado y comiteado en `c684ac9`.

## Incidencia

La primera suite completa se bloqueó porque la sesión F12 estaba ejecutando su
prueba de ruido con 12 workers en paralelo. No se tocó su worktree: se esperó a
que terminara y se relanzó la suite en solitario. Al cruzar medianoche UTC
aparecieron fallos preexistentes de fecha (`date.today()` local frente a
`market_today()` de Nueva York) en `test_agent_compare` y `test_model_compare`;
se corrigieron los tests para usar la fecha de mercado y la suite quedó verde.
El test DSL que fijaba 5 plantillas se actualizó a 8.

COLA-NOCHE TERMINADA
