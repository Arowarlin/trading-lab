# Paper/demo frente a live: qué no se replica

Este documento lista lo que **Alpaca paper** y **MT5 demo** no aplican y cómo
se cubre cada hueco. Nada de esto justifica pasar a live: la decisión es
humana y sigue siendo paper/demo.

| Hueco | Por qué no se replica en paper | Cómo lo cubrimos |
|---|---|---|
| Latencia real | El paper ejecuta en el servidor del bróker sin cola de producción | `tca` mide la latencia observada y la EWMA de slippage frente al supuesto del backtest |
| Slippage real | El paper fills al precio posted, con liquidez sintética | `tca` y `drift` comparan el slippage p50/p95 con los umbrales del backtest |
| Profit target y drawdown reales | El fondeo evaluates规则 del bróker, no las nuestras | `prop/simulator.monte_carlo` + oráculo `prop-ev`; el guard de cuenta usa los límites efectivos del contrato |
| Latencia delLanguage Server | El LLM local no tiene cola ni throttling | `lab llm status` mide `schema_ok`; el ranking de modelos mide la latencia mediana |
| News blackout real | El feed de noticias puede llegar tarde | `news_blackout` bloquea por evento con ventana ±30 min; el forward solo opera con `news_ok` |
| Fallas de bróker | Paper nunca rechaza órdenes por margen | `killswitch`, `risk_pause` y el guard de presupuesto cortan antes |
| Reintentos y duplicados | Paper no repite fills | La cadena de hash de `orders` y `console_actions` detecta cualquier inserción doble o alteration |
| Rollover y swap | El intradía de MT5 demo no cobra swap real | Los costes intradía se calibran con `execution_model.py` y el informe de `intraday_broker` |
| Filtro de símbolos del bróker | Paper permite cualquier ticker del catálogo | `asset_aliases` + `symbol_allowed` en cada apertura |

## Reglas que no se relajan

- Nunca `mode=live` sin autorización humana explícita.
- El simulacro (`lab drill`) **rechaza** `mode=live` y exige operador armado.
- Las alertas críticas (kill-switch, cadena de auditoría rota) no se suprimen
  nunca por presupuesto de alertas.
