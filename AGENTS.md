# TradingLab · reglas para agentes

- **Paper/demo solamente.** Nunca live, nunca dinero real, nunca activar bots ni F13
  sin aprobación humana explícita.
- **Ningún agente ejecuta `lab campaign run`, `research`, `research-intraday`,
  `research-swing` ni ningún barrido que sume pruebas al DSR sin aprobación
  explícita del operador en esa misma sesión.** `lab campaign run` exige además
  `--approved-by-operator`.
- **No tocar `.env`.** Los secretos viven en Windows Credential Manager (keyring).
- **No borrar archivos.** No `git push`, no reescribir historial y no registrar
  tareas programadas sin autorización.
- **Scripts que corren como administrador.** Modificar `scripts/register_tasks_tz.ps1`,
  `config/schedule.yaml` o cualquier script ejecutado por una tarea con
  `RunLevel Highest` requiere aprobación explícita del operador en esa misma
  sesión: la tarea corre como administrador y puede cambiar el Programador.
- **Cambios en componentes de producción** (EA `us100-ftmo1`, carril forward FTMO,
  riesgo FTMO, `ai_trader`, Prop Fund y `ea_lab`). Cada cambio necesita:
  (a) baseline antes del cambio (`lab propfund baseline --reason "..."`);
  (b) un test de regresión que compare el comportamiento anterior y el nuevo;
  (c) una entrada en `docs/CHANGELOG-produccion.md`;
  (d) un tag `tl2-<id>-pre` antes del primer commit, para el rollback.
  El baseline no bloquea: informa. Sigue prohibido operar en real y activar bots
  o F13 sin aprobación humana explícita.
- Cada bloque termina con: tests sintéticos, `ruff`, `pytest`, `lab doctor`,
  README/PLAN actualizados y un commit pequeño.
- Si hay datos ausentes, escribir **Sin datos**; no inventar precios, offsets ni
  históricos.
- Al terminar un bloque, enviar el resumen final a Telegram si está configurado:

  ```powershell
  .\.venv\Scripts\lab.exe telegram send --file resumen.txt
  ```

  Si Telegram no está configurado, usar `lab alerts send` (ntfy). El resumen usa
  el formato: **Hecho / 1..N / Aviso / Siguiente**.

## Coordinación entre sesiones

- Tomar el lock `readme-plan` antes de escribir `README.md`/`PLAN.md`, `changelog-produccion` antes del CHANGELOG de producción, `protected-manifest` antes del manifiesto protegido y `tl3-registry` antes del registro TL3.
- Hacer los commits por ruta (`git add <rutas>`), nunca `git add -A`, `git add .` ni `git commit -a`.
- Una sola cola activa por proyecto: `proyecto-<nombre>` (por ejemplo, `proyecto-nqedge`).
- Antes de cambiar el plan de un proyecto: comprobar locks, procesos y ficheros sin commit, y anotar el «Plan vigente» en el README del proyecto.
- Los locks viejos (más de 2 h) no se roban: se informan y decide el operador.
