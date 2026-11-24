# RESULTADO · N1 — FundingPips CFD-006 = 2-Step Standard

Fecha: 2026-11-22. Repo `E:\trading-lab`, rama `feature/prop-fund-multifirm`.
No se registró, aprobó, ejecutó, confirmó ni supersedió ninguna campaña; no se
leyó OOS-1/OOS-2; no se hizo push; no se tocaron tareas programadas, umbrales,
el carril del EA, `us100-trend-d1` ni el worktree `tl2-f12`.

## 1. Contraste regla | configurado antes | público | ¿coincide?

| Regla pública 2-Step Standard | Configurado antes | Público | ¿Coincidía? |
|---|---|---|---|
| Fase 1: objetivo 8 % | `profit_target: 6000` (6 %, Pro) | 8 % = 8.000 USD | **No** |
| Fase 2: objetivo 5 % | No declarado (la cuenta está en evaluación) | 5 % = 5.000 USD | **No declarado** |
| Pérdida diaria 5 % | `daily_loss: 3000` (3 %, Pro) | 5 % = 5.000 USD | **No** |
| Base de la pérdida diaria | No declarada; motores usan equidad | Mayor de balance o equidad al inicio del día; flotante + cerrado | **No** |
| Pérdida máxima 10 % estática | `max_loss: 6000` (6 %, Pro), `drawdown_mode: static` | 10 % = 10.000 USD, estática | **No** (el modo sí) |
| Mínimo 3 días de trading por fase | `min_trading_days: 0` | 3 días | **No** |
| Comisión forex/metales | 5 USD/lote **por lado** (`per_side`) = 10 USD/lote ida y vuelta | 5 USD/lote **ida y vuelta** | **No** (se duplicaba) |
| Comisión índices/energía | 0 | 0 | Sí |
| Máx. 20 lotes por operación | `max_lots: 20` | 20 | Sí |
| Riesgo máx. por idea (fondeada) | 0,5 %/trade interno; sin cap de firma declarado | 3 % (<50K) / 2 % (>=50K) | Cumple (0,5 % < 2 %), pero el cap no estaba declarado |
| Reinicio diario | 00:00 del servidor (supuesto técnico) | Medianoche del servidor | Coincide el supuesto, no verificado en panel |
| Drawdown | `static` | Estático | Sí |

Corregido en archivos **no protegidos**:

- `config/propfund/accounts.yaml` · CFD-006: límites `daily_loss 5000`,
  `max_loss 10000`, `profit_target 8000`, `min_trading_days 3`,
  `daily_loss_base: higher_of_balance_or_equity`; notas con el modelo
  confirmado por el operador y el riesgo de cuenta fondeada.
- `config/propfund/firms.yaml` · `fundingpips_2step`: programa renombrado
  `2-Step Standard`, con 13 reglas (objetivos 8/5 %, diario 5 %, máximo 10 %
  estático, base mayor de balance/equidad, reset 00:00 servidor, 3 días,
  comisión 5 USD/lote ida y vuelta en forex/metales, 0 en índices/energía y
  3 %/2 % por idea en fondeada). Estado `needs_verification`: es dato del
  operador y debe confirmarse en el panel.
- `config/propfund/firms.yaml` · `fundingpips_trial`: mismas reglas de base
  diaria, reset y comisión añadidas al programa que usa CFD-006.
- `config/propfund/costs.yaml` · CFD-006: `commission_side` pasa de
  `per_side` a `round_turn` en los 7 símbolos; la fuente dice “5 USD por lote
  ida y vuelta (dato del operador 2026-11-22)”. Los índices siguen a 0.
- `src/tradinglab/propfund/models.py`: `AccountLimits.daily_loss_base`
  (`balance` | `equity` | `higher_of_balance_or_equity`).
- `src/tradinglab/propfund/snapshots.py`: `_rules_from_account` traduce la
  base declarada a `PropRules.daily_loss_mode` (balance/equity) y, cuando la
  firma usa el mayor de ambos, deja la advertencia en `notes` porque
  `PropRules` solo modela equidad.

## 2. Cómo calculan la pérdida diaria el overlay y el MC prop

| Motor | Archivo | Base del día | Flotante | ¿Coincide con FundingPips? |
|---|---|---|---|---|
| Overlay de firma | `src/tradinglab/prop/overlay.py` (protegido) | `day_start = equity` al cambiar el día local | Solo retornos de barras; no separa flotante | **No exacto**: la firma usa `max(balance, equity)` |
| MC prop (días) | `src/tradinglab/prop/simulator.py::monte_carlo` (protegido) | `day_start = equity` antes del retorno del día | No modela flotante intradía | **No exacto**: equity, no el mayor |
| MC prop (por trade) | `src/tradinglab/prop/simulator.py::multiverse_by_trade` (protegido) | `initial + cumsum(PnL cerrado)` | No modela flotante | **No exacto** |
| Guard de reglas | `src/tradinglab/prop/guard.py` (protegido) | `day_start_balance` si el modo es `balance`; si no, `day_start_equity` | No hay modo “mayor de ambos” | **No exacto**: no existe `daily_loss_mode=max` |
| Stop diario de cuenta | `src/tradinglab/account_daily.py` (protegido) | `day_start_equity` | No modela flotante | **No exacto** |

