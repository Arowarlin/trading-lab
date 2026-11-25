# Metodología de backtest · Fase C

Fijada el 2026-11-25 **antes** de ejecutar ninguna variante sobre datos reales.
Código: `tools/phase_c.py`. Tests sintéticos: `tests/test_phase_c.py`.

Cambiar cualquier regla después de ver resultados invalida el preregistro. Un
cambio así exige un registro nuevo de pruebas.

## Gate

`phase_c.py` se niega a ejecutar sin una fila `NASDAQ EDGE Fase C` en
`informal_trials` (`data/lab.db`). Nunca lee fechas ≥ 2024-01-01: hay un assert.

## Datos y periodos

| Serie | DEV | OOS-1 |
|---|---|---|
| NQ CME M1 (Databento) | 2010-06 → 2018-12 | **Sin datos** (la caché termina en 2018) |
| Dukascopy M1 bid (proxy de precio) | 2012 → 2021 | 2022 → 2023 |

El modelo E (perfil y RVOL) solo corre en NQ. Sin NQ 2019+ no tiene OOS-1, y no
puede superar los criterios de aceptación hasta que se compren esos datos.

## Ejecución

- Señal al cierre de la vela M5 (9:30, 9:35…, etiquetadas por apertura).
- Mercado: apertura de la M1 siguiente ± slippage.
- Límite: se llena si el precio la atraviesa 1 tick, sin slippage.
- Stops: salen con slippage.
- Stop y objetivo en la misma vela M1: primero el stop.
- Tras TP1 no se evalúa TP2 en la misma vela.
- Gestión común:
  - 50 % en TP1 = 1R; el stop pasa a break-even;
  - 50 % en TP2 = 2R, o el objetivo del modelo (VWAP en C-rev; VA opuesto o POC en E);
  - si el objetivo del modelo está a menos de 1R, no hay operación.
- Ventana de entrada 9:35–11:30 ET; cierre forzoso a las 15:55 ET; una posición a la vez.
- Máximo 3 operaciones al día; se para tras 2 pérdidas o −2R en el día. Con $150 de riesgo, −2R equivale al límite personal de −$300.
- Tamaño en MNQ: floor($150 / (riesgo_pt × $2 + comisión)). Si sale 0 → NO TRADE, contado en `skips.no_trade_size`.
- Noticias: las entradas empiezan a las 9:35. Las ventanas de las 08:30 ya terminaron (+20 min) y FOMC (14:00) cae fuera de la ventana. Por eso el filtro no cambia ninguna operación de la V1. Se reporta la expectancy en días Tier 1 frente a días sin noticias.

## Especificación de cada modelo

| Variante | Regla exacta |
|---|---|
| A_ORn_close | Primer cierre M5 fuera del OR de n min. Entrada a mercado. Stop = el más cercano entre el lado opuesto del OR y entrada ∓ ATR14(M5). |
| A_ORn_retest | La misma ruptura, pero entrada límite en el borde del OR durante 30 min. |
| B_PD/ON_reclaim | El nivel (PDH/PDL u ONH/ONL) se rebasa ≥ 2 ticks y una M5 cierra de vuelta dentro en ≤ 3 velas. Se abre en contra del barrido. Stop = extremo del barrido ± 1 tick. Solo si la sesión abre dentro del nivel. |
| B_*_disp | Lo mismo, y la vela del reclaim tiene un rango ≥ 1,5×ATR14(M5). |
| C_rev | Cierre M5 fuera de VWAP ± 2σ seguido de un cierre dentro. Objetivo = VWAP. Stop = extremo de las últimas 7 velas ± 1 tick. |
| C_cont | Pendiente del VWAP de 30 min; pullback a VWAP ± 0,5σ con cierre a favor. Stop = min(mínimo de la vela, VWAP − 0,5σ) − 1 tick. |
| C_*_F | Filtro de régimen con ADX14 de la M15 ya cerrada: < 20 para rev y > 25 para cont. |
| D_iso/struct_mid/edge | Vela con cuerpo ≥ 2×ATR14(M5) que deja un FVG de 3 velas. Límite en el 50 % o en el borde cercano durante 60 min. Stop = borde lejano ± 1 tick. "struct" exige la misma dirección que el cierre M15 frente a 4 M15 antes. |
| E_accept | Apertura fuera del VA de la víspera y 2 cierres M5 dentro. Objetivo = borde opuesto del VA. Stop = extremo de las 2 velas ± 1 tick. |
| E_reject | Cierre fuera del VA y luego cierre dentro. Objetivo = POC. |
| E_*_rvol | Volumen acumulado ≥ 1,2× la mediana de 20 sesiones a la misma hora. |

Perfil: cierres M1 ponderados por volumen, bins de 1 pt, VA del 70 %. Es una
aproximación, no un Volume Profile tick a tick.

## Escenarios de coste

| Escenario | Slippage por lado | Comisión MNQ ida y vuelta |
|---|---:|---:|
| zero_cost | 0 | $0 |
| base | 1 tick | $1,50 [HIPÓTESIS: la comisión real de MNQ en las firmas es Sin datos] |
| slip2 | 2 ticks | $1,50 |
| slip4 | 4 ticks | $1,50 |
| comm2x | 1 tick | $3,00 |

## Métricas

- Por operación: n, win rate, PF, expectancy en R (neta y antes de comisión), ganancia y pérdida medias.
- Diarias: drawdown máximo en R, Sharpe y Sortino anualizados.
- Desgloses: por año, hora, día de la semana, días Tier 1 frente a días sin noticias, y motivos de salida.
- Robustez: suma de R sin el 1 % de mejores días.
- DSR: `tradinglab.stats.dsr_from_returns` con retornos diarios. Las otras variantes aportan la dispersión de los Sharpe y `n_trials` sale del recuento total del laboratorio. Se calcula en la Fase D para las finalistas.
- Monte Carlo Topstep 50K y ablación: solo para las variantes que pasen DEV y OOS-1.
