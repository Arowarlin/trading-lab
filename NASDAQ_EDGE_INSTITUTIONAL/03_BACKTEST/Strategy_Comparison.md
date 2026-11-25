# Comparación de las 22 variantes · Fase C (2026-11-25)

Ejecutado con `tools/phase_c.py --run` tras el registro del operador en
`informal_trials`:
- id 6: 7 miradas de la Fase B;
- id 7: 22 variantes.

`count_tests` del laboratorio: 1926. Metodología fijada antes de ejecutar:
`Backtest_Methodology.md`. Resultados completos (5 escenarios de coste,
desgloses por año, hora, día y noticias): `phase_c_results.json`. Operaciones:
`trades/`.

## Veredicto

**Ninguna variante cumple los criterios de aceptación. No existe una ventaja
demostrada** en las familias A–E tal como se preregistraron.

1. **Bruto ≈ 0.** Sin costes, la expectancy de las 22 variantes en DEV está
   entre −0,12R y +0,06R con n de cientos a miles. El error estándar ronda
   ±0,03–0,05R, así que nada se separa de cero.
   - Las dos D_struct (+0,25R y +0,19R) tienen 8 y 16 operaciones: no hay muestra.
2. **El neto es claramente negativo en DEV: de −0,14R a −0,51R.**
   - Los stops estructurales son pequeños frente al coste fijo por contrato.
   - Ejemplo: A_OR15_close en NQ 2010–2018 tiene un stop mediano de 5,5 pt. Los 2 ticks de slippage más la comisión cuestan 0,23R por operación.
   - PF neto entre 0,38 y 0,96. Ninguno llega al 1,30 exigido.
3. **OOS-1 (Dukascopy 2022–2023) es casi neutro.**
   - Con el índice más alto, los stops miden ~30 pt y el coste baja a ~0,04R.
   - Cuatro variantes salen positivas: A_OR5_close +0,022R, A_OR30_close +0,034R, B_PD_disp +0,046R (n = 46) y D_iso_mid +0,134R (n = 40).
   - Las cuatro son negativas en DEV, y los criterios exigen ambos periodos.
   - No se rescatan: elegirlas por su OOS-1 sería selección retrospectiva.
4. **NQ y Dukascopy coinciden** en DEV en signo y orden de magnitud. El
   resultado no depende de la fuente.

## Tabla (expectancy en R por operación; neto = escenario base: 1 tick por lado + $1,50 de comisión)

| Variante | NQ DEV n | NQ DEV bruto | NQ DEV neto | PF neto | DUK DEV n | DUK DEV bruto | DUK DEV neto | DUK OOS-1 n | DUK OOS-1 neto | ¿Pasa? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A_OR5_close | 1850 | +0.037 | -0.192 | 0.69 | 2209 | -0.012 | -0.174 | 491 | +0.022 | No |
| A_OR5_retest | 1346 | -0.074 | -0.267 | 0.58 | 1592 | -0.109 | -0.249 | 387 | -0.033 | No |
| A_OR15_close | 1793 | -0.008 | -0.230 | 0.64 | 2133 | +0.002 | -0.151 | 482 | -0.003 | No |
| A_OR15_retest | 1310 | -0.052 | -0.231 | 0.63 | 1533 | -0.066 | -0.196 | 375 | -0.059 | No |
| A_OR30_close | 1631 | +0.028 | -0.191 | 0.69 | 1925 | +0.001 | -0.142 | 442 | +0.034 | No |
| A_OR30_retest | 1167 | -0.039 | -0.211 | 0.66 | 1381 | -0.072 | -0.199 | 320 | -0.055 | No |
| B_PD_reclaim | 421 | +0.006 | -0.271 | 0.59 | 508 | +0.058 | -0.161 | 108 | -0.053 | No |
| B_PD_disp | 167 | +0.005 | -0.238 | 0.62 | 233 | +0.042 | -0.164 | 46 | +0.046 | No |
| B_ON_reclaim | 957 | -0.011 | -0.259 | 0.60 | 1136 | -0.021 | -0.210 | 268 | -0.111 | No |
| B_ON_disp | 383 | -0.030 | -0.242 | 0.61 | 479 | -0.085 | -0.239 | 101 | -0.100 | No |
| C_rev_noF | 1906 | -0.082 | -0.490 | 0.39 | 2397 | -0.023 | -0.343 | 580 | -0.141 | No |
| C_rev_F | 497 | -0.057 | -0.489 | 0.38 | 653 | -0.004 | -0.327 | 153 | -0.188 | No |
| C_cont_noF | 3137 | +0.002 | -0.211 | 0.66 | 3898 | +0.020 | -0.138 | 896 | -0.079 | No |
| C_cont_F | 1821 | -0.013 | -0.227 | 0.64 | 2180 | +0.009 | -0.150 | 489 | -0.053 | No |
| D_iso_mid | 122 | -0.008 | -0.386 | 0.43 | 197 | -0.094 | -0.419 | 40 | +0.134 | No |
| D_iso_edge | 176 | -0.013 | -0.234 | 0.64 | 258 | -0.115 | -0.302 | 47 | -0.171 | No |
| D_struct_mid | 8 | +0.250 | -0.016 | 0.96 | 16 | +0.188 | -0.009 | 1 | +1.479 | No |
| D_struct_edge | 19 | +0.053 | -0.070 | 0.87 | 29 | -0.051 | -0.160 | 2 | -0.268 | No |
| E_accept_norvol | 603 | -0.066 | -0.511 | 0.38 | — | — | — | — | — | No |
| E_accept_rvol | 200 | -0.022 | -0.476 | 0.42 | — | — | — | — | — | No |
| E_reject_norvol | 334 | -0.062 | -0.211 | 0.66 | — | — | — | — | — | No |
| E_reject_rvol | 99 | +0.017 | -0.162 | 0.72 | — | — | — | — | — | No |

## Lo que no se hizo, y por qué

- **DSR, Monte Carlo Topstep 50K y ablación:** el preregistro los limita a las
  variantes que pasan DEV y OOS-1. No pasa ninguna; calcularlos sobre
  expectancy negativa no aporta.
- **Walk-forward:** la partición preregistrada era DEV → OOS-1. No se añadió un
  walk-forward por variante porque ya falla el DEV completo.
- **OOS-2 (2024–2026):** sigue sellado y sin leer. No hay ninguna configuración
  final que merezca su única lectura.
- **Modelo E:** sin OOS-1 (no hay NQ 2019+). En DEV ya es negativo neto
  (−0,16 a −0,51R), así que comprar los datos no cambiaría el veredicto.

## Advertencia sobre lo que **no** debe hacerse ahora

- Ensanchar stops, cambiar objetivos o filtrar años hasta que algo salga
  positivo es exactamente la sobreoptimización que el encargo prohíbe.
- Cualquier hipótesis nueva necesita un preregistro nuevo y un registro nuevo
  del operador. Las 22 de aquí ya están gastadas.