No se tocó ninguno de esos archivos: están en el manifiesto protegido
(`ftmo_risk`). La diferencia queda declarada en la cuenta y avisada en
`_rules_from_account`; para igualar la regla haría falta un modo nuevo en
`PropRules`/`PropGuard`, decisión del operador.

El `buffer_vs_firm_pct: 0.20` de CFD-006 hace que el límite interno efectivo
sea 4 % (80 % de 5 %), por debajo del 5 % público: es colchón, no un
incumplimiento.

## 3. Onboarding-mtf de CFD-006 recalculado

Comando ejecutado en lectura: `build_rows(("CFD-006",), ...)` con la misma
función única `cost_r_for` que usan `lab propfund onboarding-mtf` y
`lab discovery suggest`. R típico = mediana ATR(14) de los últimos 12 meses.

| Símbolo | TF | cost_R antes | cost_R después | Viable antes | Viable después |
|---|---|---:|---:|---|---|
| US100 | H4 | 0,0221 | 0,0221 | Sí | Sí |
| US100 | D1 | 0,0081 | 0,0081 | Sí | Sí |
| US500 | H4 | 0,0724 | 0,0724 | Sí | Sí |
| US500 | D1 | 0,0278 | 0,0278 | Sí | Sí |
| US30 | H4 | Sin datos | Sin datos | no | no |
| US30 | D1 | Sin datos | Sin datos | no | no |
| XAUUSD | H4 | 0,0182 | **0,0169** | Sí | Sí |
| XAUUSD | D1 | 0,0068 | **0,0063** | Sí | Sí |
| EURUSD | H4 | 0,0973 | **0,0751** | Sí | Sí |
| EURUSD | D1 | 0,0364 | **0,0281** | Sí | Sí |
| GBPUSD | H4 | 0,0851 | **0,0681** | Sí | Sí |
| GBPUSD | D1 | 0,0321 | **0,0257** | Sí | Sí |
| USDJPY | H4 | 0,0405 | **0,0404** | Sí | Sí |
| USDJPY | D1 | 0,0148 | **0,0148** | Sí | Sí |

Celdas que cambian de viable: **ninguna**. Bajan cost_R todos los símbolos con
comisión (XAUUSD y los tres pares FX), sobre todo EURUSD H4 (0,0973 → 0,0751)
y GBPUSD H4 (0,0851 → 0,0681), que quedaban al límite del 0,10. Los índices no
cambian porque su comisión ya era 0. La tabla completa de 49 celdas está en
`.orquestador/onboarding-mtf-CFD-006-antes.json` y `...-despues.json`.

## 4. Tests

- `tests/test_propfund.py`:
  - `test_coste_fundingpips_trial_comisiones_oficiales` exige
    `commission_side == "round_turn"` y “ida y vuelta” en la fuente.
  - `test_fundingpips_cfd006_es_2step_standard`: límites 5.000/10.000/8.000,
    3 días, static, base mayor de balance/equidad, 20 lotes; y las 13 reglas
    del programa (8/5 %, 5 %, 10 %, comisión 5/0, 3 %/2 % fondeada).
  - `test_cfd006_rules_para_mc_declaran_equity_y_avisan_del_mayor`: el MC
    recibe 5 %/10 %/8 %, `daily_loss_mode=equity`, reset `Etc/GMT-2` y la nota
    de la diferencia.
  - `test_fundingpips_comision_ida_y_vuelta_no_se_duplica`: EURUSD y XAUUSD
    pagan 5 USD/lote (no 10); US100 paga 0.
- `tests/test_propfund_onboarding_mtf.py`, `test_propfund_constraints.py`,
  `test_propfund_snapshots.py` y `test_discovery_costs.py` siguen en verde.

## 5. Comprobaciones de cierre

- `pytest -q` completo: **1635 passed, 1 skipped** (1 warning preexistente:
  `psutil` no instalado). Tiempo 1:13:49, dominado por
  `test_noise_five_campaigns` (marcado `slow`). La primera tanda se había
  bloqueado por la suite F12 en paralelo; se relanzó sola y pasó.
- `ruff check src/tradinglab tests`: limpio.
- `lab propfund verify`: **4 OK** (ai_trader, ea_us100_ftmo1, ftmo_forward,
  ftmo_risk).
- `count_tests`: **1703** (`lab lessons holdout`, trials globales; no se
  registró nada).

## 6. Commit y tag

- Commit `236f0b1` · `tl2: N1 - reglas FundingPips 2-Step Standard`
- Tag `tl2-n1`
