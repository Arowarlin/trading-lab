# RESULTADO · R2k — arreglos antes de la primera campaña

Fecha: 2026-11-22. Sin campañas (ni borrador), sin approve/run/confirm/supersede,
sin OOS, sin push, sin tareas programadas, sin borrar y sin cambiar umbrales.

## Hecho

- Test de ruido: 30/30 ejecuciones limpias; no se relajó el test ni ningún umbral.
- `R típico` corregido a **últimos 12 meses** (ATR 14 y ATR % del precio).
- Una sola función `cost_r_for` para el cribado cuenta×símbolo×TF; `suggest`
  muestra la columna de cribado y la de operaciones, y la factibilidad sigue
  usando la mediana de `trade.r_cost` de las operaciones reales.
- `preflight --spec` y `feasibility --spec`: funcionan sin registrar campaña.
- Compatibilidad plantilla × TF declarada en `valid_timeframes`; asia H4/D1
  quedan fuera y suggest/preflight las rechazan.
- Propuestas rehechas con 3 familias distintas en `.orquestador/PROPUESTAS-campanas.md`.
- Commit `043e979` · `tl2: R2k - arreglos previos a campaña`.
- Tag `tl2-r2k`.

## 1. Test inestable (30 ejecuciones)

- Método: 2 tandas de 15, `pytest -q -p no:randomly tests/test_discovery_noise_full.py
  -k never_level4`, `--basetemp` distinto por ejecución; el test usa semilla 2.
- Resultado: **30 PASS / 30, 0 FAIL**. No se cambió el test ni se tocó ningún
  umbral.
- El único fallo histórico (suite R2j-b) fue `mark_done` sin encontrar
  `noise-full-1y`, sin excepción en `register_synthetic`/`run_campaign`; no se
  reprodujo. Es compatible con interferencia de la ejecución de pytest
  interrumpida/tmp_path, no con que el ruido llegue a nivel 4. No hay evidencia
  de agujero estadístico y no se aplicó ningún parche a ciegas.
- En la suite completa apareció otro no-determinismo de reloj:
  `test_web_discovery` insertaba un trial con fecha fija 2026-11-18; al cruzar
  a lunes UTC quedaba en la semana ISO anterior. Se corrigió el fixture para
  usar la semana ISO actual. No es un umbral ni un cambio de producción.

## 2. R típico corregido (últimos 12 meses)

Definición nueva: mediana de ATR(14) sobre los últimos 12 meses de Dukascopy
(o desde `usable_from` si es posterior), con ATR en % del precio. El coste sigue
siendo spread p75 + comisión ida/vuelta + slippage asumido ×2.

### Celdas que cambian de viable (12, todas no → SÍ)

| Cuenta | Símbolo | TF | Antes viable | Ahora viable | cost_R antes | cost_R ahora |
|---|---|---|---|---|---:|---:|
| CFD-001 | US100 | M15 | no | SÍ | 0.2548 | 0.0925 |
| CFD-001 | US100 | M30 | no | SÍ | 0.1704 | 0.0630 |
| CFD-001 | XAUUSD | M15 | no | SÍ | 0.4668 | 0.0914 |
| CFD-001 | XAUUSD | M30 | no | SÍ | 0.3327 | 0.0630 |
| CFD-001 | XAUUSD | H1 | no | SÍ | 0.2185 | 0.0431 |
| CFD-001 | XAUUSD | H4 | no | SÍ | 0.1074 | 0.0209 |
| CFD-006 | US100 | M15 | no | SÍ | 0.2646 | 0.0961 |
| CFD-006 | US100 | M30 | no | SÍ | 0.1770 | 0.0654 |
| CFD-006 | US500 | H4 | no | SÍ | 0.1052 | 0.0724 |
| CFD-006 | XAUUSD | M15 | no | SÍ | 0.4296 | 0.0795 |
| CFD-006 | XAUUSD | M30 | no | SÍ | 0.3062 | 0.0548 |
| CFD-006 | XAUUSD | H1 | no | SÍ | 0.2010 | 0.0375 |

