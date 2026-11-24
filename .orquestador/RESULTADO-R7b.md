# RESULTADO — R7b · deriva demo vs backtest de los carriles que ya operan

Modelo: DeepSeek V4.1 Flash. Worktree `C:\Users\PC\.local\share\opencode\worktree\tl2-r7b`,
rama `tl2-r7b`, base `c684ac9` (`tl2: N3 - propuestas de la manana`). Solo lectura:
no se operó, no se enviaron ni cerraron órdenes, no se tocaron campañas, OOS,
umbrales, archivos protegidos ni `E:\trading-lab\data`. Sin push y sin merge.

## Hecho

Se añadió `lab drift report [--lane X] [--db RUTA] [--json]` y la lógica de
deriva por carril en `src/tradinglab/drift.py` (la función `build_drift` de bots
se conserva intacta). `drift.py` ya existía con la deriva por bot; se extendió
en vez de reemplazarlo para no romper `lab drift`, la consola ni
`reports drift`. Para cada operación demo se reconstruye la operación que
la regla congelada del mismo carril habría hecho ese día con las mismas velas
del bróker, y se comparan señal, entrada, salida, slippage, spread y R. La base
se abrió con `sqlite3` en modo `ro`; MT5 se usó attach-only y se verificó el
login antes y después.

## 1. Inventario demo (solo lectura)

Copia de `E:\trading-lab\data\lab.db` hecha con `sqlite3.backup` dentro del
worktree: `data\lab-r7b-copy.db` (15.646.720 bytes). Señales hasta
`2026-11-23T13:32Z`; fills hasta `2026-11-23T10:20Z`.

| Carril | Símbolo / TF | Demo | Cerradas | Abiertas | Primera | Última | Estado |
|---|---|---:|---:|---:|---|---|---|
| forward eurusd-london-pullback-forward | EURUSD M15 | 5 | 5 | 0 | 2026-11-12 13:32Z | 2026-11-23 09:17Z | medido |
| forward usdjpy-tokyo-breakout-forward | USDJPY M15 | 2 | 2 | 0 | 2026-11-18 02:47Z | 2026-11-20 02:47Z | medido |
| forward us100-trend-d1 (incubación) | US100.CASH H4 | 0 | 0 | 0 | — | — | sin datos |
| EA us100-ftmo1 | US100.cash M5 | 2 | 2 | 0 | 2026-11-16 14:55Z | 2026-11-18 15:55Z | medido |
| ai_trader | varios | 42 | 39 | 3 | 2026-11-13 14:46Z | 2026-11-20 22:17Z | registro |

`us100-trend-d1` no tiene operaciones: sus dos señales registradas
(`2026-11-12 12:54` y `2026-11-13 04:02`) quedaron bloqueadas por
`outside_entry_window`. No se extrapola nada de este carril.

`ai_trader`, solo como registro (no tiene backtest equivalente):

| Estilo | Estado | N | R |
|---|---|---:|---:|
| scalping | closed | 38 | +7.066 |
| intraday | closed | 1 | -0.044 |
| swing | proposed | 3 | 0.000 |
| **total** | | **42** | **+7.022** |

## 2. Señales coincidentes, perdidas y extra

«Puntual» = la entrada demo ocurrió dentro de 2 barras (30 min en M15) de la
señal del backtest. «Match» = coinciden día y lado, aunque la entrada sea tardía.

| Carril | Señales BT | Coinciden | Puntuales | Perdidas | Extra | Match | Puntual |
|---|---:|---:|---:|---:|---:|---:|---:|
| EURUSD forward | 8 | 4 | 2 | 3 | 0 | 50% | 25% |
| USDJPY forward | 2 | 2 | 2 | 0 | 0 | 100% | 100% |
| US100-trend-d1 | 0 | — | — | — | — | Sin datos | Sin datos |
| EA us100-ftmo1 | 2 | 0 | 0 | 2 | 2 | 0% | 0% |

Precisión/recall de EURUSD: 4/5 = 80% de las entradas demo tienen señal del
mismo lado; 4/8 = 50% de las señales del backtest fueron tomadas. Las 3 señales
perdidas tienen motivo operativo registrado:

- `2026-11-13`: `blocked freshness: datos viejos: 259 min sin refrescar`.
- `2026-11-18`: `guard de cuenta: máximo de operaciones diarias alcanzado (1)`.
- `2026-11-20`: `guard de cuenta: máximo de operaciones diarias alcanzado (1)`.

