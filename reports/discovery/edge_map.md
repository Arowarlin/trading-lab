# Edge Map · TradingLab 2.0

Solo lectura del databank. Sin OOS-2, sin campañas y sin DSR nuevo.

## Resumen

- sin probar: 0
- solo viabilidad: 0
- inválida: 1
- sin edge bruto: 8
- edge bruto que el coste elimina: 3
- sobreajustada: 1
- candidata nivel 3: 0
- confirmada nivel 4: 0
- no verificable: 0

## Mapa

| Hipótesis | Instrumento | TF | Fuente | Estado | Bruto mediana | Bruto mejor | Neto mediana | Cost_R | Ops+ | Candidatas | Confirmadas |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fix_reversal | EURUSD | H1 | dukascopy | edge bruto que el coste elimina | 0.0219 | 0.0273 | -0.0133 | 0.0327 | 6/6 | 0 | 0 |
| fix_reversal | GBPUSD | H1 | dukascopy | edge bruto que el coste elimina | 0.0127 | 0.0143 | -0.0227 | 0.0285 | 6/6 | 0 | 0 |
| d1_extension_reversion | US100 | D1 | dukascopy | sin edge bruto | 0.1504 | 0.8087 | 0.1361 | 0.0085 | 10/27 | 0 | 0 |
| turn_of_month | US100 | D1 | dukascopy | sin edge bruto | 0.0604 | 0.1245 | 0.0207 | 0.0089 | 7/9 | 0 | 0 |
| intraday_momentum_close | US100 | M5 | broker | inválida | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 0 | 0 |
| intraday_momentum_close_v2 | US100 | M5 | broker | sin edge bruto | -0.0112 | 0.0184 | -0.0778 | 0.0523 | 8/32 | 0 | 0 |
| ny_open_vol_filter | US100 | M5 | broker | sobreajustada | Sin datos | Sin datos | 0.0292 | 0.0470 | Sin datos | 0 | 0 |
| d1_extension_reversion | US500 | D1 | dukascopy | sin edge bruto | -0.0539 | 0.0811 | -0.1257 | 0.0414 | 1/27 | 0 | 0 |
| turn_of_month | US500 | D1 | dukascopy | sin edge bruto | 0.0819 | 0.1628 | 0.0156 | 0.0384 | 6/9 | 0 | 0 |
| asia_range_reversion | USDJPY | H1 | dukascopy | sin edge bruto | -0.0533 | -0.0291 | -0.1170 | 0.0422 | 0/27 | 0 | 0 |
| fix_reversal | USDJPY | H1 | dukascopy | sin edge bruto | -0.0018 | 0.0066 | -0.0476 | 0.0410 | 5/6 | 0 | 0 |
| donchian_vol_h4 | USDJPY | H4 | dukascopy | edge bruto que el coste elimina | 0.0188 | 0.0764 | -0.0032 | 0.0236 | 3/27 | 0 | 0 |
| donchian_vol_h4 | XAUUSD | H4 | dukascopy | sin edge bruto | 0.0422 | 0.1511 | 0.0141 | 0.0374 | 9/27 | 0 | 0 |

## Cuentas sin conectar

- CFD-002 · ftmo · ftmo_2step · DISCONNECTED · fuera de la capa de firma

La etiqueta usa la mediana de la rejilla (grid) o de la frontera de rango 1 (GA). El mejor valor es informativo y no decide.
