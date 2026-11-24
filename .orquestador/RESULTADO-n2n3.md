# RESULTADO · COLA-N2N3 — cestas + informes

Fecha: 2026-11-24. Rama de trabajo `wip/basket-20261124` (base `ec3ffbf`,
auditoría maestra), worktree `E:\trading-lab-n2n3`. La rama principal
`feature/prop-fund-multifirm` tiene cambios del operador en curso y **no se
tocó**.

Cumplido: sin register/approve/run/confirm/supersede de campañas reales, sin
leer OOS-2, sin calcular rendimiento de specs no aprobadas, sin push, sin
tareas programadas, sin borrar, sin umbrales, sin protegidos, sin carril del
EA, sin operar, sin descargar. `pytest -q` completo se ejecutará una sola vez
al final.

## N2 · Ejecución de campañas de cesta

### Qué se cableó

- **Registro** (`basket.register`, invocado desde
  `campaigns.register_from_spec` cuando la spec declara `basket:`):
  - una sola campaña; `n_total` = combinaciones de la rejilla (18 en
    `q3-tsmom-cesta-d1`), **no** combinaciones × símbolos;
  - un snapshot por símbolo (`<id>__<SYMBOL>.parquet`) y `dataset_hash`
    combinado estable; el `config_hash` incluye la cesta, los símbolos, sus
    fuentes y el coste por símbolo;
  - calidad por símbolo y OOS-2 resuelto al último cierre común.
- **Preflight** (`engine.preflight`): detecta la cesta y valida cada
  combinación en cada símbolo; informe `instrument=BASKET`, población =
  combinaciones.
- **Aprobación** (`campaigns.approve`): usa el preflight y la viabilidad de
  cesta; no se relajó ningún umbral.
- **Viabilidad** (`feasibility.check`): `basket.check_campaign` calcula solo
  operaciones, pliegues, coste/swap y tiempo; **no** llama a
  `metrics.summarize` (test específico lo impide).
- **Ejecución** (`engine.run_campaign` → `basket.run_campaign`, solo campaña
  aprobada):
  - por combinación, una pierna por símbolo con el mismo genoma; R agregado
    por fecha; coste y swap por símbolo/cuenta con `swap_credit=false` (de
    `engine.yaml`);
  - pliegues globales sobre el calendario de sesiones del IS común;
  - control de deriva por cesta: réplicas por símbolo con semilla estable y
    mezcla de lados de las operaciones reales, agregadas por operaciones;
  - OOS-1 por cesta; OOS-2 sigue sellado y se lee una sola vez por estrategia
    (`read_holdout` devuelve las piernas de la cesta y registra la lectura);
  - el guard `require_approved_campaign` corta antes de calcular rendimiento.
- **Resultados**: `discovery results` funciona con la cesta y añade la línea
  `Cesta: ...`; `results.campaign_results` lee las métricas agregadas y la
  atribución por símbolo.

### Cambios auxiliares

- `fastbt.Trade` conserva `selected_account` e `instrument`; `CostBook.apply`
  rellena la cuenta elegida por operación. Así la cesta puede agregar
  `cost_by_account` sin inventar una cuenta media.
- `read_holdout` acepta `frames` para tests sintéticos y devuelve un dict
  `{símbolo: barras}` en campañas de cesta.
- No se tocó ningún archivo del manifiesto protegido.

### Tests nuevos

`tests/test_discovery_basket_run.py` (8 tests, datos sintéticos y DB temporal):

1. `n_total` = 4 con 2 símbolos y rejilla 2×2; snapshots por símbolo;
   preflight 4/4 y viabilidad 4/4.
2. Cesta con ventaja conocida (cambio de mes sintético): run completo por
   `engine.run_campaign`, 4/4 evaluadas, finalistas ≥ 1, OOS-1 positivo.
3. `approve(verify=True)` ejecuta preflight y viabilidad de cesta.
4. Cesta sin ventaja: 0 finalistas y neto IS ≤ 0.
5. Guard: una cesta en borrador no calcula rendimiento
   (`UnapprovedPerformanceError`) y no deja estrategias.
6. Viabilidad no calcula expectativa/PF (monkeypatch a `metrics.summarize`).
7. Con `cost_mode: best`, la viabilidad de cesta cubre **las dos** cuentas
   (CFD-001 y CFD-006), no solo la elegida por operación.
8. OOS-2 de cesta: primera lectura devuelve los dos símbolos; la segunda
   falla.

### Comprobaciones de N2

- `ruff check src/tradinglab tests`: limpio.
- `tests/test_discovery_basket_run.py`: **8 passed** (incluye el caso `best`
  con las dos cuentas).
