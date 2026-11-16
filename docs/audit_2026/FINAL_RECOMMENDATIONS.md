# FINAL_RECOMMENDATIONS

## Qué hacer primero

1. **T01: corregir el DSR.** Hoy es la puerta principal del lab y deja pasar ruido (la mejor de 1040 series de ruido saca 0,9999998).
2. **T03: el EA dentro del guardián y del stop de cuenta**, antes de pasar el guardián a CLOSE.
3. Desactivar los forwards de EURUSD y USDJPY (Sharpe −4,4 y −4,6).
4. Mover el EA a una cuenta FTMO Free Trial dedicada y empezar su forward pre-registrado.

## Qué mantener

El protocolo (pre-registro, holdout sellado, contador único y cementerio), el PBO/CSCV, el walk-forward, la réplica del EA, el motor de eventos, el guardián MQL5, el kill-switch, el lease, la separación entre LLM y código en el carril IA, F13 como piloto operativo y la observabilidad (Vector, Healthchecks y Telegram).

## Qué corregir

El DSR (T01 y T02), el PBO de campaña (T04), el swap (T06), el spread de las limitadas (T07), la contabilidad por operación (T08), las zonas horarias (T09), el informe de Optuna (T10) y el riesgo por símbolo y clúster (T12).

## Qué descartar

EURUSD london_pullback, USDJPY tokyo_breakout, nuevos barridos de familias M15/H1 en FX, volatility targeting y los condicionadores de régimen (ya rechazados), y tsmom en una cesta pequeña.

## Qué no construir todavía

- Más estilos o agentes en el carril IA.
- ML profundo o modelos en GPU.
- Order flow sin datos.
- Motores por mercado: basta con un `CostModel` común.
- Futuros reales y LIVE.
- Refactorizar `cli.py` por tamaño.
- Comprar un challenge antes de tener el forward del EA completo.
