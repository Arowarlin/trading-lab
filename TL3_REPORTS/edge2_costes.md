# EDGE-2 Y0 - diagnostico de huecos y costes de indices

Generado por `scripts/edge2_x0.py` (solo lectura). No se toco `engine.yaml`.

## 1. Huecos H1/H4 frente a M15 (solo no programados)

| Activo | TF | Ano | Huecos | Duracion mediana (min) | Duracion max (min) | Clases |
|---|---|---:|---:|---:|---:|---|
| US100 | M15 | 2014 | 7 | 75.0 | 165.0 | noche Dukascopy pre-2018:7 |
| US100 | M15 | 2015 | 2 | 60.0 | 60.0 | noche Dukascopy pre-2018:2 |
| US100 | M15 | 2019 | 2 | 75.0 | 75.0 | hueco real:2 |
| US100 | M15 | 2020 | 7 | 90.0 | 120.0 | hueco real:7 |
| US100 | M15 | 2024 | 2 | 120.0 | 165.0 | hueco real:2 |
| US100 | M30 | 2014 | 8 | 210.0 | 210.0 | noche Dukascopy pre-2018:8 |
| US100 | M30 | 2020 | 1 | 120.0 | 120.0 | hueco real:1 |
| US100 | M30 | 2024 | 1 | 150.0 | 150.0 | hueco real:1 |
| US100 | H1 | 2013 | 12 | 3000.0 | 3180.0 | hueco de historia (>1 dia):11, noche Dukascopy pre-2018:1 |
| US100 | H1 | 2014 | 38 | 2100.0 | 4440.0 | hueco de historia (>1 dia):21, noche Dukascopy pre-2018:17 |
| US100 | H1 | 2015 | 182 | 540.0 | 5040.0 | hueco de historia (>1 dia):37, noche Dukascopy pre-2018:145 |
| US100 | H1 | 2016 | 252 | 540.0 | 4860.0 | hueco de historia (>1 dia):47, noche Dukascopy pre-2018:205 |
| US100 | H1 | 2017 | 251 | 540.0 | 4920.0 | hueco de historia (>1 dia):48, noche Dukascopy pre-2018:203 |
| US100 | H1 | 2018 | 69 | 600.0 | 4920.0 | hueco de historia (>1 dia):12, noche Dukascopy 2018:57 |
| US100 | H1 | 2020 | 4 | 360.0 | 840.0 | hueco real:4 |
| US100 | H1 | 2024 | 1 | 120.0 | 120.0 | hueco real:1 |
| US100 | H1 | 2025 | 3 | 300.0 | 360.0 | cierre temprano:1, festivo:2 |
| US100 | H4 | 2013 | 2 | 2040.0 | 2160.0 | hueco de historia (>1 dia):2 |
| US100 | H4 | 2014 | 14 | 720.0 | 3840.0 | hueco de historia (>1 dia):5, noche Dukascopy pre-2018:9 |
| US100 | H4 | 2015 | 182 | 480.0 | 4800.0 | hueco de historia (>1 dia):37, noche Dukascopy pre-2018:145 |
| US100 | H4 | 2016 | 252 | 480.0 | 4800.0 | hueco de historia (>1 dia):47, noche Dukascopy pre-2018:205 |
| US100 | H4 | 2017 | 251 | 480.0 | 4800.0 | hueco de historia (>1 dia):48, noche Dukascopy pre-2018:203 |
| US100 | H4 | 2018 | 69 | 480.0 | 4800.0 | hueco de historia (>1 dia):12, noche Dukascopy 2018:57 |
| US100 | H4 | 2020 | 1 | 720.0 | 720.0 | hueco real:1 |
| US500 | M15 | 2014 | 26 | 90.0 | 225.0 | noche Dukascopy pre-2018:26 |
| US500 | M15 | 2015 | 1 | 60.0 | 60.0 | noche Dukascopy pre-2018:1 |
| US500 | M15 | 2019 | 1 | 135.0 | 135.0 | hueco real:1 |
| US500 | M15 | 2020 | 6 | 82.5 | 120.0 | hueco real:6 |
| US500 | M15 | 2024 | 1 | 75.0 | 75.0 | hueco real:1 |
| US500 | M30 | 2014 | 12 | 120.0 | 210.0 | noche Dukascopy pre-2018:12 |
| US500 | M30 | 2019 | 1 | 120.0 | 120.0 | hueco real:1 |
| US500 | M30 | 2020 | 1 | 120.0 | 120.0 | hueco real:1 |
| US500 | H1 | 2013 | 11 | 3000.0 | 3180.0 | hueco de historia (>1 dia):10, noche Dukascopy pre-2018:1 |
| US500 | H1 | 2014 | 38 | 3000.0 | 4440.0 | hueco de historia (>1 dia):23, noche Dukascopy pre-2018:15 |
| US500 | H1 | 2015 | 192 | 540.0 | 5100.0 | hueco de historia (>1 dia):40, noche Dukascopy pre-2018:152 |
| US500 | H1 | 2016 | 249 | 540.0 | 4860.0 | hueco de historia (>1 dia):50, noche Dukascopy pre-2018:199 |
| US500 | H1 | 2017 | 249 | 540.0 | 4920.0 | hueco de historia (>1 dia):50, noche Dukascopy pre-2018:199 |
| US500 | H1 | 2018 | 69 | 600.0 | 4920.0 | hueco de historia (>1 dia):12, noche Dukascopy 2018:57 |
| US500 | H1 | 2019 | 1 | 120.0 | 120.0 | hueco real:1 |
| US500 | H1 | 2020 | 3 | 420.0 | 840.0 | hueco real:3 |
| US500 | H1 | 2025 | 1 | 360.0 | 360.0 | cierre temprano:1 |
| US500 | H4 | 2013 | 1 | 1920.0 | 1920.0 | hueco de historia (>1 dia):1 |
| US500 | H4 | 2014 | 16 | 720.0 | 4080.0 | hueco de historia (>1 dia):6, noche Dukascopy pre-2018:10 |
| US500 | H4 | 2015 | 192 | 480.0 | 5040.0 | hueco de historia (>1 dia):39, noche Dukascopy pre-2018:153 |
| US500 | H4 | 2016 | 249 | 480.0 | 4800.0 | hueco de historia (>1 dia):50, noche Dukascopy pre-2018:199 |
| US500 | H4 | 2017 | 248 | 480.0 | 4800.0 | hueco de historia (>1 dia):50, noche Dukascopy pre-2018:198 |
| US500 | H4 | 2018 | 69 | 480.0 | 4800.0 | hueco de historia (>1 dia):12, noche Dukascopy 2018:57 |
| US500 | H4 | 2020 | 1 | 720.0 | 720.0 | hueco real:1 |
| US30 | M15 | 2014 | 8 | 82.5 | 195.0 | noche Dukascopy pre-2018:8 |
| US30 | M15 | 2019 | 1 | 180.0 | 180.0 | hueco real:1 |
| US30 | M15 | 2020 | 6 | 82.5 | 120.0 | hueco real:6 |
| US30 | M15 | 2024 | 2 | 120.0 | 165.0 | hueco real:2 |
| US30 | M30 | 2014 | 2 | 165.0 | 180.0 | noche Dukascopy pre-2018:2 |
| US30 | M30 | 2019 | 1 | 150.0 | 150.0 | hueco real:1 |
| US30 | M30 | 2020 | 3 | 120.0 | 210.0 | hueco real:3 |
| US30 | M30 | 2024 | 1 | 150.0 | 150.0 | hueco real:1 |
| US30 | H1 | 2013 | 3 | 600.0 | 2220.0 | hueco de historia (>1 dia):1, noche Dukascopy pre-2018:2 |
| US30 | H1 | 2014 | 33 | 3000.0 | 4440.0 | hueco de historia (>1 dia):21, noche Dukascopy pre-2018:12 |
| US30 | H1 | 2015 | 182 | 540.0 | 5100.0 | hueco de historia (>1 dia):37, noche Dukascopy pre-2018:145 |
| US30 | H1 | 2016 | 252 | 540.0 | 4860.0 | hueco de historia (>1 dia):47, noche Dukascopy pre-2018:205 |
| US30 | H1 | 2017 | 251 | 540.0 | 4920.0 | hueco de historia (>1 dia):48, noche Dukascopy pre-2018:203 |
| US30 | H1 | 2018 | 69 | 600.0 | 4920.0 | hueco de historia (>1 dia):12, noche Dukascopy 2018:57 |
| US30 | H1 | 2019 | 1 | 120.0 | 120.0 | hueco real:1 |
| US30 | H1 | 2020 | 3 | 420.0 | 840.0 | hueco real:3 |
| US30 | H1 | 2024 | 1 | 120.0 | 120.0 | hueco real:1 |
| US30 | H1 | 2025 | 2 | 270.0 | 300.0 | cierre temprano:1, festivo:1 |
| US30 | H4 | 2013 | 2 | 1320.0 | 2160.0 | hueco de historia (>1 dia):1, noche Dukascopy pre-2018:1 |
| US30 | H4 | 2014 | 12 | 720.0 | 3840.0 | hueco de historia (>1 dia):5, noche Dukascopy pre-2018:7 |
| US30 | H4 | 2015 | 182 | 480.0 | 5040.0 | hueco de historia (>1 dia):37, noche Dukascopy pre-2018:145 |
| US30 | H4 | 2016 | 252 | 480.0 | 4800.0 | hueco de historia (>1 dia):47, noche Dukascopy pre-2018:205 |
| US30 | H4 | 2017 | 250 | 480.0 | 4800.0 | hueco de historia (>1 dia):48, noche Dukascopy pre-2018:202 |
| US30 | H4 | 2018 | 69 | 480.0 | 4800.0 | hueco de historia (>1 dia):12, noche Dukascopy 2018:57 |
| US30 | H4 | 2020 | 1 | 720.0 | 720.0 | hueco real:1 |

