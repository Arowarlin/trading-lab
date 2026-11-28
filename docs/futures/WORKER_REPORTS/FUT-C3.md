# FUT-C3 · Research A: evaluador único (fills L1b, R neta y criterios §7)

**Fecha:** 2026-11-28 · **Modelo:** DeepSeek V4.1 Flash (OpenCode Go) · **Worktree:** `E:\tl-fut-ra`
(rama `fut-ra`) · **Carril:** P1b.

## Hecho

1. `src/tradinglab/futures/research_a_eval.py` (nuevo):
   - `Spec` (frozen): `tick=0.25`, `point_value=2.0` (MNQ), `commission_side=0.75`, `latency_s=0.5`,
     `size=1`, `hold_s=900`, `target_r=1.5`, `slip_ticks=0`.
   - `simulate(ev, quotes, trades, spec)` → dict o `None` (Sin datos). `t_señal` = cierre de la vela del
     evento (`minute + 60 s`); entrada a mercado en `t_señal + L` al ask (largo) / bid (corto), con 1 tick
     peor si el tamaño no cabe en el mejor nivel; stop disparado por el primer trade en el stop o más allá,
     llenado al bid (largo) / ask (corto) en `t_disparo + L`; objetivo 1,5 R solo si un trade lo atraviesa
     1 tick (fill al límite); salida por tiempo a los 15 minutos de la entrada; mismo segundo → gana el stop.
   - `R_net = (dir·(salida − entrada)·2 − 2·comisión − 2·slip·tick·punto) / (|entrada − stop|·2)`.
   - `cr1_t(x, sessions)`: t de la media con `Var = G/(G−1)·Σ_g S_g²/n²` (agrupado por sesión).
   - `verdict(...)`: orden literal de `RA_spec.md` §7 — (a) `rechazada`; (b) `rechazada por costes`;
     (c) `rechazada por latencia`; (d) `inconclusa`; si no, `candidata` / `candidata, no monetizable todavía
     en prop`. `Sin datos` con `n < 2` o t no calculable.
   - `evaluate(bars, refs, footprints, hypothesis, quotes, trades, t_crit, split, mu_star_r=0.08, spec)`:
     usa `research_a.detect` (sin modificarlo) y evalúa base, estrés de coste (+1 tick por lado) y estrés de
     latencia (L = 1 s). Devuelve `n`, `dropped`, medias, `t_cr1`, `t_crit`, medianas y veredicto; añade la
     nota de (e) `no operable en firmas con reglas de microscalping` si la mediana del tiempo en posición
     < 30 s. Las cotizaciones y los trades se preparan una vez (no por evento).
2. `tests/test_futures_research_a_eval.py` (nuevo): 9 tests con cotizaciones y trades sintéticos:
   entrada al ask en `t+L`; stop disparado por trade y llenado al bid (ignorando la cotización anterior a
   `t_disparo+L`); objetivo tocado sin atravesar → no se llena y, con 1 tick de través, fill al límite; mismo
   segundo → stop; corto (entrada al bid, stop al ask); regla de tamaño (1 tick peor); `cr1_t` de
   `[2, 2, 0, 0]` por sesiones = 1,0 exacto; los seis veredictos de §7 en orden; end-to-end con dos sesiones.

## Ficheros

- `src/tradinglab/futures/research_a_eval.py` (nuevo)
- `tests/test_futures_research_a_eval.py` (nuevo)
- `docs/futures/WORKER_REPORTS/FUT-C3.md` (nuevo, este informe)

## Salida literal

```text
PS E:\tl-fut-ra> .\.venv\Scripts\ruff.exe check src\tradinglab\futures\research_a_eval.py tests\test_futures_research_a_eval.py
All checks passed!
```

```text
PS E:\tl-fut-ra> .\.venv\Scripts\python.exe -m pytest -q tests\test_futures_research_a_eval.py
.........                                                                [100%]
9 passed in 0.62s
```

Conjunto P1 (C2 + C3):

```text
PS E:\tl-fut-ra> .\.venv\Scripts\python.exe -m pytest -q tests\test_futures_research_a_eval.py tests\test_futures_research_a.py
.....................                                                    [100%]
21 passed in 4.16s
```

## Aviso

1. **Estrés de coste (criterio b).** «+1 tick por lado» se aplica como coste (`2·tick·punto`) manteniendo el
   riesgo base `|entrada − stop|`, igual que `research_b.outcome(slip_ticks=1)`; es la lectura equivalente a
   1 tick adverso en cada precio base sin mover el denominador.
2. **Salida por tiempo** a los 15 minutos del **fill de entrada**; los trades que pueden disparar stop u
   objetivo son los de `[entrada, entrada + 15 min)`.
3. **Sin cota de espera en la cotización:** se usa la primera cotización con `ts_event ≥ t` (la cobertura de
   §2, ≥ 99 % de los segundos RTH, es la que lo garantiza). Un evento sin cotización en cualquiera de los tres
   escenarios queda **Sin datos** y se cuenta en `dropped`.
4. **Sin datos reales.** No se ha descargado nada ni se ha ejecutado el evaluador con datos de mercado. La
   primera ejecución real espera a que el operador registre FUT-RA-1 (OP-4/OP-7 pendientes).
5. **No se tocaron** `README.md`, `PLAN.md`, `research_a.py` ni `orderflow.py`: la tarea limita los ficheros.
   `AGENTS.md` pide actualizar README/PLAN por bloque; queda pendiente para la sesión que tenga el lock
   `readme-plan`.
6. `point_value = 2 USD/punto` y `commission_side = 0.75 USD` son los datos del operador; OP-7 debe aclarar
   si la comisión incluye exchange, clearing y NFA (si no, se suman antes de registrar).

## Siguiente

Carril P1 terminado (P1a y P1b en verde). Sigue la cadena S en el PC del operador (S1 verificación) y los
carriles P2 (`E:\tl-fut-data`) y P3 (`E:\tl-fut-mcp`). Antes de cualquier lectura real: OP-4 y OP-7.
