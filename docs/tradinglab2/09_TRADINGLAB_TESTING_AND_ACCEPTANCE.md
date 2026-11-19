# 09 · Pruebas y criterios de aceptación

## 1. Regresión (cada fase)

```powershell
cd E:\trading-lab
.\.venv\Scripts\Activate.ps1
lab propfund verify
pytest -q --basetemp E:\pytest-tmp
```
Criterio: mismos tests verdes que la línea base de la fase 0 + los nuevos; `verify` OK en los 5 grupos.

## 2. Tests nuevos obligatorios

| Test | Comprueba |
|---|---|
| `test_discovery_isolation.py` | `discovery` no importa funciones de órdenes; no escribe en tablas no `disc_*` salvo vía `campaign`/`count_tests` |
| `test_discovery_dsl.py` | AST inválidos rechazados (tipos, profundidad, nodos, autocomparación); hash estable |
| `test_discovery_lookahead.py` | Para cada bloque: alterar barras > t no cambia la salida en ≤ t; pivotes desplazados |
| `test_discovery_parity.py` | `fastbt` = `backtest_intraday` (modo serie) y = `run_event_backtest` (SL/TP, huecos, empates) |
| `test_discovery_costs.py` | CFD y futuros usan modelos distintos; dato ausente → no factible |
| `test_discovery_segments.py` | El cargador de la campaña devuelve solo IS; leer OOS-2 dos veces falla |
| `test_discovery_count.py` | Registrar campaña aumenta `count_tests` en N_total; lecturas de holdout también |
| `test_discovery_nsga2.py` | Dominancia, frentes, crowding con casos conocidos |
| `test_discovery_genetic.py` | Operadores producen AST válidos; semilla → resultado reproducible |
| `test_discovery_jobs.py` | Reanudación, cancelación, error por job |
| `test_discovery_agents.py` | Salida LLM inválida se rechaza; agentes no cambian niveles ni métricas |
| `test_discovery_levels.py` | Nivel 4 imposible sin DSR de confirmación ≥ 0,90 y PBO ≤ 0,30 |

## 3. Prueba de humo controlada (sin sumar al DSR real)

Campaña `small` con `dry_run: true` sobre **datos sintéticos** (paseo aleatorio): el sistema debe
**no encontrar nada** (ningún nivel ≥ 3). Si "encuentra" estrategias en ruido, el diseño está roto.
Es la prueba de aceptación más importante.

## 4. Aceptación final del MVP (fases 0–7)

- Paridad verde; prueba de ruido sin falsos positivos.
- Una campaña `small` real en US100 M5 **aprobada por ti**, con informe: N bruto, N efectivo, frontera,
  finalistas, OOS-1, robustez y los tres DSR.
- El resultado puede ser "0 finalistas": es un resultado válido y se archiva.