Las dos entradas «coincidentes» de EURUSD llegaron muy tarde: `2026-11-12`
+317 min y `2026-11-16` +392 min. En la primera, el primer intento vivo
(`13:17Z`) también fue bloqueado por freshness (679 min); en la segunda no hay
fila de señal antes de `15:32Z`. El EA no coincide ni en lado: el motor congelado
genera largos en 11-16 y 11-18; la demo vendió esos dos días.

## 3. Operaciones, precio y R

### EURUSD forward

| Día | Demo | Entrada → salida | R demo | Backtest | Entrada → salida | R BT | Delay | Slip ejec. | Slip vs BT | Spread | Nota |
|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 11-12 | short | 1.10854 → 1.10665 | +1.34 | short | 1.10878 → 1.10992 | -1.00 | 317 min | 0.36 | 2.16 | 0.090 | coincide; primer bloqueo freshness 679 min |
| 11-13 | — | — | — | short | 1.10654 → 1.10510 | +1.47 | — | — | — | 0.090 | perdida; freshness 259 min |
| 11-16 | short | 1.10058 → 1.10058 | 0.00 | short | 1.10260 → 1.10141 | +1.08 | 392 min | 0.00 | 18.32 | 0.182 | coincide; entrada tardía |
| 11-17 | short | 1.10043 → 1.09910 | +1.66 | short | 1.10046 → 1.09898 | +1.84 | 3 min | -0.27 | 0.27 | 0.091 | coincide |
| 11-18 | — | — | — | short | 1.09785 → 1.09659 | +0.99 | — | — | — | 0.091 | perdida; max trades 1/1 |
| 11-19 | long | 1.09835 → 1.09804 | -0.22 | short | 1.09748 → 1.09814 | -1.00 | 498 min | 0.73 | 7.93 | 0.091 | señal contraria |
| 11-20 | — | — | — | short | 1.09863 → 1.09839 | +0.34 | — | — | — | 0.091 | perdida; max trades 1/1 |
| 11-23 | long | 1.09812 → 1.09683 | -1.00 | long | 1.09813 → 1.09684 | -1.00 | 2 min | -0.09 | -0.09 | 0.091 | coincide (stop) |

R acumulada en los 4 pares coincidentes: demo **+1.783R**, backtest **+0.923R**,
drift (BT − demo) **-1.080R**. La diferencia no viene del coste de ejecución:
viene de que el backtest entró antes y se comió el stop el 11-12, mientras la
demo entró tarde y salió mejor. Es timing, no spread.

### USDJPY forward

| Día | Demo | Entrada → salida | R demo | Backtest | Entrada → salida | R BT | Delay | Slip ejec. | Slip vs BT | Spread | Nota |
|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 11-18 | short | 159.362 → 159.424 | -0.32 | short | 159.358 → 159.444 | -0.45 | 2 min | -0.06 | -0.25 | 0.188 | coincide |
| 11-20 | short | 159.198 → 159.159 | +0.15 | short | 159.224 → 159.151 | +0.27 | 3 min | -0.13 | 1.63 | 0.188 | coincide |

R acumulada: demo **-0.174R**, backtest **-0.173R**, drift **+0.001R**. Es el
carril más limpio, pero solo hay 2 operaciones.

### EA us100-ftmo1

| Día | Demo | Entrada → salida | R demo | Backtest | Entrada → salida | R BT | Slip ejec. | Slip vs BT | Spread | Nota |
|---|---|---|---:|---|---|---:|---:|---:|---:|---|
| 11-16 | — | — | — | long | 27479.68 → 27365.79 | -1.00 | — | — | 0.528 | señal BT no emparejada |
| 11-16 | short | 27495.13 → 27176.03 | +2.97 | — | — | — | 0.73 | -4.26 | 0.527 | señal extra (demo hizo otra cosa) |
| 11-18 | — | — | — | long | 27165.78 → 27050.44 | -1.00 | — | — | 0.534 | señal BT no emparejada |
| 11-18 | short | 26981.13 → 26925.38 | +0.44 | — | — | — | 0.74 | 0.56 | 0.537 | señal extra (demo hizo otra cosa) |

R demo: **+3.413R** con riesgo base del setfile (1,0% = 1.000 USD por operación;
los fills externos no traen `risk_usd`, así que no es el R dinámico exacto
1,0/0,6/0,35/0,25%). No hay pares coincidentes: no se calcula drift de R.

## 4. Costes: slippage y spread

