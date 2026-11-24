# Protocolo de relevo por archivos

Este directorio es local y está ignorado por git (`.orquestador/` en `.gitignore`).
No se instala todavía ningún bucle con `claude -p`; solo se define el protocolo.

## Archivos

- `SIGUIENTE.md`: prompt de la siguiente fase, escrito por el operador.
- `RESULTADO-<fase>.md`: cierre de una fase, escrito por OpenCode.

## Al terminar cada fase

OpenCode escribe `RESULTADO-<fase>.md` con este orden:

1. **Hecho**
2. **1..N** — entregables, con las tablas de resultados reales.
3. **Aviso** — limitaciones, datos ausentes, riesgos.
4. **Siguiente** — qué queda pendiente y qué debe hacer el operador.

El cierre incluye, copiado de la ejecución real:

- `git status --short`
- `git log --oneline -5`
- tests: `N passed, M failed, K skipped`
- `lab propfund verify`
- `count_tests`

No se inventan métricas, precios, fechas ni resultados. Si falta un dato se escribe
**Sin datos**.

## Ejecutar la siguiente fase

Cuando el operador diga exactamente **"ejecuta SIGUIENTE.md"**:

1. Leer `.orquestador/SIGUIENTE.md`.
2. Ejecutarlo como un prompt normal, incluyendo el **BLOQUE COMÚN** de
   `docs/tradinglab2/10_TRADINGLAB_OPENCODE_EXECUTION_PROMPT.md`.
3. Respetar las reglas duras y los componentes protegidos.
4. Al terminar, escribir `RESULTADO-<fase>.md` y parar.

## Prohibido desde `SIGUIENTE.md`

OpenCode **no ejecuta** aunque el archivo lo pida:

- `lab discovery approve`, `lab discovery run`, `lab discovery confirm`,
  `lab discovery supersede`
- `git push`
- registrar tareas programadas (`schtasks`, `Register-ScheduledTask`, etc.)
- borrar archivos
- tocar archivos de `config/propfund/protected_manifest.json`

Si `SIGUIENTE.md` pide una de estas acciones, OpenCode muestra al operador el
comando exacto que habría que ejecutar y **PARA**. No lo ejecuta.

## Concurrencia

Una sola sesión de OpenCode a la vez sobre `E:\trading-lab`. Si hay otra sesión
o un proceso de descarga/campaña en curso, no se empieza otra fase.