### Tabla recalculada 2 cuentas × símbolos × 7 TF

| Cuenta | Símbolo | TF | usable_from | R típico | ATR % precio | Coste | cost_R | Viable | Motivo |
|---|---|---|---|---:|---:|---:|---:|---|---|
| CFD-001 | US100 | M1 | 2018-01-02 | 9.758714 | 0.035 | 3.945476 | 0.4043 | no | cost_R 0.4043 > 0.10 |
| CFD-001 | US100 | M5 | 2018-01-02 | 23.153214 | 0.082 | 3.945476 | 0.1704 | no | cost_R 0.1704 > 0.10 |
| CFD-001 | US100 | M15 | 2015-01-02 | 42.658429 | 0.152 | 3.945476 | 0.0925 | SÍ | OK |
| CFD-001 | US100 | M30 | 2015-01-02 | 62.644214 | 0.223 | 3.945476 | 0.063 | SÍ | OK |
| CFD-001 | US100 | H1 | 2018-01-02 | 91.168071 | 0.324 | 3.945476 | 0.0433 | SÍ | OK |
| CFD-001 | US100 | H4 | 2019-01-01 | 185.744286 | 0.66 | 3.945476 | 0.0212 | SÍ | OK |
| CFD-001 | US100 | D1 | 2014-01-01 | 505.215036 | 1.799 | 3.945476 | 0.0078 | SÍ | OK |
| CFD-001 | XAUUSD | M1 | 2005-01-02 | 2.013571 | 0.046 | 0.792437 | 0.3935 | no | cost_R 0.3935 > 0.10 |
| CFD-001 | XAUUSD | M5 | 2005-01-02 | 4.802857 | 0.109 | 0.792438 | 0.165 | no | cost_R 0.1650 > 0.10 |
| CFD-001 | XAUUSD | M15 | 2005-01-02 | 8.669643 | 0.197 | 0.792438 | 0.0914 | SÍ | OK |
| CFD-001 | XAUUSD | M30 | 2004-01-01 | 12.586429 | 0.287 | 0.792433 | 0.063 | SÍ | OK |
| CFD-001 | XAUUSD | H1 | 2005-01-02 | 18.389571 | 0.419 | 0.792424 | 0.0431 | SÍ | OK |
| CFD-001 | XAUUSD | H4 | 2004-01-01 | 37.915321 | 0.864 | 0.792413 | 0.0209 | SÍ | OK |
| CFD-001 | XAUUSD | D1 | 2003-05-04 | 101.849393 | 2.327 | 0.792248 | 0.0078 | SÍ | OK |
| CFD-001 | EURUSD | M1 | 2003-05-04 | 0.000113 | 0.01 | 0.00017 | 1.5063 | no | cost_R 1.5063 > 0.10 |
| CFD-001 | EURUSD | M5 | 2003-05-04 | 0.000276 | 0.024 | 0.00017 | 0.615 | no | cost_R 0.6150 > 0.10 |
| CFD-001 | EURUSD | M15 | 2003-05-04 | 0.000503 | 0.043 | 0.00017 | 0.3381 | no | cost_R 0.3381 > 0.10 |
| CFD-001 | EURUSD | M30 | 2003-05-04 | 0.000742 | 0.064 | 0.00017 | 0.2291 | no | cost_R 0.2291 > 0.10 |
| CFD-001 | EURUSD | H1 | 2003-05-04 | 0.001079 | 0.093 | 0.00017 | 0.1576 | no | cost_R 0.1576 > 0.10 |
| CFD-001 | EURUSD | H4 | 2003-05-04 | 0.002262 | 0.195 | 0.00017 | 0.0751 | SÍ | OK |
| CFD-001 | EURUSD | D1 | 2003-05-04 | 0.006042 | 0.521 | 0.00017 | 0.0281 | SÍ | OK |
| CFD-001 | GBPUSD | M1 | 2003-05-04 | 0.000149 | 0.011 | 0.00022 | 1.4737 | no | cost_R 1.4737 > 0.10 |
| CFD-001 | GBPUSD | M5 | 2003-05-04 | 0.000368 | 0.027 | 0.00022 | 0.5981 | no | cost_R 0.5981 > 0.10 |
| CFD-001 | GBPUSD | M15 | 2003-05-04 | 0.000661 | 0.049 | 0.00022 | 0.3326 | no | cost_R 0.3326 > 0.10 |
| CFD-001 | GBPUSD | M30 | 2003-05-04 | 0.000963 | 0.072 | 0.00022 | 0.2285 | no | cost_R 0.2285 > 0.10 |
| CFD-001 | GBPUSD | H1 | 2003-05-04 | 0.001414 | 0.105 | 0.00022 | 0.1556 | no | cost_R 0.1556 > 0.10 |
| CFD-001 | GBPUSD | H4 | 2003-05-04 | 0.002939 | 0.219 | 0.00022 | 0.0749 | SÍ | OK |
| CFD-001 | GBPUSD | D1 | 2003-05-04 | 0.007778 | 0.58 | 0.00022 | 0.0283 | SÍ | OK |
| CFD-001 | USDJPY | M1 | 2003-05-04 | 0.017143 | 0.011 | 0.017296 | 1.0089 | no | cost_R 1.0089 > 0.10 |
| CFD-001 | USDJPY | M5 | 2003-05-04 | 0.043643 | 0.028 | 0.017296 | 0.3963 | no | cost_R 0.3963 > 0.10 |
| CFD-001 | USDJPY | M15 | 2003-05-04 | 0.081429 | 0.051 | 0.017296 | 0.2124 | no | cost_R 0.2124 > 0.10 |
| CFD-001 | USDJPY | M30 | 2003-05-04 | 0.120571 | 0.076 | 0.017296 | 0.1435 | no | cost_R 0.1435 > 0.10 |
| CFD-001 | USDJPY | H1 | 2003-05-04 | 0.176071 | 0.111 | 0.017296 | 0.0982 | SÍ | OK |
| CFD-001 | USDJPY | H4 | 2003-05-04 | 0.372286 | 0.235 | 0.017296 | 0.0465 | SÍ | OK |
| CFD-001 | USDJPY | D1 | 2003-05-04 | 1.018964 | 0.644 | 0.017296 | 0.017 | SÍ | OK |
| CFD-006 | US100 | M1 | 2018-01-02 | 9.758714 | 0.035 | 4.097528 | 0.4199 | no | cost_R 0.4199 > 0.10 |
| CFD-006 | US100 | M5 | 2018-01-02 | 23.153214 | 0.082 | 4.097528 | 0.177 | no | cost_R 0.1770 > 0.10 |
| CFD-006 | US100 | M15 | 2015-01-02 | 42.658429 | 0.152 | 4.097528 | 0.0961 | SÍ | OK |
| CFD-006 | US100 | M30 | 2015-01-02 | 62.644214 | 0.223 | 4.097528 | 0.0654 | SÍ | OK |
| CFD-006 | US100 | H1 | 2018-01-02 | 91.168071 | 0.324 | 4.097528 | 0.0449 | SÍ | OK |
| CFD-006 | US100 | H4 | 2019-01-01 | 185.744286 | 0.66 | 4.097528 | 0.0221 | SÍ | OK |
| CFD-006 | US100 | D1 | 2014-01-01 | 505.215036 | 1.799 | 4.097528 | 0.0081 | SÍ | OK |
| CFD-006 | US500 | M1 | 2018-01-02 | 1.604357 | 0.022 | 2.282791 | 1.4229 | no | cost_R 1.4229 > 0.10 |
| CFD-006 | US500 | M5 | 2018-01-02 | 3.855071 | 0.052 | 2.282791 | 0.5922 | no | cost_R 0.5922 > 0.10 |
| CFD-006 | US500 | M15 | 2015-01-02 | 7.080286 | 0.096 | 2.282791 | 0.3224 | no | cost_R 0.3224 > 0.10 |
| CFD-006 | US500 | M30 | 2015-01-02 | 10.442429 | 0.141 | 2.282791 | 0.2186 | no | cost_R 0.2186 > 0.10 |
| CFD-006 | US500 | H1 | 2018-01-02 | 15.309571 | 0.207 | 2.282791 | 0.1491 | no | cost_R 0.1491 > 0.10 |
| CFD-006 | US500 | H4 | 2019-01-01 | 31.543143 | 0.427 | 2.282791 | 0.0724 | SÍ | OK |
| CFD-006 | US500 | D1 | 2018-01-01 | 82.209393 | 1.115 | 2.282791 | 0.0278 | SÍ | OK |
| CFD-006 | US30 | M1 | 2018-01-02 | 10.642857 | 0.021 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | M5 | 2015-01-02 | 25.632857 | 0.051 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | M15 | 2015-01-02 | 47.515429 | 0.094 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | M30 | 2015-01-02 | 71.346429 | 0.142 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | H1 | 2018-01-02 | 106.19 | 0.211 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | H4 | 2019-01-01 | 220.711143 | 0.439 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | US30 | D1 | 2015-01-01 | 598.776214 | 1.193 | Sin datos | Sin datos | no | Sin datos: spread p75 |
| CFD-006 | XAUUSD | M1 | 2005-01-02 | 2.013571 | 0.046 | 0.68961 | 0.3425 | no | cost_R 0.3425 > 0.10 |
| CFD-006 | XAUUSD | M5 | 2005-01-02 | 4.802857 | 0.109 | 0.68961 | 0.1436 | no | cost_R 0.1436 > 0.10 |
| CFD-006 | XAUUSD | M15 | 2005-01-02 | 8.669643 | 0.197 | 0.68961 | 0.0795 | SÍ | OK |
| CFD-006 | XAUUSD | M30 | 2004-01-01 | 12.586429 | 0.287 | 0.68961 | 0.0548 | SÍ | OK |
| CFD-006 | XAUUSD | H1 | 2005-01-02 | 18.389571 | 0.419 | 0.68961 | 0.0375 | SÍ | OK |
| CFD-006 | XAUUSD | H4 | 2004-01-01 | 37.915321 | 0.864 | 0.68961 | 0.0182 | SÍ | OK |
| CFD-006 | XAUUSD | D1 | 2003-05-04 | 101.849393 | 2.327 | 0.68961 | 0.0068 | SÍ | OK |
| CFD-006 | EURUSD | M1 | 2003-05-04 | 0.000113 | 0.01 | 0.00022 | 1.9494 | no | cost_R 1.9494 > 0.10 |
| CFD-006 | EURUSD | M5 | 2003-05-04 | 0.000276 | 0.024 | 0.00022 | 0.7959 | no | cost_R 0.7959 > 0.10 |
| CFD-006 | EURUSD | M15 | 2003-05-04 | 0.000503 | 0.043 | 0.00022 | 0.4375 | no | cost_R 0.4375 > 0.10 |
| CFD-006 | EURUSD | M30 | 2003-05-04 | 0.000742 | 0.064 | 0.00022 | 0.2964 | no | cost_R 0.2964 > 0.10 |
| CFD-006 | EURUSD | H1 | 2003-05-04 | 0.001079 | 0.093 | 0.00022 | 0.2039 | no | cost_R 0.2039 > 0.10 |
| CFD-006 | EURUSD | H4 | 2003-05-04 | 0.002262 | 0.195 | 0.00022 | 0.0973 | SÍ | OK |
| CFD-006 | EURUSD | D1 | 2003-05-04 | 0.006042 | 0.521 | 0.00022 | 0.0364 | SÍ | OK |
| CFD-006 | GBPUSD | M1 | 2003-05-04 | 0.000149 | 0.011 | 0.00025 | 1.6746 | no | cost_R 1.6746 > 0.10 |
| CFD-006 | GBPUSD | M5 | 2003-05-04 | 0.000368 | 0.027 | 0.00025 | 0.6796 | no | cost_R 0.6796 > 0.10 |
| CFD-006 | GBPUSD | M15 | 2003-05-04 | 0.000661 | 0.049 | 0.00025 | 0.378 | no | cost_R 0.3780 > 0.10 |
| CFD-006 | GBPUSD | M30 | 2003-05-04 | 0.000963 | 0.072 | 0.00025 | 0.2596 | no | cost_R 0.2596 > 0.10 |
| CFD-006 | GBPUSD | H1 | 2003-05-04 | 0.001414 | 0.105 | 0.00025 | 0.1768 | no | cost_R 0.1768 > 0.10 |
| CFD-006 | GBPUSD | H4 | 2003-05-04 | 0.002939 | 0.219 | 0.00025 | 0.0851 | SÍ | OK |
| CFD-006 | GBPUSD | D1 | 2003-05-04 | 0.007778 | 0.58 | 0.00025 | 0.0321 | SÍ | OK |
| CFD-006 | USDJPY | M1 | 2003-05-04 | 0.017143 | 0.011 | 0.015083 | 0.8798 | no | cost_R 0.8798 > 0.10 |
| CFD-006 | USDJPY | M5 | 2003-05-04 | 0.043643 | 0.028 | 0.015083 | 0.3456 | no | cost_R 0.3456 > 0.10 |
| CFD-006 | USDJPY | M15 | 2003-05-04 | 0.081429 | 0.051 | 0.015083 | 0.1852 | no | cost_R 0.1852 > 0.10 |
| CFD-006 | USDJPY | M30 | 2003-05-04 | 0.120571 | 0.076 | 0.015083 | 0.1251 | no | cost_R 0.1251 > 0.10 |
| CFD-006 | USDJPY | H1 | 2003-05-04 | 0.176071 | 0.111 | 0.015083 | 0.0857 | SÍ | OK |
| CFD-006 | USDJPY | H4 | 2003-05-04 | 0.372286 | 0.235 | 0.015083 | 0.0405 | SÍ | OK |
| CFD-006 | USDJPY | D1 | 2003-05-04 | 1.018964 | 0.644 | 0.015083 | 0.0148 | SÍ | OK |

