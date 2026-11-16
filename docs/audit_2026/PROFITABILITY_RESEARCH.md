# PROFITABILITY_RESEARCH — Dónde puede haber ventaja real para este lab

Punto de partida: un operador con un PC, datos gratuitos (Yahoo, Dukascopy, MT5, FRED, CFTC) y cuentas demo o de fondeo. **No hay** ventaja de latencia, ni datos de order book de pago, ni capacidad de market making. Eso descarta HFT, order flow real y arbitraje estadístico de alta frecuencia.

## Fuentes de edge que sobreviven a esas restricciones

| Fuente | Por qué existe | Encaje con el lab | Evidencia previa del lab |
|---|---|---|---|
| **Momentum de series temporales multi-activo (diario o semanal)** | Las primas de riesgo y la infrarreacción están documentadas durante décadas. | Alto, pero solo como **cartera diversificada** (más de 20 instrumentos), no un activo suelto. | tsmom en una cesta pequeña fue rechazado en la campaña B, que está contaminada. |
| **Estacionalidad intradía del índice: apertura de Nueva York y última media hora** | Flujos de cobertura de gamma, rebalanceo de ETFs apalancados y MOC. | Alto. El EA ya explota la apertura. | El EA es el mejor candidato. |
| **Efecto de fin de mes y cambio de mes en índices** | Flujos de fondos de pensiones y nóminas. | Medio. Pocos eventos al año: hace falta una muestra larga. | No probado. |
| **Carry de FX (diario)** | Prima de riesgo. | Bajo en FTMO: el swap del CFD se come gran parte del diferencial. | No probado. |
| **Reversión a corto plazo en ETFs y acciones grandes (1-5 días)** | Provisión de liquidez. | Medio, en acciones paper de Alpaca, con costes bajos. | No probado. |
| **Sesión de Londres y Nueva York en oro (XAUUSD)** | Fixes de Londres y el solape de sesiones. | Medio. El spread del CFD es alto respecto al rango M5. | Familias asian_rev y overlap_breakout: sin edge documentado. |

## Lo que la evidencia del lab ya dice

1. Las familias intradía M15 y H1 genéricas (ORB, pullback, breakout de sesión) en FX dan **cero celdas** que sobrevivan a los costes. No hay que insistir con más parámetros.
2. El único resultado consistente está en la **apertura de Nueva York del US100 con lógica estructural** (el EA). Es coherente con la literatura sobre flujos de apertura.
3. Los filtros de régimen y el objetivo de volatilidad no añadieron valor.

## Implicación metodológica

- Menos familias y más hipótesis con fundamento económico, cada una con su **pre-registro**.
- Usar el presupuesto de pruebas (el N del DSR) en 2 o 3 hipótesis buenas al trimestre, no en barridos de cientos de celdas.
- Una cartera de 3 o 4 fuentes poco correlacionadas (apertura del índice, momentum diversificado diario, cambio de mes y reversión a corto en acciones) vale más que optimizar la misma idea.

## No construir todavía

Order flow o footprint (no hay datos), ML profundo sobre precios (muestra insuficiente y GPU AMD sin CUDA), arbitraje estadístico intradía entre pares de FX (costes) ni más estilos para el carril IA.
