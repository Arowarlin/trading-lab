# Control remoto por Telegram

Puente local entre Telegram y TradingLab/OpenCode. Permite recibir el resumen
final de un proceso y, si se activa el modo agente, enviar instrucciones para
que OpenCode siga trabajando en `E:\trading-lab`.

- **Long polling**: el PC pregunta a Telegram; no abre puertos ni necesita IP
  pública ni túneles.
- **Token en keyring**: Windows Credential Manager. Nunca en `.env`, git ni logs.
- **Solo tu chat**: se ignoran otros chats, usuarios y mensajes reenviados.
- **Dos modos**: `commands` (seguro, por defecto) y `agent` (OpenCode restringido).
- **Sin live**: el modo agente se bloquea si `mode` no es `paper`.

## Paso a paso

### 1. Crear el bot

1. En Telegram, abre **@BotFather**.
2. Envía `/newbot`, elige un nombre y un usuario que termine en `bot`.
3. Copia el **token** que te da BotFather. No lo pegues en este chat ni en un
   archivo del repo.

### 2. Abrir el chat

1. Abre el bot recién creado.
2. Envía `/start` (o cualquier mensaje). Esto permite que `setup` descubra tu
   chat ID.

### 3. Configurar en el PC

En una terminal local del PC:

```powershell
cd E:\trading-lab
.\.venv\Scripts\lab.exe telegram setup
```

El comando:

- pide el token con la entrada oculta;
- valida el bot con `getMe`;
- descubre tu chat ID (espera hasta 60 s a que escribas al bot);
- guarda token y chat ID en el keyring;
- escribe `config/telegram.yaml` (ignorado por git);
- envía un mensaje de prueba.

Si no detecta el chat, pide el chat ID a mano. Puedes obtenerlo con
**@userinfobot** o de la URL `getUpdates` de la API de Telegram.

### 4. Activar el puente

```powershell
.\.venv\Scripts\lab.exe telegram enable
.\.venv\Scripts\lab.exe telegram test
```

`enable` activa la configuración; todavía no hay ningún proceso escuchando.
Para probarlo en primer plano:

```powershell
.\.venv\Scripts\lab.exe telegram bridge
```

Déjalo corriendo y envía `/ping` al bot. Debes recibir `pong`.

### 5. Arranque automático al iniciar sesión