### Comparativa FTMO vs FundingPips

| Símbolo | TF | cost_R CFD-001 (FTMO) | cost_R CFD-006 (FundingPips) | Más barata | Delta |
|---|---|---:|---:|---|---:|
| US100 | M1 | 0.4043 | 0.4199 | CFD-001 | 0.0156 |
| US100 | M5 | 0.1704 | 0.1770 | CFD-001 | 0.0066 |
| US100 | M15 | 0.0925 | 0.0961 | CFD-001 | 0.0036 |
| US100 | M30 | 0.0630 | 0.0654 | CFD-001 | 0.0024 |
| US100 | H1 | 0.0433 | 0.0449 | CFD-001 | 0.0017 |
| US100 | H4 | 0.0212 | 0.0221 | CFD-001 | 0.0008 |
| US100 | D1 | 0.0078 | 0.0081 | CFD-001 | 0.0003 |
| XAUUSD | M1 | 0.3935 | 0.3425 | CFD-006 | 0.0511 |
| XAUUSD | M5 | 0.1650 | 0.1436 | CFD-006 | 0.0214 |
| XAUUSD | M15 | 0.0914 | 0.0795 | CFD-006 | 0.0119 |
| XAUUSD | M30 | 0.0630 | 0.0548 | CFD-006 | 0.0082 |
| XAUUSD | H1 | 0.0431 | 0.0375 | CFD-006 | 0.0056 |
| XAUUSD | H4 | 0.0209 | 0.0182 | CFD-006 | 0.0027 |
| XAUUSD | D1 | 0.0078 | 0.0068 | CFD-006 | 0.0010 |
| EURUSD | M1 | 1.5063 | 1.9494 | CFD-001 | 0.4430 |
| EURUSD | M5 | 0.6150 | 0.7959 | CFD-001 | 0.1809 |
| EURUSD | M15 | 0.3381 | 0.4375 | CFD-001 | 0.0994 |
| EURUSD | M30 | 0.2291 | 0.2964 | CFD-001 | 0.0674 |
| EURUSD | H1 | 0.1576 | 0.2039 | CFD-001 | 0.0463 |
| EURUSD | H4 | 0.0751 | 0.0973 | CFD-001 | 0.0221 |
| EURUSD | D1 | 0.0281 | 0.0364 | CFD-001 | 0.0083 |
| GBPUSD | M1 | 1.4737 | 1.6746 | CFD-001 | 0.2010 |
| GBPUSD | M5 | 0.5981 | 0.6796 | CFD-001 | 0.0816 |
| GBPUSD | M15 | 0.3326 | 0.3780 | CFD-001 | 0.0454 |
| GBPUSD | M30 | 0.2285 | 0.2596 | CFD-001 | 0.0312 |
| GBPUSD | H1 | 0.1556 | 0.1768 | CFD-001 | 0.0212 |
| GBPUSD | H4 | 0.0749 | 0.0851 | CFD-001 | 0.0102 |
| GBPUSD | D1 | 0.0283 | 0.0321 | CFD-001 | 0.0039 |
| USDJPY | M1 | 1.0089 | 0.8798 | CFD-006 | 0.1291 |
| USDJPY | M5 | 0.3963 | 0.3456 | CFD-006 | 0.0507 |
| USDJPY | M15 | 0.2124 | 0.1852 | CFD-006 | 0.0272 |
| USDJPY | M30 | 0.1435 | 0.1251 | CFD-006 | 0.0184 |
| USDJPY | H1 | 0.0982 | 0.0857 | CFD-006 | 0.0126 |
| USDJPY | H4 | 0.0465 | 0.0405 | CFD-006 | 0.0059 |
| USDJPY | D1 | 0.0170 | 0.0148 | CFD-006 | 0.0022 |

