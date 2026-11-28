# FUT-C2 · Research A: detectores y conteo sin desenlaces

**Fecha:** 2026-11-28 · **Modelo:** DeepSeek V4.1 Flash (OpenCode Go) · **Worktree:** `E:\tl-fut-ra`
(rama `fut-ra`) · **Carril:** P1a.

## Hecho

1. `src/tradinglab/futures/research_a.py` (nuevo):
   - `seal(bars)`: descarta ≥ 2024-01-01 (OOS-2, OP-8) **antes** de cualquier rasgo.
   - `s_c(bars, sessions=20)`: `sC` = 1,4826·MAD de `cvd_t − cvd_{t−30}` en las 20 sesiones previas, en el
     mismo minuto del día (solo pasado). `R30` y `cvd_{t−30}` se calculan **dentro** de la sesión.
   - `med_l(footprints, sessions=20)`: `medL` por sesión = mediana del pool de volúmenes `B+S` no nulos por
     nivel de las 20 sesiones previas con footprint.
   - `detect(bars, refs, footprints, hypothesis)` → `list[dict]` con `minute`, `side` (+1/−1) y `stop`,
     **sin desenlaces**. Reglas literales de `RA_spec.md` §5: A, C, D, E, H e I, cada una con su simétrica:
     - A: `z ≤ −3`, `close ≥ open`, `V ≥ 2·medV` ⇒ largo, stop `low − tick` (simétrica `z ≥ 3`,
       `close ≤ open` ⇒ corto, stop `high + tick`).
     - C: `t0 = argmax(high[t−30..t−1])`, `high_t > high_t0`, `cvd_t < cvd_t0 − sC` ⇒ corto, stop `high + tick`
       (simétrica con `argmin(low)`).
     - D: ≥ 3 niveles consecutivos con `buy(k) ≥ 3·sell(k−1)` y `buy(k) ≥ medL`, `close ≥ (high+low)/2` ⇒
       largo, stop en el nivel más bajo del apilamiento − tick (simétrica de venta).
     - E: `close > max(R30) + tick` y `Δ < 0` ⇒ corto, stop `high + tick` (simétrica).
     - H: `close > max(R30) + tick`, `z ≥ 2` y `cvd_t − cvd_{t−30} > 0` ⇒ largo, stop `low − tick` (simétrica).
     - I: `V ≥ 3·medV`, `high − low ≥ 2·medRng` y `signo(Δ) = signo(close−open) ≠ 0` ⇒ esa dirección, stop en
       el extremo opuesto ± tick.
   - Ventana 09:45–15:30 NY, máximo 3 eventos por sesión e hipótesis, separados ≥ 15 minutos.
   - `count_events(bars, refs, footprints=None, tick=0.25)` → `DataFrame` con índice `(hypothesis, year)` y
     columnas `events`, `cost_filter`, `tradable` (sin columnas de P&L, R, salida ni objetivo).
2. `tests/test_futures_research_a.py` (nuevo): 12 tests con velas sintéticas construidas a mano (no trades):
   por hipótesis, día con señal (assert `minute`, `side`, `stop` exactos) y día sin señal; lado simétrico;
   regla de 15 minutos (dos señales a 10 min ⇒ solo la primera); tope de 3 por sesión; ventana 09:45/15:30;
   descarte ≥ 2024-01-01; `s_c` = 22,239 con MAD = 15 exacta; `med_l` sin mirar el futuro; nombres de las
   columnas de `count_events`.

## Ficheros

- `src/tradinglab/futures/research_a.py` (nuevo)
- `tests/test_futures_research_a.py` (nuevo)
- `docs/futures/WORKER_REPORTS/FUT-C2.md` (nuevo, este informe)

## Salida literal

```text
PS E:\tl-fut-ra> .\.venv\Scripts\ruff.exe check src\tradinglab\futures\research_a.py tests\test_futures_research_a.py
All checks passed!
```

```text
PS E:\tl-fut-ra> .\.venv\Scripts\python.exe -m pytest -q tests\test_futures_research_a.py
............                                                             [100%]
12 passed in 3.24s
```

Regresión de los módulos vecinos (no modificados):

```text
PS E:\tl-fut-ra> .\.venv\Scripts\python.exe -m pytest -q tests\test_futures_orderflow.py tests\test_futures_research_b.py tests\test_futures.py
..............                                                           [100%]
14 passed in 3.82s
```

## Aviso

1. **Entrada proxy en el filtro de coste.** `count_events` no tiene cotizaciones: `cost_filter` cuenta
   `|close − stop| < 4,2` puntos usando el cierre de la vela de señal como entrada. La entrada real (ask/bid en
   `τ + L`) la pone FUT-C3. Está escrito en el docstring del módulo y de `count_events`.
2. **Lecturas de la especificación fijadas** (no se ajustan después): `sC` por minuto del día; `medL` como
   mediana del pool de las 20 sesiones previas; apilamiento de D = racha completa, y si hay apilamiento en las
   dos direcciones manda el largo.
3. **Sin datos reales.** No se ha descargado nada ni se ha calculado ningún desenlace. `count_events` solo
   cuenta eventos y filtros; cualquier P&L/R/salida queda para FUT-C3, que tampoco se ejecutará con datos
   hasta que el operador registre FUT-RA-1 (OP-4/OP-7 pendientes).
4. **`D` sin footprint** no se cuenta (**Sin datos**), no se inventa una fila.
5. `TICK = 0.25` (NQ/MNQ) y `COST_STOP_POINTS = 4.2` fijados como constantes del módulo.

## Siguiente

P1b · FUT-C3: evaluador único (`research_a_eval.py`) con fills L1b, latencia y criterios de `RA_spec.md` §7,
usando `research_a.detect` sin modificarlo.
