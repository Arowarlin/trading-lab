# RESULTADO · COLA-RÁPIDA — Q1, Q2 y Q3

Fecha: 2026-11-23. Misma sesión que R9c, después de `5e0130b` (`tl2-r9c`).
Solo preflight/feasibility (operaciones, pliegues y coste con swap). Sin
register/approve/run/confirm/supersede, sin OOS, sin push, sin descargar, sin
operar y sin tocar protegidos.

## Q1 · Hipótesis 4 — rebote tras ventas fuertes

Specs (sin código nuevo; `d1_extension_reversion` ya es long-only):

- `q1-rebote-us500-d1.yaml`: US500 D1, Dukascopy, IS 2018-01-01…2024-06-30,
  CFD-006 target.
- `q1-rebote-us100-d1.yaml`: US100 D1, Dukascopy, IS 2014-01-01…2024-06-30,
  CFD-001/CFD-006 best.

Hipótesis literal en ambas specs: "Tras una caída extrema de corto plazo en un
índice que sigue en tendencia larga, el precio rebota en los días siguientes
porque la caída es sobrerreacción y liquidez, no un cambio de régimen. Comprar
la extensión debe superar el coste de una operación de varios días y ser
estable en los tres pliegues." Referencia: Boyarchenko, Larsen & Whelan (2023),
reversión asimétrica tras ventas fuertes.

Preflight: 27/27 válidos en cada spec (3 z_n × 3 z_entry × 3 stop_mult).

Feasibility (cost_R con swap R9c):

| Spec | Factibles | Ops IS | Cost_R |
|---|---:|---|---:|
| US500 | 15/27 (55,6 %) | 2–38 | 0.0306–0.0744 |
| US100 | 18/27 (66,7 %) | 2–75 | −0.5359–−0.0833 |

El US100 negativo es el crédito de swap largo de FTMO; no es un error de
coste. Las combinaciones con <15 ops IS o <3 por pliegue quedan fuera.

Commit `tl2: Q1 - specs rebote`, tag `tl2-q1`.

## Q2 · Hipótesis 2 — reversión alrededor de los fix

Plantilla nueva `fix_reversal` (H1), `symmetric: false`. Hipótesis literal:
"El dólar se aprecia antes de los fix WM/Reuters y revierte después, porque el
flujo de órdenes que mueve el precio antes de la fijación es temporal. Si es
real, entrar contra el dólar al cierre de la barra del fix y salir tras 1-3
horas supera el coste de un ida y vuelta intradía." Referencia: Krohn, Mueller
& Whelan (2024), *Journal of Finance*, DOI 10.1111/jofi.13306.

Reglas implementadas: `side` fijo por spec; `fix_start`/`fix_end` fijan la
barra. Tokio 09:00–09:59 JST (fix 09:55) para USDJPY, lado **corto**; Londres
15:00–15:59 (fix 16:00) para EURUSD/GBPUSD, lado **largo**. Entrada al open
siguiente (= cierre de la barra del fix), salida por tiempo M ∈ {1,2,3} h,
stop 2,5/3,0 ×ATR(14), sin target. 6 combinaciones por spec.

Tests nuevos (`tests/test_discovery_fix_reversal.py`, 5 passed): lado fijo,
6 combinaciones, fix de Londres invierno (15:00 UTC) y verano (14:00 UTC),
desfase DST Londres/NY, Tokio sin DST (00:00 UTC), sin anticipación y entrada
exacta al cierre (16:00 Londres).

Specs:

| Spec | n_total | Preflight | Feasibility | Ops IS | Cost_R |
|---|---:|---|---:|---|---:|
| `q2-fix-usdjpy-h1` | 6 | 6/6 | 6/6 | 3.771 | 0.0330–0.0415 |
| `q2-fix-eurusd-h1` | 6 | 6/6 | 6/6 | 3.764 | 0.0327–0.0392 |
| `q2-fix-gbpusd-h1` | 6 | 6/6 | 6/6 | 3.763 | 0.0285–0.0378 |

Commit `tl2: Q2 - plantilla fix_reversal`, tag `tl2-q2`.

## Q3 · Hipótesis 3 — momentum de serie temporal en cesta

Implementación mínima en `src/tradinglab/discovery/basket.py`:

- `combine_daily`: suma R por fecha entre símbolos.
- `basket_percentile`: percentil de la cesta a partir de los drift por símbolo
  (ponderado por operaciones). Es rendimiento y pasa por
  `guard.require_approved`; no se usa en feasibility.
- `check_spec`: preflight/feasibility de cesta; solo operaciones, pliegues,
  coste con swap y tiempo medio. **Sin expectativa, PF ni percentil.**
- Preflight/feasibility de cesta cableados en `engine.preflight_spec` y
  `feasibility.check_spec` cuando la spec declara `basket`.

Spec `q3-tsmom-cesta-d1.yaml`: `ts_momentum_d1` en XAUUSD, US500, US100,
EURUSD, GBPUSD y USDJPY (Dukascopy), IS común 2018-01-01…2024-06-30, 18
combinaciones (2 fast × 3 slow × 3 stop), coste/swap por símbolo y cuenta.
Hipótesis literal en el YAML (Moskowitz/Ooi/Pedersen 2012; Hurst/Ooi/Pedersen
2017). n_total = 18, no 18 × 6.

Preflight: 18/18 válidos. Feasibility: **17/18**; ops IS 29–43 por cesta;
cost_R 0.0528–0.1031; una combinación (fast 50 / slow 250 / stop 2,5) supera
0,10 y queda fuera.

### Incidente Q3 (rendimiento antes de aprobar)

El comando de comprobación de Q3 (`python -c "from tradinglab.discovery import
basket…"`) imprimió literalmente:

```text
n 17 / 18 pct 94.4 passes True
0 fast_n=50 slow_n=150 stop=2.5 ops 41 folds [8, 9, 8] cost_r 0.0897 feasible True []
1 fast_n=50 slow_n=150 stop=3.0 ops 41 folds [9, 9, 8] cost_r 0.0747 feasible True []
2 fast_n=50 slow_n=150 stop=3.5 ops 41 folds [9, 9, 8] cost_r 0.0641 feasible True []
3 fast_n=50 slow_n=200 stop=2.5 ops 38 folds [9, 9, 8] cost_r 0.0528 feasible True []
4 fast_n=50 slow_n=200 stop=3.0 ops 36 folds [8, 9, 7] cost_r 0.0707 feasible True []
5 fast_n=50 slow_n=200 stop=3.5 ops 36 folds [8, 9, 7] cost_r 0.0658 feasible True []
6 fast_n=50 slow_n=250 stop=2.5 ops 31 folds [6, 6, 7] cost_r 0.1031 feasible False ['coste_R 0.1031 > 0.1000']
7 fast_n=50 slow_n=250 stop=3.0 ops 31 folds [6, 6, 7] cost_r 0.0985 feasible True []
8 fast_n=50 slow_n=250 stop=3.5 ops 31 folds [6, 6, 7] cost_r 0.0844 feasible True []
9 fast_n=100 slow_n=150 stop=2.5 ops 43 folds [9, 10, 8] cost_r 0.0567 feasible True []
10 fast_n=100 slow_n=150 stop=3.0 ops 42 folds [10, 9, 8] cost_r 0.0621 feasible True []
11 fast_n=100 slow_n=150 stop=3.5 ops 42 folds [10, 10, 7] cost_r 0.0565 feasible True []
12 fast_n=100 slow_n=200 stop=2.5 ops 34 folds [6, 7, 8] cost_r 0.0764 feasible True []
13 fast_n=100 slow_n=200 stop=3.0 ops 34 folds [6, 7, 8] cost_r 0.0646 feasible True []
14 fast_n=100 slow_n=200 stop=3.5 ops 34 folds [6, 7, 8] cost_r 0.0601 feasible True []
15 fast_n=100 slow_n=250 stop=2.5 ops 29 folds [4, 6, 6] cost_r 0.0853 feasible True []
16 fast_n=100 slow_n=250 stop=3.0 ops 29 folds [4, 6, 6] cost_r 0.0718 feasible True []
17 fast_n=100 slow_n=250 stop=3.5 ops 29 folds [4, 6, 6] cost_r 0.0758 feasible True []
```

