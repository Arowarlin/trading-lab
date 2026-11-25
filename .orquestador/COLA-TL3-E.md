# COLA TL3-E · Verificación previa, avisos que viajan y coordinación entre sesiones

**Creada:** 2026-11-25 por Claude. **Aprobada por el operador** ("Sí, prepárala"): ideas 1, 2 y 4 de
la revisión de `ath-quant-desk` (MIT, GiacomoGhi). Se adapta el proceso; no se copia código.
**Modo:** cadena continua E0 → E5, sin pedir confirmación. Un commit pequeño por bloque.
**No suma al contador** ni toca producción. No se calcula el rendimiento de nada; las comprobaciones
son de mecánica y de unidades.

## 1. Motivo

En un solo día, cinco errores se detectaron **después** de gastar una prueba o de publicar un informe:
- swap de T8 100 veces mayor;
- spread en puntos MT5 usado como precio en T5-bis (C1);
- conjunto de 48 operaciones distinto del de T5;
- umbral de cobertura de T7 (371 frente a 357);
- swap de H1.

Además, dos sesiones escribieron README y PLAN a la vez (commit mezclado `725c5f1`), y otras dos
sesiones siguieron planes contrarios sobre NASDAQ_EDGE al mismo tiempo. Los avisos sobre el EA,
`ai_trader` y FundingPips están repartidos en informes que nadie más lee.

## 2. Reglas

- Las de `AGENTS.md` y `COLA-TL3-D.md §1`. Escritura solo con Python o con `git`.
- **Commits por ruta:** `git add <rutas>` y `git commit -- <rutas>`. Nunca `git add -A`, `git add .`
  ni `git commit -a`.
- **Arranque:** solo con el árbol de trabajo limpio. Se permiten los externos conocidos
  `reports/discovery/edge_map.md` y `tl2-edge-map.patch`.
  - Si hay otros ficheros versionados modificados (p. ej. `PLAN.md` o `NASDAQ_EDGE_INSTITUTIONAL/`
    de otra sesión), comprueba cada 5 min durante 60 min como máximo.
  - Si siguen así: `bloqueado: otra sesión con cambios sin commit`. **No** los toques ni los incluyas.
- **Prohibido:** producción (EA, `ai_trader`, forward, Prop Fund/`prop/`, riesgo FTMO, `execution/`,
  `config/propfund/`, `schedule.yaml`, `.env`); `record-informal`; órdenes; campañas; push; borrar
  ficheros; modificar el código congelado de `NASDAQ_EDGE_INSTITUTIONAL/tools/forward_models.py`.
  Tampoco se leen ni se citan resultados de `NASDAQ_EDGE_INSTITUTIONAL/03_BACKTEST/`, aparte de su
  existencia y su fila en el contador.

## 3. Bloques

### E0 · Cola y arranque
- Comprueba la condición de arranque de §2.
- `git add -f .orquestador/COLA-TL3-E.md`; commit `tl3: E0 - cola TL3-E`.

### E1 · Coordinación entre sesiones (idea 4)
1. **Módulo nuevo `src/tradinglab/orq_lock.py`:**
   - `acquire(resource, owner, *, wait_s=0)`: `os.mkdir(".orquestador/locks/<resource>.lock")` es la
     operación atómica. Dentro escribe `owner.json` (owner, cola, pid, host, `started_at` UTC). Si ya
     existe, reintenta cada 10 s hasta `wait_s`; luego lanza `LockBusy` con el dueño.
   - `release(resource, owner)`: solo el dueño. **Mueve** el lock a
     `.orquestador/locks/released/<resource>.<timestamp>.lock` con `os.replace`; nunca borra.
   - `status()`: locks vivos, dueño y antigüedad. "Viejo" = más de 2 h. Un lock viejo **no** se roba:
     se informa y decide el operador.
   - Context manager `with held(resource, owner): ...`.
2. **CLI aparte:** `scripts/orq_lock.py acquire|release|status`, sin tocar `cli.py`.
3. **Recursos estándar:**
   - `readme-plan` (README.md + PLAN.md);
   - `changelog-produccion`;
   - `protected-manifest`;
   - `tl3-registry`;
   - `pytest-full`;
   - `proyecto-<nombre>`, uno por proyecto, p. ej. `proyecto-nqedge`.
4. **Tests:**
   - con dos procesos (`multiprocessing`) que piden el mismo recurso, solo uno gana;
   - `release` mueve y no borra;
   - otro dueño no puede liberar;
   - un lock viejo se informa y no se roba;
   - `held` libera también si hay una excepción.