Resumen: **36 viables** (CFD-001 17, CFD-006 19); antes 24 (11/13). No hay
ninguna celda que pase de viable a no viable. M1/M5 siguen sin ser viables;
M15/M30/H1/H4/D1 ganan celdas al usar el régimen de precio actual.

### Una sola función de cost_R

- `propfund/onboarding_mtf.py::cost_r_for` calcula el cribado (ATR 12m).
- `lab propfund onboarding-mtf` y `edge_map.template_cost_r` la usan.
- `suggest` muestra `cost_R cribado` y `cost_R operaciones`; la factibilidad usa
  la de operaciones (`_trade_cost_r`, mediana de `trade.r_cost`), restaurada.
- Tests: `test_cost_r_compartido_onboarding_y_edge_map` y
  `test_base_viability_usa_r_cost_de_operaciones`.

## 3. Preflight y feasibility en seco

Comandos nuevos:

```text
lab discovery preflight --spec .orquestador/specs/<nombre>.yaml
lab discovery feasibility --spec .orquestador/specs/<nombre>.yaml
```

| Spec | Plantilla | Comprobados | Factibles | % | Gate |
|---|---|---:|---:|---:|---|
| asia-usdjpy-h1 | asia_range_reversion | 40 | 38 | 95.0 % | PASA |
| ny-open-us100-m15 | ny_open_vol_filter | 40 | 38 | 95.0 % | PASA |
| session-breakout-us100-m15 | session_breakout_htf | 40 | 31 | 77.5 % | PASA |

