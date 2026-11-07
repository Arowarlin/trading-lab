# Fase 8 — Motor de eventos: evaluación

Fecha: 2026-11-07. **Sin cambios de código.**

## Situación

El backtester propio cubre acciones/ETF/forex diarios con comisión, slippage,
OOS y Monte Carlo. Le faltan sesiones, rollover, contratos continuos y ejecución
intradía realista.

## NautilusTrader

- Última versión PyPI: **1.231.0** (2026-08-02), Python >=3.12 y <3.15.
- No se identifica una “v2” estable en PyPI a esta fecha; no se usa una
  candidata para capital real.
- Ofrece motor de eventos, órdenes, adaptadores IBKR/Databento y backtest de
  alta fidelidad.
- Coste: migrar estrategias, datos y ejecución; nueva curva de aprendizaje;
  otra capa de dependencias y datos de pago (Databento).
- No resuelve por sí solo el problema de edge; F13 sigue siendo necesario.

## Decisión

Mantener el backtester propio para F13 y research diario. Reevaluar Nautilus
solo si se pasa a intradía, futuros con rollover o se necesita un motor de
órdenes serio. Antes de tocar código, escribir una comparación de coste y una
prueba de concepto aislada en venv aparte.

## Cierre 2026-11-07

- **No se adopta NautilusTrader ni se añade dependencia alguna.**
- Se mantiene el backtester propio y el motor de órdenes actual.
- Gate para reabrir: F13 en marcha + datos intradía reales + necesidad
  demostrada de eventos/rollover; la PoC iría en un venv separado.
- Evidencia: `pytest tests/test_engine_decision.py -q` → decisión y ausencia de
  `nautilus`/`databento` en `pyproject.toml`.