**Conclusion literal:** no es un error del control. Los cientos de huecos de H1/H4 en 2015-2018 son
noches sin datos de Dukascopy (~8-10 h); en 2018 persisten. Desde 2019-01-01 quedan 8 huecos en H1
y 1 en H4 (0,017 % y 0,008 %), por debajo del umbral de fallo. Por eso H1/H4 empiezan **2019-01-02**
y no 2018-01-02. M15/M30 empiezan en 2015-01-02 por `usable_from` (US100/US500/US30).

**Enmienda Y1.1:** `intraday_momentum_close_v2` queda excluida del plan por el fallo de
`fastbt._session_mask` con `flat_at` 15:55 en M15/M30/H1 (la posicion no se cierra en el dia).
No se modifica `fastbt.py` en EDGE-2.
## 2. Costes por activo y TF

Spread = mediana de medianas horarias y p75 de p75 horarias. Comision por lado. Swap = una noche
con modelo `historical` (peor lado, sin credito). Slippage = supuesto de `engine.yaml`. Stop = 2x ATR(14).
Cota enmendada de swap de indice: entre 0,8 y 7,3 bps/noche (1/3 a 3x la referencia CFD-006 ~2,44).

| Activo | TF | Cuenta | Spread med (bps) | Spread p75 (bps) | Comision/lado (bps) | Swap/noche (bps) | Slippage/lado (bps) | ATR(14) | Coste R |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| US100 | M15 | CFD-001 | 0.71 | 0.71 | 0.00 | 6.24 | 1.59 | 13.79 | 0.0888 |
| US100 | M15 | CFD-006 | 0.38 | 0.39 | 0.00 | 2.44 | 1.59 | 13.79 | 0.0813 |
| US100 | M30 | CFD-001 | 0.71 | 0.71 | 0.00 | 6.24 | 1.60 | 20.09 | 0.0609 |
| US100 | M30 | CFD-006 | 0.38 | 0.39 | 0.00 | 2.44 | 1.60 | 20.09 | 0.0558 |
| US100 | H1 | CFD-001 | 0.71 | 0.71 | 0.00 | 6.24 | 1.20 | 53.45 | 0.0243 |
| US100 | H1 | CFD-006 | 0.38 | 0.39 | 0.00 | 2.44 | 1.20 | 53.45 | 0.0217 |
| US100 | H4 | CFD-001 | 0.71 | 0.71 | 0.00 | 6.24 | 1.20 | 111.05 | 0.0117 |
| US100 | H4 | CFD-006 | 0.38 | 0.39 | 0.00 | 2.44 | 1.20 | 111.05 | 0.0104 |
| US500 | M15 | CFD-001 | 0.81 | 0.81 | 0.00 | 2.45 | 1.94 | 4.66 | 0.1298 |
| US500 | M15 | CFD-006 | 1.82 | 1.82 | 0.00 | 2.44 | 1.94 | 4.66 | 0.1575 |
| US500 | M30 | CFD-001 | 0.81 | 0.81 | 0.00 | 2.45 | 1.95 | 6.75 | 0.0896 |
| US500 | M30 | CFD-006 | 1.82 | 1.82 | 0.00 | 2.44 | 1.95 | 6.75 | 0.1087 |
| US500 | H1 | CFD-001 | 0.81 | 0.81 | 0.00 | 2.45 | 1.66 | 14.98 | 0.0416 |
| US500 | H1 | CFD-006 | 1.82 | 1.82 | 0.00 | 2.44 | 1.66 | 14.98 | 0.0516 |
| US500 | H4 | CFD-001 | 0.81 | 0.81 | 0.00 | 2.45 | 1.66 | 30.34 | 0.0205 |
| US500 | H4 | CFD-006 | 1.82 | 1.82 | 0.00 | 2.44 | 1.66 | 30.34 | 0.0255 |
| US30 | M15 | CFD-001 | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 41.14 | Sin datos |
| US30 | M15 | CFD-006 | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 41.14 | Sin datos |
| US30 | M30 | CFD-001 | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 59.50 | Sin datos |
| US30 | M30 | CFD-006 | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 59.50 | Sin datos |
| US30 | H1 | CFD-001 | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 134.41 | Sin datos |
| US30 | H1 | CFD-006 | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 134.41 | Sin datos |
| US30 | H4 | CFD-001 | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 273.04 | Sin datos |
| US30 | H4 | CFD-006 | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | 273.04 | Sin datos |

