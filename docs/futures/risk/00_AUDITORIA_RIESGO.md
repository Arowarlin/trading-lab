# FUT-RISK-0 · Auditoría: qué existe para asignar riesgo y simular payouts (Paso 1)

**Fecha:** 2026-11-27 · **SHA:** `20af163` · **Método:** inventario de solo lectura de `src/tradinglab`,
`tests/`, `NASDAQ_EDGE_INSTITUTIONAL/`, `TL3_REPORTS/` y `reports/` (agente de exploración + revisión de
Claude). Prefijo `S/` = `src/tradinglab/`.

Los ficheros de `prop/*`, `symbol_risk.py` y `ea_horizon.py` están en el **manifiesto protegido**
(producción FTMO): se envuelven, no se editan.

## 1. Lo que existe

| Componente | Qué calcula | Unidades | Tests | Límite para prop firms de futuros |
|---|---|---|---|---|
| `S/prop/simulator.py:20` `monte_carlo` | P(aprobar/romper), bootstrap diario iid o en bloques fijos | % diario compuesto | test_prop* | EOD sin flotante, trailing sin bloqueo, consistencia ignorada, sin tarifas ni payouts (FUT-01) |
| `S/prop/simulator.py:142` `monte_carlo_program` | Fases encadenadas (2 fases) | % | test_prop_n1 | Sin fase financiada |
| `S/prop/simulator.py:303` `multiverse_by_trade` | Permutación de operaciones: P(rotura diaria/máxima), curvas p5/50/95 | USD por operación | test_multiverse | Sin objetivo, sin bloqueo, sin excursión intrabarra |
| `S/exposure_sweep.py:271` | Rejilla de exposición k ∈ {0,25…1} → EV = P(aprobar)·payout − tarifa | % → EUR | 12 tests | Economía FTMO: una tarifa, sin reset, activación ni reemplazo |
| `S/ea_horizon.py:43` | Escalera de riesgo por drawdown del EA; EV a 21-750 días | % / EUR | ninguno | Solo el EA FTMO |
| `S/campaign.py:71` `MC_KELLY = (0.5, 0.75)` | **No es Kelly**: escala retornos antes de un MC de 60 días | % | indirectos | Nombre engañoso |
| `S/horizons.py:233` `_required_for` | μ diaria mínima para P(aprobar) ≥ 50 % | % | test_horizons | Normal iid; base para un μ\* |
| `S/metrics.py:49` `risk_of_ruin` | `((1−e)/(1+e))^(1/f)` con f = 1 % | prob. | test_metrics | Ruina = perder el 100 %, no tocar un MLL |
| `S/instruments.py:112,355` | `lots_for_risk` = suelo(riesgo / (stop·USD/pt)); specs NQ/MNQ/ES/MES/GC/MGC | USD → entero | test_instruments | Sin costes por contrato |
| `S/propfund/router.py:95` `_size` | Contratos de futuros desde riesgo USD | entero | test_propfund | Ignora costes, `max_contracts` y equivalencia mini/micro |
| `S/propfund/risk.py:78,124,154` | Límites por cuenta y globales; exposición NQ+MNQ+US100 | USD | test_propfund | Trailing = pico de equidad, sin EOD/intradía ni bloqueo |
| `S/propfund/models.py:191` `AccountLimits.max_contracts` | Declarado | — | — | **Nunca se aplica** |
| `S/propfund/costs.py:596` `estimate_futures` | Coste ida y vuelta por contrato y en R | USD / R | test_propfund | Comisiones MNQ/NQ = null (FUT-03) |
| `S/portfolio_lab.py:409-524,658` | Correlación por días activos, coincidencia de pérdidas, asignación equal / inverse-vol / tope | ρ / pesos | test_portfolio_lab | Pesos continuos |
| `S/vol_target.py:29,42` | Volatilidad EWMA (t−1) y factor `min(tope, objetivo/vol)` | % / × | test_vol_target | Falta redondeo a contratos |
| `S/prop/defense.py` | Zonas por uso del drawdown (factor 1 → 0), circuito diario, cierre por hora | % / USD | test_prop_defense | % de HWM, sin bloqueo |
| `S/discovery/robustness.py:174,214` | Barajado/remuestreo en R; *moving-block* con ℓ de `arch.optimal_block_length` | R | test_eng1_mc | MBB, no stationary bootstrap |
| `S/discovery/power.py`, `sprt.py`, `stats.py`, `validation.py`, `global_dsr.py` | MDE, SPRT, DSR, PBO | — | sí | Validación, no tamaño |
| `NEI/tools/forward_models.py:241` `contracts_for_risk` | suelo(riesgo / (stop·2 + 2·comisión + 2·slippage)); comisión ausente → error | USD → entero MNQ | test_forward_models | MNQ fijo |
| `NEI/05_RISK/Risk_Engine.md` (Pine) | `min(riesgo, máx., DLL restante, distancia al umbral − buffer)` → contratos | USD / entero | test_risk_math | Sin módulo Python |
| `docs/futures/research/propfirms_2026-11/sim/ev_sim.py`, `docs/futures/risk/sim/risk_sim.py` | Topstep 50K en USD: trailing EOD con bloqueo, consistencia, tarifas, payouts, reemplazo, ruina del presupuesto | USD / entero MNQ | ninguno | **Investigación**, operaciones sintéticas |
| `config/prop_economics/firms_futures.yaml` | Catálogo de 10 firmas: bots, modo de ejecución, copiadores | — | 5 tests | Sin cifras económicas |

