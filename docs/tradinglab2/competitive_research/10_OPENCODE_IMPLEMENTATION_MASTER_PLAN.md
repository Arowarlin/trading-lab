# 10 · Plan maestro para OpenCode

**Modelo:** DeepSeek V4.1 Flash (OpenCode Go). Una sesión nueva por fase. Se aplica siempre el BLOQUE COMÚN de
`docs/tradinglab2/10_TRADINGLAB_OPENCODE_EXECUTION_PROMPT.md` (con la excepción vigente: `pytest -q` sin
`--basetemp`).

## Reglas transversales

1. Nada se edita en archivos protegidos (`config/propfund/protected_manifest.json`); `lab propfund verify`
   en cada cierre.
2. Ninguna fase lee OOS-2 salvo `levels.confirm`.
3. Pruebas de perturbación, retests y transfer **no suman al DSR** y se marcan `informative` o
   `falsification`; las campañas nuevas sí, al aprobarse.
4. Umbrales nuevos en `config/discovery/engine.yaml`, nunca en código; se guardan en la campaña (hash de
   perfil).
5. Migraciones de `data/discovery.db` aditivas (ALTER/CREATE IF NOT EXISTS), nunca destructivas.
6. Commit con rutas explícitas y tag `tl2-<fase>` solo tras "commit" del operador. Sin push.
7. Rollback: `git reset --hard <tag anterior>` solo con autorización; `discovery.db` se copia a
   `data/backups/discovery-<fecha>.db` antes de cada migración.

## Fases

### R0 (7c + 7d)
Ya especificada en la conversación (regímenes con años disponibles, simetría, reintento, serie del EA).

### R1 · Perturbation Lab
- **Archivo:** `discovery/perturb.py`.
- **API:** `noise_test(strategy, frame, *, paths, scale_atr, seed) -> dict`,
  `delay_test(strategy, frame, *, entry_delays=(1,2), exit_delays=(1,2)) -> dict`,
  `execution_mc(strategy, frame, *, skip_frac, spread_source, slippage_pts, paths, seed) -> dict`.
- **Datos:** `load_segment(campaign,"is")` + `"oos1"` (campaña `done`); spread por hora de
  `broker_spreads`/perfil de la cuenta.
- **Ruido:** por vela, `x' = x + ε·ATR14_local`, ε ~ N(0, scale_atr) independiente para O, H, L, C; después
  reparar coherencia (H = max(O,H,L,C), L = min(...)). Semilla = semilla de campaña + offset fijo.
- **Salida:** base, mediana, p10, % de caminos con expectativa > 0, degradación relativa.
- **Gate (nivel 3):** `perturb.min_median_ratio` (0,5) y mediana > 0 en noise, delay +1 y execution MC.
- **Tests:** estrategia de control con edge sintético inyectado (sobrevive), estrategia ajustada a ruido
  (cae), determinismo, no lee OOS-2 (AST), no cambia `count_tests`.
- **CLI:** `lab discovery perturb STRATEGY_ID`.

### R2 · Datos 1c
- `discovery/fetch.py`: descarga M5 por cuenta con `AttachOnlyBroker(path=terminal_path)`, sin login ni
  `shutdown`; verifica login esperado antes y después; escribe en `data/cache/discovery/<SYMBOL>_M5.parquet`
  (nunca en `data/cache/ea/`); `data_sources` lo lee.
- CLI `lab discovery fetch SYMBOL --account CFD-001 --bars N` y después `data-check`.

### R3 · Databank v2
- Tablas: `disc_collections(id, name, created_at, rule_json)`, `disc_collection_items`, `disc_tags`,
  `disc_families(family_id, fingerprint)`; fingerprint = AST canónico sin valores numéricos.
- Clones: misma familia + correlación diaria > 0,9 entre campañas.
- `acceptance_profiles` en `engine.yaml` con nombre; hash guardado en `disc_campaigns`.
- CLI `lab discovery collections|tag|families|clones`.

### R4 · Consola (Fase 8 + addendum techain)
Rutas GET `/api/discovery/*`; vistas: campañas y presupuesto (count_tests, n_total, n_effective),
evolución por generación, databank con filtros, detalle (reglas, equity, mapas de calor de meseta,
hora × día, perturbaciones, veredicto), colecciones. Cada botón conectado o "Próximamente".

### R7 · Portfolio Lab (referencia: QuantAnalyzer Portfolio Master)
- `discovery/portfolio_lab.py`: reutiliza `portfolio.build_clusters/simulate` y
  `propfund.risk.exposure_by_underlying`. Entrada: solo estrategias de nivel ≥ 3 (o 4).
- Búsqueda de combinaciones (exhaustiva si ≤ 12 estrategias; genética si más) con restricciones: correlación
  diaria máxima, exposición por subyacente, reglas de la cuenta. Objetivo: P(pasar) y DD conjunto del MC
  del challenge, no beneficio.
- Selección con IS+OOS-1; validación con walk-forward de cartera. Cada búsqueda se registra con su número
  de combinaciones evaluadas (informe de presupuesto). Nunca lee OOS-2.
- What-if (excluir horas/días) solo como informe; prohibido aplicarlo a la estrategia.

### R7b · Demo vs backtest
- `discovery/live_drift.py`: lee operaciones cerradas de MT5 en solo lectura (AttachOnlyBroker por cuenta,
  filtrando por magic) y del registro del forward existente; las compara con la distribución esperada del
  backtest de esa estrategia (expectativa R, coste real vs modelado, slippage, frecuencia, hora de
  entrada).
- Alerta cuando la expectativa real cae fuera del intervalo del 95 % del bootstrap del backtest con un
  mínimo de 30 operaciones. Solo informa: no apaga bots ni cambia parámetros.
- CLI `lab discovery drift STRATEGY_ID|EA_ID` y panel en la consola.

### R5, R6, R8, R9
Según `docs/tradinglab2/10` (fases 9–12) más: bloques causales con test de look-ahead, `locked` en
plantillas, multi-mercado k-de-n con lista pre-declarada, contraste del simulador de challenge.

## Criterios de aceptación generales
pytest verde; `lab propfund verify` OK; prueba de ruido sintético sigue sin nivel 4; reproducibilidad de
una campaña sintética idéntica antes y después de cada fase.
