# 01 · Auditoría de TradingLab (Fase 0)

Fecha: 2026-11-19 · rama `feature/prop-fund-multifirm` · base `master@b038c37`.

## Estado de la base

| Medida | Resultado |
|---|---|
| Archivos fuente | 485 (sin `data/`, `reports/`, `uv.lock`) |
| Suite (Linux, sin marcas `network/mt5/lmstudio/alpaca/credentials`) | **1195 passed, 13 failed, 2 skipped** antes de tocar nada |
| `ruff check .` | limpio |

Los 13 fallos son previos y ajenos a esta expansión: dependen de Windows o de
datos locales que no viajan con el repositorio (`ai_replay` ×4 sin datos M5,
`ea_forward` ×3 y `ea_registry` ×2 con rutas `C:/Users/PC/...` del setfile,
`guardian` ×1 con el terminal real, `optimize` ×1 y `research` ×2 con
fixtures de datos). En el PC del operador deben pasar como hasta ahora.

## Arquitectura existente (lo que ya funciona)

| Área | Módulos | Estado real |
|---|---|---|
| Núcleo / CLI | `cli.py` (10.669 líneas, ~45 sub-apps), `config.py`, `db.py` | funcional |
| Reglas de fondeo | `prop/rules.py`, `guard.py`, `defense.py`, `overlay.py`, `simulator.py` | funcional para FTMO; Topstep/Apex/Lucid/MFF solo plantillas inactivas |
| Cuentas | `accounts.py` + `config/accounts.yaml` | 5 cuentas: `paper_main`, `alpaca_paper` (capital propio), `ftmo_demo`, `ftmo_trial_ea` (blocked), `topstep_template` |
| Ejecución | `execution/mt5.py`, `mt5_offsets.py`, `projectx.py`, `paper.py`, `alpaca.py`, `tradestation.py` | MT5 demo real; ProjectX dry-run; una sesión MT5 por proceso |
| Costes | `broker_costs.py` (spreads por hora desde ticks MT5), `config/costs.yaml` | comisiones FTMO verificadas (Forex 2,50 USD/lote/lado, metales 0,0007 %, índices 0) |
| Instrumentos | `instruments.py`, `asset_aliases.py` | catálogo FX/metales/futuros CME; alias solo para 4 canónicos del perfil `intraday_fx` |
| Datos de futuros | `data/futures.py` | **stub**: `ProjectXFuturesProvider` no descarga barras; solo ES=F/NQ=F diario como validación parcial |
| Investigación | `research.py`, `walkforward.py`, `regimes.py`, `optimize.py`, `stats.py` | funcional (DSR/PBO/WF) |
| Consola | `web.py` (3.060 líneas) + `webui/index.html` (7.015 líneas, sin CDN) | funcional, 18 vistas |

## Componentes protegidos identificados

Congelados en `config/propfund/protected_manifest.json` (SHA-256, CRLF→LF) y
vigilados por `tests/test_propfund.py::test_componentes_protegidos_intactos`
y `lab propfund verify`.

| Grupo | Qué es | Archivos |
|---|---|---|
| `ea_us100_ftmo1` | EA externo `us100-ftmo1` (US100.cash, magics 93010001/93020001, setfile v3 challenge) y su espejo Python | 18 |
| `ai_trader` | Carril IA discrecional (`config/ai_trader.yaml`, `ai_*.py`, scripts y agentes OpenCode) | 17 |
| `ftmo_forward` | **Las dos estrategias existentes del carril FTMO**: `eurusd-london-pullback-forward` (EURUSD M15) y `usdjpy-tokyo-breakout-forward` (USDJPY M15), más la incubación `us100-trend-d1` que vive en el mismo `config/intraday_forward.yaml` | 8 |
| `ftmo_risk` | `prop/`, `guardian.py`, `account_daily.py`, `symbol_risk.py`, `execution/mt5*.py`, `TradingLabGuardian.mq5`, `guardian.yaml`, `prop_templates.yaml` | 14 |
| `f13_hash` | `lab.yaml`, `bots.yaml`, `prop.yaml`, `f13.yaml`, `accounts.yaml`: entran en el hash congelado del piloto F13; cambiarlos lo detiene | 5 |

> `ai_trader` y `us100-ftmo1` **no** son "las dos estrategias": son
> identificadores protegidos aparte. Las dos estrategias son las del forward.

### Cómo se ejecutan (y por qué no se tocan)

* **EA**: corre dentro del terminal MT5; el laboratorio solo lo registra
  (`mt5_eas.yaml`), lee sus fills y lo suma al guardián y al stop diario.
* **ai_trader**: tareas programadas `TradingLab-AI-*` sobre `ftmo_demo`, magics 20261191-93.
* **Forward**: `TradingLab-IntradayForward` cada 5 min, magics 20261151/…, 1 trade/día.
* Los tres comparten `ftmo_demo` y el riesgo de `ftmo_risk`.

## Hallazgos y riesgos técnicos

1. **F13 bloquea editar `accounts.yaml`/`prop.yaml`.** Por eso la capa nueva
   vive en `config/propfund/`. Retirar `paper_main`/`alpaca_paper` y el carril
   de acciones/ETF del archivo legacy rompería el piloto F13 (ETF QQQ, activo
   hasta 2027-01-08). El Prop Fund los excluye como destino sin tocarlos.
2. **MT5 = una cuenta por proceso.** `execution/mt5.py` inicializa una sola
   sesión. Varias cuentas MT5 concurrentes exigen un worker/terminal aislado por
   cuenta (Fase 4), nunca cambiar de login en caliente.
3. **Futuros sin datos intradía.** Ninguna estrategia de futuros puede pasar de
   `research` hasta implementar un proveedor real (ProjectX History, Databento,
   Rithmic…).
4. **Costes incompletos.** El spread nunca se fija: sin medición, el router
   rechaza por "Sin datos de coste". Es el comportamiento deseado.
5. **Reglas de firmas.** Solo FTMO tiene valores numéricos (fuente secundaria
   LuxAlgo del 2026-11-05). El resto queda `needs_verification`.
