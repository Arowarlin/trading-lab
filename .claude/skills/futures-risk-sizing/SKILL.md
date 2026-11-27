---
name: futures-risk-sizing
description: "Dimensionar contratos de futuros (minis y micros) desde el riesgo en USD, el stop en ticks y los límites de la firma y del perfil (evaluation, funded, payout_producing, personal). Usar al proponer un ticket, un perfil de riesgo o la política de tamaño del motor EV."
---

# futures-risk-sizing

## Propósito
Contratos enteros correctos y dentro de los topes de la cuenta.

## Cuándo usarla
Ticket semiautomático, perfil de riesgo o política de tamaño.

## Entradas
Instrumento, stop en ticks, riesgo máximo en USD, firma, programa, fase, balance y colchón al MLL.

## Procedimiento
1. Valor del tick de `src/tradinglab/instruments.py` (NQ 5 USD, MNQ 0,50, ES 12,50, MES 1,25, GC 10, MGC 1).
2. Riesgo por contrato = ticks × valor del tick + costes por contrato.
3. Contratos = suelo(riesgo permitido / riesgo por contrato); 0 → **NO TRADE**.
4. Aplicar topes: máximo de la firma, escalado por balance, ventana de noticias, colchón al MLL y DLL restante.

## Validación
Redondeo siempre hacia abajo; el riesgo real ≤ permitido.

## Salidas
Tabla de tamaño con el cálculo.

## Falla si
Falta el tope de la firma o el escalado (Sin datos): no se propone tamaño.

## Restricciones
Nunca envía órdenes; solo paper/demo.
