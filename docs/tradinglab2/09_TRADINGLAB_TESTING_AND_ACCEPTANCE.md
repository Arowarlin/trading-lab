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

**Criterio corregido (Fase 6, decisión del operador).** La versión anterior —"media OOS-1 de los
finalistas ≤ 0"— era circular: la regla del doc 05 §5 exige OOS-1 > 0 y PF > 1,1 para ser finalista,
así que su media es positiva por construcción. La prueba de Fase 6 usa 5 campañas sintéticas (perfil
`small`, 0,9 años M5, costes reales de US100) y exige:

1. individuos factibles > 0 en cada campaña (si no, la prueba no vale);
2. media OOS-1 **agregada de todos los candidatos pre-selección** ≤ 0;
3. Spearman medio entre fitness IS (expectativa) y expectativa OOS-1 de los candidatos ≤ 0,3;
4. los finalistas (número y media OOS-1) se reportan solo como diagnóstico.

La corrida de Fase 6 dio 43 candidatos, media OOS-1 **−0,174** y Spearman medio **−0,173**; 0
finalistas en las 5 campañas de 0,9 años.

**Corrección de la Fase 7b (2026-11-20).** El `test_vs_random` que se calculaba sobre IS+OOS-1 dio
percentiles 98,9–100 a finalistas de ruido: esos tramos ya se habían usado para seleccionarlos, así que
la comparación estaba sesgada. Ahora se llama `test_vs_random_insample`, es **informativo** y no decide
nivel ni veredicto. El requisito es `test_vs_random_oos2`: se calcula dentro de `confirm` con la misma
lectura única de OOS-2, N=1000 entradas aleatorias con la misma sesión, salidas y número de entradas, y
exige percentil ≥95 para el nivel 4. Si OOS-2 tiene menos de `min_trades_oos2` (30 por defecto)
operaciones, tanto `test_vs_random_oos2` como el DSR de confirmación quedan **Sin datos** y no se pasa
el nivel 4.

**Fixtures de la Fase 7b.** Con la regla de finalistas corregida (IS completa >0), la corrida de 1 año
bajó de **K=3 a K=1**; la de 0,9 años se mantiene en **K=2**. Los fixtures son
`tests/fixtures/discovery_noise_seed2_finalists.json` (1 finalista) y
`tests/fixtures/discovery_noise_09y_seed2_finalists.json` (2 finalistas).

| Campaña | Finalista | test_vs_random_insample | test_vs_random_oos2 | Ops OOS-2 | OOS-2 | DSR confirmación | PBO | Nivel | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| 1 año | 7f0bf5962f12 | 95,7 | Sin datos | 12 | −0,2715 | Sin datos | 0,4604 | 3 | SOBREAJUSTADA |
| 0,9 años | cf187a0037c7 | 99,9 | Sin datos | 20 | −0,0367 | Sin datos | 0,1901 | 3 | SOBREAJUSTADA |
| 0,9 años | 45bb81729134 | 99,3 | Sin datos | 21 | −0,0075 | Sin datos | 0,1901 | 3 | SOBREAJUSTADA |

Los tres tramos OOS-2 sintéticos tienen menos de 30 operaciones, así que el nuevo mínimo bloquea
`test_vs_random_oos2` y el DSR (Sin datos). Aun así, **ninguno llega a nivel 4**. El cálculo del test
OOS-2 con ≥30 operaciones se verifica en `tests/test_discovery_levels.py`: en la corrida sintética de
control con 65 operaciones OOS-2 el percentil fue **38,5** (no 99) y el DSR de confirmación **0,0012**.
El test OOS-2 no infla el ruido.

## 4. Aceptación final del MVP (fases 0–7)

- Paridad verde; prueba de ruido sin falsos positivos.
- Una campaña `small` real en US100 M5 **aprobada por ti**, con informe: N bruto, N efectivo, frontera,
  finalistas, OOS-1, robustez y los tres DSR.
- El resultado puede ser "0 finalistas": es un resultado válido y se archiva.
