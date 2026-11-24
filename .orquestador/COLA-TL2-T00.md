# COLA TL2-T00 · Quitar la protección y dejar control de cambios
Modelo: DeepSeek V4.1 Flash (OpenCode Go). Un solo bloque. Rama actual `feature/prop-fund-multifirm`.

Orden del operador (2026-11-24, literal): "EL PASO YA NO ESTA PROTEGIDO QUITALE LA PROTECCION". Autoriza inspeccionar y modificar `us100-ftmo1`, `ai_trader`, el forward FTMO, el riesgo FTMO, Prop Fund y `ea_lab`, siempre con pruebas, comparación con el comportamiento anterior, documentación y rollback.

Lee primero: `.orquestador/tl2-audit/TL2_OPENCODE_TASKS.md`, sección **T00**. Esa es la especificación. Si algo no cuadra con el código, escríbelo en el RESULTADO y PARA. No improvises arquitectura.

## Pasos
1. `git tag tl2-t00-pre`.
2. `propfund/protected.py`:
   - `verify()` ya no falla cuando un archivo cambia. Devuelve `ok=True` con las listas `changed` y `unchanged`. `ok=False` solo si falta el manifiesto.
   - Añade `write_baseline(reason)`, que recalcula los hashes y añade una entrada `{date, reason, changes}` a `authorizations`.
3. `propfund/cli.py`:
   - `lab propfund verify` muestra los archivos cambiados como información, en amarillo, y sale con código 0.
   - Nuevo comando `lab propfund baseline --reason "..."`.
4. En `models.py`, `registry.py` y `router.py`, el significado "la ejecuta su propio motor" pasa a llamarse `external_engine`:
   - acepta `protected:` del YAML antiguo como alias de lectura;
   - el router sigue rechazando enviar órdenes a estrategias `external_engine`. **No cambies esa regla.**
5. `AGENTS.md`: añade la regla de cambios en producción (regla común 4 de TL2_OPENCODE_TASKS.md). No quites las demás reglas (demo, sin push, sin borrar, sin campañas sin aprobación, sin `.env`).
6. Crea `docs/CHANGELOG-produccion.md` con la primera entrada: retirada de la protección, la fecha y la frase literal del operador.
7. Tests:
   - verify con un archivo modificado devuelve `ok=True` y lo lista;
   - `baseline` añade la autorización;
   - el router rechaza `external_engine`;
   - el YAML antiguo con `protected: true` sigue cargando.

## Prohibido
Cambiar la lógica de trading, los parámetros, los setfiles o los límites de riesgo de cualquier componente. Esta tarea solo cambia el mecanismo de protección. Además: campañas, OOS, push, borrar, tareas programadas y operar.

## Cierre
- `ruff check`, `pytest -q` (una vez), `lab propfund verify` (4 grupos, código 0) y `count_tests` (debe seguir en 1883).
- Commit `tl2: T00 - protección → control de cambios`, tag `tl2-t00`.
- Escribe `.orquestador/RESULTADO-T00.md`: archivos tocados, tests, salida de verify, y confirmación de que el diff no toca lógica de trading (`git diff tl2-t00-pre --stat`).
- PARA.
