# TL3-C · T5-bis rehecho: simulación vs ejecución real

> Rehecho en TL3-C: la versión de 134f7c9 usó otro conjunto de 48;
> ver COLA-TL3-C H-g. Este informe usa las 48 de T5 (todas menos #52 y #54).

Agregados de control: IA 0.2953, gemela 0.2594, tendencia 0.3179, real 0.0479.

## Resumen

| Conjunto | n | R real | R sim | Gap | IC95 gap | Entrada | Costes | Salida/resto |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| Todas | 48 | 0.0479 | 0.2953 | -0.2475 | [-0.5362; +0.0484] | +0.0661 | -0.0089 | -0.3047 |
| Sin posibles no ejecutadas | 46 | 0.0500 | 0.2777 | -0.2278 | [-0.5118; +0.0644] | +0.0686 | -0.0092 | -0.2872 |

Las columnas Entrada + Costes + Salida/resto suman el gap.
La definición de R real (`risk_usd`) no se puede aislar por contrato;
queda dentro de Salida/resto.

## Por símbolo y lado

| Corte | n | Gap |
|---|---:|---:|
| symbol=GBPUSD | 2 | -0.3708 |
| symbol=US100.cash | 26 | -0.2356 |
| symbol=USDJPY | 1 | -0.1173 |
| symbol=XAUUSD | 19 | -0.2575 |
| side=buy | 13 | -0.6057 |
| side=sell | 35 | -0.1144 |

## Motivos de salida

| Real | Simulado | n |
|---|---|---:|
| SL | forzoso | 4 |
| TP | TP | 10 |
| TP | forzoso | 29 |
| forzoso | forzoso | 2 |
| otro | forzoso | 1 |
| posible no ejecutada | TP | 1 |
| posible no ejecutada | forzoso | 1 |

Coincidencias de motivo: 12/48.
Posibles no ejecutadas: 2 (#3, #5).

## Mayores gaps

| ID | Símbolo | Lado | Real | Sim | Gap | Entrada | Costes | Resto |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 35 | US100.cash | buy | +1.4694 | -1.3861 | +2.8555 | -0.1998 | -0.0936 | +3.1489 |
| 51 | XAUUSD | sell | -0.9689 | +1.4179 | -2.3868 | -0.2880 | -0.0926 | -2.0062 |
| 27 | XAUUSD | sell | +1.3181 | -1.0680 | +2.3861 | +0.1735 | +0.0379 | +2.1747 |
| 53 | XAUUSD | buy | -1.1889 | +0.9140 | -2.1029 | +0.3665 | +0.1176 | -2.5869 |
| 20 | US100.cash | buy | -1.0750 | +0.9633 | -2.0383 | +0.5696 | +0.0337 | -2.6415 |
| 37 | US100.cash | buy | -1.0238 | +0.9938 | -2.0176 | +0.2034 | +0.0197 | -2.2407 |
| 38 | XAUUSD | buy | -0.9851 | +0.9768 | -1.9619 | +0.1383 | -0.0387 | -2.0615 |
| 45 | US100.cash | buy | -0.9513 | +0.9881 | -1.9394 | -0.0634 | -0.0708 | -1.8051 |
| 44 | US100.cash | buy | -0.8022 | +0.9700 | -1.7722 | +0.2188 | -0.1963 | -1.7947 |
| 49 | US100.cash | buy | +0.7227 | -0.7785 | +1.5012 | +0.0839 | +0.0181 | +1.3992 |

## Conclusión

El gap se concentra en la **entrada** y en la **salida/resto** (ejecución real
frente a la apertura de la vela siguiente y cierre forzoso). Los costes del
modelo no explican el gap. No se encontró un error en la simulación de T5 y
no se modificó `ai_trader`.
