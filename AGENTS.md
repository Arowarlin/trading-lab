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
