# RESULTADO · R2i-b — onboarding multi-timeframe CFD-001 y CFD-006

Fecha: 2026-11-22. Solo lectura de costes ya medidos. Sin campañas, sin OOS, sin
push, sin aprobar/ejecutar nada. No se abrió ni attachó MT5.

## Método

- **R típico del TF** = mediana de ATR(14) sobre la historia Dukascopy desde
  `usable_from`. No es una señal ni un backtest; es una escala de riesgo.
- **Spread**: `spread_p75_price` del perfil de la cuenta, calculado desde
  `broker_spreads` (p75 de los p75 horarios). No se usa un spread fijo global.
- **Comisión**: por lote USD o % del volumen, convertida a unidades de precio
  (ida y vuelta; `per_side` = 2 lados, `round_turn` = 1).
- **Slippage**: `engine.yaml::assumed_slippage` por lado ×2.
- **Coste por operación** = spread + comisión + slippage ×2.
- **cost_R** = coste / R típico. **Viable** si `cost_R <= 0.10` y el TF está
  dentro de `usable_from`.
- Cobertura: se usa `usable_from` de **Dukascopy** para los 7×7 TF. Todos los TF
  de la tabla están dentro; el motivo "fuera de usable_from" no aparece.
- MT5: no se abrió sesión; no hay login que verificar antes/después. Los costes
  salen de `data/lab.db::broker_spreads` ya medidos. Si falta un spread, la fila
  queda "Sin datos".

## Tabla cuenta × símbolo × TF

## Coste por operación frente al R típico

R típico = mediana de ATR(14) del TF en Dukascopy desde `usable_from`.
Coste = spread p75 + comisión (ida/vuelta) + slippage asumido ×2.
Viable si `cost_R <= 0.10` y el TF está dentro de `usable_from`.

