# Carril de acciones (ORB) en paper

El carril de acciones es la única vía del laboratorio que toca **acciones**.
Vive en `config/equities_lane.yaml` y su estado se ve con:

```
.venv\Scripts\lab.exe daytrader lane
```

## El ticker lo decide el operador

El scan **no elige**: la lista de pre-apertura propone y el operador decide.
Desde el 2026-11-11 el carril tiene un ticker fijo:

| Campo | Valor | Por qué |
|---|---|---|
| `ticker` | `AAPL` | El mismo que usa el pipeline externo (`trader/entry.json`) y el 13F de Berkshire que da los pesos de referencia |
| `setup` | `orb` | Ruptura del rango de apertura |
| `interval` | `5m` | Intervalo del scan |
| `opening_range_minutes` | `15` | Ventana del rango de apertura |
| `account` | `alpaca_paper` | Cuenta del laboratorio |
| `only_ticker` | `true` | Cualquier otro símbolo se rechaza |

Cambiar el ticker es editar `config/equities_lane.yaml` y volver a lanzar
`lab daytrader lane`. Ese archivo **no** está en el hash congelado de F13.

## Qué hace y qué no hace

`lab daytrader import` lee `watchlist.json`, `orders.json` y `state/risk.json`
del pipeline externo (`C:\Users\PC\Proyectos\trading\trader`) y pasa cada orden
por los guards del laboratorio.

Para que una orden llegue al bróker **paper** hacen falta cuatro cosas:

1. `daytrader.enabled: true` en `config/lab.yaml` (decisión del operador del
   2026-11-11).
2. `--execute` en la línea de comandos.
3. La cuenta es paper (`alpaca_paper`) y `mode` no es `live`.
4. El veredicto del pipeline externo es `PASS` **y** el símbolo es el ticker
   del carril.

El orden de los guards es: **ticker del carril → veredicto externo → guards
del laboratorio**. Una orden de otro símbolo se rechaza con
`BLOCK · ticker fuera del carril de acciones (AAPL)`.

## Límites

- El pipeline externo manda sus propios límites (`config.json` del trader):
  50 USD por operación, 150 USD al día, 3 operaciones al día, mínimo 1:1 de
  reward:risk, sin entradas después de las 15:30 y plano a las 15:55.
- El laboratorio añade los suyos: presupuesto de riesgo por activo y por
  clúster, kill-switch, blackout de noticias y límites de la cuenta
  (`alpaca_paper`: 0,75 % por operación, 1,5 % abierto, 3 operaciones al día).
- Todo es **paper**: el guard de identidad rechaza cuentas reales.

## Nada se ejecuta solo

Ninguna tarea programada llama a `lab daytrader import --execute`. El carril
queda listo para que el operador lo lance a mano cuando la señal externa sea
`PASS`:

```
.venv\Scripts\lab.exe daytrader import --execute
```

El import sin `--execute` es un dry-run: muestra el plan y no toca nada.
