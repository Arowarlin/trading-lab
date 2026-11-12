# Encendido del forward swing US100 (demo)

Fecha: 2026-11-11. Cuenta: `ftmo_demo` (MT5, `require_demo=true`). Nada de live.

El bot `us100-trend-d1` vive en `config/intraday_forward.yaml` con
`enabled: false`. La tarea `TradingLab-IntradayForward` lo evalúa **solo en la
primera barra H4 del día UTC** (00:00-04:00), en los primeros cinco minutos
tras su cierre (04:00-04:04 UTC). Mientras esté desactivado, la tarea hace un
dry-run y no envía nada.

## 1. Encender

Edita `config/intraday_forward.yaml` y cambia **solo** esta línea del bloque
`us100-trend-d1`:

```yaml
    enabled: true
```

No hace falta tocar la tarea ni reiniciar nada: el `.ps1` lee el YAML en cada
pasada y decide `--execute` o dry-run.

## 2. Comprobar en seco

```powershell
lab intraday forward --bot us100-trend-d1 --bars 2000
```

Debe mostrar la tabla del forward con `Señal`, `Acción` (`flat`, `open_long`,
`open_short` o `hold`) y `Sin --execute: dry-run`. Si sale
`fuera de la ventana de entrada`, es normal: la barra H4 válida es la de
00:00-04:00 UTC y el dry-run se ejecuta a cualquier hora.

## 3. Comprobar que la tarea lo toma

```powershell
Get-ScheduledTask -TaskName "TradingLab-IntradayForward" | Select-Object State
Get-ScheduledTaskInfo -TaskName "TradingLab-IntradayForward"
Get-Content logs\intraday_forward\forward_execute_$(Get-Date -Format yyyyMMdd).log -Tail 30
```

En el log debe aparecer `us100-trend-d1` y, cuando esté encendido,
`FIN us100-trend-d1 exit=0`. Si está apagado verás
`us100-trend-d1 enabled:false; solo dry-run (no se envia)`.

La ejecución real la hace la tarea sola en la ventana de 04:00-04:04 UTC. No
hace falta `-Force`; si se usa, el bot sigue exigiendo que la última barra H4
sea la primera del día.

## 4. Primeras 24 horas: qué mirar

| Qué | Comando | Qué se busca |
|---|---|---|
| Posición y stop | `lab mt5 positions` | Una posición con magic `20261153`, SL a 3×ATR |
| Diario / FIFO | `lab journal --bot forward:us100-trend-d1` | La ida y vuelta aparece como operación cerrada |
| TCA | `lab tca --bot forward:us100-trend-d1` | Slippage real ≤ 3 bps; si no hay 5 fills, dirá muestra insuficiente |
| Guardián | `lab guardian status` | ALERT sin disparos; la puerta sigue en 5 sesiones |
| Riesgo | `lab status` | Colchón diario/drawdown en verde |
| Acciones | `lab web` → Consola → Acciones, o `lab audit verify` | Sin acciones raras; la cadena de auditoría intacta |
| Alertas | `lab alerts status` | El canal sigue vivo; sin `intraday_forward_failed` |

La posición puede dormir varios días: `force_exit: null` y `swing: true`. FTMO
Swing permite overnight y fin de semana; esta demo no impone restricción de
overnight. Solo la cierran la señal contraria o el stop. El stop lo custodia
MT5, no el proceso de Python.

## 5. Incubación

```powershell
lab lifecycle report --bot us100-trend-d1
```

Criterios congelados (hash `67f7695cf087e673`, ventana 2026-11-11 → 2027-01-10):
60 días, mínimo 8 trades, Sharpe forward > 0, slippage ≤ 3 bps, 0 breach.
Estar incubando **no** cambia `enabled`; el bot sigue apagado hasta que el
operador lo encienda.

Nota: se incubó con `--force` porque la puerta de evidencia no es elegible
(el research swing dio 0/10 y PBO 80,3 %); el operador asume la incubación
forward para medirla en demo. Sin `--force`, el comando se niega.

## 6. Revertir

1. `enabled: false` en el bloque `us100-trend-d1`.
2. La tarea volverá a hacer dry-run; no hay que desregistrarla.
3. Si hay posición abierta y se quiere cerrar ya:
   `lab mt5 close --ticket <ticket>` (o desde la consola). Si no, se queda con
   su stop y la cierra la señal contraria.

## Avisos

- **No tocar `config/lab.yaml`** sin re-congelar F13: el hash cubre ese archivo
  y cualquier cambio invalida el bot QQQ hasta `lab f13 refreeze`.
- El tamaño efectivo es el **volumen mínimo** del bróker: `exposure: 0.75`
  aplicado sobre el mínimo cae por debajo del mínimo, así que se usa el mínimo
  (documentado en el propio YAML).
- El forward es demo. No se relajan umbrales ni se activan bots fuera de este
  procedimiento.
