# TL3 · Contrafactual de `ai_trader` (T5, M1 MT5)

Operaciones cerradas leídas: 48; simuladas: 48.
Login MT5: 1515349730 antes / 1515349730 después.
Coste: spread de la vela de entrada + 1 punto total de slippage; gemela recalculada con `shadow_seed`; regla de tendencia con la sesión NYSE anterior; cierre forzoso 12:00 NY en scalping.

## Resultados

| Benchmark | n | Media R | IC95 |
|---|---:|---:|---:|
| IA (recalculada) | 48 | 0.2953 | [0.0144; 0.5689] |
| Gemela aleatoria | 48 | 0.2594 | [-0.0150; 0.5227] |
| Regla de tendencia | 48 | 0.3179 | [0.0654; 0.5622] |
| Siempre tomar | 48 | 0.2953 | [0.0144; 0.5689] |

## Diferencias (IA − benchmark)

| Benchmark | n | Δ R | IC95 |
|---|---:|---:|---:|
| Gemela aleatoria | 48 | +0.0360 | [-0.0843; +0.1462] |
| Regla de tendencia | 48 | -0.0225 | [-0.1833; +0.1206] |
| Siempre tomar | 48 | +0.0000 | [+0.0000; +0.0000] |

## Desglose por lado y símbolo (Δ frente a la gemela)

| Corte | n | Δ R |
|---|---:|---:|
| side=buy | 13 | -0.2158 |
| side=sell | 35 | +0.1295 |
| symbol=XAUUSD | 19 | -0.1273 |
| symbol=US100.cash | 26 | +0.1563 |
| symbol=GBPUSD | 2 | +0.0406 |
| symbol=USDJPY | 1 | +0.0000 |

## Veredicto: **no concluyente**

Regla TL3_AI_TRADER_AUDIT §5: solo aporta si Δ frente a la tendencia ≥ 0,1 R con IC95 > 0. Si el IC95 incluye 0, el veredicto es no concluyente. No se tocó `ai_trader.py`.
