# Auditoría de repintado

| Elemento | Cómo se calcula | ¿Puede repintar? |
|---|---|---|
| ATR diario y su percentil | `request.security("D", ta.atr(14)[1], lookahead_on)` | No: valor de la vela diaria cerrada |
| ADX 15 min | `request.security("15", fAdx()[1], lookahead_on)` | No: M15 cerrada |
| OR5/15/30, ONH/ONL, PDH/PDL | Acumulados con `var` sobre barras ya vistas; el OR se dibuja solo cuando termina su ventana | No |
| VWAP RTH | `ta.vwap(hlc3, rthStart)` | En la vela abierta cambia con el precio, como cualquier VWAP. En las velas cerradas es fijo |
| Estado WAIT/NO TRADE | Reglas de cuenta, horario y noticias | Las alertas `alert()` solo se emiten con `barstate.isconfirmed`, una vez por cambio |
| Señales BUY/SELL | No existen | — |
| Calendario | Timestamps fijos en `America/New_York` | No. El DST lo resuelve `timestamp()` con la zona IANA |

En el motor de backtest (Fase C), la señal se calcula al cierre de la M5 y la
entrada en la M1 siguiente. Lo comprueba el test
`test_model_a_signal_ignores_future_bars`: cambiar todo el futuro no altera la
señal ni el stop.
