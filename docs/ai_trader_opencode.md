# OpenCode no interactivo del carril IA

## Qué se configuró

La configuración vive en el proyecto, no en la configuración global:

- `.opencode/opencode.json`: fija el modelo
  `opencode-go/deepseek-v4.1-flash` y el agente por defecto `build` para el
  trabajo interactivo. **No lleva permisos globales**, para no restringir la
  sesión normal del operador.
- `.opencode/agents/ai-operator.md`: agente primario no interactivo que usa el
  mismo modelo y lleva los permisos restrictivos. Es el que invoca
  `scripts/ai_trader_session.ps1` con `opencode run --agent ai-operator`.

El modelo exacto se verificó con:

```powershell
opencode models | Select-String "deepseek-v4.1-flash"
opencode run --help
```

## Permisos del agente `ai-operator`

- `edit: *` → **deny**. No puede crear, editar ni parchear archivos.
- `shell: *` → **deny**; solo se permiten estas órdenes, tanto escritas como
  `lab ai-trader ...` como cuando el shell resuelve el binario a
  `...\.venv\Scripts\lab.exe ai-trader ...`:
  - `lab ai-trader snapshot ...`
  - `lab ai-trader propose ...`
  - `lab ai-trader skip ...`
  - `lab ai-trader execute ...`
  - `lab ai-trader plan ...`
  - `lab ai-trader manage ...`
  - `lab ai-trader scoreboard ...`
  - `lab ai-trader status ...`
- `shell: git *` → deny (además del deny general).
- `question`, `subagent`, `webfetch`, `websearch`, `execute` (Code Mode),
  `external_directory` y lectura de `.env` → deny.
- `skill: *` → deny, salvo `trading-lab-operador`.
- `read`, `glob` y `grep` dentro del proyecto → allow, para que pueda leer
  `AGENTS.md`, el skill versionado y la documentación.

La regla general de shell es `deny` y las ocho excepciones van después: en
OpenCode gana la última regla que coincide. El comando debe empezar por
`lab ai-trader ...`; el script de sesión pone `.venv\Scripts` en el `PATH`.

## Invocación

```powershell
$env:PATH = "E:\trading-lab\.venv\Scripts;$env:PATH"
opencode run --standalone --agent ai-operator `
  --model opencode-go/deepseek-v4.1-flash `
  --auto `
  "Usa el skill trading-lab-operador. Sesión london: sigue el procedimiento del skill para esta sesión. Termina con una línea por decisión y el scoreboard."
```

`--standalone` es importante: arranca un servidor privado con el `PATH` del
proceso que llama, donde está `.venv\Scripts`, en vez de depender del servicio
compartido. `--auto` evita que una petición de permiso no contemplada bloquee
la sesión; las reglas `deny` siguen mandando. El shell puede resolver `lab` a
`...\.venv\Scripts\lab.exe`; por eso el agente permite también `*lab.exe
ai-trader ...` con la misma lista cerrada.

## Cómo revertirlo

1. Borrar `.opencode/agents/ai-operator.md` (o quitarle el bloque
   `permissions`).
2. Quitar `model` y `default_agent` de `.opencode/opencode.json` si se quiere
   volver al modelo global.
3. Quitar `--agent ai-operator` de `scripts/ai_trader_session.ps1` o cambiar el
   agente por el que se use.
4. OpenCode recarga la configuración sin reiniciar; si hay una sesión en curso,
   conviene terminarla y abrir otra.

No se tocó la configuración global `~/.config/opencode/opencode.json` ni el
agente `telegram.md`. El cambio es solo de este proyecto.