- Preflight de las 3 propuestas: 40/40 válidos, 0 rechazados, 0 duplicadas.
- Test `tests/test_discovery_spec.py`: `count_tests` y el número de filas de
  `disc_campaigns` son idénticos antes y después. Estado real: 1676 y 5 filas.
- No se registró ninguna campaña; `--spec` construye el contexto en memoria.

## 4. Compatibilidad plantilla × TF

Cada plantilla declara `valid_timeframes`; `genetic.template_timeframes` lo usa
para generar, sugerir y validar.

| Plantilla | M1 | M5 | M15 | M30 | H1 | H4 | D1 |
|---|---|---|---|---|---|---|---|
| asia_range_reversion | — | SÍ | SÍ | SÍ | SÍ | NO (declarada, no representable) | NO (declarada, no representable) |
| intraday_momentum_close | — | SÍ | SÍ | SÍ | NO (declarada, no representable) | — | — |
| intraday_momentum_close_v2 | — | SÍ | SÍ | SÍ | NO (declarada, no representable) | — | — |
| ny_open_vol_filter | SÍ | SÍ | SÍ | — | — | — | — |
| session_breakout_htf | — | SÍ | SÍ | SÍ | — | — | — |

- `asia_range_reversion` mantiene `timeframes` H4/D1 como declaración histórica,
  pero `valid_timeframes` los excluye: el rango 18:00-03:00 no es representable
  en barras H4/D1.
