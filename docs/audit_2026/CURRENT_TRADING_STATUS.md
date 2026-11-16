# CURRENT_TRADING_STATUS — Estado de bots, estrategias y cuentas

Leyenda: **D** = documentado en el repo. **V** = verificado de forma independiente en esta auditoría. **SD** = Sin datos verificables: el resultado está en la base de datos local del PC.

## Cuentas

| Cuenta | Tipo | Qué opera |
|---|---|---|
| ftmo_demo (MT5) | Demo FTMO 100k | EA US100 FTMO1, us100-trend-d1, EURUSD london_pullback, USDJPY tokyo_breakout y las tres familias del carril IA |
| alpaca_paper | Paper | F13 (QQQ), del 13-11-2026 al 08-01-2027 |
| darwinex demo | Demo | Sin uso relevante documentado |
| paper_main | Bróker interno | Ya no aloja F13 |

**Riesgo estructural:** casi todo el riesgo de la demo FTMO está en un solo instrumento (US100) y en una sola cuenta, sin límite por símbolo.

## Estrategias

| Estrategia | Evidencia | Estado real | Decisión recomendada |
|---|---|---|---|
| EA US100 FTMO1 v3 | D: 480 operaciones, PF 1,45, +0,30R, PBO 0,24, Sharpe WF 1,31. V: el código del motor es coherente y el tester de MT5 coincide. **El DSR 1,0 no es válido** (error de unidades). | Mejor candidato del lab, **sin OOS limpio** | Mantener. Forward pre-registrado en una cuenta dedicada. |
| us100-trend-d1 | D: incubando. No se modela el swap. | Sin evidencia de edge neta de financiación | Mantener en incubación tras recalcular con swap. |
| EURUSD london_pullback | D: Sharpe −4,42 y MaxDD −30 % | Negativa | **Desactivar** (con aprobación del operador). |
| USDJPY tokyo_breakout | D: Sharpe −4,63 | Negativa | **Desactivar** (con aprobación del operador). |
| F13 (QQQ, Alpaca) | D: piloto operativo | Prueba de fontanería, no de edge | Mantener hasta el 08-01-2027 y solo juzgar la ejecución. |
| Carril IA (scalping, intradía, swing) | SD: pocos días de muestra | Experimental | Mantener con límites. No promover nada antes de 100 operaciones por estilo. |
| tsmom D1 | D: rechazada en la campaña B | Cementerio | Descartada. |
| Overnight reversal | D: Sharpe −0,15 | Cementerio | Descartada. |
| Intradía M15/H1 (campaña A) | D: 0 de 228 celdas | Cementerio, aunque el diseño de la campaña tenía un fallo en la condición (c) | No reabrir sin una hipótesis nueva. |
| Volatility targeting y condicionadores | D: rechazados | Cementerio | Descartados. |

## Contadores

- Pruebas DSR (`count_tests`): unas 1033, según la última lectura documentada.
- Holdout global: una lectura documentada en la campaña B, que está contaminada.

## Lo que no se puede afirmar hoy

- Que alguna estrategia del lab tenga una ventaja neta de costes demostrada fuera de muestra. **No hay ninguna.**
- Que el carril IA sea positivo: con días de muestra, el intervalo de confianza incluye pérdidas.
