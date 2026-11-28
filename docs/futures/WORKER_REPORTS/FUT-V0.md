# FUT-V0 · Verificación en Windows

- **Fecha:** 2026-11-28
- **Rama:** `claude/vibrant-mayer-r46s0o` (`f837d4d`)
- **Worktree:** `E:\tl-fut-s` (el árbol principal `E:\trading-lab` no se ha tocado)
- **Modelo:** DeepSeek V4.1 Flash

## Hecho

1. Worktree creado desde `origin/claude/vibrant-mayer-r46s0o`; árbol limpio antes de empezar.
2. `uv sync --frozen --extra dev --extra discovery` → venv propio en `E:\tl-fut-s\.venv` (CPython 3.12.16, 93 paquetes).
3. `ruff check .` → sin errores.
4. `pytest -q -m "not network and not mt5 and not lmstudio and not alpaca and not credentials"` → **3 fallos, 2466 pasados** (34 min 22 s).
5. `lab doctor` → **FAIL solo en Frescura** (esperado: los datos viven en `E:\trading-lab\data` y no se han copiado). WARN en Telegram remoto, carpeta `logs`, vendors `TradingAgents`/`Trading-R1`, Deep LLM, MetaTrader5 (x2) y reglas de fondeo.
6. `lab propecon programs --today 2026-12-01` y `lab propecon ranking` → OK (tablas abajo).

## Ficheros

- `docs/futures/WORKER_REPORTS/FUT-V0.md` (este informe). No se ha escrito código ni se ha modificado ningún otro fichero del repo.

## Salidas literales

### `ruff check .`

```text
All checks passed!
```

### `pytest`

Última línea literal:

```text
3 failed, 2466 passed, 18 skipped, 3 deselected, 1 warning in 2062.09s (0:34:22)
```

Fallos, literales:

```text
=========================== short test summary info ===========================
FAILED tests/test_claude_hooks.py::test_runner_end_to_end - AssertionError: a...
FAILED tests/test_console_shell.py::test_barra_lateral_con_secciones_y_todas_las_vistas
FAILED tests/test_console_shell.py::test_inventario_ui_base_sigue_completo - ...
3 failed, 2466 passed, 18 skipped, 3 deselected, 1 warning in 2062.09s (0:34:22)
```

```text
___________________________ test_runner_end_to_end ____________________________
E       AssertionError: assert 127 == 0
E        +  where 127 = CompletedProcess(args=['bash', 'E:\\tl-fut-s\\.claude\\hooks\\run.sh', 'bash'], returncode=127, stdout='', stderr='/bin/bash: E:tl-fut-s.claudehooksrun.sh: No such file or directory\n').returncode
```

```text
_____________ test_barra_lateral_con_secciones_y_todas_las_vistas _____________
E       AssertionError: assert {'accounts', ...cisions', ...} == {'accounts', ...cisions', ...}
E
E         Extra items in the left set:
E         'futecon'
E         Use -v to get more diff
```

```text
___________________ test_inventario_ui_base_sigue_completo ____________________
E       AssertionError: assert {'accounts', ...cisions', ...} == {'accounts', ...cisions', ...}
E
E         Extra items in the left set:
E         'futecon'
E         Use -v to get more diff
```

### `lab doctor` (solo filas FAIL y WARN)

```text
| Frescura          | FAIL   | 17/17 fallan ? EURUSD H1 (sin datos), EURUSD   |
|                   |        | H4 (sin datos), EURUSD M15 (sin datos), GBPUSD |
|                   |        | H1 (sin datos)                                 |
| Telegram remoto   | WARN   | sin configurar                                 |
| Carpeta logs      | WARN   | E:\tl-fut-s\logs                               |
| TradingAgents     | WARN   | E:\tl-fut-s\vendor\TradingAgents               |
| Trading-R1        | WARN   | E:\tl-fut-s\vendor\Trading-R1                  |
| Deep LLM          | WARN   | sin configurar: el deep se corre bajo demanda  |
| MetaTrader 5      | WARN   | Falta el paquete MetaTrader5. Instálalo con:   |
|                   |        | uv pip install MetaTrader5                     |
| Riesgo abierto    | WARN   | Falta el paquete MetaTrader5. Instálalo con:   |
|                   |        | uv pip install MetaTrader5                     |
| Reglas fondeo     | WARN   | plantilla FTMO en config/prop.yaml: límites    |
|                   |        | contrastados con el directorio público         |
|                   |        | (verified_source), no con tu contrato; aviso   |
|                   |        | aceptable hasta verificarlo: el guard usa el   |
|                   |        | lado conservador (equity + colchón)            |
```

