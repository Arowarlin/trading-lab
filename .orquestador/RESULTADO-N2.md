# RESULTADO N2 · Código muerto a `legacy/`

- **Fecha:** 2026-11-25
- **Rama:** `tl2-n2` (desde `feature/prop-fund-multifirm` en `c65bf74`)
- **Tag:** `tl2-n2`

## Método

Para cada uno de los 18 módulos de `TL2_ARCHITECTURE.md §1` se buscaron
referencias en `src/`, `tests/`, `scripts/` (también `.ps1`), `config/`,
`integrations/` y `AGENTS.md`, incluyendo importaciones dinámicas y cadenas
`"tradinglab.<x>"`. Se excluyó el propio archivo y su test directo.

## Tabla

| Módulo | Referencias externas | Decisión |
|---|---|---|
| `ea_lab.session_data` | 0 | **Movido** a `legacy/src/tradinglab/ea_lab/` |
| `overnight_report` | 0 | **Movido** a `legacy/src/tradinglab/` |
| `execution_model` | 0 (solo su test) | **Movido** a `legacy/src/tradinglab/`; test a `legacy/tests/` |
| `discovery.export_samples` | Solo `tests/fixtures/f12_export/README.md` | Se queda (referencia documental) |
| `conditioners` | `conditioner_report.py`, `web.py`, `config/conditioners.yaml` | Se queda |
| `data.futures` | `cli.py`, `datacheck.py`, `instruments.py`, `market_agents.py`, `market_pilots.py`, `operator.py`, `session.py`, `web.py` | Se queda |
| `data.yahoo` | `config.py`, `freshness.py`, `instruments.py`, `intel/news.py`, `config/*.yaml` | Se queda |
| `discovery.indicators_ext` | `discovery/blocks.py`, `discovery/compiler.py` | Se queda |
| `discovery.optimizer` | `discovery/robustness.py` | Se queda |
| `ea_lab.atr` | 51 referencias (ai_*, campaign, cli, drift…) | Se queda |
| `ea_lab.validation` | 15 referencias (profiles, discovery, web…) | Se queda |
| `health` | 17 referencias (account_daily, ai_session, cli, drift…) | Se queda |
| `intel.finnhub` | `cli.py`, `intel/providers.py`, `scripts/intel_daily.ps1` | Se queda |
| `prop.overlay` | `propfund/models.py`, `propfund/snapshots.py`, manifiesto | Se queda |
| `propfund.router` | `propfund/cli.py`, `costs.py`, `models.py`, `registry.py`, `config/*.yaml` | Se queda |
| `strategies.meanrev` | `cli.py`, `optimize.py`, `regimes.py`, `research.py`, `vol_report.py`, `strategies/__init__.py` | Se queda |
| `strategies.sector_momentum` | `research.py`, `strategies/__init__.py` | Se queda |
| `trailing` | 22 referencias (ea_us100_engine, dsl, fastbt, export_mql5…) | Se queda |

## Movimientos

```text
legacy/src/tradinglab/ea_lab/session_data.py
legacy/src/tradinglab/overnight_report.py
legacy/src/tradinglab/execution_model.py
legacy/tests/test_execution_model.py
```

`legacy/` está en `norecursedirs` de pytest, así que sus tests no se
ejecutan en la suite. No hay importaciones de estos módulos en `src/`.

## Verificación

- `ruff check src tests`: limpio. `legacy/` queda fuera del lint activo.
- `pytest -q`: **1956 passed, 1 skipped** (30:47). Único aviso:
  `psutil no está instalado: la cola corre sin prioridad below normal`.
- `count_tests` = 1894.

## Cierre

Merge `--ff-only` a `feature/prop-fund-multifirm`, tag `tl2-n2`.
`git status` conserva solo los cambios externos
(`reports/discovery/edge_map.md` y `tl2-edge-map.patch`).
