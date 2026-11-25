# Hipótesis · preregistro de la Fase C (borrador para aprobar)

Ninguna de estas hipótesis tiene un edge demostrado. Que sean populares no
cuenta como evidencia. El laboratorio ya probó varias familias en US100, US500
y FX: cambio de mes, rebote tras ventas fuertes y reversión en los fix. **Ninguna**
dio candidatas tras costes; ver `reports/discovery/edge_map.md`. Ninguna era
intradía de la sesión de Nueva York.

El punto de partida esperado es "sin edge".

## Reglas comunes a los seis modelos

- Instrumento de investigación: NQ (CME). MNQ hereda el precio, con un coste
  por contrato distinto. US100 se valida aparte.
- Barras M1 agregadas a M5 para las señales. Señal al **cierre** de la vela.
  Entrada en la apertura de la vela siguiente + 1 tick de slippage.
- Stop y objetivos con OCO intrabar.
  - Si stop y TP caen en la misma vela, se asume **primero el stop**.
- Ventana de entrada: 9:35–11:30 ET. Todo cerrado a las 15:55 ET. Tier 1 ±15 min y Tier 2 ±10 min bloqueados.
- Riesgo: $150 por operación. Contratos = floor($150 / (stop_pt × $/pt + costes)).
  - Si sale 0 → **NO TRADE**; no se agranda el stop.
- Máximo 3 operaciones al día; parar tras 2 pérdidas o −$300 en el día.
- Métricas siempre **netas**: comisión (input) + slippage de 1 tick por lado
  (y una variante de estrés de 2 y 4 ticks).

## Modelos y variantes (presupuesto de pruebas cerrado)

Cada variante es una prueba contada (DSR). El operador la registra antes de
ejecutarla con `lab learning record-informal ... --approved-by-operator`.
Total: **22 variantes + ablaciones**. No se añaden variantes después de ver
resultados.

| Modelo | Definición objetiva | Variantes (n) |
|---|---|---|
| **A · NY Open Breakout** | OR de N min desde 9:30. Long si una vela M5 cierra > ORH + 1 tick (short simétrico). Stop en el lado opuesto del OR o 1·ATR5m (el más cercano). TP1 = 1R, TP2 = 2R | N ∈ {5, 15, 30} × entrada {cierre de ruptura, retest del ORH en ≤ 6 velas} = **6** |
| **B · Liquidity Sweep** | El precio rebasa PDH/PDL u ONH/ONL ≥ 2 ticks y una vela M5 **cierra de vuelta dentro**. Entrada en contra del barrido. Stop 1 tick más allá del extremo del barrido. TP en el VWAP o 2R | nivel {PD, ON} × confirmación {cierre dentro, cierre dentro + vela de desplazamiento ≥ 1,5·ATR} = **4** |
| **C · VWAP** | Reversión: cierre M5 fuera de VWAP ± 2σ seguido de un cierre dentro, con objetivo en el VWAP. Continuación: pullback a VWAP ± 0,5σ en la dirección de la pendiente del VWAP de 30 min | {reversión, continuación} × filtro de régimen {sin, con F} = **4** |
| **D · Displacement + FVG** | Vela de desplazamiento con cuerpo ≥ 2·ATR(14) M5 que deja un FVG de 3 velas. Entrada límite en el 50 % del FVG en ≤ 12 velas. Stop bajo el FVG | {FVG aislado, FVG a favor de la estructura M15} × {entrada 50 %, entrada en el borde} = **4** |
| **E · Auction / Volume** | Perfil de volumen de la sesión anterior **desde M1** (aproximación por precio de cierre; no es order flow). Aceptación: 2 cierres M5 dentro del VA → objetivo en el extremo opuesto. Rechazo: fuera del VA y cierre de vuelta → objetivo en el POC | {aceptación, rechazo} × RVOL {sin filtro, RVOL ≥ 1,2 a la misma hora} = **4**. **Solo con NQ y volumen CME** |
| **F · Régimen** | No es un modelo de entrada: es un filtro. Ejes: tendencia/rango (ADX 14 en M15 y pendiente del VWAP), volatilidad (cuartil del ATR diario previo), compresión (OR15 / ATR diario < p25 del DEV), día de noticias | se evalúa como ablación sobre A–E |

Limitaciones del modelo E:
- TradingView no da volumen por precio intrabar en todos los planes.
- El perfil desde barras M1 es una aproximación. Se documenta como tal y no se
  presenta como Volume Profile exacto.
- En US100 (tick volume) **no** se aplica.

## Ablación

Para el mejor modelo de OOS-1 se quita cada filtro uno a uno: régimen, noticias,
RVOL, ventana horaria, retest y confirmación. Un filtro se mantiene solo si:
- mejora la expectancy neta en DEV **y** en OOS-1;
- no reduce la muestra por debajo de 200 operaciones en DEV.

## Criterios de aceptación (umbrales de investigación, no promesas)

- PF neto > 1,30 y expectancy neta > 0 en DEV **y** en OOS-1.
- DSR ≥ 0,90 con el recuento total de pruebas del laboratorio.
- ≥ 200 operaciones en DEV y ≥ 60 en OOS-1.
- Sin dependencia de outliers: el resultado sigue positivo quitando el 1 % de
  las mejores sesiones.
- Robusto ante slippage: sigue positivo con 2 ticks por lado.
- Estable por año: ≤ 1 año con expectancy negativa en DEV, y ese año no peor que −0,1R por operación.
- Monte Carlo sobre la secuencia de R aplicando las reglas Topstep 50K:
  - P(tocar el MLL) < 20 %;
  - P(alcanzar $3.000) reportada con su intervalo.
- Solo entonces se hace una lectura de OOS-2 por configuración.

Si nada lo cumple: se informa **"sin ventaja demostrada"**. El indicador puede
construirse igualmente como herramienta de contexto y riesgo, pero sin
señales BUY/SELL y con el estado permanente `NO EDGE VALIDATED`.