Con el puente parado (Ctrl+C), registra la tarea:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:\trading-lab\scripts\register_telegram_task.ps1
Start-ScheduledTask -TaskName TradingLab-Telegram
```

Comprueba:

```powershell
Get-ScheduledTaskInfo -TaskName TradingLab-Telegram
```

La tarea se ejecuta al iniciar sesión Windows. El PC debe estar encendido y con
la sesión iniciada; si se suspende, el puente deja de responder hasta que
vuelva.

### 6. Modo agente (opcional)

Por defecto solo responde a comandos. Para permitir instrucciones libres:

```powershell
.\.venv\Scripts\lab.exe telegram mode agent --yes
```

El agente `telegram` está en `.opencode/agents/telegram.md` y trabaja con una
lista blanca estricta:

- permite leer/editar código, tests y documentación;
- permite `git status/diff/log/add/commit`, `pytest`, `ruff` y comandos
  read-only de `lab`;
- deniega `.env`, `config/`, `data/`, `.opencode/`, `pyproject.toml`, `uv.lock`,
  borrado, `git push`, `lab operator`, `lab orchestrate`, `lab f13 freeze`,
  web y subagentes;
- se bloquea si el laboratorio no está en `paper`.

Prueba:

```text
/continue revisa el estado de F13 y dime si hay algo pendiente
```

El puente envía primero “Recibido. Trabajando…” y después el resumen final del
agente.

### 7. Parar o desactivar

```powershell
Stop-ScheduledTask -TaskName TradingLab-Telegram
.\.venv\Scripts\lab.exe telegram disable
```

Para eliminar la tarea:

```powershell
Unregister-ScheduledTask -TaskName TradingLab-Telegram -Confirm:$false
```

## Comandos de Telegram

| Comando | Efecto |
|---|---|
| `/help` | Ayuda |
| `/status` | Modo, F13, decisiones, repo y sesión |
| `/f13` | Estado y criterios de F13 |
| `/decisions` | Resultados con retorno 20d |
| `/ping` | Comprobar conexión |
| `/pause` | Pausar el puente |
| `/resume` | Reactivar |
| `/mode commands\|agent` | Cambiar modo |
| `/new` | Empezar sesión de agente nueva |
| `/continue <texto>` | Instrucción al agente |
| `/push` | Preparar push a `origin/master` (pide confirmación) |
| `/backup` | Preparar backup + restore test (pide confirmación) |
| `/pushbackup` | Preparar push y backup (pide confirmación) |
| `/confirm <código>` | Confirmar la acción pendiente |
| `/cancel` | Cancelar la acción pendiente |

## Push y backup con aprobación humana

**Sí: un mensaje tuyo desde el chat autorizado es una aprobación humana.** Para
`push` y `backup` se exige confirmación en dos pasos, para que no se dispare por
un toque accidental:

1. Envía `/push`, `/backup` o `/pushbackup`.
2. El puente revisa el estado y responde con un **código de 6 dígitos** válido
   **5 minutos**.
3. Responde `/confirm 123456` para ejecutar. El código es de un solo uso.
4. `/cancel` cancela la acción pendiente; `/pause` también la cancela.

Detalles:

- `/push`: solo rama `master`; hace `git fetch origin`, muestra commits por
  delante y cambios sin commit, y ejecuta `git push origin master` sin `--force`.
  Si no hay commits por delante, no pide confirmación.
- `/backup`: ejecuta `scripts/backup.ps1` (zip + restore test +
  `integrity_check`). Puede tardar 1–2 minutos.
- `/pushbackup`: primero push y, si va bien, backup.
- Cada ejecución queda auditada en `console_actions` con actor
  `telegram:<user_id>`; no se guardan token ni código.
- El agente automático sigue **sin poder hacer push**: solo este flujo del
  puente, con tu `/confirm`, puede ejecutarlo.

## Enviar un resumen desde el PC

Para que el resumen final de un proceso interactivo llegue a Telegram:

```powershell
.\.venv\Scripts\lab.exe telegram send --text "Hecho
1. ...
Aviso
- ...
Siguiente
- ..."
```

También acepta `--file resumen.txt` o `--stdin`.

## Seguridad y límites

- El token del bot es un secreto: quien lo tenga puede hablar con tu bot. No lo
  publiques. Protege tu cuenta de Telegram con 2FA.
- El puente solo acepta el `chat_id` y `user_id` guardados. Ignora reenviados.
- El modo agente no es un sandbox: el agente puede editar código y ejecutar
  tests; esos tests pueden ejecutar código. Es confianza personal, no aislamiento
  frente a un atacante. Revisa los commits antes de fusionar o publicar.
- El agente no puede hacer `git push`, borrar archivos, tocar `.env`, cambiar
  configuración ni activar F13.
- **Un solo puente**: si ejecutas `lab telegram bridge` mientras la tarea está
  activa, Telegram devolverá `409 Conflict`. Para probar a mano, para primero la
  tarea.
- Los logs están en `logs/telegram/` y no contienen el token. El estado está en
  `data/telegram_state.json`.

## Solución de problemas

| Síntoma | Revisión |
|---|---|
| `sin configurar` | Ejecuta `lab telegram setup` y luego `enable` |
| No responde | ¿Tarea activa? `Get-ScheduledTaskInfo -TaskName TradingLab-Telegram` |
| `409 Conflict` | Hay dos procesos; para la tarea o el bridge manual |
| Error de keyring | Ejecuta setup en la misma sesión de Windows del usuario |
| El agente no arranca | `opencode --version`; debe existir `opencode.exe` |
| El agente tarda | Es normal; el puente avisa y envía el resumen al terminar |
| No llega el resumen | Revisa `logs/telegram/agent_*.log` (sin secretos) |

## Evidencia

- `pytest tests/test_telegram.py -q` → 23 passed.
- `lab doctor` muestra `Telegram remoto` como OK cuando está configurado.
