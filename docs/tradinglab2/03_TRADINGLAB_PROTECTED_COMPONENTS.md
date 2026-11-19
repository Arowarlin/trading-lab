# 03 · Componentes protegidos

La protección ya está implementada: `src/tradinglab/propfund/protected.py` congela por SHA-256
(CRLF normalizado) los archivos de `config/propfund/protected_manifest.json`, y
`tests/test_propfund.py::test_componentes_protegidos_intactos` falla si alguno cambia.
`lab propfund verify` lo comprueba a mano.

## Inventario

| Grupo | Componentes | Por qué |
|---|---|---|
| `ea_us100_ftmo1` | `integrations/mt5/us100_ftmo1/**`, `config/mt5_eas.yaml`, `ea_registry.py`, `ea_us100.py`, `ea_us100_engine.py`, `ea_forward.py`, `ea_horizon.py`, `docs/ea_us100_ftmo1.md` | EA del operador en forward demo (magics 93010001/93020001) |
| `ai_trader` | `config/ai_trader.yaml`, `ai_trader.py`, `ai_session.py`, `ai_setups.py`, `ai_learn.py`, `ai_distill.py`, `ai_replay.py`, `scripts/ai_trader_*.ps1`, `scripts/register_ai_trader_tasks.ps1`, docs y agentes OpenCode del carril | Carril IA discrecional en demo |
| `ftmo_forward` | `config/intraday_forward.yaml`, `forward_intraday.py`, `intraday.py`, `swing.py`, `strategies/swing.py`, `asset_aliases.py`, scripts del forward | Las dos estrategias FTMO (EURUSD london_pullback, USDJPY tokyo_breakout) + us100-trend-d1 |
| `ftmo_risk` | `prop/**`, `guardian.py`, `account_daily.py`, `symbol_risk.py`, `execution/mt5.py`, `execution/mt5_offsets.py`, `mql5/TradingLabGuardian.mq5`, `config/guardian.yaml`, `config/prop_templates.yaml` | Riesgo que protege a los anteriores |
| `f13_hash` | `config/{lab,bots,prop,f13,accounts}.yaml` | Piloto F13 (se retira en la migración, con re-freeze aprobado) |

## Consecuencias para 2.0

- **`intraday.py` está protegido** (aloja el forward FTMO). 2.0 **importa** `backtest_intraday`,
  `run_event_backtest` y los cachés, **nunca** los edita. Los indicadores nuevos van en un módulo nuevo.
- **`ea_us100_engine.py` está protegido.** El EA no se usa para experimentos genéticos. Puede aparecer
  en el databank como estrategia **de referencia de solo lectura** (`origin = "protected_reference"`),
  sin mutarla.
- **`prop/simulator.py` está protegido**: se llama para el Monte Carlo de challenge, sin cambios.
- El motor genético corre en **otro proceso y otras tablas** (prefijo `disc_`), con límites de CPU para no
  perjudicar a MT5, al EA ni a `ai_trader`.

## Pruebas de regresión obligatorias (cada fase)

1. `lab propfund verify` → OK en todos los grupos.
2. `pytest -q` completo (línea base local: 1231 passed, 1 skipped).
3. `tests/test_ea_registry.py`, `tests/test_ea_forward.py`, `tests/test_guardian.py`, `tests/test_ai_trader*.py`,
   `tests/test_intraday*.py` sin cambios en el código de test.
4. Test nuevo `tests/test_discovery_isolation.py`: importar `tradinglab.discovery` no modifica
   `strategy_trials`, `lifecycle` ni ninguna tabla protegida; ningún módulo de `discovery` importa
   funciones de envío de órdenes (`submit_market`, `close_position`, `modify_position`).

## Conflictos documentados (fuera del plan ejecutable)

- `InpSlBufAtr` en el motor del EA (ver doc 01 §3): requiere autorización explícita para investigarlo.
- `regime_gate` estricto: no se cambia; 2.0 lo usa solo en el nivel 3–4 y añade un informe de dependencia
  de régimen (no un gate) en el nivel 2.
