# Motor de riesgo del indicador (V1.0)

Implementado en `04_PINE_SCRIPT/Nasdaq_Edge_Indicator.pine`, sección MOTOR DE
RIESGO. Espejo en Python con tests en `tests/test_risk_math.py` (6 casos).

## Entradas que el usuario introduce

El indicador no puede leer la cuenta.

| Entrada | Por defecto | Nota |
|---|---|---|
| Saldo actual, umbral de drawdown/MLL vigente, P&L de hoy, operaciones hoy, pérdidas seguidas | 50.000 / 48.000 / 0 / 0 / 0 | Copiar del dashboard de la firma. Si la fecha del estado tiene más de 1 día → NO TRADE |
| Riesgo habitual / máximo absoluto | $150 / $250 | |
| Pérdida diaria personal | $300 | |
| Pérdidas consecutivas máximas | 2 | |
| Operaciones máximas | 3 (configurable hasta 5) | |
| Comisión ida y vuelta por contrato | **0 → bloquea** | Obligatoria. La real de MNQ en las firmas es Sin datos |
| Slippage por lado | 1 tick | |
| Colchón sobre el umbral | $100 | |

## Fórmulas

```
presupuesto = min(riesgo_habitual, riesgo_max,
                  pérdida_diaria_personal + min(P&L_hoy, 0),
                  DLL_firma + min(P&L_hoy, 0)   [si la firma tiene DLL],
                  (saldo − umbral) − colchón) × multiplicador_tier3
coste_contrato = stop_pt × $/pt + comisión + 2 × slippage_ticks × tick × $/pt
contratos = min(floor(presupuesto / coste_contrato), máximo_firma, tope_noticias_firma)
```

- `máximo_firma` se expresa en la unidad del instrumento (1 mini = 10 micros).
- `tope_noticias_firma` vale 0 en NQ y 3 en MNQ dentro de la ventana Tier 1 ±5 min de Topstep 50K.

## Reglas

1. Si los contratos salen 0 → **NO TRADE · Stop demasiado ancho para el presupuesto**.
   - El stop nunca se amplía.
   - No se "redondea" a 1 contrato.
2. Hay NO TRADE con: límite diario personal o de la firma alcanzado, 2 pérdidas seguidas, máximo de operaciones, bloqueo de noticias, fuera de horario, calendario caducado, reglas sin reverificar, estado de cuenta sin actualizar, comisión sin configurar, o sin stop.
3. No hay martingala, grid ni promediado: el indicador solo dimensiona una operación con un stop definido, y el presupuesto **baja** tras las pérdidas, nunca sube.
4. **Riesgo previsto ≠ pérdida real.**
   - El panel dice "riesgo previsto (no es pérdida garantizada)".
   - Gaps, slippage en noticias y liquidaciones de la firma pueden superar el stop.
   - En Apex Intraday y en Topstep, la pérdida abierta cuenta contra el umbral en tiempo real.

## Ejemplos verificados por test

| Caso | Cálculo | Resultado |
|---|---|---|
| MNQ, stop 20 pt, comisión $1,50, slippage 1 tick | 40 + 1,50 + 1,00 = $42,50 por contrato | 3 contratos, riesgo $127,50 |
| NQ, stop 20 pt, comisión $5,76, slippage 1 tick | 400 + 5,76 + 10 = $415,76 | **0 → NO TRADE** |
| P&L de hoy −$200 | 300 − 200 | presupuesto $100 |
| Saldo 48.150, umbral 48.000, colchón 100 | 150 − 100 | presupuesto $50 |
| MNQ, stop 2 pt, Topstep en ventana Tier 1 | 23 por presupuesto | 3 (tope de la firma) |
