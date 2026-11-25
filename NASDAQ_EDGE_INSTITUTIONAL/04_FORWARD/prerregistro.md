# Prerregistro forward · NQEDGE (F4)

Escrito el 2026-11-25, **antes** de que exista ningun dato forward. Cualquier
cambio posterior de codigo o de reglas invalida este prerregistro y exige una
variante nueva con fecha de inicio nueva.

## Variantes congeladas

| ID | Familia | Definicion exacta | Objetivo |
|---|---|---|---|
| NQF-A | A · NY Open Breakout | OR de 15 min (9:30-9:44 ET). Entrada al cierre de la primera vela M5 que cierra > ORH + 1 tick (o < ORL - 1 tick), sin retest. Stop en el lado opuesto de la OR o 1xATR5 desde el cierre, el mas cercano. | 2R |
| NQF-B | B · Liquidity Sweep | Nivel ON (ONH/ONL). Barrido >= 2 ticks y cierre M5 de vuelta dentro en <= 3 velas. Entrada en contra. Stop 1 tick mas alla del extremo del barrido. | VWAP |
| NQF-C | C · VWAP | Cierre M5 fuera de VWAP +/- 2 sigma y cierre siguiente de vuelta dentro. Entrada en contra. Stop en el extremo de las ultimas 6 velas M5 +/- 1 tick. | VWAP |

Reglas comunes: entrada en la apertura de la vela M1 siguiente + 1 tick de
slippage; si SL y TP caen en la misma vela, primero el SL; flat 15:55 ET;
ventana de entrada 9:35-11:30 ET; maximo 3 operaciones/dia y parada tras 2
perdidas o -300 USD/dia (esta ultima solo se puede aplicar en vivo, con
desenlaces); FOMC sin entradas; Tier 1 dentro de la sesion, sin entradas en
+/- 5 min y cierre a mercado 5 min antes.

Si el objetivo (VWAP) queda a menos de 1R de la entrada, la senal se descarta.

## Hashes del codigo congelado

| Fichero | SHA-256 |
|---|---|
| `tools/forward_models.py` | `cb7ee5a996e28becba65d211c99f23436c9ec4e31cd0ae8c4281268cb47c69b3` |
| `tests/test_forward_models.py` | `4c44ce6d35c3ebb01499da41e57492c789230a15dfad43ed93dfa5d90f61327b` |
| `tools/forward_mechanics.py` | `ffa17e97d882bfe0940f62cca17fdd21badec47f879edc44f5196e8d8cca9288` |

`tools/forward_daily.py` (F5) solo lee datos y escribe el ledger; su hash se
guarda en cada fila del ledger. No define senales.

## Inicio

- **Nominal:** primera sesion NYSE completa despues del commit de F4.
  - 2026-11-26: festivo (Thanksgiving).
  - 2026-11-27: cierre anticipado (13:00), no completa.
  - **2026-11-30 (lunes), primera sesion completa.**
- **Efectivo:** condicionado al input del operador. La comision MNQ por
  contrato y lado no esta fijada: **Sin datos**.
  `bloqueado: falta comision MNQ del operador`. El forward no arranca hasta
  que el operador la fije; la fecha de inicio se desplaza a la primera sesion
  completa siguiente a ese input.
- Sin fecha de fin. Termina al llegar a **n = 200 operaciones cerradas por
  variante**, cada una por separado.

## Tamano y potencia

- SL de 1R y TP de 2R, sin parciales.
- sd aproximada: sqrt(p(1-p)) x 3 ~ 1,4R (C y B apuntan al VWAP; no se afina
  sin mirar desenlaces).
- alpha = 0,05/3 (Bonferroni, 3 pruebas) y potencia 80 %:
  MDE = (2,13 + 0,84) x 1,4 / sqrt(200) ~ **0,29R**.
- Un efecto real menor de ~0,3R puede quedar sin detectar; "no confirma" no lo
  descarta.

## Evaluacion unica

- **Una sola evaluacion por variante**, al llegar a n = 200. Antes no se mira
  ningun resultado: los informes intermedios solo dan numero de operaciones y
  fechas.
- Criterio por variante, 3 pruebas:
  - (a) media neta de R con 1 tick > 0 y t unilateral >= 2,13;
  - (b) media neta con 2 ticks por lado > 0;
  - (c) informativo: Monte Carlo Topstep 50K sobre la secuencia de R, frente a
    la linea base de ventaja cero con la misma regla de riesgo (metodo de
    `TL3_REPORTS/propfund_zero_edge.md`).
- Veredicto literal: **"confirma"** / **"no confirma"**. Sin reinterpretacion
  ni cambio de variante.
- En F7 el operador registra 3 pruebas (`TL3-NQF-A/B/C`) **antes** de evaluar.
- Indicador Pine (fase E): puede mostrar las senales con la etiqueta "en
  forward, sin validar". El estado global sigue siendo `NO EDGE VALIDATED`.

## Riesgo y costes

- Instrumento: **MNQ**, 150 USD de riesgo por operacion.
- Contratos = floor(150 / (stop_pt x 2 USD + comision x 2 + slippage x 2)),
  con slippage de 1 tick por lado. Si sale 0: NO TRADE. No se agranda el stop.
- Comision: **Sin datos** (input del operador). Slippage: 1 tick por lado;
  estres de 2 y 4 ticks.

## Datos

- M1 de `US100.cash` en MT5, attach-only, login verificado antes y despues,
  como proxy de precio de NQ durante **toda** la prueba. Declarado; no se
  cambia de fuente a mitad.
- Volumen: no se usa. El VWAP usa tick volume y queda marcado como proxy.
- OOS-2 (2024-01-01 a 2026-11-20) sigue sellado.

## Mecanica esperada (F3, solo conteos)

| Variante | Senales/dia DEV | Dias con senal | Stop mediana | Stop p90 | n=200 estimado (senales) |
|---|---:|---:|---:|---:|---|
| NQF-A | 0,938 | 93,81 % | 6,84 pt (27,4 ticks) | 25,79 pt (103,2 ticks) | 214 sesiones, ~2027-09-26 |
| NQF-B | 0,198 | 19,19 % | 4,25 pt (17,0 ticks) | 16,32 pt (65,3 ticks) | 1013 sesiones, ~2030-10-18 |
| NQF-C | 1,120 | 72,28 % | 4,00 pt (16,0 ticks) | 15,75 pt (63,0 ticks) | 179 sesiones, ~2027-08-08 |

Las fechas son cotas optimistas de **senales** (no descuentan NO TRADE ni el
corte por perdidas). NQF-B descarta el 61 % de sus senales porque el VWAP queda
a menos de 1R; su forward puede durar anos. No se cambia la variante por ello.

## Prohibiciones vigentes

No se calcula P&L, expectativa, PF, win rate ni ningun resultado de las
variantes antes de F7, ni historico ni forward. Solo conteos. Sin ordenes, sin
bots, sin F13, sin `record-informal`, sin tareas programadas, sin push.