- Regresión dirigida: basket, costs, engine, feasibility, spec, parity,
  fastbt, drift, fitness, results, count, segments y guard: **126 passed**.
- `discovery register --spec q3-tsmom-cesta-d1.yaml --dry-run`: **n_total 18**,
  `dataset_hash` combinado, OOS-2 fin 2026-11-19T22:00Z, calidad `warn`;
  **no escribió nada**.
- `discovery feasibility --spec q3-tsmom-cesta-d1.yaml`: **17/18 factibles**,
  ops IS 29–43, `cost_R` 0,0528–0,1031 (idéntico a Q3; solo operaciones y
  coste, sin PnL).
- No se registró, aprobó ni ejecutó `q3-tsmom-cesta-d1`.

### Aviso de la enmienda del operador

`.orquestador/PLAN-BUSQUEDA.md` contiene una enmienda sin commit del
2026-11-24 que **pausa las campañas, incluida Q3**, hasta cerrar la auditoría
TL2 (fase 0 y costes T10–T13). No se tocó ni se commiteó esa enmienda. Los
cuatro comandos de Q3 quedan al final de este documento, pero **no deben
ejecutarse** hasta que el operador cierre la auditoría. La auditoría también
señala un posible doble spread en salidas no-target: el cableado de cesta usa
la cadena de coste actual y no la modifica.

Commit: `tl2: N2 - run de cestas` · tag `tl2-noche2-n2`.
Fix de coste por cuenta (se agregan **todas** las cuentas de la cesta, no solo
la elegida por `best`): commit `tl2: N2 - coste por cuenta de toda la cesta`,
incluido en el mismo tag `tl2-noche2-n2`.

## N3 · Informes cortos de las 7 campañas

Solo lectura del databank (`IS` y el `OOS-1` que el pipeline ya leyó). No se
leyó OOS-2, no se registró ni ejecutó ninguna campaña y no se propone ninguna
variante ni re-optimización.

### Informes

Siete archivos de una página en `reports/discovery/`:

`q2-fix-usdjpy-h1.md`, `q2-fix-eurusd-h1.md`, `q2-fix-gbpusd-h1.md`,
`r9-tom-us500-d1.md`, `r9-tom-us100-d1.md`, `q1-rebote-us500-d1.md`,
`q1-rebote-us100-d1.md`.

| Campaña | Veredicto | Bruto (R) | Coste (R) | Neto (R) | Deriva | Ops | Pliegues |
|---|---|---|---:|---:|---:|---:|---:|
| q1-rebote-us500-d1 | sin edge bruto | −0,0539 | 0,0515 | −0,1257 | 0,8–68,2 | 2–38 | 0–2/3 |
| q1-rebote-us100-d1 | muestra insuficiente (OOS-1 0 ops) | 0,1504 | 0,0103 | 0,1361 | 26,0–99,9 | 2–75 | 0–3/3 |
| q2-fix-usdjpy-h1 | edge bruto que el coste elimina | −0,0018 | 0,0410–0,0498 | −0,0476 | 19,3–47,2 | 3.771 | 0/4 |
| q2-fix-eurusd-h1 | edge bruto que el coste elimina | 0,0234 | 0,0327–0,0359 | −0,0133 | 100,0 | 3.764 | 0–1/4 |
| q2-fix-gbpusd-h1 | edge bruto que el coste elimina | 0,0128 | 0,0315–0,0362 | −0,0227 | 100,0 | 3.763 | 0/4 |
| r9-tom-us500-d1 | no válido: anclaje D1 desplazado | No se analiza | No se analiza | No se analiza | No se analiza | No se analiza | No se analiza |
| r9-tom-us100-d1 | no válido: anclaje D1 desplazado | No se analiza | No se analiza | No se analiza | No se analiza | No se analiza | No se analiza |

Las cifras de q1/q2 son medianas de la rejilla y rangos; el detalle de la
mejor combinación está en cada informe. Los dos `r9-tom-*` dicen literalmente
«ejecutadas con el anclaje D1 antiguo (desplazado); resultado no válido;
sustituidas por r9b-tom» y **no** analizan su rendimiento, como pedía la cola.

### Bruto por año y por cuenta (solo el fix de Londres)

Para las tres campañas `q2-fix-*` se recalculó **solo el bruto** desde el
snapshot congelado (mismo compilador y mismas barras; sin coste) para partir
2010–2024 por año. El bruto recalculado coincide con el bruto almacenado dentro
del ~10 %. El coste y el neto que se muestran por cuenta son los **almacenados
por la campaña** (mediana por cuenta); no se reescribe nada.