No imprimió expectativa, PF ni percentil. **Pero `_run_combo` los calculaba
internamente** con `metrics.summarize` antes de aprobar, aunque feasibility no
los devolviera. Es una violación del guard de R9b. Se corrigió: feasibility usa
`CostBook.apply` y `fastbt.run(collect_metrics=False)`, sin `summarize`, y el
test `test_feasibility_cesta_no_calcula_expectativa` falla si se llama a
`metrics.summarize`. No se usaron esos valores ni se tocó la spec de Q3 después
de ver el resultado.

Deuda pendiente para el operador (NO ejecutada):

```powershell
.\.venv\Scripts\lab.exe learning record-informal --n 18 --reason "Q3: rendimiento calculado antes de aprobar" --approved-by-operator
```

`count_tests` sigue en 1775 hasta que el operador ejecute esa anotación
(pasaría a 1793).

### Límite de Q3

`run`/`register` de una campaña de cesta **no están cableados** en el motor:
solo preflight/feasibility. No se incluyen comandos de ejecución para Q3 porque
fallarían; queda como fase pendiente. Esto es una parada consciente, no un
resultado de rendimiento.

Tests: `tests/test_discovery_basket.py` (5 passed) para agregación, percentil
con guard, carga de cesta y ausencia de expectativa/PF en feasibility.

Commit `tl2: Q3 - campañas multi-símbolo`, tag `tl2-q3`.

## Cierre de la cola

Verificación final:

- `ruff check src/tradinglab tests docs`: limpio.
- `pytest -q`: **1789 passed, 1 skipped**.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1775** (la anotación Q3 de 18 miradas queda pendiente y
  **no se ha ejecutado**; pasaría a 1793).
- Sin register/approve/run, sin OOS, sin push, sin descargar.

### Tabla de specs listas

| Orden | Spec | n_total | Ops IS | Cost_R | Estado |
|---|---|---:|---|---:|---|
| 1 | `q1-rebote-us500-d1` | 27 | 2–38 | 0.0306–0.0744 | 15/27 factibles |
| 2 | `q1-rebote-us100-d1` | 27 | 2–75 | −0.5359–−0.0833 | 18/27 factibles |
| 3 | `q2-fix-usdjpy-h1` | 6 | 3.771 | 0.0330–0.0415 | 6/6 factibles |
| 4 | `q2-fix-eurusd-h1` | 6 | 3.764 | 0.0327–0.0392 | 6/6 factibles |
| 5 | `q2-fix-gbpusd-h1` | 6 | 3.763 | 0.0285–0.0378 | 6/6 factibles |
| 6 | `q3-tsmom-cesta-d1` | 18 | 29–43 | 0.0528–0.1031 | 17/18 factibles; solo preflight/feasibility |

### Comandos del operador (NO ejecutados)

```powershell
cd E:\trading-lab

# Q1 — rebote
.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/q1-rebote-us500-d1.yaml
.\.venv\Scripts\lab.exe discovery approve q1-rebote-us500-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run q1-rebote-us500-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results q1-rebote-us500-d1

.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/q1-rebote-us100-d1.yaml
.\.venv\Scripts\lab.exe discovery approve q1-rebote-us100-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run q1-rebote-us100-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results q1-rebote-us100-d1

# Q2 — fix reversal
.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/q2-fix-usdjpy-h1.yaml
.\.venv\Scripts\lab.exe discovery approve q2-fix-usdjpy-h1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run q2-fix-usdjpy-h1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results q2-fix-usdjpy-h1

.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/q2-fix-eurusd-h1.yaml
.\.venv\Scripts\lab.exe discovery approve q2-fix-eurusd-h1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run q2-fix-eurusd-h1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results q2-fix-eurusd-h1

.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/q2-fix-gbpusd-h1.yaml
.\.venv\Scripts\lab.exe discovery approve q2-fix-gbpusd-h1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run q2-fix-gbpusd-h1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results q2-fix-gbpusd-h1
```

Q3 **no tiene comandos ejecutables**: `register/approve/run` de cesta no están
cableados; solo preflight/feasibility. Se deja para una fase posterior.

### Deuda de contador Q3 (NO ejecutada)

```powershell
.\.venv\Scripts\lab.exe learning record-informal --n 18 --reason "Q3: rendimiento calculado antes de aprobar" --approved-by-operator
```

PARA.
