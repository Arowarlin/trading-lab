# COLA ROBUST-1 · Arreglar la herramienta de robustez antes de EDGE-2

**Creada:** 2026-11-26 por Claude a petición del operador ("Sí, prepárala"), tras revisar el X3 de
EDGE-1.
**Tipo:** corrección del motor de investigación (`discovery/`). No es producción ni suma al contador:
no se crean campañas ni pruebas. Volver a ejecutar X3 es falsación sobre estrategias que ya existen.
**Modo:** cadena continua R0 → R7, sin pedir confirmación.
**Arranque:** inmediato, siempre que no haya ningún `lab discovery run` en marcha (EDGE-2 no ha
lanzado ninguna campaña). Lock `proyecto-robust`.

## 1. Hallazgos (Claude, solo lectura)

| # | Hallazgo | Evidencia | Efecto |
|---|---|---|---|
| H-1 | **`point` = 0,01 por defecto para pares de forex.** `retester.py:121-122` suma `1×` y `2×setup.point` de slippage. Hay `point: float = 0.01` por defecto en `basket.py:419/486` y `costs.py:498/736`, y está fijo en `edge_map.py:1214` (`point=0.01`) | En `TL3_REPORTS/edge1_finalistas.md`, "Slip x2 R" da **−3,7 a −7,9 R** en EURUSD/GBPUSD: con 0,01 de "punto", +2 puntos son **200 pips**. USDJPY sale razonable y XAUUSD/índices tienen 0,01 correcto | El estrés de slippage (puerta 3) **no vale** en EURUSD/GBPUSD. El veredicto de EDGE-1 no cambia, porque esos finalistas también fallan el PBO y el walk-forward |
| H-2 | **PBO idéntico entre campañas distintas** | 0,634 en `edge1-01` (USDJPY H4) y en `edge1-11` (USDJPY H1) | Puede ser casualidad (PBO discreto con pocas estrategias) o un error de matriz o de caché |
| H-3 | **Walk-forward poco informativo en baja frecuencia** | `robustness.py:271-275`: `walk_forward(matrix, train_len=60, test_len=20)`; casi todos dan eficiencia 0,000 | Con estrategias H1/H4 que operan pocas veces al año, las ventanas de prueba de 20 días casi no tienen operaciones |
| H-4 | **Coherencia del plan de EDGE-2** | `edge2: Y1 - plan congelado` (22:18) fue **antes** de `edge2: Y0 - corrige clasificacion de huecos` (22:40), que cambió `edge2_costes.md`/`edge2_data.json` | El plan puede apoyarse en la clasificación de huecos anterior (por ejemplo, el inicio de H1/H4 en 2019) |

## 2. Reglas

- `AGENTS.md` y `PLANTILLA-COLA.md`: commits por ruta; locks; no tocar producción, `engine.yaml`
  (umbrales congelados) ni `fastbt.py`/`export_mql5.py`/`dsl.py`/`drift.py` (son de MOTOR-FLAT).
  Sin push.
- **Sin cambiar puertas ni umbrales:** WF ≥ 0,3, PBO ≤ 0,30, slippage +2 > 0. Solo se corrigen
  errores que un test sintético demuestre.
- **Prohibido leer el OOS-2.** Si tras R4 algún finalista pasa las 4 puertas, **no** se hace
  `confirm`: se PARA y se avisa al operador.
- Contador: anótalo al inicio y al final. No puede cambiar por esta cola.

## 3. Bloques

### R0 · Cola, lock y tag
`git add -f .orquestador/COLA-ROBUST-1.md`; commit `robust1: cola`; lock `proyecto-robust`; tag
`robust-pre` **antes** de tocar código.

### R1 · `point` por instrumento (H-1)
1. Localiza dónde se construye `setup.point` para cada campaña (fuentes broker y dukascopy) y cada
   valor por defecto de 0,01 (`basket.py`, `costs.py`, `edge_map.py:1214` y donde aparezca).
2. `point` debe salir de la especificación del instrumento (`propfund/instruments.resolve` o la del
   bróker). Referencia esperada:

   | Instrumento | `point` |
   |---|---|
   | EURUSD, GBPUSD | 0,00001 |
   | USDJPY | 0,001 |
   | XAUUSD | 0,01 |
   | US100, US500, US30 | 0,01 |

   Si un instrumento no tiene especificación: **error "Sin datos: point"**. Nunca se usa 0,01 por
   defecto.
3. Tests:
   - para cada instrumento y fuente, `setup.point` es el de la tabla;
   - `slippage_plus_2` suma exactamente `2 × point` por lado;
   - con `tl3.verify.magnitude`, el coste extra de `slippage_plus_2` en bps queda en un rango
     plausible (EURUSD ≈ 0,2 bps; 200 pips debe hacer fallar el test).