Coste de equilibrio para neto > 0 (bruto de la mejor combinación):

| Campaña | Coste de equilibrio (R) | bps | pips ida y vuelta | Coste almacenado (R) |
|---|---:|---:|---:|---:|
| q2-fix-usdjpy-h1 | 0,0052 | 0,23 | 0,25 | 0,041–0,048 |
| q2-fix-eurusd-h1 | 0,0234 | 1,04 | 1,24 | 0,033–0,035 |
| q2-fix-gbpusd-h1 | 0,0120 | 0,64 | 0,90 | 0,028–0,036 |

Las tablas por año 2010–2024 están en cada informe. Es información descriptiva,
no una propuesta: el coste tendría que caer ~30–72 % (según el par) para que el
neto fuese > 0 con el bruto actual.

### Edge Map

`reports/discovery/edge_map.md` lleva una sección nueva «Hipótesis probadas
(2026-11-24)» que marca:

- **H1 cambio de mes** (`turn_of_month`, US500/US100 D1): probada con
  `r9b-tom-*`; `r9-tom-*` archivadas por anclaje.
- **H2 fix de divisas** (`fix_reversal`, USDJPY/EURUSD/GBPUSD H1): probada;
  edge bruto que el coste elimina.
- **H4 rebote tras ventas** (`d1_extension_reversion`, US500/US100 D1):
  probada; US500 sin edge bruto; US100 muestra insuficiente.

Comprobado con `edge_map.suggest` (22 filas): ninguna de las 7 combinaciones
plantilla × mercado × TF probadas vuelve a aparecer. La misma plantilla en
**otros** mercados sigue como «por probar»; eso no es una re-optimización de lo
ya visto. La hipótesis 3 (cesta) no se marca como probada: está pausada por la
enmienda de auditoría y no se ha registrado.

### Comprobaciones de N3

- Los 7 informes existen y usan solo datos del databank y del snapshot IS.
- No se leyó OOS-2; no se registró, aprobó ni ejecutó ninguna campaña.
- No se tocaron specs, umbrales, campañas ni el contador.
- `suggest` no repropone las 7 combinaciones probadas.
- `reports/discovery/edge_map.md` actualizado solo con la sección de hipótesis
  probadas; la tabla histórica del 2026-11-22 se conserva.

Commit: `tl2: N3 - informes campañas 23-nov` · tag `tl2-noche2-n3`.

## Cierre

- `ruff check src/tradinglab tests`: limpio.
- `pytest -q --basetemp E:\pytest-tmp-n2n3-final`: **1798 passed, 1
  skipped, 6 failed** (1:51:09). Los 6 fallos son de **entorno del worktree**,
  no de N2/N3:
  - 5 en `tests/test_ea_forward.py` por el hash congelado del EA: el worktree
    limpio tiene LF (`.gitattributes eol=lf`) y el hash esperado se calculó con
    CRLF. En el checkout del operador (CRLF) los **12 tests pasan**; en el
    worktree, igualando temporalmente los 9 archivos del EA a CRLF, también
    **12 passed**. Se revirtió y no se commiteó ningún cambio del carril EA.
  - 1 en `tests/test_optimize.py` porque al worktree le faltaban los
    `reports/` no versionados que alimentan `dsr_global`; tras copiarlos,
    **1 passed**. No es código.
- `lab propfund verify`: **4 OK** (ai_trader, ea_us100_ftmo1, ftmo_forward,
  ftmo_risk).
- `count_tests`: **1883** (sin cambios; no se registró nada).
- `git status`: limpio salvo los commits de N2/N3.
- Tags: `tl2-noche2-n2` (N2, incluye el fix de coste por cuenta) y
  `tl2-noche2-n3` (informes).

## N2N3 TERMINADA

## Comandos pendientes del operador (NO ejecutados)

> Pausa por la auditoría TL2 (enmienda del 2026-11-24): **no ejecutar Q3**
> hasta cerrar la fase 0 y T10–T13. El dry-run y la viabilidad ya están
> verificados; no se registró nada.

```powershell
cd E:\trading-lab
.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/q3-tsmom-cesta-d1.yaml
.\.venv\Scripts\lab.exe discovery approve q3-tsmom-cesta-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run q3-tsmom-cesta-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results q3-tsmom-cesta-d1
```

> La deuda de 18 miradas de Q3 (`lab learning record-informal --n 18
> --reason "Q3: rendimiento calculado antes de aprobar" --approved-by-operator`)
> sigue pendiente y **no se ejecutó**; cambiaría el contador de 1883 a 1901.
