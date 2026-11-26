# COLA WF-TF · Walk-forward con ventanas por timeframe (una sola vez)

**Creada:** 2026-11-26 por Claude a petición del operador ("Sí, prepárala").
**Prerregistro que se aplica:** `TL3_REPORTS/robust1_wf_windows.md`, commit `ccf27cb` (26-11 09:07),
SHA-256 `f8ad4e9e30c2b4aa…`. Antes de empezar se comprueba que el hash no ha cambiado; si cambió,
`bloqueado: prerregistro alterado`.
**Tipo:** falsación con una herramienta corregida. **No** suma al contador, **no** crea campañas,
**no** lee el OOS-2 y **no** hace `confirm`.
**Modo:** cadena continua W0 → W5, sin pedir confirmación. Lock `proyecto-wf-tf`.

## 1. Declaración (se copia literalmente al principio del informe)

> Esta evaluación es una **segunda oportunidad** para los finalistas de EDGE-1. La propuesta de
> ventanas se escribió a partir de la **frecuencia** de operaciones, no de resultados, pero se aplica
> sabiendo que tres finalistas de `edge1-11` (USDJPY H1; 5178, 5309 y 5385) solo fallaban por un WF
> "no informativo". Se aplica **igual a los 22**, una sola vez y con los mismos umbrales. El juez final
> sigue siendo el OOS-2 (2023-2026), **sin abrir**, que solo el operador puede autorizar a leer una vez.

## 2. Reglas

- **Sin cambiar** `engine.yaml`, `robustness.py`, `walkforward.py` ni ninguna puerta: eficiencia
  ≥ 0,3, `stitched_sharpe` > `wf_min_oos_sharpe` (0,0), al menos 3 pliegues (si no, **Sin datos**),
  PBO ≤ 0,30, ruido y ejecución ≥ 0,5, slippage +2 > 0.
- **Sin escribir** en `discovery.db` ni en `lab.db`: los resultados van a un informe y a un JSON.
  EDGE-2 sigue corriendo y no debe verse afectada.
- No se toca `fastbt.py`, `export_mql5.py`, `dsl.py` ni `drift.py` (MOTOR-FLAT), ni los scripts
  `edge1_*`/`edge2_*`.
- **Prohibido** leer el OOS-2 o llamar a `confirm`. Si alguien pasa las 4 puertas: se informa y se
  **PARA**.
- Commits por ruta; locks `proyecto-wf-tf` y, para la documentación, `readme-plan`. Sin push.

## 3. Bloques

### W0 · Cola y comprobaciones
- `git add -f .orquestador/COLA-WF-TF.md`; commit `wf-tf: cola`.
- Lock `proyecto-wf-tf`.
- Hash del prerregistro (§ cabecera). `count_tests` al inicio.

### W1 · Script de evaluación (sin efectos)
1. `scripts/wf_tf_eval.py`:
   - construye la matriz del WF **con la misma función** que usa `discovery/robustness.py` tras el
     arreglo R2 de ROBUST-1 (serie diaria ordenada de días hábiles con ceros). Hay que importarla,
     **no** reescribirla;
   - llama a `tradinglab.walkforward.walk_forward(matrix, train_len, test_len)` con las ventanas del
     prerregistro según el TF: M5/M15 60/20, M30 120/40, H1 180/60, H4 360/120, D1 504/126;
   - aplica el mismo `verdict` y la misma condición `ok` que `robustness.py:282-288`.
2. Tests sintéticos:
   - con las ventanas 60/20 reproduce exactamente la eficiencia de `robustness.py` (identidad con la
     herramienta actual);
   - con menos de 3 pliegues devuelve **Sin datos**;
   - no escribe en ninguna base de datos.
3. Commit `wf-tf: W1 - script y tests`.

### W2 · Evaluación única de los 22 finalistas de EDGE-1
1. Ejecuta `wf_tf_eval.py` **una vez** sobre los 22. Por finalista se registran:
   - pliegues;
   - mediana de operaciones por ventana de prueba;
   - eficiencia y `stitched_sharpe`;
   - veredicto WF-TF.
2. Combina con las demás puertas **ya calculadas** en la "Repetición tras ROBUST-1"
   (`TL3_REPORTS/edge1_finalistas.md`; no se recalculan): Gate 1, PBO, ruido, ejecución, Gate 3.
3. **Puerta 4:** entre los que pasan las puertas 1 a 3 con WF-TF, agrupa por correlación de retornos
   diarios > 0,7 y quédate con el de menor `cost_r` de cada grupo.
4. Informe `TL3_REPORTS/wf_tf_resultados.md`:
   - la declaración de §1;
   - una tabla con WF antiguo (60/20) frente a WF-TF;
   - el veredicto de las 4 puertas;
   - los grupos de la puerta 4;
   - y, si alguno pasa, la frase: **"Candidato a `confirm`: requiere autorización explícita del
     operador; la plantilla `trend_pullback_mtf` es de 24 h y mantiene posiciones varios días
     (swap y fin de semana; ver COLA-MOTOR-FLAT)"**.
5. JSON con las mismas cifras: `TL3_REPORTS/wf_tf_resultados.json`.
6. Commit `wf-tf: W2 - EDGE-1`.

### W3 · Los mismos pasos para EDGE-2 cuando haya finalistas
- Espera a que exista `TL3_REPORTS/edge2_finalistas.md` (la salida de su Y3). Comprueba cada 15 min
  con salida mínima, hasta el tag `edge2` como mucho.
- Aplica W2 a los finalistas de EDGE-2, sin tocar la cola de EDGE-2. Sección "EDGE-2" en el mismo
  informe.
- Si EDGE-2 cierra sin finalistas: `W3 = sin finalistas`.
- Commit `wf-tf: W3 - EDGE-2`.

### W4 · Cierre
- `ruff`, `pytest -q` (esperando si hay otro `pytest` en marcha) y `lab doctor`.
- `count_tests`: no puede cambiar por esta cola; EDGE-2 sí lo cambia en paralelo, así que se informan
  las dos cifras.
- Una línea en ESTADO y en PLAN (bajo el lock `readme-plan`).
- Commit, tag `wf-tf-1` y liberación de locks.

### W5 · Aviso y PARA
- Telegram con el formato **Hecho / 1..N / Aviso / Siguiente**:
  - cuántos finalistas pasan las 4 puertas con WF-TF (EDGE-1 y EDGE-2);
  - el candidato a `confirm`, si lo hay;
  - y la frase "OOS-2 sin leer; decide el operador".
- **PARA.**