| Cuenta | Símbolo | TF | usable_from | R típico | Coste | cost_R | Viable | Motivo |
|---|---|---|---|---:|---:|---:|---|---|
| CFD-001 | US100 | M1 | 2018-01-02 | 4.340571 | 3.945476 | 0.909 | no | cost_R 0.9090 > 0.10 |
| CFD-001 | US100 | M5 | 2018-01-02 | 10.508643 | 3.945476 | 0.3755 | no | cost_R 0.3755 > 0.10 |
| CFD-001 | US100 | M15 | 2015-01-02 | 15.486786 | 3.945476 | 0.2548 | no | cost_R 0.2548 > 0.10 |
| CFD-001 | US100 | M30 | 2015-01-02 | 23.155143 | 3.945476 | 0.1704 | no | cost_R 0.1704 > 0.10 |
| CFD-001 | US100 | H1 | 2018-01-02 | 43.7755 | 3.945476 | 0.0901 | SÍ | OK |
| CFD-001 | US100 | H4 | 2019-01-01 | 98.004714 | 3.945476 | 0.0403 | SÍ | OK |
| CFD-001 | US100 | D1 | 2014-01-01 | 188.9525 | 3.945476 | 0.0209 | SÍ | OK |
| CFD-001 | XAUUSD | M1 | 2005-01-02 | 0.426929 | 0.74956 | 1.7557 | no | cost_R 1.7557 > 0.10 |
| CFD-001 | XAUUSD | M5 | 2005-01-02 | 0.948286 | 0.74947 | 0.7903 | no | cost_R 0.7903 > 0.10 |
| CFD-001 | XAUUSD | M15 | 2005-01-02 | 1.605357 | 0.749459 | 0.4668 | no | cost_R 0.4668 > 0.10 |
| CFD-001 | XAUUSD | M30 | 2004-01-01 | 2.252286 | 0.749241 | 0.3327 | no | cost_R 0.3327 > 0.10 |
| CFD-001 | XAUUSD | H1 | 2005-01-02 | 3.430214 | 0.749454 | 0.2185 | no | cost_R 0.2185 > 0.10 |
| CFD-001 | XAUUSD | H4 | 2004-01-01 | 6.976643 | 0.749303 | 0.1074 | no | cost_R 0.1074 > 0.10 |
| CFD-001 | XAUUSD | D1 | 2003-05-04 | 18.602 | 0.749105 | 0.0403 | SÍ | OK |
| CFD-001 | EURUSD | M1 | 2003-05-04 | 0.000201 | 0.00017 | 0.847 | no | cost_R 0.8470 > 0.10 |
| CFD-001 | EURUSD | M5 | 2003-05-04 | 0.000485 | 0.00017 | 0.3505 | no | cost_R 0.3505 > 0.10 |
| CFD-001 | EURUSD | M15 | 2003-05-04 | 0.000839 | 0.00017 | 0.2026 | no | cost_R 0.2026 > 0.10 |
| CFD-001 | EURUSD | M30 | 2003-05-04 | 0.001187 | 0.00017 | 0.1432 | no | cost_R 0.1432 > 0.10 |
| CFD-001 | EURUSD | H1 | 2003-05-04 | 0.00169 | 0.00017 | 0.1006 | no | cost_R 0.1006 > 0.10 |
| CFD-001 | EURUSD | H4 | 2003-05-04 | 0.003496 | 0.00017 | 0.0486 | SÍ | OK |
| CFD-001 | EURUSD | D1 | 2003-05-04 | 0.009345 | 0.00017 | 0.0182 | SÍ | OK |
| CFD-001 | GBPUSD | M1 | 2003-05-04 | 0.000215 | 0.00022 | 1.0233 | no | cost_R 1.0233 > 0.10 |
| CFD-001 | GBPUSD | M5 | 2003-05-04 | 0.00055 | 0.00022 | 0.4 | no | cost_R 0.4000 > 0.10 |
| CFD-001 | GBPUSD | M15 | 2003-05-04 | 0.001002 | 0.00022 | 0.2195 | no | cost_R 0.2195 > 0.10 |
| CFD-001 | GBPUSD | M30 | 2003-05-04 | 0.001457 | 0.00022 | 0.151 | no | cost_R 0.1510 > 0.10 |
| CFD-001 | GBPUSD | H1 | 2003-05-04 | 0.002118 | 0.00022 | 0.1039 | no | cost_R 0.1039 > 0.10 |
| CFD-001 | GBPUSD | H4 | 2003-05-04 | 0.004415 | 0.00022 | 0.0498 | SÍ | OK |
| CFD-001 | GBPUSD | D1 | 2003-05-04 | 0.011791 | 0.00022 | 0.0187 | SÍ | OK |
| CFD-001 | USDJPY | M1 | 2003-05-04 | 0.018571 | 0.017296 | 0.9313 | no | cost_R 0.9313 > 0.10 |
| CFD-001 | USDJPY | M5 | 2003-05-04 | 0.046714 | 0.017296 | 0.3703 | no | cost_R 0.3703 > 0.10 |
| CFD-001 | USDJPY | M15 | 2003-05-04 | 0.083929 | 0.017296 | 0.2061 | no | cost_R 0.2061 > 0.10 |
| CFD-001 | USDJPY | M30 | 2003-05-04 | 0.120714 | 0.017296 | 0.1433 | no | cost_R 0.1433 > 0.10 |
| CFD-001 | USDJPY | H1 | 2003-05-04 | 0.173286 | 0.017296 | 0.0998 | SÍ | OK |
| CFD-001 | USDJPY | H4 | 2003-05-04 | 0.3585 | 0.017296 | 0.0482 | SÍ | OK |
| CFD-001 | USDJPY | D1 | 2003-05-04 | 0.923214 | 0.017296 | 0.0187 | SÍ | OK |
| CFD-006 | US100 | M1 | 2018-01-02 | 4.340571 | 4.097528 | 0.944 | no | cost_R 0.9440 > 0.10 |
| CFD-006 | US100 | M5 | 2018-01-02 | 10.508643 | 4.097528 | 0.3899 | no | cost_R 0.3899 > 0.10 |
| CFD-006 | US100 | M15 | 2015-01-02 | 15.486786 | 4.097528 | 0.2646 | no | cost_R 0.2646 > 0.10 |
| CFD-006 | US100 | M30 | 2015-01-02 | 23.155143 | 4.097528 | 0.177 | no | cost_R 0.1770 > 0.10 |
| CFD-006 | US100 | H1 | 2018-01-02 | 43.7755 | 4.097528 | 0.0936 | SÍ | OK |
| CFD-006 | US100 | H4 | 2019-01-01 | 98.004714 | 4.097528 | 0.0418 | SÍ | OK |
| CFD-006 | US100 | D1 | 2014-01-01 | 188.9525 | 4.097528 | 0.0217 | SÍ | OK |
| CFD-006 | US500 | M1 | 2018-01-02 | 1.0135 | 2.282791 | 2.2524 | no | cost_R 2.2524 > 0.10 |
| CFD-006 | US500 | M5 | 2018-01-02 | 2.421357 | 2.282791 | 0.9428 | no | cost_R 0.9428 > 0.10 |
| CFD-006 | US500 | M15 | 2015-01-02 | 3.833857 | 2.282791 | 0.5954 | no | cost_R 0.5954 > 0.10 |
| CFD-006 | US500 | M30 | 2015-01-02 | 5.655714 | 2.282791 | 0.4036 | no | cost_R 0.4036 > 0.10 |
| CFD-006 | US500 | H1 | 2018-01-02 | 9.735357 | 2.282791 | 0.2345 | no | cost_R 0.2345 > 0.10 |
| CFD-006 | US500 | H4 | 2019-01-01 | 21.6935 | 2.282791 | 0.1052 | no | cost_R 0.1052 > 0.10 |
| CFD-006 | US500 | D1 | 2018-01-01 | 57.916714 | 2.282791 | 0.0394 | SÍ | OK |
| CFD-006 | US30 | M1 | 2018-01-02 | 7.607357 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | M5 | 2015-01-02 | 16.265714 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | M15 | 2015-01-02 | 29.929071 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | M30 | 2015-01-02 | 44.143143 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | H1 | 2018-01-02 | 75.583143 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | H4 | 2019-01-01 | 160.962286 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | D1 | 2015-01-01 | 379.836429 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | XAUUSD | M1 | 2005-01-02 | 0.426929 | 0.68961 | 1.6153 | no | cost_R 1.6153 > 0.10 |
| CFD-006 | XAUUSD | M5 | 2005-01-02 | 0.948286 | 0.68961 | 0.7272 | no | cost_R 0.7272 > 0.10 |
| CFD-006 | XAUUSD | M15 | 2005-01-02 | 1.605357 | 0.68961 | 0.4296 | no | cost_R 0.4296 > 0.10 |
| CFD-006 | XAUUSD | M30 | 2004-01-01 | 2.252286 | 0.68961 | 0.3062 | no | cost_R 0.3062 > 0.10 |
| CFD-006 | XAUUSD | H1 | 2005-01-02 | 3.430214 | 0.68961 | 0.201 | no | cost_R 0.2010 > 0.10 |
| CFD-006 | XAUUSD | H4 | 2004-01-01 | 6.976643 | 0.68961 | 0.0988 | SÍ | OK |
| CFD-006 | XAUUSD | D1 | 2003-05-04 | 18.602 | 0.68961 | 0.0371 | SÍ | OK |
| CFD-006 | EURUSD | M1 | 2003-05-04 | 0.000201 | 0.00022 | 1.0961 | no | cost_R 1.0961 > 0.10 |
| CFD-006 | EURUSD | M5 | 2003-05-04 | 0.000485 | 0.00022 | 0.4536 | no | cost_R 0.4536 > 0.10 |
| CFD-006 | EURUSD | M15 | 2003-05-04 | 0.000839 | 0.00022 | 0.2621 | no | cost_R 0.2621 > 0.10 |
| CFD-006 | EURUSD | M30 | 2003-05-04 | 0.001187 | 0.00022 | 0.1853 | no | cost_R 0.1853 > 0.10 |
| CFD-006 | EURUSD | H1 | 2003-05-04 | 0.00169 | 0.00022 | 0.1302 | no | cost_R 0.1302 > 0.10 |
| CFD-006 | EURUSD | H4 | 2003-05-04 | 0.003496 | 0.00022 | 0.0629 | SÍ | OK |
| CFD-006 | EURUSD | D1 | 2003-05-04 | 0.009345 | 0.00022 | 0.0235 | SÍ | OK |
| CFD-006 | GBPUSD | M1 | 2003-05-04 | 0.000215 | 0.00025 | 1.1628 | no | cost_R 1.1628 > 0.10 |
| CFD-006 | GBPUSD | M5 | 2003-05-04 | 0.00055 | 0.00025 | 0.4545 | no | cost_R 0.4545 > 0.10 |
| CFD-006 | GBPUSD | M15 | 2003-05-04 | 0.001002 | 0.00025 | 0.2495 | no | cost_R 0.2495 > 0.10 |
| CFD-006 | GBPUSD | M30 | 2003-05-04 | 0.001457 | 0.00025 | 0.1716 | no | cost_R 0.1716 > 0.10 |
| CFD-006 | GBPUSD | H1 | 2003-05-04 | 0.002118 | 0.00025 | 0.118 | no | cost_R 0.1180 > 0.10 |
| CFD-006 | GBPUSD | H4 | 2003-05-04 | 0.004415 | 0.00025 | 0.0566 | SÍ | OK |
| CFD-006 | GBPUSD | D1 | 2003-05-04 | 0.011791 | 0.00025 | 0.0212 | SÍ | OK |
| CFD-006 | USDJPY | M1 | 2003-05-04 | 0.018571 | 0.015083 | 0.8122 | no | cost_R 0.8122 > 0.10 |
| CFD-006 | USDJPY | M5 | 2003-05-04 | 0.046714 | 0.015083 | 0.3229 | no | cost_R 0.3229 > 0.10 |
| CFD-006 | USDJPY | M15 | 2003-05-04 | 0.083929 | 0.015083 | 0.1797 | no | cost_R 0.1797 > 0.10 |
| CFD-006 | USDJPY | M30 | 2003-05-04 | 0.120714 | 0.015083 | 0.1249 | no | cost_R 0.1249 > 0.10 |
| CFD-006 | USDJPY | H1 | 2003-05-04 | 0.173286 | 0.015083 | 0.087 | SÍ | OK |
| CFD-006 | USDJPY | H4 | 2003-05-04 | 0.3585 | 0.015083 | 0.0421 | SÍ | OK |
| CFD-006 | USDJPY | D1 | 2003-05-04 | 0.923214 | 0.015083 | 0.0163 | SÍ | OK |

