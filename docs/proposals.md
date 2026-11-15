# Propuestas de configuración

Una propuesta es un YAML en `config/proposals/` que describe un cambio **sin
aplicarlo**. No hay ningún cargador automático: ningún bot, tarea ni proceso lee
esta carpeta. La aplicación es siempre manual y con confirmación del operador.

## `disable_fx_forward`

Archivo: `config/proposals/disable_fx_forward.yaml`.

Propone desactivar los dos forwards de FX con Sharpe negativo en backtest:

| Bot | Magic | Cambio |
|---|---|---|
| `eurusd-london-pullback-forward` | `20261151` | `enabled: true → false` |
| `usdjpy-tokyo-breakout-forward` | `20261152` | `enabled: true → false` |

No toca `us100-trend-d1` (`20261153`) ni `config/intraday_forward.yaml`.

Aplicación manual:

1. Editar `config/intraday_forward.yaml` y poner `enabled: false` solo en los dos
   bots indicados.
2. Verificar que `us100-trend-d1` sigue con `enabled: true`.
3. Reiniciar `TradingLab-IntradayForward` para que relea el YAML.
4. Ejecutar `lab doctor` y `lab f13 config-check`.

No existe `lab proposals apply`; si se añade en el futuro, deberá exigir
`--confirm` y registrar la acción en `console_actions`.