## 3. Cotas y bloqueos

- Swap US100: PASA (6.24, 2.44, 6.24, 2.44, 6.24, 2.44, 6.24, 2.44 bps/noche).
- Swap US500: PASA (2.45, 2.44, 2.45, 2.44, 2.45, 2.44, 2.45, 2.44 bps/noche).
- Swap US30: Sin datos.
- Spread US100 0,3-3 bps: PASA (0.71, 0.38, 0.71, 0.38, 0.71, 0.38, 0.71, 0.38).
- US30: spread Sin datos en `broker_spreads` y en `costs.measured.yaml`; **Sin datos**, queda fuera.

## 4. Viabilidad Y1 (cost_r <= 0,10)

Combinaciones viables: **18** de **24**.

| Plantilla | Activo | TF | cost_r | Cuenta peor |
|---|---|---|---:|---|
| trend_pullback_mtf | US100 | H4 | 0.0117 | CFD-001 |
| vol_squeeze_breakout | US100 | H4 | 0.0117 | CFD-001 |
| donchian_vol_h4 | US100 | H4 | 0.0117 | CFD-001 |
| trend_pullback_mtf | US100 | H1 | 0.0243 | CFD-001 |
| vol_squeeze_breakout | US100 | H1 | 0.0243 | CFD-001 |
| st_reversal_idx | US100 | H1 | 0.0243 | CFD-001 |
| trend_pullback_mtf | US500 | H4 | 0.0255 | CFD-006 |
| vol_squeeze_breakout | US500 | H4 | 0.0255 | CFD-006 |
| donchian_vol_h4 | US500 | H4 | 0.0255 | CFD-006 |
| trend_pullback_mtf | US500 | H1 | 0.0516 | CFD-006 |
| vol_squeeze_breakout | US500 | H1 | 0.0516 | CFD-006 |
| st_reversal_idx | US500 | H1 | 0.0516 | CFD-006 |
| trend_pullback_mtf | US100 | M30 | 0.0609 | CFD-001 |
| vol_squeeze_breakout | US100 | M30 | 0.0609 | CFD-001 |
| st_reversal_idx | US100 | M30 | 0.0609 | CFD-001 |
| trend_pullback_mtf | US100 | M15 | 0.0888 | CFD-001 |
| vol_squeeze_breakout | US100 | M15 | 0.0888 | CFD-001 |
| st_reversal_idx | US100 | M15 | 0.0888 | CFD-001 |
| trend_pullback_mtf | US500 | M30 | 0.1087 | CFD-006 |
| vol_squeeze_breakout | US500 | M30 | 0.1087 | CFD-006 |
| st_reversal_idx | US500 | M30 | 0.1087 | CFD-006 |
| trend_pullback_mtf | US500 | M15 | 0.1575 | CFD-006 |
| vol_squeeze_breakout | US500 | M15 | 0.1575 | CFD-006 |
| st_reversal_idx | US500 | M15 | 0.1575 | CFD-006 |

