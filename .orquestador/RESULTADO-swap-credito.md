# RESULTADO · swap-credito — los créditos no cuentan en discovery

Fecha: 2026-11-23. Sesión única en `E:\trading-lab`, HEAD `566ae30` (`tl2-q3`).
Sin register/approve/run, sin OOS, sin rendimiento no aprobado, sin push, sin
tareas programadas, sin borrar, sin tocar protegidos y sin operar.

## 1. Decisión

`discovery.swap_credit: false` en `config/discovery/engine.yaml`. En discovery
un swap **positivo** (crédito de financiación) cuenta como 0; solo el swap
negativo es coste. Motivo: el swap medido hoy (2026-11-23) aplicado a todo el
histórico 2010-2024 mezcla tipos de interés de épocas distintas y, con
`cost_mode: best`, el crédito de FTMO puede convertir una estrategia larga en
“ganadora” por financiación, no por mercado. La capa de empresa/onboarding
puede seguir mostrando el crédito real como información separada.

Implementación:

- `src/tradinglab/propfund/costs.py`: `SwapSpec.per_night_r`/`r` aceptan
  `allow_credit`; si es `False`, un valor positivo se devuelve como 0. El
  fallback de empresa (`estimate_cfd`, `SwapSpec.total_usd`) mantiene el
  crédito real por defecto.
- `src/tradinglab/discovery/fastbt.py`: `CfdProfileCosts` lee
  `load_engine_config().discovery.swap_credit` y lo pasa al ajustar `Trade`;
  `swap_r` queda 0.0 si el swap era crédito.
- `src/tradinglab/discovery/costs.py`: `CostBook` aplica el mismo flag por
  cuenta antes de elegir best/worst/target; afecta a `cost_R` y a la selección.
- `src/tradinglab/discovery/drift.py`: el control de deriva usa el flag al
  valorar las entradas aleatorias.
- `src/tradinglab/propfund/onboarding_mtf.py`: añade
  `swap_credit_r_night` (largo/corto) y una línea de informe:
  “Crédito de swap no contado en discovery: … R/noche”. No se usa para
  seleccionar.

## 2. Tests

- `tests/test_discovery_swap.py`: 11 passed. Incluye:
  - largo US100 FTMO → `swap_r == 0.0` y `r_cost` solo con spread/comisión;
  - largo US100 CFD-006 → swap negativo aplicado;
  - corto US100 FTMO → swap negativo aplicado;
  - `CostBook` target con crédito → 0;
  - config por defecto `swap_credit=False`.
- `tests/test_propfund_onboarding_mtf.py`: el crédito real aparece en
  `swap_credit_r_night` pero no en `cost_r`.
- `pytest -q` completo: **1794 passed, 1 skipped**.

## 3. Coste recalculado (solo feasibility)

Sin tocar rendimiento ni campañas. `cost_R` antes/después:

| Spec | Antes | Después | Factibles |
|---|---|---|---:|
| `r9-tom-us500-d1` | 0.0316–0.0638 | **0.0316–0.0638** | 9/9 |
| `r9-tom-us100-d1` | −0.2626–−0.0587 | **0.0085–0.0093** | 9/9 |
| `q1-rebote-us500-d1` | 0.0306–0.0744 | **0.0306–0.0744** | 15/27 |
| `q1-rebote-us100-d1` | −0.5359–−0.0833 | **0.0070–0.0302** | 18/27 |

El US100 deja de tener coste negativo: el crédito de FTMO ya no compensa el
coste. El US500 no cambia porque CFD-006 cobra swap negativo. No se recalculó
ninguna expectativa, PF ni percentil.

## 4. Verificación

- `ruff check src/tradinglab tests docs`: limpio.
- `pytest -q`: **1794 passed, 1 skipped**.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1775** (la anotación Q3 de 18 miradas sigue pendiente y no
  se ha ejecutado).
- Sin push, sin campañas, sin OOS, sin órdenes.

## Commits y tag

```text
4d6f2c0  tl2: swap - créditos no cuentan en discovery  (tl2-swap-credito)
```

## Avisos

- El flag es de discovery; la capa de empresa conserva el crédito real como
  información. No se usa para seleccionar.
- Las cifras `cost_R` de US100 cambian de signo; es el efecto buscado, no un
  error de coste.
- La deuda Q3 (`record-informal --n 18`) sigue preparada, no ejecutada.

PARA.