«Slip ejec.» = fill frente al ask (largo) o bid (corto) del tick de ejecución
(±15 s): es el deslizamiento puro. «Slip vs BT» = fill frente a la entrada del
backtest; incluye el retraso de la entrada, no es coste de ejecución.

| Carril | n | Slip ejec. p50 / p95 | Slip vs BT p50 / p95 | Slippage asumido | Spread real p50 / p95 | Spread perfil |
|---|---:|---:|---:|---:|---:|---:|
| EURUSD forward | 5 | 0.00 / 0.65 bps | 2.16 / 16.24 bps | 0.45 bps | 0.091 / 0.164 bps | 0.091 bps |
| USDJPY forward | 2 | -0.09 / -0.07 bps | 0.69 / 1.54 bps | 0.31 bps | 0.188 / 0.188 bps | 0.188 bps |
| EA us100-ftmo1 | 2 | 0.73 / 0.74 bps | -1.85 / 0.32 bps | 0.36 bps | 0.532 / 0.537 bps | 0.699 bps |
| US100-trend-d1 | 0 | Sin datos | Sin datos | — | Sin datos | — |
| ai_trader | 0 | Sin datos | Sin datos | — | Sin datos | — |

En el EA no hay ninguna señal emparejada: sus dos filas usan el open de la
barra de ejecución (`bar_open`) como referencia, no una entrada BT. Por eso su
«slip vs BT» no es comparable con el de EURUSD/USDJPY.

## 5. Qué significa para confiar en los costes asumidos del discovery

1. **Spread:** el perfil de `config/propfund/costs.yaml` (CFD-001) coincide con
   el spread medido en EURUSD (0,091 vs 0,091 bps) y USDJPY (0,188 vs 0,188).
   En US100 el real es **menor** que el perfil (0,532 vs 0,699 bps), así que el
   perfil es conservador. No hay evidencia de spread subestimado.
2. **Slippage de ejecución:** en EURUSD el p50 es 0,00 bps y el p95 0,65 bps
   frente a 0,45 asumido: el p50 está por debajo y el p95 solo lo supera en
   0,20 bps. En USDJPY el p50 es -0,09 bps (favorable) frente a 0,31 asumido.
   En el EA el p50 es 0,73 bps frente a 0,36 (2×), pero con n=2 y un spread real
   menor que el perfil; no es concluyente. **No se observa que el coste de
   ejecución del discovery esté subestimado en FX.**
3. **El drift grande no es coste, es cobertura/timing:** EURUSD solo tiene 25%
   de entradas puntuales, 3 señales perdidas por freshness/max-trades y dos
   entradas con 5-6,5 horas de retraso. El «slip vs BT» de 16 bps en el p95 es
   movimiento de precio por entrar tarde, no deslizamiento del bróker. Meterlo
   en `cost_R` como si fuera spread sería doble contabilidad y error de régimen.
4. **El EA no es un forward válido todavía:** el motor congelado y la demo van
   en direcciones opuestas los dos días. Antes de usar su R como evidencia hay
   que reconciliar setfile/versión/logs del EA; el +3,41R demo no valida el
   backtest porque no hay una sola señal coincidente.
5. **Muestra:** 5 operaciones EURUSD, 2 USDJPY, 2 EA. Los p95 de n=2/n=5 no son
   cuantiles estables. No se extrapola ni se cambia ningún umbral.

## 6. Propuesta de umbrales de alerta (NO configurada)

Solo propuesta para que el operador decida; no se escribió en `config/` ni se
activó ninguna tarea:

- Cobertura: `match_pct < 80%` o `timely_pct < 80%` con n ≥ 20 operaciones demo
  → deriva operativa (revisar freshness, schedule y max-trades antes que el
  edge).
- Slippage de ejecución: `p50 > asumido + 1 bps` o `p95 > 2× asumido` con
  n ≥ 20 fills → revisar el perfil de coste.
- Spread: `p95 > 1,5× perfil` con n ≥ 20 fills → revisar bróker/perfil.
- R: `|drift acumulado| > 2R` con n ≥ 20 pares → deriva de edge, no de coste.
- Cualquier día con señal BT y demo bloqueado por freshness → incidente
  operativo, se cuenta aparte y no se mezcla con el drift de mercado.

## 7. Tests y verificación

- Módulo nuevo: **9 passed** (`pytest -q -p no:randomly tests/test_drift_lanes.py`).
- `ruff check src/tradinglab/drift.py src/tradinglab/cli.py tests/test_drift_lanes.py`:
  **All checks passed**.