## FTMO vs FundingPips

Solo símbolos permitidos por ambas cuentas (US100, XAUUSD, EURUSD, GBPUSD,
USDJPY). US500 y US30 no los permite CFD-001; US30 no tiene spread medido en
CFD-006.

| Símbolo | TF | cost_R CFD-001 (FTMO) | cost_R CFD-006 (FundingPips) | Más barata | Delta |
|---|---|---:|---:|---|---:|
| US100 | M1 | 0.9090 | 0.9440 | CFD-001 | 0.0350 |
| US100 | M5 | 0.3755 | 0.3899 | CFD-001 | 0.0145 |
| US100 | M15 | 0.2548 | 0.2646 | CFD-001 | 0.0098 |
| US100 | M30 | 0.1704 | 0.1770 | CFD-001 | 0.0066 |
| US100 | H1 | 0.0901 | 0.0936 | CFD-001 | 0.0035 |
| US100 | H4 | 0.0403 | 0.0418 | CFD-001 | 0.0016 |
| US100 | D1 | 0.0209 | 0.0217 | CFD-001 | 0.0008 |
| XAUUSD | M1 | 1.7557 | 1.6153 | CFD-006 | 0.1404 |
| XAUUSD | M5 | 0.7903 | 0.7272 | CFD-006 | 0.0631 |
| XAUUSD | M15 | 0.4668 | 0.4296 | CFD-006 | 0.0373 |
| XAUUSD | M30 | 0.3327 | 0.3062 | CFD-006 | 0.0265 |
| XAUUSD | H1 | 0.2185 | 0.2010 | CFD-006 | 0.0174 |
| XAUUSD | H4 | 0.1074 | 0.0988 | CFD-006 | 0.0086 |
| XAUUSD | D1 | 0.0403 | 0.0371 | CFD-006 | 0.0032 |
| EURUSD | M1 | 0.8470 | 1.0961 | CFD-001 | 0.2491 |
| EURUSD | M5 | 0.3505 | 0.4536 | CFD-001 | 0.1031 |
| EURUSD | M15 | 0.2026 | 0.2621 | CFD-001 | 0.0596 |
| EURUSD | M30 | 0.1432 | 0.1853 | CFD-001 | 0.0421 |
| EURUSD | H1 | 0.1006 | 0.1302 | CFD-001 | 0.0296 |
| EURUSD | H4 | 0.0486 | 0.0629 | CFD-001 | 0.0143 |
| EURUSD | D1 | 0.0182 | 0.0235 | CFD-001 | 0.0054 |
| GBPUSD | M1 | 1.0233 | 1.1628 | CFD-001 | 0.1395 |
| GBPUSD | M5 | 0.4000 | 0.4545 | CFD-001 | 0.0545 |
| GBPUSD | M15 | 0.2195 | 0.2495 | CFD-001 | 0.0299 |
| GBPUSD | M30 | 0.1510 | 0.1716 | CFD-001 | 0.0206 |
| GBPUSD | H1 | 0.1039 | 0.1180 | CFD-001 | 0.0142 |
| GBPUSD | H4 | 0.0498 | 0.0566 | CFD-001 | 0.0068 |
| GBPUSD | D1 | 0.0187 | 0.0212 | CFD-001 | 0.0025 |
| USDJPY | M1 | 0.9313 | 0.8122 | CFD-006 | 0.1192 |
| USDJPY | M5 | 0.3703 | 0.3229 | CFD-006 | 0.0474 |
| USDJPY | M15 | 0.2061 | 0.1797 | CFD-006 | 0.0264 |
| USDJPY | M30 | 0.1433 | 0.1249 | CFD-006 | 0.0183 |
| USDJPY | H1 | 0.0998 | 0.0870 | CFD-006 | 0.0128 |
| USDJPY | H4 | 0.0482 | 0.0421 | CFD-006 | 0.0062 |
| USDJPY | D1 | 0.0187 | 0.0163 | CFD-006 | 0.0024 |

