# Dependencias verificadas

Fecha de verificación: 2026-11-08. Fuente: PyPI JSON y GitHub API.

## Runtime (fijadas en `pyproject.toml` + `uv.lock`)

| Paquete | Versión fijada | Notas |
|---|---|---|
| pandas | 3.1.1 | motor de datos/backtest |
| numpy | 2.5.4 | cálculo numérico |
| yfinance | 1.8.0 | datos diarios |
| typer | 0.27.3 | CLI |
| rich | 15.0.0 | salida de consola |
| pydantic | 2.14.3 | settings |
| pydantic-settings | 2.16.2 | settings |
| pyyaml | 6.0.3 | config |
| python-dotenv | 1.2.4 | `.env` fallback |
| pyarrow | 26.0.1 | parquet |
| httpx | 0.28.1 | HTTP |
| alpaca-py | 0.45.0 | Alpaca paper |
| **keyring** | **25.7.0** | **nuevo**: Windows Credential Manager; backend verificado `WinVaultKeyring`; licencia MIT; Python >=3.9 |
| **optuna** | **5.0.0** | **nuevo Etapa 7**: MIT; Python >=3.9; walk-forward y contador `optimization_trials`; deps SQLAlchemy/Alembic (MIT), tqdm (MPL-2.0), Mako/MarkupSafe (MIT/BSD-3) |
| **quantstats** | **0.0.86** | **nuevo Etapa 7**: Apache-2.0; Python >=3.10; HTML vs SPY; deps matplotlib (PSF/BSD), scipy (BSD-3), seaborn (BSD-3), tabulate (MIT); smoke HTML OK con pandas 3.1.1 y numpy 2.5.4 |

Extra `mt5`: `MetaTrader5==5.0.6231`, `tzdata==2026.6`.

## Desarrollo

| Paquete | Versión | Notas |
|---|---|---|
| pytest | 9.2.0 | tests |
| ruff | 0.17.4 | lint; reglas del proyecto: `E4,E7,E9,F,I` |
| **pre-commit** | **4.7.0** | **nuevo**: hook ruff y pytest pre-push; licencia MIT; Python >=3.11 |

## Evaluadas y no instaladas

| Herramienta | Versión | Licencia | Decisión |
|---|---|---|---|
| restic | 0.19.1 | BSD-2-Clause | propuesta para backup cifrado externo |
| Kopia | 0.23.1 | Apache-2.0 | alternativa con GUI |
| ib_async | 2.1.0 | BSD-2-Clause | Fase 6; requiere IB Gateway/TWS y cuenta paper |
| nautilus_trader | 1.231.0 | LGPL-3.0 | Fase 8; no hay v2 estable en PyPI; esperar |
| pyqlib | 0.9.7 | MIT | Fase 7; venv aparte, no romper `.venv` |
| ProsusAI/finbert | — | **CC-BY-NC-SA 4.0** | **No usar**: restricción no comercial; usar Qwen inicialmente |

## Herramientas externas de verificación (venv aparte, NO dependencias)

Fecha: 2026-11-11. Venv: `.venv-vbt` (uv 0.13.7, CPython 3.12.16). **No están
en `pyproject.toml` ni en `uv.lock`**: el laboratorio nunca las importa y `uv
sync --frozen` no las instala. Solo sirven para contrastar motores propios con
implementaciones independientes.

| Paquete | Versión | Licencia | Uso |
|---|---|---|---|
| vectorbt | 1.2.0 | Apache-2.0 (polakowo/vectorbt) | oráculo del motor de backtest |
| prop-ev | 0.1.0 (git `eea3870`) | MIT (Makeph/prop-ev) | oráculo del simulador de fondeo |
| pyarrow | 26.0.1 | Apache-2.0 | lectura de parquet en el venv de oráculos |
| numpy / pandas | 2.5.4 / 3.1.1 | BSD-3-Clause | resueltos por uv |
| numba / scipy / matplotlib | 0.68.1 / 1.18.1 / 3.11.2 | MIT / BSD-3 / PSF-like | dependencias de vectorbt |

Reproducir:

```powershell
uv venv .venv-vbt
uv pip install --python .venv-vbt vectorbt pyarrow
uv pip install --python .venv-vbt "git+https://github.com/Makeph/prop-ev"
```

- `scripts/oracle_vectorbt.py` se ejecuta con `.venv-vbt\Scripts\python.exe`.
- `scripts/oracle_prop_ev.py` se ejecuta con el venv principal y llama a prop-ev
  en un subproceso con `.venv-vbt`, para que el paquete externo no entre en el
  entorno del laboratorio.
- `.venv-vbt` está en `.gitignore` (`.venv-*/`).

## Notas

- `uv.lock` fija todo el árbol transitivo; CI usa `uv sync --frozen`.
- El CI no necesita secretos ni brokers: usa mocks y tests locales.
- Antes de añadir una dependencia nueva: comprobar PyPI, Python soportado,
  licencia, mantenimiento y coste de instalación; anotarlo aquí.
