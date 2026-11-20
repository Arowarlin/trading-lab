# 11 · Prompt de la primera fase recomendada (R1 · Perturbation Lab)

**Requisito previo:** R0 (7c + 7d) cerrada con tags `tl2-f7c` y `tl2-f7d`.
**Modelo:** DeepSeek V4.1 Flash. Sesión nueva.

```text
Lee docs/tradinglab2/10_TRADINGLAB_OPENCODE_EXECUTION_PROMPT.md (BLOQUE COMÚN; pytest -q sin --basetemp)
y docs/tradinglab2/competitive_research/07 y 10 (sección R1).
Ejecuta SOLO la fase R1 · Perturbation Lab.

Objetivo: pruebas de falsificación que comparan una estrategia con versiones perturbadas de sí misma
(ruido en OHLC, entradas/salidas retrasadas, Monte Carlo de ejecución). Se ejecutan sobre IS+OOS-1,
NUNCA OOS-2. No son hipótesis nuevas: NO suman a count_tests.

1. discovery/perturb.py con noise_test, delay_test y execution_mc según doc 10 §R1. Reutiliza fastbt,
   compiler, data_sources, campaigns.load_segment y propfund.costs. Semillas deterministas.
2. engine.yaml, sección perturb: noise_paths 500, noise_scale_atr 0.10, entry_delays [1,2],
   exit_delays [1,2], exec_paths 1000, exec_skip_frac 0.05, min_median_ratio 0.5. Guarda estos valores en
   la validación.
3. levels.py: el nivel 3 exige además noise, delay +1 (entrada) y execution_mc con mediana > 0 y
   ≥ min_median_ratio × base. Prueba no calculable = no superada ("Sin datos").
4. CLI: lab discovery perturb STRATEGY_ID (guarda disc_validations; no toca OOS-2).
5. Tests: (a) estrategia con edge sintético inyectado sobrevive; (b) estrategia ajustada a ruido falla;
   (c) determinismo; (d) AST: perturb.py no llama a read_holdout; (e) count_tests no cambia;
   (f) coherencia OHLC tras el ruido.
6. Calibración: pasa la prueba de ruido completa de la fase 7b y los 2 finalistas archivados de la
   campaña real (64af2965…, 07093bb0…) por el Perturbation Lab y pega la tabla (base, mediana, p10,
   ratio). NO ejecutes confirm.
7. ruff, pytest -q, lab propfund verify. Muéstrame el plan antes ("OK PLAN") y el diff antes del commit
   ("commit"). Commit "tl2: R1 - perturbation lab", tag tl2-r1. Sin push. PARA.
```