## Resumen

## Viables por cuenta

- **CFD-001**: 11 viables — US100 H1, US100 H4, US100 D1, XAUUSD D1, EURUSD H4, EURUSD D1, GBPUSD H4, GBPUSD D1, USDJPY H1, USDJPY H4, USDJPY D1
- **CFD-006**: 13 viables — US100 H1, US100 H4, US100 D1, US500 D1, XAUUSD H4, XAUUSD D1, EURUSD H4, EURUSD D1, GBPUSD H4, GBPUSD D1, USDJPY H1, USDJPY H4, USDJPY D1

## Viables por TF

- **M1**: ninguna
- **M5**: ninguna
- **M15**: ninguna
- **M30**: ninguna
- **H1**: CFD-001 US100, CFD-001 USDJPY, CFD-006 US100, CFD-006 USDJPY
- **H4**: CFD-001 US100, CFD-001 EURUSD, CFD-001 GBPUSD, CFD-001 USDJPY, CFD-006 US100, CFD-006 XAUUSD, CFD-006 EURUSD, CFD-006 GBPUSD, CFD-006 USDJPY
- **D1**: CFD-001 US100, CFD-001 XAUUSD, CFD-001 EURUSD, CFD-001 GBPUSD, CFD-001 USDJPY, CFD-006 US100, CFD-006 US500, CFD-006 XAUUSD, CFD-006 EURUSD, CFD-006 GBPUSD, CFD-006 USDJPY

