# RESULTADO · R7 · Portfolio Lab (corregido: solo R por operación)

Fecha: 2026-11-23. Ejecutado en la sesión R7, worktree
`C:\Users\PC\.local\share\opencode\worktree\tl2-r7` (desde `c684ac9`).
`E:\trading-lab` intacto salvo este archivo. Sin campañas, sin approve/run/confirm/
supersede, sin OOS de discovery, sin push, sin borrar, sin tocar umbrales, sin operar.

## Hecho

- Módulo `src/tradinglab/portfolio_lab.py` y comando
  `lab portfolio analyze --strategies A,B,... --account CFD-001 [--paths N] [--seed N] [--block-size N] [--json]`.
- **Corrección aplicada antes del cierre:** las series reales ya no se construyen a
  partir de equity ni de retornos del subyacente. Solo se aceptan resultados por
  operación en R (`pnl / riesgo_inicial`) con fecha de cierre.
- Los aliases `ftmo-eurusd`, `ftmo-usdjpy` y `us100-trend-d1` ahora fallan con
  **Sin datos** y un mensaje explicativo; se conservan para que el error sea visible.
- Nuevo token real `fwd:SIMBOLO:SETUP` sobre `ai_trades` (SQLite copia, `mode=ro`):
  exige `status=closed`, `risk_usd > 0`, `pnl` y `exit_ts`; calcula R por operación
  y lo contrasta con `r_multiple`.
- Días sin operación = 0 R, pero **no** se cuentan como pérdida ni entran en la
  correlación/pérdidas simultáneas: esos cálculos usan solo días en que ambas series
  operaron. Test dedicado con una operación por semana.
- Tres pesos fijos: `equal`, `inverse_vol` y `capped` (tope por idea de la firma).
  No se optimiza ningún peso sobre la muestra evaluada.
- `monte_carlo` y `multiverse_by_trade` se **llaman** desde `prop/simulator.py`
  (protegido); no se modifica. `lab propfund verify`: **4 OK**.
- Tests del módulo: **15 passed**. `ruff check`: limpio.
  `pytest -q` completo: **10 failed, 1638 passed, 3 skipped** (6052,97 s, 1:40:52).
  Los 10 fallos son baseline de entorno documentados en R7b: `test_ai_replay` ×4
  (sin datos de barras para el replay), `test_ea_forward` ×3 (hash congelado
  `f490642b…` vs `7292c007…`), `test_ea_lab_candidate` y
  `test_ea_lab_session_equivalence` (hash de pre-registro ausente en el doc) y
  `test_optimize` ×1 (DSR global `None`). **Ninguno es de `test_portfolio_lab.py`**.
- Commit `fff0502` (`tl2: R7 - Portfolio Lab`) · tag `tl2-r7`. Sin push ni merge.
- Resumen al operador: **enviado a Telegram** (puente activo, chat autorizado
  `1364122708`) con formato Hecho / 1..N / Aviso / Siguiente. ntfy devolvió
  `HTTPStatusError` en dos intentos; al estar Telegram configurado, se usó ese
  canal según AGENTS.md. Borrador en
  `C:\Users\PC\AppData\Local\Temp\opencode\r7-resumen.txt`.

## 1. Qué cambió y por qué

| Antes (inválido) | Ahora (corregido) | Motivo |
|---|---|---|
| `us100-trend-d1`: retornos diarios del índice convertidos a R → P(rompe diario) 1.000 | Token rechazado con **Sin datos** | El parquet solo trae `returns`; no hay riesgo inicial por operación. |
| `ftmo-eurusd`/`ftmo-usdjpy`: `equity` diario convertido a R → P(pasar) 0, P(rompe máx.) 1.000 | Tokens rechazados con **Sin datos** | Equity diario no es PnL por operación ni declara riesgo inicial; la escala era falsa. |
| Ratio 4,33 de pérdidas simultáneas con correlación 0,19 | Ratio recalculado sobre días con operación en ambas series | Los días sin operación se contaban como pérdidas. |
| Discovery alimentaba también P(rompe diario/máx.) | P(pasar) se mantiene; ruptura por operación = **Sin datos** | El databank guarda R diario agregado, no filas por operación con riesgo inicial. |