- `suggest` devuelve solo M5/M15/M30/H1 (comprobado en la salida nueva).
- `campaigns.register` rechaza H4/D1 con “no declara H4/D1”.
- `feasibility.scan` ya no incluye H4/D1 para asia.
- Tests actualizados: `test_plantillas_declaran_timeframes_compatibles`,
  `test_h4_d1_no_compatibles`,
  `test_scan_h4_d1_quedan_fuera_por_incompatibles`.

## 5. Propuestas

`.orquestador/PROPUESTAS-campanas.md` contiene 3 propuestas de familias
distintas (asia_range_reversion USDJPY H1, ny_open_vol_filter US100 M15,
session_breakout_htf US100 M15), todas compatibles, con cribado ≤0.10, cuentas
viables de T2, IS 2021-10-01→2024-06-30 y preflight/feasibility en seco ≥50 %.

- n_total estimado por campaña: 440 (small GA).
- DSR actual: 1676. Si se aprobaran las 3: 1676 + 3×440 = **2996**.
- No se registró ninguna; el DSR no cambió.

## 6. Cierre

`git status --short`:

```text
?? tl2-edge-map.patch
```

`git log --oneline -5`:

```text
043e979 tl2: R2k - arreglos previos a campaña
d94e625 tl2: R2i-b - onboarding multi-timeframe
8a121d0 tl2: R2j-b - calendario completo, tramos y usable_from
06ecf30 tl2: R2j - calendarios por instrumento
1a5049d merge: principal (R2g + R2g-fix) en integración
```

- `pytest -q`: **1612 passed, 1 skipped (1169,82 s; 1 warning psutil)**.
- `ruff check src/tradinglab tests`: **limpio**.
- `lab propfund verify`: **OK en ai_trader (17), ea_us100_ftmo1 (18), ftmo_forward (8) y ftmo_risk (14)**.
- `count_tests`: **1676** (sin campañas nuevas).
- Tag `tl2-r2k` → `043e979`.

## Aviso

- El fallo histórico del test de ruido no se reprodujo en 30 intentos. Si vuelve
  a aparecer, hay que capturar el orden/estado exacto; no se relajó el control.
- La corrección de R típico cambia la foto de viabilidad (36 vs 24 celdas), pero
  no cambia ningún umbral ni la factibilidad de operaciones.
- No se ejecutaron campañas ni se leyó OOS-1/OOS-2. No se hizo push.

## Siguiente

PARA.