- **CFD-001 (FTMO)**: 11 viables de 35 celdas (5 símbolos × 7 TF).
- **CFD-006 (FundingPips)**: 13 viables de 49 celdas (7 símbolos × 7 TF).
- **M1-M30**: ninguna viable en ninguna cuenta; el coste supera 0.10 R.
- **H1**: viables US100 y USDJPY en ambas cuentas.
- **H4**: viables US100, EURUSD, GBPUSD y USDJPY en ambas; XAUUSD solo en
  CFD-006. XAUUSD H4 CFD-001 queda en 0.1074 > 0.10.
- **D1**: viables todos los símbolos permitidos; US500 D1 solo CFD-006.
- **Más barata por símbolo**: US100, EURUSD y GBPUSD → CFD-001; XAUUSD y USDJPY
  → CFD-006. En US100 la diferencia es pequeña (0.0901 vs 0.0936 en H1).
- **US30 CFD-006**: Sin datos; no hay `broker_spreads[broker:CFD-006]` para
  DJI30. No se inventa ni se mide en esta tarea.
- **US500 CFD-001 / US30 CFD-001**: no permitidos por la cuenta.

## Ficheros y tests

- `src/tradinglab/propfund/onboarding_mtf.py`: cálculo puro de comisión,
  coste, cost_R, ATR típico y tabla.
