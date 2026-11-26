# RESULTADO · ROBUST-1 · Arreglar la herramienta de robustez

**Fecha:** 2026-11-26 · **Modo:** cadena R0→R7 · **Tag:** `robust-pre` → `robust-1`.

## Hecho

Se corrigieron los cuatro hallazgos de EDGE-1 y se repitió X3 sin leer OOS-2,
sin campañas nuevas, sin `record-informal`, sin órdenes y sin push.

## 1..7

1. **R0 · Cola, lock y tag.** Commit `robust1: cola` con
   `.orquestador/COLA-ROBUST-1.md` (`git add -f`), lock `proyecto-robust` y tag
   `robust-pre` antes de tocar código.
2. **R1 · `point` por instrumento.** `point` sale de
   `propfund.instruments.point_size` (EURUSD/GBPUSD `0,00001`, USDJPY `0,001`,
   XAUUSD/índices `0,01`, futuros su tick). Sin especificación:
   `Sin datos: point`. Se corrigieron campaña, spec, `QueueSetup`, cesta,
   `edge_map` y los valores por defecto de 0,01. El estrés `slippage +2` de
   EURUSD pasa de ~182 bps a 0,18 bps.
3. **R2 · PBO.** Las matrices de `edge1-01`/`edge1-11` no eran iguales, pero
   `_pbo_wf` las construía con una unión **desordenada** de días con operación.
   Ahora `_frontier_frame` ordena y reindexa a días hábiles con ceros.
   `edge1-01` PBO **0,743**; `edge1-11` **0,198** (antes 0,634/0,634 por el
   redondeo de la matriz defectuosa). Test sintético de orden/calendario.
4. **R3 · WF etiquetado.** 14 de 22 finalistas caen en campañas con mediana
   < 2 operaciones por pliegue y se etiquetan **“WF no informativo (baja
   frecuencia)”**. La puerta sigue en ≥ 0,3 y no se tocaron ventanas ni
   umbrales. Propuesta por TF prerregistrada en
   `TL3_REPORTS/robust1_wf_windows.md`.
5. **R4 · X3 repetido.** `scripts/edge1_x3.py --refresh --append-section`
   sobre los 22 finalistas: **0 pasan las 4 puertas**. Gate 3 pasa en la
   mayoría; gate 2 sigue fallando por WF/PBO/ruido. Se conserva la tabla
   original y se añade “Repetición tras ROBUST-1”.
6. **R5 · EDGE-2.** Comparados `49551da` y `768e572`: solo cambia la
   clasificación de huecos; **no cambian** `cost_r`, elegibilidad ni inicio.
   El plan Y1 sigue válido, sin Y1b, sin cancelar ni registrar borradores.
7. **R6 · Cierre.** `ruff check .` limpio; `pytest -q` **2073 passed + 1
   skipped** (34:40); `lab doctor` Frescura FAIL 7/17 y Reglas fondeo WARN
   (entorno); `lab propfund verify` **4 OK**; `count_tests` **12.694 → 12.694**.
   README §11, PLAN y ESTADO actualizados bajo el lock `readme-plan`, con la
   línea de TL2-TCA2 (**TCA v2 activa; 0 filas v2 hasta el primer fill**; no
   hace falta reiniciar: las tareas programadas arrancan un proceso nuevo).
   Tag `robust-1` y locks liberados.

## Aviso

- **No se leyó OOS-2** ni se hizo `confirm`.
- No se ejecutaron campañas, `research*`, `record-informal`, órdenes ni push.
- Las validaciones `retest/pbo/wf` de los 22 finalistas se refrescaron en
  `data/discovery.db` (solo lectura de mercado; no suman al DSR). El contador
  no cambió.
- `lab doctor` mantiene el FAIL de Frescura y el WARN de Reglas fondeo como
  avisos de entorno preexistentes.
- `reports/discovery/edge_map.md` sigue modificado por otra sesión; no se
  incluyó en ningún commit.
- La línea de TCA2 en README/PLAN/ESTADO llegó actualizada por otra sesión
  como “TCA v2 activa (tareas programadas); 0 filas v2 hasta el primer fill”.
  La enmienda de Claude (09:20) confirma que **no hace falta reiniciar**:
  `ai_trader` y el forward arrancan un proceso nuevo en cada ejecución.

## Comprobaciones copiadas

```text
git status --short (antes del commit de cierre)
 M .orquestador/COLA-ROBUST-1.md
 M ESTADO.md
 M PLAN.md
 M README.md
 M reports/discovery/edge_map.md   # otra sesión, no se toca
?? TL3_REPORTS/edge2_wait.log
?? TL3_REPORTS/lab_doctor_f3.log
?? TL3_REPORTS/lab_propfund_verify_f3.log
?? TL3_REPORTS/pytest_f3.log

git log --oneline -5
ec555ef robust1: R6 - enmienda TL2-TCA2 y locks
44e0069 robust1: R5 - coherencia EDGE-2
d901b10 robust1: R4 - X3 de EDGE-1 repetido
ccf27cb robust1: R3 - WF etiquetado
e652efd robust1: R2 - PBO (matriz diaria ordenada)

pytest -q
2073 passed, 1 skipped, 1 warning in 2080.81s (0:34:40)

count_tests
{'lessons': 0, 'optimization_trials': 0, 'holdout_reads': 0,
 'strategy_trials': 0, 'incubated': 0, 'campaign_registry': 0,
 'discovery': 12694, 'total': 12694}

lab propfund verify
OK ai_trader · OK ea_us100_ftmo1 · OK ftmo_forward · OK ftmo_risk

lab doctor
Frescura FAIL 7/17 · Reglas fondeo WARN · resto OK
```

## Siguiente

- **Operador:** decidir si se aplica la propuesta de ventanas WF por TF
  (`TL3_REPORTS/robust1_wf_windows.md`) en una cola nueva.
- **EDGE-2:** lista para Y2; las 18 campañas siguen en `draft`.
- **TCA v2:** activa; las primeras filas v2 se verán en el primer fill de
  `ai_trader`/forward. **No hace falta reiniciar.** No hay ninguna estrategia
  robusta que confirmar.

