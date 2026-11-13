# Latidos externos (Healthchecks.io)

Plan gratuito: **máximo 20 checks**. Aquí usamos 12. Las URLs viven en Windows
Credential Manager (`keyring`, servicio `tradinglab`) y nunca se imprimen:

```powershell
lab heartbeat setup f13
lab heartbeat setup backup
lab heartbeat status
```

`lab heartbeat ping <check> --status start|ok|fail` no falla la tarea si la URL
no está configurada; `lab doctor` avisa de los checks que faltan.

## Checks

| Check | Tarea / script | Período | Margen de gracia |
|---|---|---|---|
| `f13` | `TradingLab-F13` / `f13_daily.ps1` | 1 día | 2 h |
| `agents` | `TradingLab-Agents` / `agents_daily.ps1` | 1 día | 2 h |
| `llmcompare` | `TradingLab-LLMCompare` / `llm_compare_daily.ps1` | 1 día | 2 h |
| `intradayforward` | `TradingLab-IntradayForward` / `intraday_forward_execute.ps1` | 1 día | 3 h |
| `ai-london` | `TradingLab-AI-London` / `ai_trader_session.ps1 -Session london` | 1 día L-V | 2 h |
| `ai-ny` | `TradingLab-AI-NY` / `ai_trader_session.ps1 -Session ny` | 1 día L-V | 2 h |
| `ai-daily` | `TradingLab-AI-Daily` / `ai_trader_session.ps1 -Session daily` | 1 día L-V | 2 h |
| `ai-scalp` | `TradingLab-AI-Scalp` / `ai_trader_scalp.ps1` | 1 día L-V | 2 h |
| `ai-manage` | `TradingLab-AI-Manage` / `ai_trader_manage.ps1` | 1 día L-V | 2 h |
| `drill` | `TradingLab-Drill` / `drill_monthly.ps1` | 1 mes | 2 días |
| `backup` | `TradingLab-Backup` / `backup.ps1` | 1 día | 2 h |
| `pc` | `TradingLab-Heartbeat` / `heartbeat_pc.ps1` | 5 min | 15 min |

El check `pc` solo late si MT5 responde y SQLite abre. La tarea
`TradingLab-Heartbeat` está preparada en `scripts/register_heartbeat_task.ps1`,
**sin registrar**.

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