- `lab propfund onboarding-mtf [--accounts ...] [--write ruta]`: comando de
  solo lectura; imprime la tabla y opcionalmente escribe el Markdown.
- `tests/test_propfund_onboarding_mtf.py`: comisión por lote/porcentaje/cero,
  contrato ausente, cost_R viable/no viable, fuera de usable_from y ATR
  sintético.
- No se modificó ningún umbral (`max_cost_r` de la cuenta sigue en 0.20; el
  corte de esta tabla es el 0.10 pedido).

## Cierre

`git status --short`:

```text
?? tl2-edge-map.patch
```

`git log --oneline -5`:

```text
d94e625 tl2: R2i-b - onboarding multi-timeframe
8a121d0 tl2: R2j-b - calendario completo, tramos y usable_from
06ecf30 tl2: R2j - calendarios por instrumento
1a5049d merge: principal (R2g + R2g-fix) en integración
cb5417d tl2: R2g - huecos de fin de semana por calendario
```

- `pytest -q`: **1608 passed, 1 skipped (1105,53 s; 1 warning psutil)**.
- `ruff check src/tradinglab/propfund src/tradinglab/cli.py tests`: **limpio**.
- `lab propfund verify`: **OK en ai_trader (17), ea_us100_ftmo1 (18), ftmo_forward (8) y ftmo_risk (14)**.
- `count_tests`: **1676**.
- Tag `tl2-r2i-b` → `d94e625`.

## Aviso

- No se attachó MT5: la tarea pedía costes de lo ya medido y así se hizo. Si se
  quiere cubrir US30 CFD-006, hace falta una medición de spreads aparte.
- El R típico es ATR(14), no el stop de una estrategia concreta; cambia el
  cost_R absoluto si se usa otro R, pero no la comparación relativa.
- No se ejecutaron campañas ni se leyó OOS-1/OOS-2. No se hizo push.

## Siguiente

T3.
