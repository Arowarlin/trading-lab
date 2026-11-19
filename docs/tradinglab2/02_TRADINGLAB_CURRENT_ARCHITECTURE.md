# 02 · Arquitectura actual de TradingLab

```
                         ┌──────────────── TradingLab Console (web.py + webui/index.html) ────────────────┐
                         │ Dashboard · Mercado · Bots · Research · Agentes · IA discrecional · Prop Fund … │
                         └───────────────────────────────▲─────────────────────────────────────────────────┘
                                                         │ /api/* (solo lectura salvo acciones con CSRF+PIN)
┌──────────── CLI `lab` (cli.py, ~45 sub-apps) ──────────┴───────────────────────────────────────────────────┐
│ research · research-intraday · campaign · optimize · ea · prop · propfund · mt5 · futures · lessons · …    │
└──────┬──────────────┬───────────────────┬─────────────────────┬─────────────────────┬──────────────────────┘
       │              │                   │                     │                     │
  DATOS           INVESTIGACIÓN       VALIDACIÓN             RIESGO / FONDEO        EJECUCIÓN (demo)
  MT5 parquet     intraday.STRATEGIES stats (DSR)            prop/ 🔒 (guard,        execution/mt5.py 🔒
  data/yahoo 🗄   campaign.FAMILIES   validation (PBO)        defense, simulator)    execution/projectx (dry)
  data/futures ⚪ backtest_intraday   walkforward (WF,        propfund/ (firmas,     guardian.py 🔒 + EA MQL5
  broker_spreads  run_event_backtest   regímenes)             cuentas, router,       ai_trader 🔒
  datacheck       optimize (Optuna)   learning (holdout,      riesgo global)         forward_intraday 🔒
                  ea_us100 🔒          count_tests)           risk_budget
                  ea_lab (local)      trials (strategy_trials)
                                      lifecycle (estados)
       └──────────────────────────── SQLite data/lab.db (una sola base) ───────────────────────────────┘
```

## Flujo de investigación actual

1. Una familia escrita a mano produce una **serie objetivo** (`StrategyResult`).
2. `backtest_intraday` aplica costes por hora y devuelve retornos netos.
3. Las variantes de la rejilla forman una matriz → PBO, WF de selección, DSR local/global, regímenes.
4. Cada variante se registra en `strategy_trials` (o la campaña completa con `N_total`).
5. Las que pasan entran en `lifecycle` como candidato → incubación (forward demo).

## Puntos de extensión seguros para 2.0

| Necesidad 2.0 | Punto de extensión existente | Cómo |
|---|---|---|
| Ejecutar estrategias generadas | `backtest_intraday` (modo serie) | El compilador de reglas produce la serie objetivo |
| SL/TP/trailing | `run_event_backtest` (semántica de fills) | Nuevo motor rápido con **la misma semántica**, verificada por paridad |
| Registro estadístico | `campaign.register_campaign`, `count_tests` | Cada ejecución genética = una campaña registrada |
| Holdout final | holdout sellado de campaña / `learning` | Lectura única por finalista |
| Robustez | `cscv_pbo`, `walk_forward`, `dsr_from_returns`, `prop/simulator.py` | Reutilizar sin cambios |
| Costes | `propfund/costs.py`, `broker_spreads` | Perfil por instrumento y cuenta |
| Promoción | `lifecycle` | Solo finalistas confirmados |
| Consola | `web.py` (rutas GET) + vista nueva | Vista "Discovery Lab" aislada |
