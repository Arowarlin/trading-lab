# PENDIENTES_MENORES · lo que queda de los hallazgos LOW/MEDIUM (2026-11-27)

Hechos en la rama (sin cambio en resultados del motor): B-11, B-12, B-13, C-06, C-13, C-14,
D-09, D-10. Antes: A-01, A-02, A-04, B-01, B-02, B-03, C-01, C-02, C-04, C-07, D-04..D-07, E-01,
E-03, F0-06, F0-09, F0-10, B-14 (parcial).

Lo que sigue **no** se ha tocado porque cambia resultados, hashes o reglas de las puertas. Cada uno
necesita una decisión del operador antes de tocarlo, no solo permiso técnico.

## A · Cambian los resultados del motor (`fastbt`): versión nueva del motor

Todos juntos en un bloque "motor 0.4.0", con su tag `motor-…-pre` y un test de paridad
Numba/Python. Ninguno es urgente: los efectos son pequeños o latentes.

| ID | Efecto | Por qué esperar |
|---|---|---|
| A-03 | En 24 h no se opera la última vela del día civil (1 de cada 6 en H4) | Cambia las operaciones de todas las campañas de 24 h |
| A-05 | Sesión que cruza medianoche con `flat_at` antes de las 00:00: entradas sin gestión (latente) | Ninguna campaña actual lo usa |
| A-06 / B-05 | `_calendar_core`: objetivo corto con BID sin spread (a favor hasta 1 spread) | Cambia campañas con calendario; conviene con A-03 |
| A-07 | Entrada en la última vela descartada aunque `close_at_end=True` | 1 operación por tramo como mucho |
| A-08 | Long y short en la misma vela: gana el long | Decidir la regla (no operar, o el de mayor señal) |
| A-09 | `close_signal` (solo paridad) no cierra al pasar a short | Solo en la ruta de paridad |
| A-10 | Vela exacta en `session_end` de sesiones nocturnas | Latente |

## B · Cambian los costes de campañas nuevas

| ID | Efecto | Decisión que falta |
|---|---|---|
| B-04 | Triple swap un día antes | Esperar el informe L5 (deals reales) |
| B-06 | `ffill` sin límite del spread histórico | Límite (p. ej. 60 min) y qué hacer después: ¿mediana horaria? |
| B-07 | Pico del rollover NY una hora tarde en USDJPY ~8 meses | Anclar el spread a la hora de NY en lugar de `session_tz` |
| B-08 / B-09 | El slippage medido nunca llega a Discovery; mezcla cuentas y no casa `US100.CASH` | Política: ¿cuándo sustituye una medición aprobada al supuesto? Hoy hay muy pocas filas (T12) |
| B-10 | `slippage_plus_2` casi nulo en índices y oro: la puerta 3 no discrimina | Cambiar el escenario a "× 2 del supuesto" es una regla de puerta nueva: prerregistro |

## C · Datos

| ID | Efecto | Decisión que falta |
|---|---|---|
| C-03 | Vela parcial (la última agregada o la M5 en curso de MT5) tratada como cerrada | Toca el lector MT5 (producción si lo usa el EA/ai_trader): cola de producción |
| C-05 | `detect_rolls` borra saltos reales y no ve rolls fuera de las 18:00 ET | Rehacer la detección con las fechas de roll de CME; cambia las series de futuros |
| C-08 | Calendario CME: festivos como cierre completo (son sesiones cortas) | Verificar con el calendario oficial de CME; **Sin datos** hasta tenerlo |
| C-09 | Rejilla H4 de Databento (18:00) frente a la del compilador (17:00) | Elegir una; cambia las velas H4 de futuros |
| C-10 | `dataset_hash` ignora ASK, volumen y spread | Cambiarlo invalida el hash de todas las campañas registradas: versión de hash nueva |
| C-11 | VWAP mezcla volúmenes de fuentes distintas y cae a 1,0 en silencio | Marcar "Sin datos" cambia las estrategias con VWAP |
| C-12 | El doc 06 §3 promete controles que no existen | Documentación: quitar la promesa o implementar los controles |

## D · Estadística

| ID | Efecto | Decisión que falta |
|---|---|---|
| D-08 | `efficiency` = 0 con IS <= 0 | Regla de WF: con v3 ya no decide; se puede dejar |
| D-11 | Protocolo v2: unidades distintas y no entra en `level4_ok` | ¿Es puerta o solo informe? Prerregistro |
| D-12 | DSR, PBO y t de v2 no corrigen la autocorrelación | Con v3 la puerta decisoria es PSR+Bonferroni; queda como nota |

## B-14 · lo que falta de la TCA

1. Salidas SL/TP: reconciliar con `history_deals` (`DEAL_REASON_SL/TP`) contra el `sl`/`tp` pedido.
2. `ts_utc` del fill (`deal.time_msc`).

Toca `execution/mt5.py` otra vez (producción) y necesita deals reales para probarse: mejor después
de L5, con los mismos deals.
