# TL3-B · T5-bis: simulación vs ejecución real de `ai_trader`

Descriptivo, no suma al contador. 48 operaciones cerradas, M1 de MT5
attach-only, login verificado antes y después. No se tocó `ai_trader.py`.

## Agregado

| Métrica | Valor |
|---|---:|
| R real medio | **+0,0637** |
| R simulado medio (IA, T5) | **+0,2664** |
| **Gap real − simulado** | **−0,2027 R** |
| IC95 bootstrap del gap (10.000, semilla 7) | **[−0,4817; +0,0819]** |

El gap es negativo y su IC95 incluye 0, pero el centro está a −0,20 R: la
simulación es más optimista que la ejecución real.

## Descomposición

| Componente | Media | Lectura |
|---|---:|---|
| Entrada: precio simulado − real | +2,05 unidades | La apertura de la vela siguiente no reproduce el fill real. |
| Entrada: tiempo simulado − real | 32,1 s | El fill real llega dentro de la vela siguiente. |
| Coste real implícito (pnl vs precio) | 0,0098 R | Comisión/swap reales bajos. |
| Coste del modelo (spread + 1 pt) | 0,0216 R | El modelo cobra **más** coste que el real. |
| Definición de R | Sin datos completos | `risk_usd`/volumen no permite aislar el contrato por símbolo. |

Por símbolo (gap medio): US100.cash −0,2252; XAUUSD −0,1550; GBPUSD −0,3708;
USDJPY −0,1173. Por lado: compras −0,4403; ventas −0,1144.

## Mayores gaps

| ID | Símbolo | Lado | R real | R sim | Gap | Δ entrada | Δ tiempo |
|---:|---|---|---:|---:|---:|---:|---:|
| 35 | US100.cash | buy | +1,4694 | −1,3861 | +2,8555 | −14,65 | 6,3 s |
| 51 | XAUUSD | sell | −0,9689 | +1,4179 | −2,3868 | +2,99 | 24,2 s |
| 27 | XAUUSD | sell | +1,3181 | −1,0680 | +2,3861 | −0,97 | 13,9 s |
| 20 | US100.cash | buy | −1,0750 | +0,9633 | −2,0383 | +22,65 | 38,0 s |
| 37 | US100.cash | buy | −1,0238 | +0,9938 | −2,0176 | +47,75 | 20,0 s |
| 38 | XAUUSD | buy | −0,9851 | +0,9768 | −1,9619 | +2,50 | 10,8 s |
| 45 | US100.cash | buy | −0,9513 | +0,9881 | −1,9394 | −7,75 | 42,5 s |
| 44 | US100.cash | buy | −0,8022 | +0,9700 | −1,7722 | +10,65 | 47,9 s |
| 49 | US100.cash | buy | +0,7227 | −0,7785 | +1,5012 | +8,05 | 7,4 s |
| 3 | US100.cash | sell | 0,0000 | +1,4684 | −1,4684 | −8,40 | 47,4 s |

En varios casos el signo del resultado cambia (el simulado gana y el real
pierde, o al revés) por diferencias de entrada de decenas de puntos y por el
cierre forzoso; no es un error de cálculo del script de T5.

## "Siempre tomar" = IA

La igualdad **Δ = 0,0000** es **por construcción**, no un error: el benchmark
"siempre tomar" usa el mismo lado, entrada y niveles que la simulación de la
IA. No aporta información independiente; se mantiene solo como control de
consistencia.

## Conclusión

La diferencia se explica por **ejecución**: el precio/tiempo de entrada real
frente a la apertura de la vela siguiente y la salida/cierre forzoso. Los
costes del modelo son mayores que los reales, así que no explican el gap
negativo. No se encontró un error en la simulación de T5 y no se modificó.
No se proponen cambios en `ai_trader`.
