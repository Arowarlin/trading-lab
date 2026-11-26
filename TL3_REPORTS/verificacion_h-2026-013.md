# Verificación previa H-2026-013

- Commit verificado: `c4ec5799b77c910aea524165d1ec8aaa889669e9`.
- Plantilla: `config/discovery/templates/h1_sma50_session_long.yaml` · SHA-256 `9605ebc8c2fe8b00f0bdef31053b7f3c3de5b725d94076045275b0e665e47af9`.
- Spec: `.orquestador/specs/h-2026-013-us100-h1-sma50.yaml` · SHA-256 `bed161aef3ff61780bcd52b00e7ea4e6383b646fdf3fc5dc27f2c9dbfd9b5247`.
- `strategy_hash`: `b70ceaf335164c901a396688ba516bd6da72f5904fc7aec6c1a67a77d21c86ac`.
- `structural_hash` de la fila: `f8165f15d15bf352931fa32dd97bda5df9dd2f0d10d03f55c0d1969f86a1f8fe`.
- Datos: sintéticos y tramo IS 2019-01-02..2023-12-31 (US100 H1 Dukascopy).
- OOS-2 (2024-01-01..) **no leído**. No se imprime PnL ni expectativa.
- Verificador: `sesion-tl3-f3-audit`, distinto de la sesión que construyó F2.

# Comprobaciones

| Comprobación | Valor | Límite | Factor | Estado | Detalle |
|---|---:|---:|---:|---|---|
| atr_n | 14 | 14 | Sin datos | ok | constante |
| max_trades_per_day | 1 | 1 | Sin datos | ok | constante |
| side | long | long | Sin datos | ok | constante |
| sma_n | 50 | 50 | Sin datos | ok | constante |
| stop_atr | 2 | 2 | Sin datos | ok | constante |
| target_rr | 2 | 2 | Sin datos | ok | constante |
| time_exit | 15:00 | 15:55 | Sin datos | defecto | encabezado del spec 15:55; plantilla y fila 15:00 |
| time_exit_minutes | 360 | 415 | Sin datos | defecto | 415 derivado del spec; plantilla y fila 360 |
| fila.atr_n | 14 | 14 | Sin datos | ok | constante |
| fila.max_trades_per_day | 1 | 1 | Sin datos | ok | constante |
| fila.session_end | 10:00 | 10:00 | Sin datos | ok | constante |
| fila.side | long | long | Sin datos | ok | constante |
| fila.sma_n | 50 | 50 | Sin datos | ok | constante |
| fila.stop_atr | 2 | 2 | Sin datos | ok | constante |
| fila.target_rr | 2 | 2 | Sin datos | ok | constante |
| fila.time_exit | 15:00 | 15:00 | Sin datos | ok | la fila y la plantilla coinciden en 15:00 |
| fila.time_exit_minutes | 360 | 360 | Sin datos | ok | la fila y la plantilla coinciden en 360 |
| sintético · noches | 0 | 0 | Sin datos | ok | 235 ops; 0 cruzan día |
| sintético · SL antes que TP | ok | sí | Sin datos | ok | 3 días con SL y TP en la misma vela |
| sintético · salidas vistas | force_exit:97,stop:94,target:44 | stop, target, force_exit | Sin datos | ok | cada regla de salida al menos una vez |
| sintético · máx. 1/día | 1 | 1 | Sin datos | ok | una sola posición y un límite diario |
| NO TRADE · ATR 0 | 0 | 0 | Sin datos | ok | 88 señales rechazadas por stop no válido |
| tamaño · R normalizado | 1 | 1 | Sin datos | ok | CFD discovery no dimensiona contratos; 1 R por operación |
| DEV · noches | 21 | 0 | Sin datos | defecto | 799 ops; 21 cruzan día (2.63 %; 13 en la tabla 2021-2027; el resto, festivos/cierres 2019-2020) |
| DEV · razón de salida | force_exit:270,stop:405,target:120,time_exit:4 | stop, target, force_exit | Sin datos | ok | reglas de salida observadas en el tramo de desarrollo |
| DEV · máx. 1/día | 1 | 1 | Sin datos | ok | límite diario del DSL |
| DEV · hora de entrada | 10:00:799 | 10:00 NY | Sin datos | ok | señal 09:00 -> open de la vela siguiente |
| DEV · flat_at | 15:00:270 | 15:00 NY | Sin datos | ok | cierre de la última vela H1 de la sesión |
| DEV · señales sin operación | 2 | cada una explicada | Sin datos | aviso | 2021-04-02: señal 09:00 sin barra posterior el mismo día; 2023-04-07: señal 09:00 sin barra posterior el mismo día |
| DEV · frecuencia | 801 | Sin dato esperado | Sin datos | ok | 799 ops en 801 días con señal; el prerregistro no fija frecuencia esperada |
| DEV · huella de entradas | e44e21bd4c3a7eee | — | Sin datos | ok | SHA-256 de las fechas de entrada (16 hex) |
| DEV · cost_r mediano | 0.05388 | 0.1 | Sin datos | ok | peor de CFD-001/CFD-006; sin expectativa |
| DEV · muestra | 799 | >= 40 | Sin datos | ok | pliegues [207, 202, 77, 199] |
| hash estructural | f8165f15d15bf352 | reproducible | Sin datos | aviso | no se reproduce desde primary_params; el spec conserva 15:55 y la fila 15:00 |
| benchmark | no ejecutado en F2 | solo si entra en la puerta de potencia | Sin datos | aviso | el benchmark «sin filtro D1 y lado aleatorio» queda para antes de PnL |