- `lab propfund verify`: **4 OK** (`ai_trader`, `ea_us100_ftmo1`,
  `ftmo_forward`, `ftmo_risk`).
- `count_tests` sobre la copia y sobre `E:\trading-lab\data\lab.db`: **1060**
  (no se registró ninguna prueba nueva; la fase no lo pedía). El valor es el
  actual de la base: la copia y E: dan el mismo 1060, así que no lo cambió R7b.
- Suite completa del worktree: **1614 passed, 27 failed, 3 skipped, 1 warning
  en 3361 s (56:00)**. Ningún fallo es de `tests/test_drift_lanes.py`; los 9
  tests del módulo se repitieron después del último retoque y pasan. Los 27
  fallos son baseline/entorno, agrupados:
  - CRLF/EA (5): `test_ea_forward` ×3, `test_ea_lab_candidate`,
    `test_ea_lab_session_equivalence`.
  - Discovery sin `broker_spreads` en el `lab.db` del worktree (11):
    `test_discovery_engine::test_engine_is_reproducible`,
    `test_discovery_feasibility`, `test_discovery_jobs` ×4,
    `test_discovery_noise` ×2, `test_discovery_segments`,
    `test_discovery_spec` ×2.
  - Timeouts HTTP por contención (3): `test_fund_web` ×2, `test_web`.
  - `test_ai_replay` ×4 (entorno LLM/replay).
  - `test_operator::test_auditoria_sin_secretos` (falso positivo: `1234`
    aparece dentro de un hash, no como secreto).
  - DSR global `None` (3): `test_optimize` ×1, `test_research` ×2.
- `ruff check src/tradinglab tests`: **All checks passed**.

## 8. Git

```text
$ git status --short
(sin cambios)
```

```text
$ git log --oneline -5
28eb2f2 tl2: R7b - deriva demo vs backtest
c684ac9 tl2: N3 - propuestas de la manana
a246eeb tl2: N2-fix - fecha de mercado en tests de comparacion
e1d4f69 tl2: N2-fix - recuento de plantillas en test DSL
c2cecea tl2: N2 - plantillas H4/D1
```

Commit `28eb2f2` (`tl2: R7b - deriva demo vs backtest`), tag `tl2-r7b`.
Sin push y sin merge.

## Aviso

- La copia de la base se hizo al inicio de la fase (mtime `2026-11-23 09:42`
  local; 15.646.720 bytes). El histórico de deals de MT5 solo conserva desde
  `2026-11-19 19:42Z`; los cierres anteriores se reconstruyeron desde
  `signals`, y el cierre del 11-23 desde el deal de MT5. Los `fills` de la base
  están incompletos para algunos cierres del forward.
- El R del EA usa el riesgo base del setfile (1,0%), no el riesgo dinámico
  exacto. El precio de salida del motor EA se deriva de `ent + d × r × risk`
  porque el motor solo exporta R, no el precio de salida.
- `us100-trend-d1` no tiene operaciones; no hay deriva medible.
- `ai_trader` no tiene backtest equivalente; solo se inventarió.
- MT5 attach-only: login `1515349730` / `FTMO-Demo` antes y después; sin
  órdenes. No se tocó el terminal más allá de lectura de barras, ticks y deals.
- La suite completa del worktree tiene fallos de entorno (CRLF, `broker_spreads`
  ausente en el `lab.db` del worktree, timeouts HTTP, LLM, DSR) ya documentados
  en fases anteriores; están listados en la sección 7. Ninguno es del módulo
  nuevo.
- `E:\trading-lab` avanzó a `3f5e233` durante la fase (otra sesión); este
  worktree se quedó en `c684ac9` y no se mezcló ni se hizo merge.
- No se configuraron umbrales, no se registraron tareas, no se ejecutaron
  campañas ni OOS, no se hizo push ni merge.

## Siguiente

1. Operador: decidir si se corrige primero la cobertura del forward
   (freshness, schedule y el guard de max-trades) antes de acumular más días.
   Con 5/2/2 operaciones no hay base para concluir sobre el edge.
2. Reconciliar el EA demo contra `ea_us100_engine` (setfile, versión, logs). Sin
   eso, el forward del EA no es evidencia del backtest.
3. Si se aprueba, convertir los umbrales de la sección 6 en configuración
   explícita y añadir `lab drift report` a la rutina diaria; esta fase no lo
   hace.
4. No hay merge ni push: la rama `tl2-r7b` y el tag quedan locales.
