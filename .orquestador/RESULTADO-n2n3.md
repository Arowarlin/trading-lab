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

`tests/test_discovery_basket_run.py` (7 tests, datos sintéticos y DB temporal):

1. `n_total` = 4 con 2 símbolos y rejilla 2×2; snapshots por símbolo;
   preflight 4/4 y viabilidad 4/4.
2. Cesta con ventaja conocida (cambio de mes sintético): run completo por
   `engine.run_campaign`, 4/4 evaluadas, finalistas ≥ 1, OOS-1 positivo.
3. `approve(verify=True)` ejecuta preflight y viabilidad de cesta.
4. Cesta sin ventaja: 0 finalistas y neto IS ≤ 0.
5. Guard: una cesta en borrador no calcula rendimiento
   (`UnapprovedPerformanceError`) y no deja estrategias.
6. Viabilidad no calcula expectativa/PF (monkeypatch a `metrics.summarize`).
7. OOS-2 de cesta: primera lectura devuelve los dos símbolos; la segunda
   falla.

### Comprobaciones de N2

- `ruff check src/tradinglab tests`: limpio.
- `tests/test_discovery_basket_run.py`: **7 passed** (~2 min 36 s).
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
