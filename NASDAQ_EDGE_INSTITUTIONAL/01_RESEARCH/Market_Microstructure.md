# Microestructura · MNQ / NQ / US100

Consulta: 2026-11-25. Etiquetas de origen: **[OFICIAL]** web de la bolsa o de la
firma; **[LAB]** medido en este repositorio; **[HIPÓTESIS]** propuesta propia,
sin verificar; **Sin datos** = no encontrado.

## 1. Especificaciones de contrato

| Campo | MNQ | NQ | Fuente |
|---|---|---|---|
| Multiplicador | $2 × Nasdaq-100 | $20 × Nasdaq-100 | [OFICIAL] CME contract specs |
| Valor por punto | $2,00 | $20,00 | derivado del multiplicador |
| Tick mínimo (outright) | 0,25 pt = **$0,50** | 0,25 pt = **$5,00** | [OFICIAL] |
| Tick de calendar spread | 0,05 pt = $0,10 | 0,05 pt = $1,00 | [OFICIAL] |
| Horario CME Globex | dom 18:00 → vie 17:00 ET; pausa diaria 17:00–18:00 ET (16:00–17:00 CT) | igual | [OFICIAL] |
| Meses listados | Mar/Jun/Sep/Dic, 5 trimestres consecutivos | Mar/Jun/Sep/Dic, 6 trimestres + 2 junios + 4 diciembres adicionales | [OFICIAL] |
| Vencimiento | 9:30 ET del 3er viernes del mes de contrato | igual | [OFICIAL] |
| Liquidación | financiera | financiera | [OFICIAL] |
| Límites de precio | existen ("Price Limits", tabla aparte) | igual | [OFICIAL] valores **Sin datos** (tabla no leída) |
| Fees exchange + clearing | **Sin datos** | **Sin datos** | no leído en cmegroup.com |

Fuentes:
- https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html
- https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.contractSpecs.html

Ambas se leyeron el 2026-11-25 (cotización retrasada MNQZ6 visible ese día).

### Tabla de recorridos en dinero (por contrato, sin costes)

| Puntos | MNQ | NQ |
|---:|---:|---:|
| 5 | $10 | $100 |
| 10 | $20 | $200 |
| 15 | $30 | $300 |
| 20 | $40 | $400 |
| 30 | $60 | $600 |
| 50 | $100 | $1.000 |
| 100 | $200 | $2.000 |

1 NQ = 10 MNQ en exposición. Las firmas de fondeo usan la misma equivalencia:
Topstep "1 mini = 10 micros"; Tradeify "10 micros = 1 mini". Apex: **Sin datos**
sobre la equivalencia en la página leída.

## 2. Costes

| Concepto | MNQ | NQ | Fuente / estado |
|---|---|---|---|
| Round trip todo incluido (Tradeify) | **Sin datos** (la tabla leída no muestra micros) | $5,76 | [OFICIAL] help.tradeify.co/en/articles/10468315 |
| Round trip Topstep | **Sin datos** | **Sin datos** | artículo de comisiones no leído |
| Round trip Apex | **Sin datos** | **Sin datos** | no leído |
| Slippage | parámetro: 1 tick por lado en condiciones normales [HIPÓTESIS]; ≥ 4 ticks alrededor de Tier 1 [HIPÓTESIS] | igual | se medirá en Fase B con M1 alrededor de eventos |

Regla del proyecto: el motor de riesgo y el Strategy Tester reciben la comisión
como **input obligatorio**. Si queda en blanco, el tester no reporta métricas
netas.

## 3. US100 (CFD) · no extrapolable

US100 depende del proveedor. En este laboratorio el CFD de referencia es
`US100.cash` (FTMO, MT5):

- Spread medido por el EA: n = 6, mediana 0,295 pt, p75 1,21 pt. La muestra es
  insuficiente y está marcada `Sin datos` en `config/propfund/costs.measured.yaml` [LAB].
- Precio = índice de contado ajustado por el proveedor, no el futuro.
  - En 2026-10, Dukascopy y el bróker difieren −0,55 bps de media [LAB].
  - El futuro NQ además lleva base (carry), que se mueve con tipos y dividendos.
- Volumen = tick volume del proveedor, **no** volumen CME. Cualquier filtro de
  volumen (RVOL, perfil) calibrado en NQ **no** vale en US100 sin recalibrar.
- Horario, swap y tamaño de contrato dependen del proveedor y de la cuenta.

Consecuencia: los resultados se reportan por separado para NQ/MNQ (CME) y US100.
Un edge validado en NQ solo pasa a US100 tras una validación propia con datos del
CFD.

## 4. Sesiones y liquidez

| Franja (ET) | Nota |
|---|---|
| 18:00–09:30 | Globex overnight. Define ONH/ONL. |
| 08:30 | Publicaciones macro principales (CPI, NFP, PPI, Retail Sales, GDP, PCE). [OFICIAL] BLS/BEA/Census |
| 09:30 | Apertura del contado NYSE/Nasdaq. Ancla del opening range. |
| 10:00 | Segunda tanda macro (JOLTS; ISM, hora **Sin datos** oficial). |
| 14:00 / 14:30 | Comunicado y rueda de prensa FOMC. Topstep publica 13:00 y 13:30 CT [OFICIAL Topstep]. |
| 16:00 | Cierre del contado. |
| 16:10 | Topstep: todo cerrado a las 15:10 CT [OFICIAL]. |
| 16:45 | Tradeify: todo cerrado a las 16:45 ET [OFICIAL]. |
| 17:00 | Cierre Globex. |

Volumen por franja, distribución del rango de apertura y slippage real: **Sin
datos**. Se miden en la Fase B (ver `Nasdaq_Intraday_Research.md`). No se
publican porcentajes de la literatura sin muestra, periodo y método.

## 5. DST

CME publica el horario en ET y en CT. Las dos zonas cambian de hora a la vez, así
que el horario en ET es estable todo el año. El desfase ET↔UTC sí cambia (UTC−5
o UTC−4).

En las semanas de marzo y noviembre en que EE. UU. y Europa no coinciden, el
desfase con Europa cambia. Afecta a US100 si el bróker usa hora de servidor
europea (FTMO: Europe/Prague).

En Pine: siempre `timestamp("America/New_York", ...)` y `time(timeframe.period,
session, "America/New_York")`. Nunca horas UTC fijas.

## 6. Rollover

- NQ.c.0 de Databento (calendar roll) tiene saltos en el roll [LAB].
  - `reports/discovery/futuros-roll.md`: 17 rolls en H1 2010–2026 con salto medio −28 pt.
  - `reports/ea/us100-ftmo1-nq-2010-2017.md`: 288 sesiones de roll excluidas en M1.
- Política del proyecto:
  - Ejecución y costes sobre la serie sin ajustar.
  - Indicadores de varios días (ATR diario, PDH/PDL) sobre serie back-adjusted por diferencia, con tabla explícita de rolls.
  - La sesión del roll se marca y se reporta aparte.
- TradingView `NQ1!`/`MNQ1!` cambia de contrato según la regla de TradingView,
  no la de este proyecto. Las líneas PDH/ONH del día del roll pueden mezclar
  contratos. El indicador marca ese día como `ROLL DAY` y baja la calidad de
  señal [HIPÓTESIS de diseño].
