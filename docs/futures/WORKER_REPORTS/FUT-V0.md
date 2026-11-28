# FUT-V0 · Verificación en Windows

**Ejecutado:** 2026-11-28 por Claude (sesión local), `E:\tl-fut-s`, rama `claude/vibrant-mayer-r46s0o`
(al día con origin, sin cambios locales).

## Salidas

- `uv sync --frozen --extra dev --extra discovery`: Checked 93 packages.
- `ruff check .`: All checks passed!
- `pytest -q -m "not network and not mt5 and not lmstudio and not alpaca and not credentials"`:
  `3 failed, 2467 passed, 17 skipped, 3 deselected, 1 warning in 2058.22s (0:34:18)`
- `lab doctor` (FAIL/WARN): Frescura FAIL (17/17, EURUSD H1 sin datos en el worktree); WARN: Telegram remoto,
  Carpeta logs, TradingAgents, Trading-R1, Deep LLM, MetaTrader 5, Riesgo abierto, Reglas fondeo.
- `lab propecon programs --today 2026-12-01`: 5 programas, ninguno caducado.
- `lab propecon ranking`: MFF Rapid 3.55, Tradeify 3.45, TradeDay 3.00, Topstep 2.85, Alpha 2.80
  (Lucid 4.11 y Bulenox 3.06 provisionales).

## Fallos (no arreglados, según el prompt)

- tests/test_claude_hooks.py::test_runner_end_to_end
- tests/test_console_shell.py::test_barra_lateral_con_secciones_y_todas_las_vistas
- tests/test_console_shell.py::test_inventario_ui_base_sigue_completo

## Aviso

S1 no está en verde. S2, S3 y la copia de S4 se ejecutaron en paralelo con la suite (solo lectura y
metadatos), antes de conocer este resultado. Decide el operador si los 3 fallos bloquean la cadena.

## Siguiente

Diagnosticar los 3 fallos (Claude) y, después, compilar TradingLabBridge en NT8.
