# RESULTADO · C1-informe — cerrar C1 y preparar H4/D1

Fecha: 2026-11-22. Sesión de solo lectura sobre `data/discovery.db`. No se
registró, aprobó, ejecutó, confirmó ni supersedió ninguna campaña; no se leyó
OOS-2; no se hizo push; no se tocaron tareas programadas ni umbrales.

## 1. Informe C1

Guardado en `reports/discovery/c1-asia-usdjpy-h1-long.md`.

Campaña `c1-asia-usdjpy-h1-long`: 27/27 evaluadas, 3 pruebas efectivas, 8 en
frontera, 0 finalistas, OOS-1 medio `None`. `count_tests` **1703**.

**Clasificación Edge Map: sin edge bruto.** Las 27 combinaciones pierden antes
de costes: mediana **−0,0533 R/op**, mejor **−0,0291 R/op**. El coste no es la
causa de un edge que exista y desaparezca: no hay edge bruto que eliminar.

- Bruto 27/27 negativo; neto CF1 y CF6 27/27 negativo. Mejor por neto: ID 463
  (thr 25, stop 2,5, RR 2,5), CF1 **−0,0844 R/op**, CF6 **−0,0755 R/op**.
  Mediana por neto: ID 457, CF6 −0,1170 R/op.
- `cost_R` mediano: CF1 0,0494–0,0911; CF6 0,0411–0,0763 R/op.
- Pliegues positivos: **8/108** en total; ninguna combinación pasa de 1/4.
  Edge Map cuenta 0 estrategias con ≥3/4 pliegues positivos.
- Frontera (rank 0): 443, 444, 445, 452, 453, 454, 462, 463. Las 8 tienen
  `IS completa ≤ 0`, por eso el filtro deja 0 finalistas. Las otras 19 están
  dominadas (`rank > 0`). El informe detalla el control exacto de cada una.
- Bruto anual 2010–2024 de la mejor (463) y la mediana (457): solo 2010, 2017
  y 2019 son positivos; 2022 es el peor (−0,165 / −0,190 R/op). No hay un
  régimen anual estable; no se propone re-optimizar por año.

El neto por cuenta del informe se recalcula aplicando el cost book de CFD-001 y
CFD-006 a las mismas operaciones IS. El `expectancy_r` del pipeline es el neto
de la cuenta elegida por operación en modo `best`; en 3 de 27 combinaciones
(446, 455, 459) elige CF1 en el 2–5 % de las operaciones y difiere del CF6 puro
en <0,0007 R. Está explicado en el informe.

## 2. Hipótesis marcada como probada

`edge_map._tested_keys` solo añadía la clave `(plantilla, instrumento, TF,
fuente)`. La campaña se probó con `dukascopy` y `suggest` la volvía a proponer
para `broker`. Ahora, si una campaña tiene `n_evaluated > 0`, se añade la clave
comodín `(plantilla, instrumento, TF, "*")`; `suggest` la excluye sea cual sea
la fuente.

Comprobado en lectura: `edge_map.suggest('CFD-001', allow_dukascopy=True)`
devuelve 14 filas y ya no incluye `asia_range_reversion` / USDJPY / H1.
Test: `tests/test_discovery_edge_map_tested.py::test_tested_keys_marca_hipotesis_probada_sin_fuente`.

## 3. Comando de lectura `discovery results`

Creado `src/tradinglab/discovery/results.py` y el comando:

```powershell
Set-Location E:\trading-lab
.\.venv\Scripts\lab.exe discovery results c1-asia-usdjpy-h1-long
```

Muestra ID, parámetros, operaciones, bruto R, neto R (cuenta seleccionada),
`cost_R` CF1/CF6, PF, pliegues positivos, nivel, estado, veredicto y motivo.
Abre `discovery.db` en `mode=ro`; no toca `disc_holdout_reads` y no lee OOS-2.
`--json` devuelve el mismo contenido estructurado.

También se corrigieron los bloques de comandos de
`.orquestador/RESULTADO-C1-prep.md` y `.orquestador/RESULTADO-C1-fix.md`: la
llamada posicional a `databank.list_strategies` (keyword-only) se sustituyó por
`lab discovery results`.

Tests: `tests/test_discovery_results.py` (2 tests: lectura IS y CLI).

## 4. Propuestas H4/D1 (solo papel)

Guardadas en `.orquestador/PROPUESTAS-plantillas-H4D1.md`. No se creó ninguna
plantilla en `config/discovery/templates/` ni se registró nada.

| # | Plantilla | Familia | TF | Símbolos iniciales | Params | n_total | Ops/año |
|---|---|---|---|---|---:|---:|---|
| A | `ts_momentum_d1` | momentum de serie temporal | D1 | XAUUSD, USDJPY, EURUSD, GBPUSD | 3 | 18 | 6–18 |
| B | `donchian_vol_h4` | ruptura Donchian + volatilidad | H4 | XAUUSD, USDJPY | 3 | 27 | 30–70 |
| C | `d1_extension_reversion` | reversión tras extensión | D1 | XAUUSD, EURUSD, GBPUSD | 3 | 27 | 10–36 |

Cada una incluye hipótesis y referencias, bloques DSL usados/faltantes,
parámetros con paths y valores de grid razonados, TF/símbolos viables según el
cribado de costes y riesgo de solape con `us100-trend-d1` (que no se ha tocado:
sigue `enabled: true`, magic 20261153, y su propuesta de cementerio sigue sin
aplicar).

Orden sugerido: **B primero**, porque tiene todos los bloques DSL y el coste H4
más bajo en XAU/USDJPY; A depende de un proxy de momentum (falta `roc`) y C de
un workaround de salida (falta `exit_when`). Las tres excluyen US100 de la
primera campaña para no duplicar la incubación.

H4/D1 exigen `data_source: dukascopy`. Cribado: US100, XAUUSD y USDJPY son los
más baratos; EURUSD/GBPUSD solo son claramente viables en D1; US500 solo
CFD-006; US30 sin spread.

## 5. Comprobaciones

- `pytest -q`: **1619 passed, 1 skipped** (3 tests nuevos).
- `ruff check src/tradinglab tests`: limpio.
- `lab propfund verify`: **4 OK** (ai_trader, ea_us100_ftmo1, ftmo_forward,
  ftmo_risk).
- `count_tests`: **1703** (sin cambios; no se registró ninguna campaña).
- Informe C1 leído sin OOS-1 y sin OOS-2.
- `reports/discovery/edge_map.{md,json}` regenerado en lectura: la hipótesis
  queda como `sin edge bruto`, `dataset_verified: true`, bruto mediano
  −0,05327, neto mediano −0,11697, 0 estrategias con ≥3/4 pliegues positivos.

## 6. Commit y cierre

- Commit `f62cb9a` · `tl2: C1 - informe y comando results`
- Tag `tl2-c1-informe`
- `git status --short`: solo `?? tl2-edge-map.patch` (archivo previo, sin tocar).
- `git log --oneline -3`:

```text
f62cb9a tl2: C1 - informe y comando results
89f75fb tl2: C1-fix - grid del spec en run
641124d tl2: C1-prep - registro desde spec
```

No se ejecutó ninguna campaña real, no se leyó OOS-2, no se hizo push.

PARA.
