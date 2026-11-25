# Fuentes de datos · evaluación (2026-11-25)

Etiquetas: [LAB] = ya en el laboratorio; [OFICIAL] = documentación del proveedor
leída; [CONOCIDO] = conocimiento general del producto, no verificado hoy.
Los precios de las fuentes de pago son **Sin datos**: cada portal muestra el
coste al configurar la descarga.

| Fuente | Instrumentos | Resolución | Cobertura | Volumen | Contratos individuales / roll | Uso en el proyecto |
|---|---|---|---|---|---|---|
| **Databento GLBX.MDP3** [LAB] | NQ (y MNQ, ES…) | desde tick hasta 1d (`ohlcv-1m` usado) | NQ M1 en caché: 2010-06-07 → 2018-12-31 | volumen CME real | continuo `NQ.c.0` por calendario; la caché **no** trae `instrument_id` | serie principal NQ en DEV. Falta 2019+ y MNQ |
| **Dukascopy** [LAB] | USA100 (CFD/índice) | M1 bid+ask | 2011-09-18 → 2026-11-20 | tick volume (no CME) | sin contratos (contado) | proxy de precio para 2019–2026; spread real del proveedor; **no** apto para volumen |
| **MT5 FTMO `US100.cash`** [LAB] | CFD | M5 | desde 2021-10 | tick volume | — | validación específica de US100 |
| **CME DataMine** [CONOCIDO] | todos los CME | tick / MBO / BBO | décadas | real | contratos individuales | fuente de referencia, cara; no necesaria si Databento cubre |
| **TradingView** [CONOCIDO] | `NQ1!`, `MNQ1!`, contratos | 1m con historial limitado según el plan | intradía corto en planes básicos | real (CME, retraso según suscripción) | continuo con regla propia de TradingView | solo para el indicador; **no** para validar |
| **NinjaTrader / Kinetick** [CONOCIDO] | CME | tick/1m | años según el feed | real | contratos individuales + merge policy configurable | alternativa si no se usa Databento |

## Decisión vigente

1. Investigación NQ: Databento (el mismo dataset que ya validó el laboratorio en F10c).
2. Hasta que se compre el tramo 2019+, el periodo 2019–2021 del DEV se cubre con
   Dukascopy **solo para modelos de precio**: A, B, C con VWAP por tick volume
   (marcado como proxy), D y F.
3. MNQ = NQ en precio. MNQ cotiza desde mayo de 2019 sobre el mismo índice y en
   la misma bolsa. Coste por contrato y liquidez distintos: se modela el coste
   MNQ, no se reutiliza el de NQ.
4. US100: validación aparte con Dukascopy/MT5 en Fase F.

## Compra recomendada (decide el operador)

Databento GLBX.MDP3 `ohlcv-1m` para `NQ.c.0` y `MNQ.c.0` de 2019-01-01 a hoy, más
`definition` para la tabla de rolls con `instrument_id`. Con eso:
- la Fase C usa volumen CME real en todo el DEV y el OOS-1;
- los modelos E (perfil) y el filtro RVOL dejan de limitarse a 2010–2018.