Test nuevo: `test_retornos_de_subyacente_se_rechazan` exige error claro ante un
parquet con `returns`/`equity`, y `test_dias_sin_operacion_no_inflan_perdidas`
comprueba que 14 días con operación entre 70 días no inflan el ratio.

## 2. Series, correlación y solape

### Fuentes

| Token | Origen | Símbolo | Días | Operaciones | Granularidad |
|---|---|---|---:|---:|---|
| `syn-0`, `syn-50`, `syn-90` | 3 series sintéticas por token | SYN | 252 | 252 por serie | `operacion_R` |
| `fwd:US100.cash:orb_5m` | `ai_trades`, riesgo USD declarado | US100.cash | 5 | 11 | `operacion_R` |
| `fwd:US100.cash:ema_ribbon_pullback` | ídem | US100.cash | 3 | 6 | `operacion_R` |
| `fwd:US100.cash:vwap_bounce` | ídem | US100.cash | 2 | 5 | `operacion_R` |
| `fwd:XAUUSD:orb_5m` | ídem | XAUUSD | 5 | 10 | `operacion_R` |
| `fwd:XAUUSD:vwap_bounce` | ídem | XAUUSD | 4 | 6 | `operacion_R` |
| `94`, `258`, `478` | discovery copia, solo `fitness_is` + `oos1` | US100.CASH / XAUUSD | 1233 (unión) | Sin datos por operación | `dia_R_agregado_por_cierre` |
| alias congelados | copias `data/copies/` | EURUSD / USDJPY / US100 | — | — | **Sin datos: rechazados** |

Las operaciones forward se leen de la copia `data/lab.db` hecha con
`sqlite3 backup`. La correlación y las pérdidas simultáneas se calculan solo con
días en que ambas series operaron: 3 días comunes orb↔EMA, 4 orb↔XAU VWAP y
2 EMA↔XAU VWAP (la unión de fechas del grupo es de 5 días). Exposición de la
cartera: US100.cash 17 operaciones y XAUUSD 6, máximo 1 posición concurrente por
símbolo; nocional en USD: **Sin datos** (no se declara tamaño ni precio).

### Sintéticos (CFD-001, 2000 caminos, semilla 42)

| ρ objetivo | Correlaciones medidas | Ratio de pérdidas simultáneas | Solape |
|---|---|---|---|
| 0 | -0.064 / -0.034 / +0.019 | 0.94 / 1.00 / 1.04 | 252/252 días (100 %, por construcción) |
| 0,5 | +0,425 / +0,457 / +0,471 | 1,40 / 1,36 / 1,44 | 252/252 días |
| 0,9 | +0,878 / +0,887 / +0,888 | 1,85 / 1,79 / 1,85 | 252/252 días |

Con ρ=0,9 la cartera igual solo sube P(pasar) de 0,979 a 0,981 (+0,2 puntos):
no hay diversificación real. El test `test_correlacion_alta_no_reduce_riesgo`
lo exige.

### Forward real (tres series: US100 orb, US100 EMA ribbon, XAUUSD VWAP bounce)

- Correlaciones: US100 orb ↔ US100 EMA +0,065; US100 orb ↔ XAU VWAP -0,730;
  US100 EMA ↔ XAU VWAP +1,000 (solo **2 días comunes**: no interpretable).
- Pérdidas simultáneas: 0 en los tres pares; el par orb↔VWAP esperaba 0,25 días
  sobre 4 comunes. Ya no aparece el 4,33 espurio.
- Solape: orb↔EMA 0 operaciones; orb↔XAU VWAP 4 operaciones / 0,7 h;
  EMA↔XAU VWAP 1 operación / 0,04 h. Nocional: **Sin datos**.