Informes previos con barridos de riesgo: `reports/ea/p-pasar-oficial.md` (0,25-1,00 %),
`us100-ftmo1-reto-contraido.md`, `us100-ftmo1-v2.md §8` y `TL3_REPORTS/propfund_zero_edge.md`. Todos son
de FTMO/CFD y en %. Sus generadores no están en el repo.

## 2. Diagnóstico

| Pregunta del encargo | Respuesta |
|---|---|
| ¿Hay ventaja validada? | **No** (`01_INVESTIGACION_RIESGO.md §1`). Todo dimensionamiento es condicional |
| ¿Hay Kelly / Optimal f? | **No.** `MC_KELLY` no lo es |
| ¿Hay un motor de cuenta en USD con payouts y reemplazo? | Solo los dos simuladores de investigación; el de producción es FUT-A (sin implementar) |
| ¿Hay bootstrap que preserve la dependencia? | Moving-block en robustez; falta el stationary bootstrap de FUT-A |
| ¿Se aplican los topes de contratos? | **No** (`max_contracts` declarado y sin uso) |
| ¿Se distinguen micros y minis? | Sí en `propfund/instruments.py:236`; el router no lo usa |
| ¿Costes de futuros completos? | **No**: comisiones null |

## 3. Reutilizar, adaptar, construir

- **Reutilizar tal cual:**
  - especificaciones de contratos y `lots_for_risk`;
  - `check_global` y `exposure_by_underlying`;
  - las funciones de correlación y coincidencia de pérdidas de `portfolio_lab`;
  - `_wilson`, `DailyCircuitBreaker`, `FlattenClock` y `ewma_volatility`;
  - `power.mde`, `sprt`, DSR y PBO;
  - `optimal_block_length`;
  - las fórmulas y vectores de `Risk_Engine` / `contracts_for_risk`.
- **Adaptar** (envolviendo los protegidos):
  - `ev_sim.py` y `risk_sim.py` → motor FUT-A con `DayPath` reales;
  - la rejilla de `exposure_sweep` → riesgo en USD;
  - `router._size` → costes + `max_contracts` + micros;
  - `check_account` → EOD/intradía y bloqueo;
  - las zonas de defensa → distancia al MLL en USD;
  - `_required_for` → solver de μ\*.
- **Construir:**
  - Kelly / Kelly fraccionario / Optimal f, como **diagnóstico**, no como tamaño;
  - el stationary bootstrap;
  - el motor de cuenta USD completo (FUT-A3-A6);
  - la simulación multicuenta con números aleatorios comunes;
  - la aplicación de `max_contracts`;
  - el Optimal Risk & Payout Allocation Engine (`02_ORPAE_DISENO.md`).