### `lab propecon programs --today 2026-12-01`

```text
programa                  | versión    | consultado | caducado | incógnitas
lucid_flex_50k            | 2026-11-2… | 2026-11-27 | no       | fees.consistency_addon, fees.data_platform_monthly, fees.evaluation, fees.reset, phases.funded.inactivity_close_days, phases.funded.max_accounts, phases.funded.payout.max_fraction_of_balance
myfundedfutures_rapid_50k | 2026-11-2… | 2026-11-27 | no       | fees.reset, phases.funded.max_contracts, phases.funded.max_loss, phases.funded.payout.cap_per_payout, phases.funded.payout.max_fraction_of_balance, phases.funded.payout.processing_days, phases.funded.scaling_plan
synthetic_static          | 2026-11-2… | 2026-11-27 | no       | —
synthetic_trailing        | 2026-11-2… | 2026-11-27 | no       | —
topstep_50k_combine_xfa   | 2026-11-2… | 2026-11-27 | no       | phases.funded.payout.processing_days, phases.funded.scaling_plan
```

(`2026-11-2…` es el truncado literal de la tabla en terminal; no se ha inventado la fecha completa.)

### `lab propecon ranking`

```text
firma            | plan          | total | provisional | sin nota
myfundedfutures  | Rapid         | 3.55  | —           | —
tradeify         | Select Flex   | 3.45  | —           | —
tradeday         | QP EOD        | 3.00  | —           | —
topstep          | Combine → XFA | 2.85  | —           | —
alphafutures     | Standard      | 2.80  | —           | —
lucid            | Flex          | —     | 4.11        | costs
bulenox          | Momentum      | —     | 3.06        | payouts
takeprofittrader | —             | —     | —           | rules, payouts, drawdown, costs, platform, eligibility
apex             | —             | —     | —           | rules, payouts, automation, drawdown, costs, platform, eligibility
earn2trade       | —             | —     | —           | rules, payouts, automation, drawdown, costs, platform, eligibility
fuente: docs/futures/research/propfirms_2026-11/00_INFORME_10_FIRMAS.md
```

## Aviso

- **3 tests en rojo; no se han corregido** (S1 ordena parar):
  1. `tests/test_claude_hooks.py::test_runner_end_to_end`: `bash` recibe `E:\tl-fut-s\.claude\hooks\run.sh` y MSYS lo convierte en `E:tl-fut-s.claudehooksrun.sh`; el proceso sale 127. Es un problema de rutas Windows/Git Bash, no del código de negocio.
  2. `tests/test_console_shell.py::test_barra_lateral_con_secciones_y_todas_las_vistas`: el HTML tiene la vista `futecon` (`src/tradinglab/webui/index.html`) y el conjunto esperado del test no la incluye.
  3. `tests/test_console_shell.py::test_inventario_ui_base_sigue_completo`: mismo desfase `futecon` contra el inventario.
- El **FAIL de Frescura es esperado**: el venv y el `data/` son locales del worktree (`E:\tl-fut-s\data`), y los datos reales están en `E:\trading-lab\data` sin copiar. No es un fallo del código.
- `uv sync` avisó de que no pudo usar hardlinks entre volúmenes/caché y copió los ficheros; cosmético.
- Sin datos reales no se ha calculado ningún rendimiento.

## Siguiente

- **PARADA de la cadena S.** El operador/Claude decide qué hacer con los 3 fallos (los dos de `futecon` parecen un test desactualizado; el de `bash` es de entorno Windows). No se lanza S2 hasta indicación expresa.
