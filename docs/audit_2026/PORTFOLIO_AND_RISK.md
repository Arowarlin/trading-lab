# PORTFOLIO_AND_RISK — Cartera, exposición y protección

## Problema actual

En `ftmo_demo` conviven 7 fuentes de riesgo: el EA, us100-trend-d1, dos forwards de FX y tres estilos de IA. De ellas, **4 operan US100**. Los límites existen por estilo y por cuenta (stop de cuenta del 4 %), pero:

- No hay límite de **riesgo abierto por símbolo** ni por clúster (índices de EE. UU., USD, oro).
- El EA no entra en el stop de cuenta ni en el guardián (hallazgo A4).
- El riesgo nominal (distancia al SL × volumen) no se agrega nunca.

## Diseño propuesto (reutiliza PropGuard y `risk_budget.py`)

1. **Riesgo abierto agregado** = Σ distancia al SL × valor del tick × volumen, sobre todos los magics de la cuenta (lab más EAs registrados), recalculado en cada apertura.
2. Límites por cuenta: **por símbolo 2 %**, **por clúster 3 %** (US100+US500+US30, todo lo que lleva USD, metales) y **total abierto 4 %**, siempre por debajo del límite diario de FTMO del 5 %, con margen para el gap.
3. Pérdida diaria = realizada + flotante de todos los magics. Al 80 % del límite se bloquean las aperturas; al 100 %, el guardián cierra todo lo del lab y avisa del resto.
4. **Una estrategia por cuenta de fondeo cuando la cuenta es un experimento de validación.** El EA va a su FTMO Free Trial y la demo compartida queda para la exploración.

## Asignación entre estrategias

- Con menos de 3 estrategias validadas no se optimiza nada: se usa **igual riesgo por estrategia**.
- Con 3 o más validadas, se pasa a risk parity sobre los retornos diarios del forward, con correlación con shrinkage (Ledoit-Wolf) y rebalanceo mensual.
- No hay que añadir más volatility targeting: ya se rechazó con evidencia.

## Fondeo

- El objetivo es **P(breach) baja**, no P(pasar) en 30 días. Para el EA, el barrido de horizonte (21, 60, 120 días y sin límite) decide si conviene un challenge sin límite de tiempo.
- La EV del challenge incluye el reembolso de la cuota al pasar. Si P(pasar sin límite) × (reembolso + payout esperado) < cuota, no se compra.
- Topstep (trailing drawdown) y FTMO (límite estático y diario) llevan reglas distintas en `prop.yaml`. Nunca hay que mezclarlas en un mismo Monte Carlo.