5. **`AGENTS.md`**, sección nueva "Coordinación entre sesiones" (cinco viñetas; cambio aprobado por el
   operador):
   - lock antes de escribir README/PLAN, el CHANGELOG de producción, el manifiesto protegido o el
     registro TL3;
   - commits por ruta;
   - una sola cola activa por proyecto (`proyecto-<nombre>`);
   - antes de cambiar el plan de un proyecto: comprobar locks, procesos y ficheros sin commit, y anotar
     el "Plan vigente" en el README del proyecto;
   - los locks viejos los decide el operador.
6. **Plantilla `.orquestador/PLANTILLA-COLA.md`:**
   - cabecera de reglas;
   - condición de arranque con árbol limpio;
   - bloque **V · Verificación** (E2) antes de cualquier ejecución que cuente;
   - cierre con los locks `pytest-full` y `readme-plan`;
   - aviso por Telegram.
7. Commit `tl3: E1 - locks y coordinacion`.

### E2 · Verificación de conformidad antes de la prueba (idea 1)
1. **`docs/VERIFICACION.md`.** Principio: verifica **otra sesión** distinta de la que construyó; juzga
   la conformidad con el prerregistro, **nunca** el resultado; se hace **antes** de la ejecución que
   cuenta, con datos sintéticos y con el tramo de desarrollo, y sus salidas no contienen P&L de la
   muestra evaluada. Lleva una línea de atribución a ath-quant-desk (MIT). Lista de comprobación:
   1. **Unidades y magnitudes.** Cada componente de coste se convierte a bps o R y se compara con el
      rango esperado que declara el prerregistro. Fuera de rango por un factor de 3 o más = defecto.
   2. **Constantes frente al prerregistro.** Tabla línea a línea: valor del prerregistro frente a la
      constante del código (umbrales, ventanas, horas, δ, semillas).
   3. **Muestra.** Huella SHA-256 de los ids o fechas. Si la prueba reutiliza una muestra, se
      reproducen sus cifras de referencia publicadas.
   4. **Horas y calendario.** Entradas y salidas a la hora declarada en NY; semanas de cambio de
      horario; festivos y cierres tempranos.
   5. **Frecuencia de disparo.** Fuera de la mitad o del doble de lo esperado = vuelve al diseño.
   6. **Salidas.** Cada regla de salida se ve disparar al menos una vez, incluida la de SL primero.
   7. **Señales perdidas.** Muestra de momentos con la condición cumplida y sin operación: cada uno
      tiene explicación.
   8. **Tamaño de posición y NO TRADE.**
   9. **Sanidad del placebo o del benchmark** cuando forma parte de la puerta de potencia: dispersión
      frente a la esperada. Por ejemplo, la σ del placebo de T8 (190 frente a ~95 bps) habría saltado.
2. **Módulo `src/tradinglab/tl3/verify.py`:**
   - funciones: `magnitude(name, value, lo, hi)`, `constants_match(prereg, code)`,
     `trigger_rate(observed, expected)`, `sample_fingerprint(ids)` y `report(checks)`;
   - el informe va en markdown con veredicto "Conforma" / "Defectos".
3. **Registro:**
   - tabla nueva `verifications` en `tl3_research.db`, solo filas nuevas: `hypothesis_id`,
     `code_hash`, verificador, veredicto, informe y `created_at`. La crea `init_db` si falta;
   - `registry.require_verified(hypothesis_id, code_hash)` lanza un error si no hay "Conforma" para
     ese hash;
   - las pruebas futuras deben llamarla antes de ejecutar. No se aplica a las ya ejecutadas.