4. Commit `robust1: R1 - point por instrumento`.

### R2 · PBO repetido (H-2)
1. Recalcula el PBO de `edge1-01` y `edge1-11` y compara sus matrices de entrada (forma, hash,
   estrategias incluidas).
2. Resultados posibles:
   - **matrices distintas y PBO legítimamente igual:** se anota la resolución (valores discretos
     con pocas estrategias);
   - **matriz equivocada** (otra campaña, caché o global): se corrige con un test.
3. Commit `robust1: R2 - PBO`.

### R3 · Walk-forward en baja frecuencia (H-3), sin cambiar umbrales
1. Para cada finalista de EDGE-1, cuenta las operaciones por ventana de prueba del WF.
2. Si la mediana es < 2, la etiqueta pasa a **"WF no informativo (baja frecuencia)"** en lugar de
   0,000. La puerta sigue **sin pasar**: hace falta un valor ≥ 0,3.
3. **No** se tocan `wf_train_days`/`wf_test_days`. Una propuesta de ventanas por TF queda escrita
   para una cola futura, prerregistrada.
4. Commit `robust1: R3 - WF etiquetado`.

### R4 · Volver a ejecutar X3 de EDGE-1 con las herramientas corregidas (falsación)
1. `scripts/edge1_x3.py` sobre los 22 finalistas, con los mismos umbrales.
2. Añade a `TL3_REPORTS/edge1_finalistas.md` una sección **"Repetición tras ROBUST-1"**. La tabla
   original se conserva tal cual.
3. Si alguno pasa las 4 puertas: **PARA y avisa al operador**, sin `confirm`.
4. Commit `robust1: R4 - X3 de EDGE-1 repetido`.

### R5 · Coherencia del plan de EDGE-2 (H-4)
1. Compara `edge2_costes.md`/`edge2_data.json` de `49551da` (antes) con `768e572` (después): ¿cambia
   la elegibilidad, el `cost_r` o el inicio del desarrollo de alguna de las 18 campañas del plan?
2. Si **no cambia nada:** anótalo en `edge2_plan.md` y sigue.
3. Si **cambia algo:**
   - las campañas siguen en `draft`: no han contado ni corrido;
   - congela un plan **Y1b** con la regla de `COLA-EDGE-2 §Y1` aplicada a los datos corregidos
     (incluido el inicio de H1/H4: si 2018 ya es válido, H1/H4 empiezan el 2018-01-02);
   - cancela los borradores sustituidos con `lab discovery cancel` (o `supersede`), sin borrar
     nada, y registra los nuevos;
   - commit `edge2: Y1b - plan recongelado`.
4. Commit `robust1: R5 - coherencia EDGE-2`.

### R6 · Cierre
- `ruff`, `pytest -q` completo, `lab doctor` y `lab propfund verify`.
- Contador sin cambios.
- README §11 y PLAN, bajo el lock `readme-plan`.
- `ESTADO.md`:
  - EDGE-1: 0 robustas, con el motivo;
  - EDGE-2: lista para Y2;
  - **"reinicio pendiente de `ai_trader`/forward para TL2-TCA y TCA2"**.
- **Pendiente de TL2-TCA2** (enmienda de Claude, 2026-11-26): TCA2 cerró sin escribir README/PLAN/ESTADO
  porque creyó "huérfano" el lock `readme-plan` (ver `reports/tl3/tca2_cierre.md`). Con el mismo lock
  `readme-plan`, añade su línea:
  - `signal_price` desde `ai_trader` y forward;
  - `tca_version` (68 filas v1, 0 v2);
  - lectores solo v2;
  - tolerancia 1e-9 en la frontera del SL;
  - tags `tl2-tca2-pre`/`post`;
  - reinicio pendiente.
- **Nota en `.orquestador/PLANTILLA-COLA.md` (coordinación):** el `pid` de `owner.json` es el del
  comando `scripts/orq_lock.py`, que termina al instante. **Nunca** se usa para declarar un lock
  huérfano: solo cuenta la antigüedad (> 2 h), y lo decide el operador.
- Commit por ruta, tag `robust-1` y liberación de locks.

### R7 · Aviso
- Telegram con el formato **Hecho / 1..N / Aviso / Siguiente**:
  - instrumentos que tenían el `point` mal;
  - resultado del PBO;
  - finalistas con WF no informativo;
  - resultado de la repetición de X3;
  - plan de EDGE-2 intacto o Y1b.
- **PARA.**
