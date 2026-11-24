# RESULTADO · C2-informe — diagnóstico N2 Donchian XAUUSD H4 + merge F12a

Fecha: 2026-11-23. Sesión única en `E:\trading-lab`. No se registró, aprobó,
ejecutó, confirmó ni supersedió ninguna campaña; no se leyó OOS-2; no se hizo
push; no se tocaron tareas programadas ni el carril del EA.

## Parte A · Informe N2

Guardado en `reports/discovery/n2-donchian-xauusd-h4.md`.

Campaña `n2-donchian-xauusd-h4`: 27/27 evaluadas, `n_effective` 6, 12 en
frontera, 9 candidatas, 1 finalista, OOS-1 medio 0,3942. `count_tests` **1730**.

**Conclusión:** no hay ventaja de tendencia; hay **deriva del oro** capturada
por el lado largo y una **selección defectuosa** que conservó la segunda
combinación más débil por IS porque ordenó por OOS-1.

- **Params/Veredicto:** `discovery results` lee los parámetros del `grid`
  guardado (`channel_n`, `vol_pct`, `stop_mult`) y muestra el veredicto guardado
  o, si no existe, la selección (`FINALISTA`, `DESCARTADO`, `NO FINALISTA`).
  Tests en `tests/test_discovery_results.py`.
- **S1 confirmada:** 478 (IS neto 0,0138) es la segunda más débil de las 9
  candidatas; 484 (0,0055) es la única peor. La mejor, 470 (0,1109), fue
  descartada. La regla (`engine.py:475-493`) ordena por
  `OOS-1 − 0,001×complejidad` y luego exige `|corr| < 0,7`; no consulta IS.
- **Grupo único:** las 9 candidatas correlacionan con 478 con |r| ≥ 0,702
  (464 y 467 en 0,7024, justo por encima del umbral; 466/472/475 = 1,000).
  Como 478 tiene el mayor score OOS-1, es la representante y las otras 8 caen
  por correlación.
- **Caveat:** OOS-1 se leyó para las 9 candidatas y se usó para seleccionar; el
  0,394 de 478 es el máximo de 9 lecturas, no un holdout limpio.
- **Largo vs corto:** 27/27 con neto largo > 0; 0/27 con neto corto > 0.
  Agregado IS: largo +0,2395 bruto / +0,2040 neto; corto −0,1159 / −0,1497.
  478 IS: 361 ops (175 L / 186 S), bruto +0,0414, neto +0,0138; largo +0,1916
  bruto / +0,1631 neto, corto −0,1000 / −0,1266. 478 OOS-1: 16 ops (9 L / 7 S),
  neto +0,3942, PF 2,120; largo +0,6342 bruto, corto +0,1207.
- **Deriva:** benchmark de entradas aleatorias largas, mismo stop ATR(14)×2,5 y
  mismo tiempo medio (21,64 barras IS / 20,62 OOS-1), 1.000 sims, semilla
  20261123. IS: azar +0,1490 R/op (p5–p95 0,0266…0,2762), estrategia +0,0414
  (percentil 7,9). OOS-1: azar +0,3079 (−0,2583…0,8719), estrategia +0,4095
  (percentil 61,5). En IS la estrategia es peor que el azar largo; en OOS-1 está
  dentro de la distribución.
- **478 OOS-1:** bootstrap 10.000, semilla 20261123; neto 95 %
  [−0,1814, 0,9878], P(media ≤ 0) = 9,4 %. Cabe dentro del benchmark de deriva.
- **Perturbation Lab:** base IS+OOS-1 con CFD-001 −0,0016 R/op; ruido
  −0,0144 (p10 −0,0440), retraso entrada +1 −0,0129, +2 −0,0362, ejecución
  mediana −0,0039 (p10 −0,0215). Las tres pruebas `passed=false`; nivel 2,
  veredicto guardado `SIN VEREDICTO` (faltan PBO/WF/OOS-2). No suma al DSR.

No se cambió la lógica de selección ni se re-ejecutó la campaña. El informe
incluye tablas de las 27 combinaciones, pliegues, largo/corto, bruto anual
2005–2024 de 470/475/478 y el detalle de correlación.

## Parte B · Merge F12a

- Rama `tl2-f12-export` (tag `tl2-f12a`, HEAD 4b58a85) fusionada con
  `--no-ff`; sin squash.
- Merge limpio, sin conflictos: `cli.py` conserva `results`, `perturb`,
  `show`, `edge-map` y añade `export-mql5`.
- Commit de merge `3f5e233` · `merge: F12a exportador MQL5`; tag
  `tl2-merge-f12a`.
- No se borró el worktree ni la rama.

## Comprobaciones

- Exportador MQL5: **62 passed**.
- Tests EA: **53 passed**.
- `pytest -q`: **1698 passed, 1 skipped**.
- `ruff check src/tradinglab tests docs`: limpio.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1730**.
- `git status --short`: solo `?? tl2-edge-map.patch`.

## Commits y tags

```text
3f5e233 merge: F12a exportador MQL5      (tl2-merge-f12a)
167a6f2 tl2: C2 - informe donchian XAU   (tl2-c2-informe)
c684ac9 tl2: N3 - propuestas de la manana
```

No se hizo push. No se leyó OOS-2. No se operó.

PARA.