4. **Tests "lo habría cazado"**, con valores fijos y sin volver a ejecutar ninguna prueba:
   - `magnitude` marca `SWAP_BPS` = 200,8 con un rango esperado de 0,5 a 5 bps/noche;
   - una tolerancia de 2 × 90 "puntos" usada como precio supera la distancia típica del SL de US100
     (unos 100 pt) → defecto;
   - la huella de "las 48 primeras por id" ≠ la del conjunto de T5 (todas menos #52 y #54);
   - `constants_match` marca 371 frente a 357.
5. **Aplicación ahora: verificación de NQF-A/B/C antes de que el forward acumule operaciones.**
   - Lo hace esta sesión, que no construyó ese código. Solo lectura de
     `NASDAQ_EDGE_INSTITUTIONAL/tools/forward_models.py` y de sus tests.
   - Se usan datos sintéticos y conteos del DEV, sin desenlaces.
   - Se comprueba:
     - contra `04_FORWARD/prerregistro.md`: el OR de 15 min, el barrido ≥ 2 ticks con cierre dentro
       y el VWAP ± 2σ;
     - en MNQ: tick 0,25 y 0,50 USD por tick y contrato;
     - el tamaño `floor(150 / …)` y el NO TRADE;
     - el bloqueo de los días FOMC y el cierre 5 min antes de un Tier 1;
     - el cierre a las 15:55 y la zona horaria.
   - Informe `TL3_REPORTS/verificacion_nqf.md`.
   - Si hay **defectos**, **no** se corrige el código: corregirlo crea una variante nueva con fecha de
     inicio nueva, y eso lo decide el operador. Se anota en `RESULTADO-TL3.md`.
6. Commit `tl3: E2 - verificacion previa`.

### E3 · Avisos que viajan (idea 2)
1. **Tabla `warnings` en `tl3_research.db`**, solo filas nuevas, sin funciones de modificar ni borrar.
   Campos: `subject` (p. ej. `ea:us100-ftmo1`, `ai_trader`, `cuenta:CFD-006`, `prop.simulator`,
   `nqedge`), fecha, etapa, texto, cifras, `source_path` y `created_at`.
   - Funciones `add_warning`, `warnings_for(subject)` y `render(subject)`. Si no hay ninguno, devuelve
     "Ninguno".
2. **Siembra.** Solo hechos con su fichero fuente: copia las cifras del fichero citado; si no las
   encuentras, no añadas el aviso.

   | subject | Aviso | Fuente |
   |---|---|---|
   | `ea:us100-ftmo1` | T7 no confirma; muestra efectiva 2013-2014 y 2018-2021 | `TL3_REPORTS/ea_oop_dukascopy.md` |
   | `ea:us100-ftmo1` | El corto pierde en 2023 | `TL3_REPORTS/TL3_US100_ADDENDUM.md` |
   | `ea:us100-ftmo1` | Forward con n cerradas; n necesario para decidir | `TL3_REPORTS/ea_forward_monitor_plan.md` |
   | `ea:us100-ftmo1` | Sus componentes coinciden con NASDAQ_EDGE A-E; ningún tramo histórico es limpio | `.orquestador/COLA-NQEDGE-FORWARD.md §1` |
   | `ai_trader` | T5 no concluyente | `TL3_REPORTS/ai_trader_contrafactual.md` |
   | `ai_trader` | La simulación da más que la ejecución real; el gap está en la salida; los stops móviles no se simulan | `TL3_REPORTS/ai_trader_sim_vs_real.md` |
   | `ai_trader` | La TCA registra slippage 0 y los costes de `ai_trader` lo leen | `TL3_REPORTS/tca_diagnostico.md` |
   | `ai_trader` | Próxima evaluación única a n = N | `TL3_REPORTS/ai_trader_power_plan.md` |
   | `cuenta:CFD-006` | E-3 pendiente: la protección diaria solo usa la equidad | `docs/CHANGELOG-produccion.md` (2026-11-25) |
   | `prop.simulator` | Modelo diario: balance = equidad al inicio del día; optimista para estrategias que duermen posiciones | `docs/CHANGELOG-produccion.md` (2026-11-25) |
   | `prop.simulator` | Cifras de FundingPips anteriores a `020b41b`: rotura diaria sobrestimada | `TL3_REPORTS/tl2_diario_inventario.md` |
   | `nqedge` | Los OOS históricos están contaminados por el EA. La fase C histórica se ejecutó y el operador la registró (`informal_trials` fila 7, n = 22). El forward NQF es independiente y está prerregistrado | `.orquestador/COLA-NQEDGE-FORWARD.md` y `informal_trials` |

3. **Se muestran en** `report.status_table` (columna "Avisos" con el número y el más reciente) y en
   `scripts/tl3_warnings.py list|render <subject>`. Mostrarlos en Prop Fund, en la web o en
   `lab propfund` es producción: queda anotado como siguiente paso en `RESULTADO-TL3.md`.
4. **Tests:** no hay API para modificar ni borrar; `render` incluye todos los avisos en orden; un
   `subject` desconocido da "Ninguno"; la siembra es idempotente (volver a ejecutarla no duplica).
5. Commit `tl3: E3 - avisos que viajan`.

### E4 · Cierre
- Con `held("pytest-full")`: `ruff check`, `pytest -q` completo, `lab doctor` y
  `lab propfund verify`.
- Con `held("readme-plan")`: README §11 y PLAN, una línea por E1-E3.
- `count_tests` sin cambios respecto al arranque.
- Commit `tl3: cierre ciclo 1f` y tag `tl3-ciclo1f`.

### E5 · Aviso
- Resumen a Telegram con `lab telegram send --file <resumen>`; si no hay Telegram, `lab alerts send`.
  Formato **Hecho / 1..N / Aviso / Siguiente**, con:
  - los locks y la regla de `AGENTS.md`;
  - las verificaciones "lo habría cazado";
  - el veredicto de la verificación NQF (Conforma o los defectos);
  - el número de avisos sembrados por `subject`;
  - los bloqueos, si los hubo.
- Fin de la cola.