**Veredicto: Defectos** — 35 comprobaciones, 3 defectos (3 avisos).

## Defectos

- **time_exit**: encabezado del spec 15:55; plantilla y fila 15:00
- **time_exit_minutes**: 415 derivado del spec; plantilla y fila 360
- **DEV · noches**: 799 ops; 21 cruzan día (2.63 %; 13 en la tabla 2021-2027; el resto, festivos/cierres 2019-2020)

## Señales perdidas

- 2021-04-02 09:00 → sin barra posterior el mismo día (siguiente: 2021-04-04 18:00); festivo/cierre NYSE.
- 2023-04-07 09:00 → sin barra posterior el mismo día (siguiente: 2023-04-09 18:00); festivo/cierre NYSE.

## Noches fuera de plazo

- 2019-07-04 10:00 → 2019-07-05 09:00 (stop, 19 velas)
- 2019-11-28 10:00 → 2019-11-29 09:00 (stop, 19 velas)
- 2019-12-24 10:00 → 2019-12-26 09:00 (target, 19 velas)
- 2020-01-20 10:00 → 2020-01-21 09:00 (stop, 18 velas)
- 2020-02-17 10:00 → 2020-02-18 09:00 (stop, 18 velas)
- 2020-05-25 10:00 → 2020-05-26 09:00 (time_exit, 18 velas)
- 2020-09-07 10:00 → 2020-09-08 09:00 (stop, 18 velas)
- 2020-11-27 10:00 → 2020-11-30 09:00 (time_exit, 19 velas)
- 2021-01-18 10:00 → 2021-01-19 09:00 (target, 18 velas)
- 2021-02-15 10:00 → 2021-02-16 09:00 (stop, 18 velas)
- 2021-05-31 10:00 → 2021-06-01 09:00 (target, 18 velas)
- 2021-07-05 10:00 → 2021-07-06 09:00 (target, 18 velas)
- 2021-09-06 10:00 → 2021-09-07 09:00 (stop, 18 velas)
- 2021-11-25 10:00 → 2021-11-26 09:00 (stop, 18 velas)
- 2022-11-24 10:00 → 2022-11-25 09:00 (stop, 18 velas)
- 2022-11-25 10:00 → 2022-11-28 09:00 (stop, 19 velas)
- 2023-01-16 10:00 → 2023-01-17 09:00 (time_exit, 18 velas)
- 2023-02-20 10:00 → 2023-02-21 09:00 (stop, 19 velas)
- 2023-05-29 10:00 → 2023-05-30 09:00 (target, 18 velas)
- 2023-06-19 10:00 → 2023-06-20 09:00 (time_exit, 18 velas)
- 2023-11-23 10:00 → 2023-11-24 09:00 (stop, 17 velas)

## Notas

- El motor evalúa `hit_stop` antes que `hit_tgt` en la misma vela (`fastbt.py`); el sintético lo confirma.
- Los 21 cruces de día (2,63 %) son festivos/cierres NYSE: falta la barra de las 15:00 y el `flat_at` no se dispara. La posición se cierra en la sesión siguiente y deja de cumplir `nights == 0`.
- `time_exit`/`time_exit_minutes` discrepan solo entre el encabezado del spec (15:55/415) y la plantilla+fila (15:00/360); es un defecto documental, no de la mecánica ejecutada.
- No se ha leído OOS-1/OOS-2, no se ha calculado expectativa y no se ha registrado ninguna campaña ni prueba nueva.