### Discovery (solo IS/OOS-1)

| Par | Correlación | Días comunes | Días con pérdida en ambos | Esperado | Ratio |
|---|---:|---:|---:|---:|---:|
| 94 ↔ 258 | -0,022 | 565 | 40 | 26,02 | 1,54 |
| 94 ↔ 478 | -0,022 | 72 | 1 | 1,00 | 1,00 |
| 258 ↔ 478 | +0,459 | 45 | 1 | 0,27 | 3,75 |

Los dos últimos ratios se apoyan en **1 sola pérdida compartida**: no son evidencia.
Solape temporal: **Sin datos** (no hay marcas de posición en el databank).

## 3. Reto de fondeo: individual vs cartera

`monte_carlo` usa bootstrap de la serie diaria de R (2000 caminos, semilla 42,
`block_size=5`, horizonte 60 días). `multiverse_by_trade` reordena **PnL por
operación** conservando el tamaño del día de cierre. Sus probabilidades son
muestreos distintos: no son complementarias y no deben sumarse.

### Sintéticos · CFD-001

| Caso | Mejor individual P(pasar) | Cartera igual | Cartera inversa-vol | Días (mejor → cartera) |
|---|---:|---:|---:|---|
| ρ=0 | 0,981 | 0,9965 | 0,9965 | 26 → 26 |
| ρ=0,5 | 0,979 | 0,9895 | 0,9895 | 26 → 26 |
| ρ=0,9 | 0,979 | 0,981 | 0,981 | 25 → 25 |

P(romper diario/máx.) = 0 en todos los casos sintéticos. Sin tope por idea
declarado en la configuración de FTMO → `capped` = **Sin datos**.

### Forward real · tres series · CFD-001

| Candidato | N operaciones | P(pasar) | P(rompe diario) | P(rompe máx.) | Días medianos |
|---|---:|---:|---:|---:|---:|
| Solo US100 orb_5m | 11 | 1,000 | 0,000 | 0,000 | 7 |
| Solo US100 ema_ribbon_pullback | 6 | 1,000 | 0,000 | 0,000 | 20 |
| Solo XAUUSD vwap_bounce | 6 | 0,000 | 0,000 | 0,000 | — |
| Cartera igual | 23 | 1,000 | 0,000 | 0,000 | 25 |
| Cartera inversa-vol | 23 | 1,000 | 0,000 | 0,000 | 21 |

Veredicto: P(pasar) **no mejora** (+0,0 puntos) y tarda 18 días más que el mejor
individual (orb_5m, 7 días) en el caso igual (25 días), o 14 más en inversa-vol
(21 días). El simulador avisa
`muestra insuficiente: N < 30` para cada solitario y para la cartera de 23.
Con las cinco series forward (N=38, sin aviso) la cartera sigue en P(pasar)=1,000
y 14 días al objetivo; las individuales van 5–22 días (XAUUSD vwap_bounce 0,000).

### Forward real · tres series · CFD-006

| Candidato | N | P(pasar) | P(rompe diario) | P(rompe máx.) | Días medianos |
|---|---:|---:|---:|---:|---:|
| Solo US100 orb_5m | 11 | 1,000 | 0,000 | 0,000 | 6 |
| Solo US100 ema_ribbon_pullback | 6 | 1,000 | 0,000 | 0,000 | 16 |
| Solo XAUUSD vwap_bounce | 6 | 0,000 | 0,000 | 0,000 | — |
| Cartera igual | 23 | 1,000 | 0,000 | 0,000 | 21 |
| Cartera inversa-vol | 23 | 1,000 | 0,000 | 0,000 | 17 |
| Cartera con tope por idea | 23 | 1,000 | 0,000 | 0,000 | 17 |

