# Latidos externos (Healthchecks.io)

Plan gratuito: **máximo 20 checks**. Aquí usamos 12. Las URLs viven en Windows
Credential Manager (`keyring`, servicio `tradinglab`) y nunca se imprimen:

```powershell
lab heartbeat setup f13
lab heartbeat setup backup
lab heartbeat setup-api      # API key de gestión, oculta
lab heartbeat status
lab heartbeat schedule       # tabla objetivo, sin tocar la API
```

`lab heartbeat ping <check> --status start|ok|fail [--message "..."]` no falla
la tarea si la URL no está configurada; `lab doctor` avisa de los checks que
faltan.

## Programación objetivo

Los disparadores reales se leyeron del Programador de tareas el **2026-11-13**.
La zona es **America/Santo_Domingo** (UTC-4 en invierno). La columna *gracia*
es el margen de Healthchecks; no es el período.

| Check | Tarea / script | Cron / período | Gracia | Nota |
|---|---|---|---|---|
| `f13` | `TradingLab-F13` / `f13_daily.ps1` | `20 22 * * 1-5` | 60 min | L-V 22:20 |
| `agents` | `TradingLab-Agents` / `agents_daily.ps1` | `45 22 * * 1-5` | 60 min | L-V 22:45 |
| `llmcompare` | `TradingLab-LLMCompare` / `llm_compare_daily.ps1` | `30 18 * * 1-5` | 60 min | L-V 18:30 |
| `intradayforward` | `TradingLab-IntradayForward` / `intraday_forward_execute.ps1` | `2-57/5 * * 1-5` | 60 min | Cada 5 min desde :02; el script filtra ventanas |
| `ai-london` | `TradingLab-AI-London` / `ai_trader_session.ps1 -Session london` | `5 3 * * 1-5` | 60 min | L-V 03:05 |
| `ai-ny` | `TradingLab-AI-NY` / `ai_trader_session.ps1 -Session ny` | `35 9,10 * * 1-5` | 60 min | Dos disparadores: 09:35 y 10:35 |
| `ai-daily` | `TradingLab-AI-Daily` / `ai_trader_session.ps1 -Session daily` | `15 18 * * 1-5` | 60 min | L-V 18:15 |
| `ai-scalp` | `TradingLab-AI-Scalp` / `ai_trader_scalp.ps1` | `* 9-13 * * 1-5` | 60 min | Ventana real 09:25-13:05; el cron amplio + gracia cubre el cierre |
| `ai-manage` | `TradingLab-AI-Manage` / `ai_trader_manage.ps1` | `*/15 0-17 * * 1-5` | 30 min | Cada 15 min, 00:00-17:59, L-V |
| `drill` | `TradingLab-Drill` / `drill_monthly.ps1` | `0 3 * * 0` | 120 min | Domingos 03:00 |
| `backup` | `TradingLab-Backup` / `backup.ps1` | `0 13,19 * * 1-5` | 60 min | Dos pasadas diarias; se restringe a L-V |
| `pc` | `TradingLab-Heartbeat` / `heartbeat_pc.ps1` | **período 10 min** | 10 min | No es cron; el ping `start` sale al comenzar |

La API de gestión **no está configurada** (`HEALTHCHECKS_API_KEY` ausente en
keyring), así que esta tabla es la referencia y **no se cambiaron los checks por
API**. Para aplicarla a mano: Healthchecks → check → *Schedule* → cron, zona
`America/Santo_Domingo` y *Grace*. Si más adelante se guarda la API key con
`lab heartbeat setup-api`, se puede automatizar la actualización.

## El check `pc`

El 2026-11-13 el check llevaba ~7 h sin ping. La tarea `TradingLab-Heartbeat`
sí corría cada 5 min (`LastTaskResult=0`), pero el script solo hacía el ping
**después** de comprobar SQLite y MT5, y la tarea tiene un límite de ejecución
de **2 minutos**. Cuando `lab mt5 status` se quedó bloqueado (terminal ocupado o
sesión bloqueada), el Programador mató el proceso antes de llegar al ping: ni
`ok` ni `fail`. El nombre del check en keyring era correcto (`pc`) y la URL
respondía al ping manual.

Corrección:

- `heartbeat_pc.ps1` envía un `start` inmediato, antes de mirar nada.
- La comprobación de MT5 tiene **timeout de 60 s** y se mata el proceso si no
  responde.
- Siempre termina con `ok` o `fail`; el `fail` lleva el motivo
  (`db=...; MT5: timeout 60s`, etc.) en el cuerpo del ping.
- Así se distingue **PC caído** (no hay ningún ping) de **MT5 caído** (hay
  `start` y `fail` con motivo).

## Alertas a Telegram

En Healthchecks.io, cada check → *Integrations* → *Add integration* →
*Telegram*. Se conecta el bot de Telegram y se elige el chat. No hace falta
poner el token en `config/` ni en `.env`: la integración vive en la web de
Healthchecks.

## Notas

- Un `start` y un `ok`/`fail` por ejecución. Si el proceso muere sin cerrar, el
  check se pone en rojo al agotar el margen de gracia.
- No se usa el latido para tomar decisiones de trading: es solo vigilancia
  externa. Las compuertas de riesgo siguen en `PropGuard`, el forward y
  `ai_trader`.
- No hay coste: plan gratuito de Healthchecks.io.

## Contraseña de backup

El backup offsite usa `BACKUP_PASSWORD` de keyring (nunca `.env` ni argumentos):

```powershell
python -c "import keyring; keyring.set_password('tradinglab','BACKUP_PASSWORD','...')"
```

No se imprime la contraseña. `backup.ps1 -Offsite` la lee, cifra con AES-256-CBC
y `restore_test.ps1` la usa para descifrar el `.enc`.