FundingPips declara `max_risk_per_trade_pct = 0,02` en fase *funded* y con
`needs_verification`; con riesgo de 0,5 % por operación no liga: pesos
0,290 / 0,481 / 0,229, idénticos a inversa-vol. Todas las filas de esta tabla
llevan aviso de muestra insuficiente (N=23 < 30); solo la cartera de cinco
series en CFD-001 (N=38) queda sin aviso.

### Discovery · CFD-001

| Candidato | P(pasar) | P(rompe diario) | P(rompe máx.) | Días medianos |
|---|---:|---|---|---:|
| Solo disc-94 (nivel 3, SOBREAJUSTADA) | 0,3375 | Sin datos | Sin datos | 38 |
| Solo disc-258 (nivel 2) | 0,0110 | Sin datos | Sin datos | 48 |
| Solo disc-478 (nivel 1) | 0,0775 | Sin datos | Sin datos | 45 |
| Cartera igual | 0,0160 | Sin datos | Sin datos | 50 |
| Cartera inversa-vol | 0,0040 | Sin datos | Sin datos | 55 |

P(pasar) **empeora** -32,1 puntos frente a la mejor individual. No hay datos
para una conclusión de cartera confirmada: una sola estrategia de nivel ≥3 y
marcada `SOBREAJUSTADA`. No se leyó ningún tramo de holdout ni OOS-2.

## 4. Tests y verificación

- `ruff check src/tradinglab/portfolio_lab.py src/tradinglab/cli.py tests/test_portfolio_lab.py`: limpio.
- `pytest -q tests/test_portfolio_lab.py`: **15 passed**. Cubre correlación conocida
  (0/0,5/0,9), ρ=0,9 sin reducción de riesgo, reglas de firma y tope por idea,
  días sin operación, días comunes sin pérdidas, rechazo de retornos de subyacente,
  R por operación de `ai_trades`, solo tramos IS/OOS-1, breach “Sin datos” para
  discovery y CLI JSON/errores.
- `pytest -q` completo (una sola ejecución): **10 failed, 1638 passed, 3 skipped,
  1 warning en 6052,97 s (1:40:52)**. Ningún fallo del módulo nuevo. Los fallos
  son los grupos ya documentados en R7b §7 (replay sin barras, hashes EA/pre-registro
  desalineados, DSR global `None`); no se corrigió nada de eso porque estaba fuera
  del alcance de R7. El `F` del 74 % corresponde a `test_optimize` (DSR), no a
  Portfolio Lab: el resumen nominal lo confirma.
- `lab propfund verify` (tras la corrección): **4 OK** — ai_trader (17 archivos),
  ea_us100_ftmo1 (18), ftmo_forward (8) y ftmo_risk (14).
- `lab doctor`: Frescura **FAIL 7/17** (US100.CASH H1/M1/M15/M5 al 2026-11-20,
  entre otros) y 9 avisos; es preexistente y empeoró una serie respecto al chequeo
  anterior de la sesión por el paso del tiempo. No se tocó ningún dato.

## Aviso

- `ai_trades` es forward en demo: 5–11 operaciones por setup y 5 días de calendario.
  P(pasar)=1,000 con N=6 **no** es evidencia de robustness; el propio simulador lo
  marca como muestra insuficiente.
- La correlación +1,000 entre dos series forward se apoya en 2 días; no debe
  interpretarse como diversificación ni como riesgo de concentración medido.
- Los backtests congelados no entraron en ninguna tabla de resultados: se rechazan
  con error explícito. No se inventaron precios, offsets ni históricos.
- No se cambió ningún archivo protegido, no se ejecutó campaña ni barrido, no se
  leyó OOS-2, no se hicieron promociones, ni push, ni tareas programadas, ni borrados.
- ntfy falló con `HTTPStatusError` en dos intentos (canal configurado pero
  servidor no responde); Telegram sí estaba configurado y el resumen se envió
  por ahí. No se reintentó ntfy para no spamear.

## Siguiente

PARA.
